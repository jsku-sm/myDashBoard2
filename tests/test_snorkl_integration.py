"""Offline integration logic tests: settings, enrollment, navigation and guard.

These tests do not replace a real Streamlit/Google/OpenAI/browser deployment test.
"""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import sys
from urllib.parse import parse_qs, urlsplit
import uuid

import pytest
from cryptography.fernet import Fernet

from snorkl_navigation import (ACTIVE_TOOL, REQUESTED_COURSE, LINK_SEEN, open_snorkl,
                               close_snorkl, main_menu_changed, sync_shared_link)
from think_app.integration import (resolve_settings, matching_class, student_identity,
                                   visible_courses, course_url)
from think_app.courses import CourseManager
from think_app.storage import MemoryStore, LocalStore, AppError

ROOT = Path(__file__).resolve().parents[1]


def student(cls="1-1", **changes):
    return dict({"role": "student", "id": "10101", "name": "시험학생", "class": cls}, **changes)


@pytest.mark.parametrize("own,allowed,expected", [
    ("1-1", ["1-1"], "1-1"), ("1-1", ["1반"], "1반"),
    ("1-7", ["7반"], "7반"), ("1-2", ["1반"], None),
    ("2-1", ["1반"], None), ("2-1", ["1-1"], None),
    ("", ["1-1"], None), ("1-1", [], None),
    ("1-1", ["1반", "1-1"], "1-1"),
])
def test_enrollment_aliases_do_not_grant_other_classes(own, allowed, expected):
    assert matching_class(student(own), {"classes": allowed}) == expected


def test_only_account_identity_is_used_and_unassigned_students_denied():
    assert student_identity(student(), {"classes": ["1반"]}) == ("10101", "시험학생", "1반")
    for user in [student("1-2"), student(role="teacher"), student(name=""), student(id="")]:
        with pytest.raises(AppError):
            student_identity(user, {"classes": ["1반"]})


def test_student_course_list_is_filtered():
    courses = [{"id": "a", "classes": ["1반"]}, {"id": "b", "classes": ["1-2"]}]
    assert [c["id"] for c in visible_courses(student(), courses)] == ["a"]
    assert visible_courses(student(role="visitor"), courses) == []


def test_no_settings_means_explicit_demo_not_a_random_github_repo():
    settings = resolve_settings({}, {})
    assert settings.mode == "demo" and settings.repo == ""
    assert not settings.ai_enabled and not settings.api_key and not settings.desmos_api_key


def test_reuses_dashboard_github_without_touching_its_data():
    values = {"app": {"storage": "github"},
              "github": {"repo": "owner/private-data", "token": "secret-token", "branch": "data"},
              "snorkl": {"mode": "github", "encryption_key": "secret-key"}}
    result = resolve_settings(values, {})
    assert (result.repo, result.branch, result.github_token) == ("owner/private-data", "data", "secret-token")
    assert result.mode == "github" and result.encryption_key == "secret-key"
    assert "secret-token" not in repr(result) and "secret-key" not in repr(result)


def test_existing_standalone_secrets_are_supported_without_migration():
    values = {"THINK_MODE": "github", "GITHUB_REPO": "owner/original", "GITHUB_TOKEN": "old-token",
              "ENCRYPTION_KEY": "old-key", "OPENAI_API_KEY": "old-ai", "AI_ENABLED": True,
              "DESMOS_API_KEY": "old-desmos"}
    result = resolve_settings(values, {})
    assert (result.mode, result.repo, result.encryption_key) == ("github", "owner/original", "old-key")
    assert result.api_key == "old-ai" and result.ai_enabled and result.desmos_api_key == "old-desmos"


def test_snorkl_group_wins_over_environment_and_legacy_values():
    result = resolve_settings({"snorkl": {"mode": "local", "github_repo": "owner/specific", "ai_enabled": False},
                               "THINK_MODE": "demo", "AI_ENABLED": True},
                              {"THINK_MODE": "github", "GITHUB_REPO": "owner/environment"})
    assert result.mode == "local" and result.repo == "owner/specific" and not result.ai_enabled


@pytest.mark.parametrize("value,expected", [(True,True), (False,False), ("true",True), ("false",False),
                                           ("1",True), ("0",False), ("yes",True), ("off",False)])
def test_boolean_settings(value, expected):
    assert resolve_settings({"snorkl": {"ai_enabled": value}}, {}).ai_enabled is expected


