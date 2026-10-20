"""Distribution intent, cross-worker discovery and student material access."""
from datetime import datetime, timedelta, timezone

import pytest

from classroom_core import (ArchivedError, ClassroomService, GitHubStore,
                            PermissionDenied, StorageError, ValidationError)
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub, environment


def test_distributing_existing_draft_preserves_files_and_selected_students():
    store, users, teacher, cid, work = environment()
    draft = work("teacher").save_material(cid, "학급 학습지", body="설명", unit="다항식",
                                           files=[dict(filename="학습지.txt", data=b"worksheet")],
                                           target_student_ids=["s0"])
    assert work("s0").materials(cid) == []
    distributed = work("teacher").publish_material(cid, draft["id"])
    for field in ("body", "unit", "attachments", "target_student_ids", "publish_at", "created_at"):
        assert distributed[field] == draft[field]
    assert distributed["published"]
    assert [row["id"] for row in work("s0").materials(cid)] == [draft["id"]]
    assert work("s0").download_material(cid, draft["id"], 0)["data"] == b"worksheet"
    assert work("s1").materials(cid) == []
    with pytest.raises(PermissionDenied):
        work("s1").download_material(cid, draft["id"], 0)
    repeated = work("teacher").publish_material(cid, draft["id"])
    assert repeated == distributed
    assert len([entry for entry in store.get("materials", draft["id"])["audit"]
                if entry["action"] == "material.publish"]) == 1


def test_distribution_keeps_future_release_and_checks_class_membership(monkeypatch):
    store, users, teacher, cid, work = environment()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    draft = work("teacher").save_material(cid, "예약 학습지", files=[dict(filename="자료.txt", data=b"private")],
                                           publish_at=future)
    work("teacher").publish_material(cid, draft["id"])
    assert store.get("materials", draft["id"])["publish_at"] == future
    assert work("s0").materials(cid) == []
    with pytest.raises(PermissionDenied):
        work("s0").download_material(cid, draft["id"], 0)
    monkeypatch.setattr("classroom_core.work.now", lambda: future)
    assert len(work("s0").materials(cid)) == 1
    users["s0"]["class"] = "1-2"
    for action in (lambda: work("s0").materials(cid),
                   lambda: work("s0").download_material(cid, draft["id"], 0)):
        with pytest.raises(PermissionDenied):
            action()
    users["s0"]["class"] = "1-1"
    current = teacher.get_course(cid)
    current["student_ids"].remove("s0")
    teacher._write("courses", cid, current, current["version"], "membership.revoke")
    with pytest.raises(PermissionDenied):
        work("s0").materials(cid)


def test_student_and_unassigned_teacher_cannot_distribute_or_retarget_drafts():
    store, _, teacher, cid, work = environment()
    draft = work("teacher").save_material(cid, "초안", body="아직 비공개")
    original = store.get("materials", draft["id"])
    for actor in ("s0", "stranger"):
        with pytest.raises(PermissionDenied):
            work(actor).publish_material(cid, draft["id"])
    assert store.get("materials", draft["id"]) == original
    teacher.archive_course(cid, teacher.get_course(cid)["version"])
    with pytest.raises(ArchivedError):
        work("teacher").publish_material(cid, draft["id"])


def test_distributing_disabled_external_material_does_not_enable_provider():
    store, _, _, cid, work = environment()
    draft = work("teacher").save_material(cid, "예전 외부 자료", body="원문 보존")
    original = store.put("materials", draft["id"], dict(draft, activity_id="old-activity"), draft["version"])
    with pytest.raises(ValidationError, match="비활성화"):
        work("teacher").publish_material(cid, draft["id"])
    assert store.get("materials", draft["id"]) == original


def test_new_material_distributed_by_another_worker_is_immediately_discovered():
    remote = MockGitHub()
    writer = GitHubStore("school/data", "main", "test-token", session=remote)
    _, users, _, cid, work = environment(writer)
    reader = GitHubStore("school/data", "main", "test-token", session=remote)
    student = WorkService(ClassroomService(reader, users["s0"], users.get, lock_checker=lambda _: False))
    assert student.materials(cid) == []  # Cache the tree before the upload.
    published = work("teacher").save_material(cid, "방금 배포한 자료", published=True,
                                                files=[dict(filename="자료.txt", data=b"fresh file")])
    assert [row["id"] for row in student.materials(cid)] == [published["id"]]
    assert student.download_material(cid, published["id"], 0)["data"] == b"fresh file"
    # Fresh discovery must not turn a different student's targets or drafts public.
    work("teacher").save_material(cid, "다른 학생 자료", body="대상 비공개", published=True, target_student_ids=["s1"])
    work("teacher").save_material(cid, "비공개 초안", body="초안")
    assert [row["id"] for row in student.materials(cid)] == [published["id"]]


