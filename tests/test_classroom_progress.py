import copy

import pytest

from classroom_core import (ArchivedError, ClassroomService, ConflictError, MemoryStore,
                            PermissionDenied, ValidationError, calculate_progress)


@pytest.fixture
def setup():
    users = {"t": {"id": "t", "role": "teacher"}, "other": {"id": "other", "role": "teacher"},
             "s": {"id": "s", "role": "student", "class": "1-1"},
             "s2": {"id": "s2", "role": "student", "class": "1-1"}}
    store = MemoryStore()
    service = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    curriculum = service.create_curriculum("공통안", "수학", [
        {"id": str(i), "unit": "기하" if i < 3 else "함수", "title": f"{i}차시"} for i in range(1, 5)])
    course = service.create_course("정규", "2026-2", "수학", class_name="1-1", curriculum_id=curriculum["id"], student_ids=["s"])
    return service, users, store, curriculum, course


def update(service, course_id, lesson_id, **changes):
    course = service.get_course(course_id)
    return service.set_lesson(course_id, lesson_id, changes, course["version"], "교사 확인")


def test_skipped_due_lessons_not_offset_by_equal_early_completion(setup):
    service, _, _, _, course = setup
    cid = course["id"]
    update(service, cid, "1", planned_date="2026-10-01", progress="scheduled")
    update(service, cid, "2", planned_date="2026-10-02", progress="completed", actual_date="2026-10-02")
    update(service, cid, "3", planned_date="2026-10-30", progress="completed", actual_date="2026-10-05")
    summary = service.progress_summary(cid, "2026-10-20")
    assert (summary["completed"], summary["total"], summary["percent"]) == (2, 4, 50.0)
    assert summary["due_incomplete"] == ["1"]
    assert summary["early_completed"] == ["3"]
    assert service.progress_summary(cid, "2026-10-20", unit="기하")["percent"] == 50.0


def test_unique_completion_independent_makeup_and_other_class(setup):
    service, _, _, curriculum, first = setup
    second = service.create_course("다른 반", "2026-2", "수학", class_name="1-2", curriculum_id=curriculum["id"])
    update(service, first["id"], "1", progress="completed", actual_date="2026-10-01", makeup_needed=True)
    for kind in ("makeup", "split", "repeat"):
        service.add_session(first["id"], "1", "2026-10-02", kind=kind)
    summary = service.progress_summary(first["id"], "2026-10-20")
    assert summary["completed"] == 1 and summary["makeup_needed"]
    assert service.progress_summary(second["id"], "2026-10-20")["completed"] == 0
    assert len(service.get_course(first["id"])["lesson_records"]["1"]["sessions"]) == 3


def test_no_plan_no_applied_cancellation_and_open_resources(setup):
    service, _, _, _, course = setup
    cid = course["id"]
    assert service.progress_summary(cid)["plan_label"] == "계획 미설정"
    update(service, cid, "1", planned_date="2026-10-01", schedule_status="cancelled")
    summary = service.progress_summary(cid, "2026-10-20")
    assert summary["reschedule_needed"] == ["1"] and summary["completed"] == 0
    # Reading connected resources and returning to the calendar are read-only.
    before = service.get_course(cid)
    service.get_course(cid)
    service.progress_summary(cid)
    assert service.get_course(cid) == before
    for lesson in before["lessons"]:
        update(service, cid, lesson["id"], applied=False)
    summary = service.progress_summary(cid)
    assert summary["percent"] is None and summary["label"] == "수업안 미설정"


def test_stale_version_has_no_partial_audit_or_progress(setup):
    service, _, _, _, course = setup
    update(service, course["id"], "1", planned_date="2026-10-02")
    before = service.get_course(course["id"])
    with pytest.raises(ConflictError):
        service.set_lesson(course["id"], "2", {"progress": "in_progress"}, course["version"], "오래된 창")
    assert service.get_course(course["id"]) == before
    assert before["audit"][-1]["lesson_changes"]["1"]["after"]["planned_date"] == "2026-10-02"


