"""Regression checks with in-memory adapters; no operational repository writes."""
from types import SimpleNamespace

import pytest

import auth
import storage as db
from classroom_navigation import PENDING, apply_pending_navigation
from classroom_core import ClassroomService, MemoryStore, PermissionDenied
from classroom_core import legacy
from think_app.ownership import OwnedCourseManager
from think_app.storage import MemoryStore as NativeStore, AppError


def test_existing_password_hash_login_and_change_still_work(monkeypatch):
    rows = [{"id": "student", "role": "student", "pw_hash": auth.hash_pw("existing-secret"), "must_change": "0"}]
    monkeypatch.setattr(db, "read", lambda table: [dict(r) for r in rows])
    monkeypatch.setattr(db, "invalidate", lambda table: None)
    monkeypatch.setattr(db, "update", lambda table, uid, changes: rows[0].update(changes))
    assert auth.login(" student ", "existing-secret")["id"] == "student"
    assert auth.login("student", "wrong") is None
    auth.change_password("student", "changed-secret")
    assert auth.login("student", "existing-secret") is None
    assert auth.login("student", "changed-secret")["must_change"] == "0"
    assert "changed-secret" not in rows[0]["pw_hash"]


def test_new_teacher_bootstrap_requires_secrets_and_preserves_existing(monkeypatch):
    monkeypatch.setattr(auth, "st", SimpleNamespace(session_state={}))
    monkeypatch.setattr(db, "read", lambda table: [])
    monkeypatch.setattr(auth, "_teacher_secret", lambda: ("teacher", ""))
    with pytest.raises(db.SetupError):
        auth.ensure_teacher()
    rows = [{"id": "teacher", "role": "teacher", "pw_hash": "unchanged"}]
    monkeypatch.setattr(db, "read", lambda table: rows)
    auth.ensure_teacher()
    assert rows[0]["pw_hash"] == "unchanged"


@pytest.mark.parametrize("role", ["student", "teacher"])
def test_classroom_shortcut_selects_exact_native_activity_without_identity_change(role):
    user = {"id": "one", "role": role}
    state = {"user": user, PENDING: {"user_id": "one", "menu": "snorkl", "course_id": "course", "activity_id": "activity"}}
    apply_pending_navigation(state, user)
    assert state["user"] is user and state["nav"] == "tools"
    assert state["_classroom_requested_activity"] == "activity"
    assert state["_snorkl_requested_course"] == "course"
    if role == "student":
        assert state["snorkl_student_activity_course"] == "activity"
    else:
        assert state["selected_activity"] == "activity"


def test_pending_navigation_does_not_cross_user_sessions():
    state = {"nav": "classroom", PENDING: {"user_id": "other", "menu": "snorkl"}}
    apply_pending_navigation(state, {"id": "mine", "role": "student"})
    assert state == {"nav": "classroom"}


def test_native_teachers_cannot_open_other_teachers_course(monkeypatch):
    import think_app.ownership as ownership
    monkeypatch.setattr(ownership, "legacy_teacher_id", lambda: "original")
    store = NativeStore()
    one = OwnedCourseManager(store, {"id": "first", "role": "teacher"})
    two = OwnedCourseManager(store, {"id": "second", "role": "teacher"})
    cid = one.create("수업", "#123456", ["1-1"])
    assert one.get(cid)["owner_id"] == "first"
    assert two.list_courses() == []
    for operation in (lambda: two.get(cid), lambda: two.update(cid, "변경", "#123456", ["1-1"]), lambda: two.delete(cid)):
        with pytest.raises(AppError):
            operation()
    from think_app.courses import CourseManager
    old_id = CourseManager(store).create("기존", "#123456", ["1-1"])
    assert OwnedCourseManager(store, {"id": "original", "role": "teacher"}).get(old_id)
    with pytest.raises(AppError):
        two.get(old_id)