APP_SOURCE = '''
import streamlit as st
from classroom_core import ClassroomService, MemoryStore, StorageError
from classroom_core.work import WorkService
from views.classroom_work import render_materials

class FailingStore(MemoryStore):
    fail_materials = False
    def put(self, namespace, record_id, record, expected_version=None):
        if namespace == "materials" and self.fail_materials:
            raise StorageError("GitHub 연결 오류: 저장하지 못했습니다.")
        return super().put(namespace, record_id, record, expected_version)

if "fixture" not in st.session_state:
    users = {"t": dict(id="t", name="교사", role="teacher"),
             "s": dict(id="s", name="학생", role="student", **{"class":"1-1"})}
    store = FailingStore()
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    course = teacher.create_course("1-1", "2026-2", "수학", class_name="1-1", student_ids=["s"])
    if st.session_state.get("seed_draft"):
        draft = WorkService(teacher).save_material(course["id"], "기존 비공개 학습지", body="기존 설명",
                                                   files=[dict(filename="원본.txt", data=b"original")])
        st.session_state.draft_id = draft["id"]
    st.session_state.fixture = (store, users, course["id"])

store, users, cid = st.session_state.fixture
actor = st.session_state.get("actor", "t")
service = ClassroomService(store, users[actor], users.get, lock_checker=lambda _: False)
render_materials(service, service.get_course(cid))
'''


def _app(seed_draft=False):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(APP_SOURCE)
    app.session_state["seed_draft"] = seed_draft
    app.run()
    assert not app.exception
    return app


def _element(elements, label):
    return next(item for item in elements if item.label == label)


@pytest.mark.parametrize("button, published", [("학생에게 배포", True), ("비공개 초안 저장", False)])
def test_material_form_distribution_intent_matches_actual_student_screen(button, published):
    app = _app()
    assert not any(box.label == "학생에게 공개" for box in app.checkbox)
    _element(app.text_input, "자료 제목").set_value("우리 반 수업자료")
    _element(app.text_area, "자료 설명").set_value("학생이 읽을 학습 내용")
    _element(app.button, button).click().run()
    assert not app.exception
    store, users, cid = app.session_state["fixture"]
    saved, = store.list("materials")
    assert saved["published"] is published
    app.session_state["actor"] = "s"
    app.run()
    assert not app.exception
    assert any("우리 반 수업자료" in item.value for item in app.markdown) is published
    assert any("아직 확인할 자료가 없습니다" in item.value for item in app.info) is (not published)
    if published:
        # Editing a distributed material and saving a private draft explicitly
        # withdraws publication; stale student sessions must stop showing it.
        app.session_state["actor"] = "t"
        app.run()
        from views.classroom_work import _key
        edit_key = _key("material_form", cid, saved["id"], "t")
        app.button(key=edit_key + "_save").click().run()
        assert not app.exception
        assert not store.get("materials", saved["id"])["published"]
        app.session_state["actor"] = "s"
        app.run()
        assert not app.exception
        assert not any("우리 반 수업자료" in item.value for item in app.markdown)
        assert any("아직 확인할 자료가 없습니다" in item.value for item in app.info)


def test_existing_draft_quick_distribution_appears_on_student_material_screen():
    app = _app(seed_draft=True)
    store, users, cid = app.session_state["fixture"]
    mid = app.session_state["draft_id"]
    before = store.get("materials", mid)
    from views.classroom_work import _key
    app.button(key=_key("material_publish", cid, mid, "t")).click().run()
    assert not app.exception
    after = store.get("materials", mid)
    assert after["published"]
    assert after["attachments"] == before["attachments"]
    app.session_state["actor"] = "s"
    app.run()
    assert not app.exception
    assert any("기존 비공개 학습지" in item.value for item in app.markdown)
    assert not any("아직 확인할 자료가 없습니다" in item.value for item in app.info)


def test_failed_distribution_keeps_input_private_record_and_shows_no_success():
    app = _app(seed_draft=True)
    store, users, cid = app.session_state["fixture"]
    mid = app.session_state["draft_id"]
    original = store.get("materials", mid)
    store.fail_materials = True
    from views.classroom_work import _key
    app.button(key=_key("material_publish", cid, mid, "t")).click().run()
    assert not app.exception
    assert store.get("materials", mid) == original
    assert app.error and not app.success
    # New uploads retain their form input too when the durable save fails.
    _element(app.text_input, "자료 제목").set_value("복구할 새 자료")
    _element(app.text_area, "자료 설명").set_value("다시 저장할 설명")
    new_key = _key("material_form", cid, "new", "t")
    app.button(key=new_key + "_publish").click().run()
    assert not app.exception and app.error and not app.success
    assert _element(app.text_input, "자료 제목").value == "복구할 새 자료"
    assert len(store.list("materials")) == 1
    student = WorkService(ClassroomService(store, users["s"], users.get, lock_checker=lambda _: False))
    assert student.materials(cid) == []