def test_membership_same_account_regular_after_school_and_auth_not_trusted(setup):
    service, users, store, _, course = setup
    student = ClassroomService(store, {"id": "s", "role": "teacher"}, users.get, lock_checker=lambda _: False)
    after = service.create_course("방과후", "2026-2", "수학", kind="after_school")
    student.request_join(after["id"])
    assert student.list_courses()[-1]["membership_status"] == "pending"
    with pytest.raises(PermissionDenied):
        student.get_course(after["id"])
    service.approve_member(after["id"], "s")
    assert {row["kind"] for row in student.list_courses()} == {"regular", "after_school"}
    with pytest.raises(PermissionDenied):
        student.set_lesson(course["id"], "1", {"progress": "in_progress"}, course["version"], "위조")
    users["s"]["role"] = "disabled"
    with pytest.raises(PermissionDenied):
        student.list_courses()


def test_students_do_not_receive_classmate_ids_teacher_notes_or_audit(setup):
    service, users, store, _, course = setup
    update(service, course["id"], "1", memo="개인 관찰", makeup_reason="평가 정보")
    student = ClassroomService(store, users["s"], users.get)
    visible = student.course(course["id"])
    assert "audit" not in visible and "student_ids" not in visible
    assert "memo" not in visible["lesson_records"]["1"]
    assert "makeup_reason" not in visible["lesson_records"]["1"]
    stranger = ClassroomService(store, users["s2"], users.get)
    with pytest.raises(PermissionDenied):
        stranger.get_course(course["id"])


def test_curriculum_update_requires_explicit_per_course_apply(setup):
    service, users, store, curriculum, course = setup
    outsider = ClassroomService(store, users["other"], users.get)
    with pytest.raises(PermissionDenied):
        outsider.get_curriculum(curriculum["id"])
    update(service, course["id"], "1", progress="completed", actual_date="2026-10-01")
    revised = copy.deepcopy(curriculum["lessons"])
    revised[0]["title"] = "새 이름"
    revised.append({"id": "5", "title": "추가 차시"})
    preview = service.preview_curriculum_changes(curriculum["id"], revised)
    assert preview[0]["added"] == ["5"]
    service.update_curriculum(curriculum["id"], {"lessons": revised}, curriculum["version"], "수업안 개정")
    before = service.get_course(course["id"])
    assert len(before["lessons"]) == 4
    applied = service.apply_curriculum(course["id"], curriculum["id"], before["version"], "반별 확인")
    assert len(applied["lessons"]) == 5
    assert service.progress_summary(course["id"])["completed"] == 1


def test_archive_read_only_and_copy_excludes_students_progress_and_work(setup):
    service, _, store, _, course = setup
    update(service, course["id"], "1", progress="completed", actual_date="2026-10-01")
    store.put("submissions", "old_work", {"id": "old_work", "course_id": course["id"], "answer": "private"})
    before = service.get_course(course["id"])
    archived = service.archive_course(course["id"], before["version"])
    with pytest.raises(ArchivedError):
        service.set_lesson(course["id"], "2", {"planned_date": "2027-03-01"}, archived["version"], "보관 후 수정")
    copied = service.copy_course(course["id"], "새 학기", "2027-1")
    assert copied["student_ids"] == [] and copied["lesson_records"] == {}
    assert len(copied["lessons"]) == 4
    assert not [s for s in store.list("submissions") if s["course_id"] == copied["id"]]


def test_completion_validation_input_lock_and_password_requirement(setup):
    service, users, store, _, course = setup
    with pytest.raises(ValidationError):
        update(service, course["id"], "1", progress="completed")
    locked = ClassroomService(store, users["s"], users.get, lock_checker=lambda _: True)
    extra = service.create_course("추가", "2026-2", "수학")
    with pytest.raises(PermissionDenied, match="잠금"):
        locked.request_join(extra["id"])
    users["s"]["must_change"] = "1"
    with pytest.raises(PermissionDenied, match="비밀번호"):
        locked.list_courses()


