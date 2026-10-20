"""Shared date notes and independent resource cards use authorized course CAS."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from classroom_core import (ArchivedError, ClassroomService, ConflictError,
                            GitHubStore, MemoryStore, PermissionDenied,
                            StorageError, ValidationError)
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub


def environment(store=None):
    store = store or MemoryStore()
    users = {
        "t": {"id": "t", "role": "teacher"},
        "shared": {"id": "shared", "role": "teacher"},
        "outsider": {"id": "outsider", "role": "teacher"},
        "s": {"id": "s", "role": "student", "class": "1-1"},
        "unjoined": {"id": "unjoined", "role": "student", "class": "1-1"},
        "other": {"id": "other", "role": "student", "class": "1-2"},
    }
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    curriculum = teacher.create_curriculum("수업안", "수학", [{"id": "lesson", "title": "함수"}])
    course = teacher.create_course("수학", "2026-2", "수학", class_name="1-1",
                                   curriculum_id=curriculum["id"], teacher_ids=["shared"], student_ids=["s"])
    return store, users, teacher, course["id"], WorkService(teacher)


def actor(store, users, user_id):
    return ClassroomService(store, users[user_id], users.get, lock_checker=lambda _: False)


def note(service, course_id, day="2026-10-20", text="준비물 지참"):
    return service.set_calendar_note(course_id, day, text, service.get_course(course_id)["version"])


def place(service, course_id, kind, resource_id, day="2026-10-20"):
    return service.place_calendar_resource(course_id, kind, resource_id, day,
                                            service.get_course(course_id)["version"])


def test_note_add_edit_remove_is_shared_but_observations_stay_private():
    store, users, teacher, cid, _ = environment()
    initial = teacher.get_course(cid)
    teacher.set_lesson(cid, "lesson", {"memo": "개인 관찰", "next_note": "지원 계획",
                                       "makeup_reason": "개인 사유"}, initial["version"], "교사 기록")
    added = note(teacher, cid, text="  준비물 지참\n도형 자료  ")
    student = actor(store, users, "s")
    assert added["calendar_notes"] == {"2026-10-20": "준비물 지참\n도형 자료"}
    assert student.get_course(cid)["calendar_notes"] == added["calendar_notes"]
    assert student.list_courses()[0]["calendar_notes"] == added["calendar_notes"]
    visible_record = student.get_course(cid)["lesson_records"]["lesson"]
    assert not {"memo", "next_note", "makeup_reason"} & visible_record.keys()
    edited = note(actor(store, users, "shared"), cid, text="자료 수정")
    change = edited["audit"][-1]["calendar_notes_changes"]["2026-10-20"]
    assert change == {"before": "준비물 지참\n도형 자료", "after": "자료 수정"}
    assert edited["audit"][-1]["actor_id"] == "shared"
    removed = note(teacher, cid, text=" \n ")
    assert removed["calendar_notes"] == {}
    assert removed["audit"][-1]["calendar_notes_changes"]["2026-10-20"] == {
        "before": "자료 수정", "after": None,
    }
    assert student.get_course(cid)["calendar_notes"] == {}


@pytest.mark.parametrize("uid", ["s", "unjoined", "other", "outsider"])
def test_only_assigned_teachers_can_write_notes_or_resource_cards(uid):
    store, users, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용")
    before = note(teacher, cid)
    denied = actor(store, users, uid)
    with pytest.raises(PermissionDenied):
        denied.set_calendar_note(cid, "2026-10-21", "위조", before["version"])
    with pytest.raises(PermissionDenied):
        denied.place_calendar_resource(cid, "material", material["id"], "2026-10-21", before["version"])
    assert teacher.get_course(cid) == before


@pytest.mark.parametrize("day", [None, "", "2026-02-30", "2026-13-01", "어제"])
def test_note_date_is_required_and_valid(day):
    _, _, teacher, cid, _ = environment()
    before = teacher.get_course(cid)
    with pytest.raises(ValidationError):
        teacher.set_calendar_note(cid, day, "메모", before["version"])
    assert teacher.get_course(cid) == before


@pytest.mark.parametrize("text", [None, 12, {}, "가" * 1001])
def test_note_requires_bounded_plain_text(text):
    _, _, teacher, cid, _ = environment()
    before = teacher.get_course(cid)
    with pytest.raises(ValidationError):
        teacher.set_calendar_note(cid, "2026-10-20", text, before["version"])
    assert teacher.get_course(cid) == before


def test_note_accepts_1000_characters_and_preserves_literal_text():
    store, users, teacher, cid, _ = environment()
    text = "<b>수업 준비</b>\n" + "가" * (1000 - len("<b>수업 준비</b>\n"))
    assert note(teacher, cid, text=text)["calendar_notes"]["2026-10-20"] == text
    assert actor(store, users, "s").get_course(cid)["calendar_notes"]["2026-10-20"] == text


def test_student_account_class_change_or_membership_revocation_revokes_calendar_reads():
    store, users, teacher, cid, _ = environment()
    note(teacher, cid)
    student = actor(store, users, "s")
    assert student.get_course(cid)["calendar_notes"]
    users["s"]["class"] = "1-2"
    with pytest.raises(PermissionDenied):
        student.get_course(cid)
    assert student.list_courses() == []
    users["s"]["class"] = "1-1"
    before = teacher.get_course(cid)
    teacher.remove_member(cid, "s", before["version"])
    with pytest.raises(PermissionDenied):
        student.get_course(cid)


def test_session_schedule_is_shared_while_teacher_session_note_stays_private():
    store, users, teacher, cid, _ = environment()
    teacher.add_session(cid, "lesson", "2026-10-21", actual_date="2026-10-22", note="개인 보충 사유")
    before = teacher.get_course(cid)
    session = before["lesson_records"]["lesson"]["sessions"][0]
    visible = actor(store, users, "s").get_course(cid)["lesson_records"]["lesson"]["sessions"][0]
    assert visible == {key: session[key] for key in ("id", "kind", "planned_date", "actual_date")}
    assert "note" not in visible
    assert teacher.get_course(cid) == before


def test_archived_calendar_is_read_only_for_teachers_and_students():
    store, users, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용", published=True)
    place(teacher, cid, "material", material["id"])
    before = note(teacher, cid)
    archived = teacher.archive_course(cid, before["version"])
    for service in (teacher, actor(store, users, "shared")):
        with pytest.raises(ArchivedError):
            service.set_calendar_note(cid, "2026-10-20", "수정", archived["version"])
        with pytest.raises(ArchivedError):
            service.place_calendar_resource(cid, "material", material["id"], "2026-10-21", archived["version"])
    assert actor(store, users, "s").get_course(cid)["calendar_notes"] == before["calendar_notes"]
    assert teacher.get_course(cid) == archived


def test_copy_has_no_previous_term_date_notes_resource_schedule_or_private_sessions():
    _, _, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용", published=True)
    place(teacher, cid, "material", material["id"])
    note(teacher, cid)
    teacher.add_session(cid, "lesson", "2026-10-21", note="보충 사유")
    copied = teacher.copy_course(cid, "새 수업", "2027-1", class_name="1-1")
    assert copied["calendar_notes"] == copied["calendar_resources"] == copied["lesson_records"] == {}
    assert len(copied["copied_material_templates"]) == 1


def test_resources_place_and_move_independent_of_lessons_release_and_due_dates():
    store, users, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용", published=True, publish_at="2026-10-22T09:00:00+09:00")
    assignment = work.save_assignment(cid, "과제", "풀기", published=True, due_at="2026-10-23T16:00:00+09:00")
    original_material = store.get("materials", material["id"])
    original_assignment = store.get("assignments", assignment["id"])
    place(teacher, cid, "material", material["id"])
    placed = place(teacher, cid, "assignment", assignment["id"])
    assert placed["lesson_records"] == {}
    assert placed["calendar_resources"] == {
        f"material:{material['id']}": {"kind": "material", "id": material["id"], "date": "2026-10-20"},
        f"assignment:{assignment['id']}": {"kind": "assignment", "id": assignment["id"], "date": "2026-10-20"},
    }
    moved = place(teacher, cid, "material", material["id"], "2026-10-21")
    assert len(moved["calendar_resources"]) == 2
    assert moved["calendar_resources"][f"material:{material['id']}"]["date"] == "2026-10-21"
    audit = moved["audit"][-1]["calendar_resources_changes"][f"material:{material['id']}"]
    assert audit["before"]["date"] == "2026-10-20" and audit["after"]["date"] == "2026-10-21"
    assert store.get("materials", material["id"]) == original_material
    assert store.get("assignments", assignment["id"]) == original_assignment
    assert actor(store, users, "s").get_course(cid)["calendar_resources"] == moved["calendar_resources"]


@pytest.mark.parametrize("kind", ["material", "assignment"])
def test_resource_must_belong_to_this_course_and_not_be_disabled_external_work(kind):
    store, _, teacher, cid, _ = environment()
    other = teacher.create_course("다른 반", "2026-2", "수학", class_name="1-2")
    row = store.put(kind + "s", "resource", {"id": "resource", "course_id": other["id"], "title": "타 학급 자료"})
    before = teacher.get_course(cid)
    with pytest.raises(PermissionDenied):
        place(teacher, cid, kind, "resource")
    row["course_id"] = cid
    row["activity_id"] = "disabled-external"
    store.put(kind + "s", "resource", row, row["version"])
    with pytest.raises(ValidationError, match="비활성화"):
        place(teacher, cid, kind, "resource")
    assert teacher.get_course(cid) == before


@pytest.mark.parametrize("kind,resource_id,day", [
    ("snorkl", "id", "2026-10-20"), ([], "id", "2026-10-20"),
    ("material", "", "2026-10-20"), ("material", None, "2026-10-20"),
    ("material", "id", ""), ("material", "id", "2026-02-30"),
])
def test_invalid_resource_proposals_do_not_write(kind, resource_id, day):
    _, _, teacher, cid, _ = environment()
    before = teacher.get_course(cid)
    with pytest.raises(ValidationError):
        teacher.place_calendar_resource(cid, kind, resource_id, day, before["version"])
    assert teacher.get_course(cid) == before


def test_student_projection_contains_only_resource_identity_and_date():
    store, users, teacher, cid, _ = environment()
    raw = teacher.get_course(cid)
    raw["calendar_resources"] = {"material:hidden": {
        "kind": "material", "id": "hidden", "date": "2026-10-20", "title": "비공개 제목",
        "url": "https://private.invalid", "body": "비공개 본문", "target_student_ids": ["other"],
    }}
    store.put("courses", cid, raw, raw["version"])
    student = actor(store, users, "s")
    expected = {"material:hidden": {"kind": "material", "id": "hidden", "date": "2026-10-20"}}
    assert student.get_course(cid)["calendar_resources"] == expected
    assert student.list_courses()[0]["calendar_resources"] == expected


def test_stale_resource_write_does_not_overwrite_recent_note():
    _, _, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용")
    stale = teacher.get_course(cid)
    current = note(teacher, cid)
    with pytest.raises(ConflictError):
        teacher.place_calendar_resource(cid, "material", material["id"], "2026-10-21", stale["version"])
    assert teacher.get_course(cid) == current
    retried = place(teacher, cid, "material", material["id"])
    assert retried["calendar_notes"] == current["calendar_notes"]


def test_concurrent_note_writers_report_conflict_and_retry_retains_both_days(monkeypatch):
    store, users, teacher, cid, _ = environment()
    version = teacher.get_course(cid)["version"]
    barrier = threading.Barrier(2)
    original_put = store.put

    def synchronize(namespace, record_id, record, expected_version=None):
        if namespace == "courses" and expected_version == version:
            barrier.wait(timeout=10)
        return original_put(namespace, record_id, record, expected_version)

    monkeypatch.setattr(store, "put", synchronize)

    def save(uid, day):
        try:
            actor(store, users, uid).set_calendar_note(cid, day, uid, version)
            return uid, day, True
        except ConflictError:
            return uid, day, False

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(save, "t", "2026-10-20")
        second = pool.submit(save, "shared", "2026-10-21")
        results = [first.result(), second.result()]
    assert sum(ok for _, _, ok in results) == 1
    saved = teacher.get_course(cid)
    assert len(saved["calendar_notes"]) == 1
    assert len([entry for entry in saved["audit"] if entry["action"] == "calendar_note_update"]) == 1
    uid, day, _ = next(result for result in results if not result[2])
    note(actor(store, users, uid), cid, day=day, text=uid)
    assert teacher.get_course(cid)["calendar_notes"] == {"2026-10-20": "t", "2026-10-21": "shared"}


def test_failed_store_write_preserves_notes_resources_and_audit(monkeypatch):
    store, _, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용")
    before = note(teacher, cid)

    def fail(*args, **kwargs):
        raise StorageError("모의 저장 실패")

    monkeypatch.setattr(store, "put", fail)
    with pytest.raises(StorageError):
        note(teacher, cid, text="저장되지 않은 수정")
    with pytest.raises(StorageError):
        place(teacher, cid, "material", material["id"])
    assert teacher.get_course(cid) == before


def test_role_revocation_during_resource_validation_prevents_write(monkeypatch):
    store, users, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용")
    before = teacher.get_course(cid)
    original = WorkService._owned_record

    def revoke_role(self, namespace, record_id, course_id):
        result = original(self, namespace, record_id, course_id)
        users["t"].update(role="student", **{"class": "1-1"})
        return result

    monkeypatch.setattr(WorkService, "_owned_record", revoke_role)
    with pytest.raises(PermissionDenied):
        teacher.place_calendar_resource(cid, "material", material["id"], "2026-10-20", before["version"])
    assert store.get("courses", cid) == before


def test_resource_schedule_for_embedded_copy_template_uses_copied_identity():
    _, _, teacher, cid, work = environment()
    material = work.save_material(cid, "자료", body="내용", published=True)
    copied = teacher.copy_course(cid, "새 수업", "2027-1", class_name="1-1")
    copied_material = copied["copied_material_templates"][0]
    assert copied_material["id"] != material["id"]
    placed = place(teacher, copied["id"], "material", copied_material["id"])
    assert placed["calendar_resources"] == {
        f"material:{copied_material['id']}": {
            "kind": "material", "id": copied_material["id"], "date": "2026-10-20",
        },
    }
    with pytest.raises(PermissionDenied):
        place(teacher, copied["id"], "material", material["id"])


def test_json_restart_preserves_shared_note_and_resource_schedule_without_a_key():
    remote = MockGitHub()

    def cloud():
        return GitHubStore("jsku-sm/class-dashboard-data", "main", "synthetic-token", session=remote)

    store, users, teacher, cid, work = environment(cloud())
    material = work.save_material(cid, "수업자료", body="함수 설명", published=True)
    place(teacher, cid, "material", material["id"])
    original = note(teacher, cid, text="교과서 지참")
    restarted = actor(cloud(), users, "shared")
    assert restarted.get_course(cid) == original
    student = actor(cloud(), users, "s")
    assert student.get_course(cid)["calendar_notes"] == {"2026-10-20": "교과서 지참"}
    assert student.get_course(cid)["calendar_resources"] == original["calendar_resources"]
    assert WorkService(student).materials(cid)[0]["id"] == material["id"]
    assert all(path.startswith("data/classroom/v2/") and path.endswith(".json") for path in remote.files)