def test_invalid_configuration_stops_instead_of_silent_data_loss():
    with pytest.raises(AppError):
        resolve_settings({"snorkl": {"mode": "typo"}}, {})
    with pytest.raises(AppError):
        resolve_settings({"snorkl": {"ai_enabled": "maybe"}}, {})


def test_course_link_contains_no_identity_or_role():
    cid = uuid.uuid4().hex
    result = course_url("https://example.streamlit.app/?role=teacher&student=other#x", cid)
    assert parse_qs(urlsplit(result).query) == {"tool": ["snorkl"], "course_id": [cid]}
    assert "teacher" not in result and not urlsplit(result).fragment
    with pytest.raises(AppError):
        course_url("javascript:alert(1)", cid)
    with pytest.raises(AppError):
        course_url("https://example.streamlit.app/", "../bad")


def test_shared_link_routes_once_and_preserves_logged_in_user():
    user = student()
    state = {"user": user, "nav": "home"}
    query = {"course_id": uuid.uuid4().hex, "tool": "snorkl", "role": "teacher"}
    sync_shared_link(state, query)
    assert state["nav"] == "tools" and state[ACTIVE_TOOL] == "snorkl"
    assert state[REQUESTED_COURSE] == query["course_id"] and state["user"] is user
    state.pop(REQUESTED_COURSE)
    sync_shared_link(state, query)
    assert REQUESTED_COURSE not in state
    state["nav"] = "math2"
    main_menu_changed(state, query)
    assert "course_id" not in query and LINK_SEEN not in state
    sync_shared_link(state, query)
    assert state["nav"] == "math2"


def test_tool_can_open_return_and_reopen_without_external_url():
    state, query = {}, {"embed": "true"}
    open_snorkl(state, query)
    assert state[ACTIVE_TOOL] == "snorkl"
    close_snorkl(state, query)
    assert ACTIVE_TOOL not in state and query == {"embed": "true"}
    open_snorkl(state, query)
    assert state[ACTIVE_TOOL] == "snorkl"


def test_new_class_format_and_legacy_courses_survive_local_restart(tmp_path):
    key = Fernet.generate_key().decode()
    manager = CourseManager(LocalStore(tmp_path, key))
    new = manager.create("대시보드 수업", "#123456", ["1-1", "1-2"])
    old = manager.create("기존 소노클 수업", "#123456", ["1반"])
    restarted = CourseManager(LocalStore(tmp_path, key))
    assert len(visible_courses(student(), restarted.list_courses())) == 2
    assert restarted.get(new)["classes"] == ["1-1", "1-2"]
    assert restarted.get(old)["classes"] == ["1반"]
    assert "대시보드 수업".encode() not in (tmp_path / "state.enc").read_bytes()


def load_guard(monkeypatch, session, stored_user, locked=False):
    calls = []
    fake_st = SimpleNamespace(session_state=session, error=lambda s:calls.append(("error",s)),
                              warning=lambda s:calls.append(("warning",s)),
                              caption=lambda s:None, info=lambda s:None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "auth", SimpleNamespace(get_user=lambda uid:stored_user))
    monkeypatch.setitem(sys.modules, "realtime", SimpleNamespace(is_locked=lambda cls:locked))
    monkeypatch.setitem(sys.modules, "think_app.embedded", SimpleNamespace(render=lambda user:calls.append(("render",user))))
    spec = importlib.util.spec_from_file_location("_snorkl_guard_test", ROOT / "views/snorkl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_guard_reloads_role_and_never_forwards_password_hash(monkeypatch):
    authoritative = dict(student(), must_change="0", pw_hash="do-not-forward")
    forged = student(role="teacher")
    guard, calls = load_guard(monkeypatch, {"user": forged}, authoritative)
    guard.page(forged)
    assert calls == [("render", student())]


@pytest.mark.parametrize("session,stored,locked", [
    ({}, dict(student(), must_change="0"), False),
    ({"user": student()}, None, False),
    ({"user": student()}, dict(student(), must_change="1"), False),
    ({"user": student()}, dict(student(), must_change="0"), True),
    ({"user": student()}, dict(student(role="visitor"), must_change="0"), False),
    ({"user": student(id="another")}, dict(student(), must_change="0"), False),
])
def test_guard_denies_unauthorized_or_locked_user(monkeypatch, session, stored, locked):
    guard, calls = load_guard(monkeypatch, session, stored, locked)
    guard.page(student())
    assert not any(kind == "render" for kind, _ in calls)
    assert calls and calls[0][0] in ("warning", "error")