def test_schedule_update_preserves_assignment_deadline_and_other_course(setup):
    service, _, store, _, course = setup
    store.put("assignments", "task", {"id": "task", "course_id": course["id"], "due_at": "2026-10-30T16:00:00+09:00"})
    update(service, course["id"], "1", planned_date="2026-10-21", period="3", resources=[{"kind": "assignment", "id": "task"}])
    changed = update(service, course["id"], "1", planned_date="2026-10-23", schedule_status="changed")
    assert store.get("assignments", "task")["due_at"] == "2026-10-30T16:00:00+09:00"
    audit = changed["audit"][-1]["lesson_changes"]["1"]
    assert audit["before"]["planned_date"] == "2026-10-21" and audit["after"]["planned_date"] == "2026-10-23"


def test_compare_rejects_different_curriculum_versions(setup):
    service, _, _, curriculum, course = setup
    another = service.create_course("다른 과목", "2026-2", "영어")
    with pytest.raises(ValidationError):
        service.comparison([course["id"], another["id"]])
    empty = service.create_course("미설정", "2026-2", "수학")
    assert calculate_progress(empty)["label"] == "수업안 미설정"


def test_next_term_templates_are_atomic_sanitized_and_remapped(setup, monkeypatch):
    service, users, store, _, course = setup
    store.put("materials", "original", {"id": "original", "course_id": course["id"], "title": "설명 자료", "body": "학습 안내",
                                        "published": True, "target_student_ids": ["s"], "private_comment": "복사 금지"})
    store.put("assignments", "task", {"id": "task", "course_id": course["id"], "title": "과제", "instructions": "풀기", "methods": ["text", "file"],
                                      "rubric": [{"label": "풀이", "max_points": 10}], "material_ids": ["original"], "published": True,
                                      "due_at": "2026-10-20", "target_student_ids": ["s"], "answer": "학생 답안", "score": 8})
    old_material = store.put("materials", "old-material", {"id": "old-material", "course_id": course["id"],
        "title": "이전 외부 자료", "activity_id": "old-activity"})
    old_task = store.put("assignments", "old-task", {"id": "old-task", "course_id": course["id"],
        "title": "이전 외부 과제", "methods": ["snorkl"]})
    curriculum = service.get_curriculum(course["curriculum_id"])
    lessons = copy.deepcopy(curriculum["lessons"])
    lessons[0]["resources"] = [{"kind": "material", "id": "original"}, {"kind": "assignment", "id": "task"},
                                {"kind": "material", "id": "old-material"}, {"kind": "assignment", "id": "old-task"}]
    service.update_curriculum(curriculum["id"], {"lessons": lessons}, curriculum["version"], "연결")
    latest = service.get_course(course["id"])
    service.apply_curriculum(course["id"], curriculum["id"], latest["version"], "확인")
    copied = service.copy_course(course["id"], "새 학기", "2027-1")
    assert len(copied["copied_material_templates"]) == len(copied["copied_assignment_templates"]) == 1
    material, task = copied["copied_material_templates"][0], copied["copied_assignment_templates"][0]
    assert not material["published"] and not task["published"]
    assert "private_comment" not in material and "score" not in task and "answer" not in task
    assert task["due_at"] is None and task["target_student_ids"] == [] and task["methods"] == ["text", "file"]
    assert "activity_id" not in material and "activity_id" not in task
    assert store.get("materials", "old-material") == old_material
    assert store.get("assignments", "old-task") == old_task
    assert task["material_ids"] == [material["id"]]
    assert {r["id"] for r in copied["lessons"][0]["resources"]} == {material["id"], task["id"]}
    student = ClassroomService(store, users["s"], users.get, lock_checker=lambda _: False)
    student.request_join(copied["id"])
    service.approve_member(copied["id"], "s")
    assert "copied_material_templates" not in student.get_course(copied["id"])
    assert "copied_assignment_templates" not in student.get_course(copied["id"])
    before = len(store.list("courses"))
    put = store.put
    def fail_copy(namespace, record_id, record, expected_version=None):
        if namespace == "courses" and record.get("title") == "실패한 복사":
            from classroom_core import StorageError
            raise StorageError("모의 저장 실패")
        return put(namespace, record_id, record, expected_version)
    monkeypatch.setattr(store, "put", fail_copy)
    from classroom_core import StorageError
    with pytest.raises(StorageError):
        service.copy_course(course["id"], "실패한 복사", "2027-1")
    assert len(store.list("courses")) == before