def test_old_private_observations_are_not_shared_through_global_cache(monkeypatch):
    import think_app.ownership as ownership
    users = {uid: {"id": uid, "role": "teacher", "must_change": "0"} for uid in ("one", "two")}
    session = {"user": users["one"]}
    monkeypatch.setattr(db, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(auth, "get_user", users.get)
    monkeypatch.setattr(ownership, "legacy_teacher_id", lambda: "one")
    rows = [{"id": "legacy", "author_id": ""}, {"id": "new", "author_id": "two"}]
    assert [r["id"] for r in db._scope_private_records("observations", rows)] == ["legacy"]
    session["user"] = users["two"]
    assert [r["id"] for r in db._scope_private_records("observations", rows)] == ["new"]
    assert [r["id"] for r in db._scope_private_records("records", rows)] == ["new"]
    session["user"] = {"id": "unknown"}
    assert db._scope_private_records("observations", rows) == []


def test_native_status_is_same_original_attempt_and_blocks_other_student(monkeypatch):
    teacher = {"id": "teacher", "role": "teacher"}
    student = {"id": "s1", "role": "student"}
    course = {"id": "classroom", "student_ids": ["s1", "s2"]}
    monkeypatch.setattr(legacy, "_context", lambda user, cid, teacher=False: (None, user, course))
    monkeypatch.setattr(legacy, "get_snorkl_activity", lambda *args: {"course_id": "native", "title": "활동"})
    original = {"id": "original-attempt", "activity_id": "a", "student_id": "s1", "number": 2, "created": "2026-10-20"}
    other = dict(original, id="other-attempt", student_id="s2", number=9)
    monkeypatch.setattr(legacy, "_native", lambda: SimpleNamespace(read=lambda: {"course_attempts": {"one": original, "two": other}}))
    status = legacy.snorkl_status(student, "classroom", "a")
    assert status["submission_id"] == original["id"] and status["version"] == 2
    assert legacy.snorkl_status(teacher, "classroom", "a", student_id="s1") == status
    with pytest.raises(PermissionDenied):
        legacy.snorkl_status(student, "classroom", "a", student_id="s2")


def test_legacy_reference_checks_student_and_approved_membership(monkeypatch):
    user = {"id": "s1", "role": "student"}
    course = {"subject": "수학", "student_ids": ["s1", "s2"]}
    monkeypatch.setattr(legacy, "_context", lambda *args, **kwargs: (None, user, course))
    rows = [{"id": "one", "student_id": "s1", "subject": "수학"},
            {"id": "two", "student_id": "s2", "subject": "수학"}]
    monkeypatch.setattr(db, "read", lambda table: rows)
    assert legacy.validate_reference(user, "course", "sudanote", "one")["student_id"] == "s1"
    with pytest.raises(PermissionDenied):
        legacy.resolve_reference(user, "course", "sudanote", "two")


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_existing_app_opens_classroom_by_default_and_retains_tool_menu(monkeypatch, role):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import realtime
    from views import classroom, emotion, student_announcements
    user = dict(id="t" if role == "teacher" else "s", role=role, name="시험 계정", must_change="0", **{"class": "1-1"})
    monkeypatch.setattr(db, "get_backend", lambda: SimpleNamespace(is_local=True))
    monkeypatch.setattr(db, "backend_status", lambda: "시험 저장소")
    monkeypatch.setattr(auth, "ensure_teacher", lambda: None)
    monkeypatch.setattr(auth, "get_user", lambda uid: dict(user))
    monkeypatch.setattr(realtime, "is_locked", lambda cls: False)
    monkeypatch.setattr(realtime, "locked_classes", lambda: [])
    monkeypatch.setattr(realtime, "touch", lambda uid: None)
    monkeypatch.setattr(realtime, "has_pending", lambda uid: False)
    monkeypatch.setattr(emotion, "done_today", lambda actor: True)
    monkeypatch.setattr(student_announcements, "poll_announcements", lambda actor: None)
    monkeypatch.setattr(student_announcements, "show_announcement_popup", lambda actor: None)
    import streamlit as st
    monkeypatch.setattr(classroom, "page", lambda actor: st.write("클래스룸 첫 화면 " + actor["role"]))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.session_state["user"] = dict(user)
    app.run()
    assert not app.exception
    assert app.radio(key="nav").value == "classroom"
    assert any("수업도구" in label for label in app.radio(key="nav").options)
    assert any("클래스룸 첫 화면 " + role in element.value for element in app.markdown)
