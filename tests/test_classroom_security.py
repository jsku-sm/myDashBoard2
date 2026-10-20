"""Adversarial cross-process privacy and resource-copy regressions, offline."""
from types import SimpleNamespace

from cryptography.fernet import Fernet

from classroom_core import ClassroomService, GitHubStore
from classroom_core.legacy import _student_linked
from classroom_core import legacy, PermissionDenied
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub, environment, assignment
import pytest


def test_second_process_privacy_changes_override_first_process_list_cache():
    remote, key = MockGitHub(), Fernet.generate_key().decode()
    first = GitHubStore("school/mydashboard", "data", "test", key, session=remote)
    _, users, teacher, cid, first_work = environment(first)
    task = assignment(first_work("teacher"), cid)
    target = assignment(first_work("teacher"), cid)
    question = first_work("s0").save_question(cid, "공개에서 비공개로", visibility="course")
    observation = first_work("teacher").save_observation(cid, "s0", "공유 관찰", shared_teacher_ids=["shared"])
    assert len(first_work("s1").assignments(cid)) == 2
    assert first_work("s1").questions(cid)
    assert first_work("shared").observations(cid)

    second = GitHubStore("school/mydashboard", "data", "test", key, session=remote)
    def other(uid):
        return WorkService(ClassroomService(second, users[uid], users.get, lock_checker=lambda _: False))
    other("teacher").save_assignment(cid, "숨김", "안내", assignment_id=task["id"], published=False)
    other("teacher").save_assignment(cid, "대상 제한", "안내", assignment_id=target["id"], published=True, target_student_ids=["s0"])
    other("s0").save_question(cid, "공개에서 비공개로", visibility="private", question_id=question["id"])
    other("teacher").save_observation(cid, "s0", "공유 취소", observation_id=observation["id"], shared_teacher_ids=[])
    assert first_work("s1").assignments(cid) == []
    assert first_work("s1").questions(cid) == []
    assert first_work("shared").observations(cid) == []


def test_scoped_resource_metadata_cannot_bypass_target_and_operating_override():
    fake_native = SimpleNamespace(get_snorkl_activity=lambda *args: {"id": "hidden-activity"})
    store, users, teacher, cid, _ = environment(legacy=fake_native)
    work = WorkService(teacher, legacy=fake_native)
    material = work.save_material(cid, "개별 자료", body="개별", activity_id="hidden-activity", published=True, target_student_ids=["s0"])
    course = teacher.get_course(cid)
    course["lessons"] = [{"id": "one", "title": "차시", "resources": [
        {"kind": "material", "id": material["id"], "activity_id": "hidden-activity", "url": "https://private.example"}]}]
    student = ClassroomService(store, users["s1"], users.get, lock_checker=lambda _: False)
    assert not _student_linked(student, course, "hidden-activity")
    course["lessons"][0]["resources"] = [{"kind": "snorkl", "id": "old"}]
    course["lesson_records"] = {"one": {"resources": [{"kind": "snorkl", "id": "new"}]}}
    assert not _student_linked(student, course, "old")
    assert _student_linked(student, course, "new")
    course["lesson_records"]["one"]["applied"] = False
    assert not _student_linked(student, course, "new")


def test_copy_remaps_namespaced_ids_and_removes_private_fallback_metadata():
    store, users, teacher, cid, work = environment()
    material = work("teacher").save_material(cid, "원본 자료", body="본문", material_id="same-id", published=True)
    task = work("teacher").save_assignment(cid, "원본 과제", "안내", assignment_id="same-id", material_ids=["same-id"], published=True)
    course = teacher.get_course(cid)
    course["lessons"] = [{"id": "one", "title": "차시", "resources": [
        {"kind": "material", "id": "same-id", "activity_id": "old-native", "url": "https://private.example"},
        {"kind": "assignment", "id": "same-id", "activity_id": "old-native"}]}]
    teacher._write("courses", cid, course, course["version"], "fixture.resources")
    projection = ClassroomService(store, users["s1"], users.get).get_course(cid)
    assert "private.example" not in str(projection) and "old-native" not in str(projection)
    copied = teacher.copy_course(cid, "새 학기", "2027-1")
    copied_material = copied["copied_material_templates"][0]
    copied_task = copied["copied_assignment_templates"][0]
    assert copied_material["id"] != copied_task["id"]
    assert copied_task["material_ids"] == [copied_material["id"]]
    resources = copied["lessons"][0]["resources"]
    assert [r["id"] for r in resources] == [copied_material["id"], copied_task["id"]]
    assert "private.example" not in str(resources) and "old-native" not in str(resources)
    assert not copied_material["published"] and not copied_task["published"]


def test_native_closed_activity_keeps_own_receipt_but_cannot_launch(monkeypatch):
    store, users, teacher, cid, _ = environment()
    users["s0"]["class"] = "1-1"
    course = teacher.get_course(cid)
    course["lessons"] = [{"id": "lesson", "title": "활동", "activity_id": "native-activity"}]
    teacher._write("courses", cid, course, course["version"], "fixture.activity")
    def context(actor, course_id, teacher=False):
        service = ClassroomService(store, actor, users.get, lock_checker=lambda _: False)
        return service, service.actor(), service._course(course_id, teacher=teacher)
    monkeypatch.setattr(legacy, "_context", context)
    state = {"courses": {"native": {"id": "native", "classes": ["1-1"]}},
             "course_activities": {"native-activity": {"id": "native-activity", "course_id": "native", "title": "종료된 활동", "status": "숨김"}},
             "course_attempts": {"one": {"id": "original", "activity_id": "native-activity", "student_id": "s0", "number": 1, "created": "2026-10-20T00:00:00+00:00"}}}
    monkeypatch.setattr(legacy, "_native", lambda: SimpleNamespace(read=lambda: state))
    assert legacy.snorkl_status(users["s0"], cid, "native-activity")["submission_id"] == "original"
    with pytest.raises(PermissionDenied, match="현재 열 수 없습니다"):
        legacy.launch_snorkl(users["s0"], cid, "native-activity")


def test_shared_original_observation_requires_live_explicit_reference(monkeypatch):
    import storage as db
    store, users, teacher, cid, _ = environment()
    original = {"id": "original", "student_id": "s0", "author_id": "teacher", "content": "개인 원문"}
    references = [{"legacy_ref": "original", "teacher_id": "teacher", "student_id": "s0", "shared_teacher_ids": ["shared"]}]
    actor = users["shared"]
    service = ClassroomService(store, actor, users.get)
    monkeypatch.setattr(legacy, "_context", lambda *args, **kwargs: (service, actor, teacher.get_course(cid)))
    monkeypatch.setattr(db, "read", lambda table: [])
    monkeypatch.setattr(db, "_ready_backend", lambda: SimpleNamespace(read=lambda table: [original]))
    monkeypatch.setattr(WorkService, "observations", lambda *args: references)
    assert legacy.resolve_reference(actor, cid, "observation", "original")["content"] == "개인 원문"
    references.clear()
    with pytest.raises(PermissionDenied):
        legacy.resolve_reference(actor, cid, "observation", "original")