def test_old_lesson_activity_launches_are_hidden_without_migrating_stored_records(setup):
    service, users, store, curriculum, course = setup
    raw_curriculum = store.get("curricula", curriculum["id"])
    old_lesson = raw_curriculum["lessons"][0]
    old_lesson["activity_id"] = "old-activity"
    old_lesson["resources"] = [
        {"kind": "snorkl", "id": "old-activity", "url": "https://removed.example/activity"},
        {"kind": "url", "activity_id": "old-activity", "url": "https://removed.example/activity"},
        {"kind": "material", "id": "retained", "activity_id": "old-activity", "url": "https://private.example/file"},
        {"kind": "url", "title": "참고", "url": "https://school.example/reference"},
    ]
    saved_curriculum = store.put("curricula", curriculum["id"], raw_curriculum, raw_curriculum["version"])
    raw_course = store.get("courses", course["id"])
    raw_course["lessons"] = copy.deepcopy(saved_curriculum["lessons"])
    raw_course["lesson_records"][old_lesson["id"]] = dict(progress="in_progress", activity_id="old-activity",
        resources=[{"kind": "activity", "id": "old-activity"}])
    saved_course = store.put("courses", course["id"], raw_course, raw_course["version"])
    student = ClassroomService(store, users["s"], users.get)
    for visible in (service.get_course(course["id"]), service.list_courses()[0], student.get_course(course["id"])):
        lesson = visible["lessons"][0]
        assert "activity_id" not in lesson
        assert lesson["resources"] == [{"kind": "material", "id": "retained"},
            {"kind": "url", "title": "참고", "url": "https://school.example/reference"}]
        record = visible["lesson_records"][old_lesson["id"]]
        assert "activity_id" not in record and record["resources"] == []
    assert "activity_id" not in service.progress_summary(course["id"])["current_lesson"]
    assert "activity_id" not in service.get_curriculum(curriculum["id"])["lessons"][0]
    assert "activity_id" not in service.list_curricula()[0]["lessons"][0]
    new_course = service.create_course("새 수업", "2027-1", "수학", curriculum_id=curriculum["id"])
    assert "activity_id" not in new_course["lessons"][0]
    assert store.get("courses", course["id"]) == saved_course
    assert store.get("curricula", curriculum["id"]) == saved_curriculum
    renamed = service.update_curriculum(curriculum["id"], {"title": "이름만 변경"}, saved_curriculum["version"], "이름 수정")
    assert renamed["lessons"] == saved_curriculum["lessons"]
    assert "activity_id" not in service.get_curriculum(curriculum["id"])["lessons"][0]


def test_new_curriculum_discards_removed_activity_launch_fields(setup):
    service, _, _, _, _ = setup
    curriculum = service.create_curriculum("직접 수업안", "수학", [dict(title="차시", activity_id="removed", resources=[
        {"kind": "activity", "id": "removed"}, {"kind": "snorkl", "id": "removed"},
        {"kind": "url", "url": "https://school.example/reference"}])])
    assert "activity_id" not in curriculum["lessons"][0]
    assert curriculum["lessons"][0]["resources"] == [{"kind": "url", "url": "https://school.example/reference"}]
