"""Seven-class content/checklist tests. No live account, token or student data."""
from datetime import datetime, timedelta
import copy

import pytest

from classroom_core import (ClassroomService, MemoryStore, PermissionDenied,
                            ConflictError, StorageError, ValidationError, ArchivedError, GitHubStore)
from classroom_core.progress import TZ
from classroom_core.work import WorkService
from classroom_core.teaching_board import TeachingBoardService, CLASSES, board_model, NAMESPACE


@pytest.fixture
def env():
    users = {"t": {"id": "t", "role": "teacher"}, "other": {"id": "other", "role": "teacher"}}
    for index in range(1, 8):
        users[f"s{index}"] = {"id": f"s{index}", "role": "student", "class": f"1-{index}"}
    store = MemoryStore()
    service = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    plan = service.create_curriculum("기존 수업안", "공통수학2", [
        {"id": "base-1", "title": "직선의 방정식"}, {"id": "base-2", "title": "원의 방정식"}])
    courses = {cls: service.create_course(cls, "2026-2", "공통수학2", class_name=cls,
                 student_ids=[f"s{index}"], curriculum_id=plan["id"])
               for index, cls in enumerate(CLASSES, 1)}
    return service, TeachingBoardService(service), store, users, courses, plan


def content(board, key="upload", files=None):
    return board.create("픽토그램 만들기", term="2026-2", subject="공통수학2", body="직선과 원으로 표현해요.",
                        files=files, request_id=key)


def student(service, store, users, name):
    return WorkService(ClassroomService(store, users[name], users.get, lock_checker=lambda _: False))


def fresh_map(service, courses):
    return {cls: service.get_course(item["id"]) for cls, item in courses.items()}


def toggle(service, board, cid, lid, value):
    return board.set_completed(cid, lid, value, expected_version=service.get_course(cid)["version"],
                               actual_date=datetime.now(TZ).date().isoformat())


def test_all_seven_classes_shown_even_when_no_courses():
    model = board_model({}, [])
    assert [item["class_name"] for item in model["cards"]] == list(CLASSES)
    assert all(item["percent"] is None and item["label"] == "수업 미개설" for item in model["cards"])
    assert not model["rows"]


def test_title_only_upload_is_valid_and_is_private(env):
    service, board, store, users, courses, _ = env
    result = board.create("함수 개념 정리", term="2026-2", subject="공통수학2", request_id="title")
    assert result["attachments"] == [] and result["published_course_ids"] == []
    assert student(service, store, users, "s1").materials(courses["1-1"]["id"]) == []


def test_creation_retries_are_idempotent_and_changed_payload_rejected(env):
    _, board, store, *_ = env
    first = content(board)
    assert content(board)["id"] == first["id"]
    assert len(store.list(NAMESPACE)) == 1
    with pytest.raises(ConflictError):
        board.create("다른 내용", term="2026-2", subject="공통수학2", request_id="upload")


def test_selected_distribution_only_visible_to_selected_class(env):
    service, board, store, users, courses, _ = env
    source = content(board, files=[{"filename": "활동지.txt", "data": "수업 자료".encode()}])
    board.distribute(source["id"], [courses["1-1"]["id"], courses["1-3"]["id"]])
    work1, work2 = student(service, store, users, "s1"), student(service, store, users, "s2")
    materials = work1.materials(courses["1-1"]["id"])
    assert len(materials) == 1 and materials[0]["title"] == source["title"]
    assert not work2.materials(courses["1-2"]["id"])
    assert all(key not in materials[0] for key in ("course_ids", "published_course_ids", "owner_id", "audit", "distribution_classes"))
    assert work1.download_material(courses["1-1"]["id"], materials[0]["id"], 0)["data"] == "수업 자료".encode()
    with pytest.raises(PermissionDenied):
        work2.download_material(courses["1-1"]["id"], materials[0]["id"], 0)
    with pytest.raises(PermissionDenied):
        work2.download_material(courses["1-2"]["id"], materials[0]["id"], 0)
    # One uploaded original; no seven physical file copies.
    assert len(store.list(NAMESPACE)) == 1 and store.list("materials") == []


def test_distribution_does_not_complete_lessons_and_retries_do_not_reset(env):
    service, board, _, _, courses, _ = env
    source = content(board)
    cid = courses["1-1"]["id"]
    board.distribute(source["id"], [cid])
    assert service.progress_summary(cid)["completed"] == 0
    toggle(service, board, cid, source["lesson_id"], True)
    board.distribute(source["id"], [cid, courses["1-2"]["id"]])
    assert len(service.get_course(cid)["lessons"]) == 3
    assert service.progress_summary(cid)["completed"] == 1
    assert service.progress_summary(courses["1-2"]["id"])["completed"] == 0


def test_checkbox_persists_real_date_and_unchecks_without_losing_notes(env):
    service, board, _, _, courses, _ = env
    cid = courses["1-1"]["id"]
    service.set_lesson(cid, "base-1", {"memo": "이어 설명할 내용", "planned_date": "2026-10-01"},
                       service.get_course(cid)["version"], "계획")
    done = toggle(service, board, cid, "base-1", True)
    assert done["lesson_records"]["base-1"]["actual_date"] == datetime.now(TZ).date().isoformat()
    assert service.progress_summary(cid)["percent"] == 50.0
    undone = toggle(service, board, cid, "base-1", False)
    record = undone["lesson_records"]["base-1"]
    assert record["progress"] == "scheduled" and record["actual_date"] == ""
    assert record["memo"] == "이어 설명할 내용" and record["planned_date"] == "2026-10-01"
    assert service.progress_summary(courses["1-2"]["id"])["completed"] == 0
    assert len(undone["audit"]) > len(courses["1-1"]["audit"])


def test_stale_checkbox_never_overwrites_new_record(env):
    service, board, _, _, courses, _ = env
    cid = courses["1-1"]["id"]
    version = service.get_course(cid)["version"]
    toggle(service, board, cid, "base-1", True)
    with pytest.raises(ConflictError):
        board.set_completed(cid, "base-1", False, expected_version=version, actual_date="2026-10-01")
    assert service.progress_summary(cid)["completed"] == 1


def test_future_completion_rejected(env):
    service, board, _, _, courses, _ = env
    cid = courses["1-1"]["id"]
    with pytest.raises(ValidationError, match="미래"):
        board.set_completed(cid, "base-1", True, expected_version=service.get_course(cid)["version"],
                            actual_date=(datetime.now(TZ).date() + timedelta(days=1)).isoformat())


@pytest.mark.parametrize("changes", [{"applied": False}, {"schedule_status": "cancelled"}])
def test_unapplied_and_cancelled_lessons_cannot_be_checked(env, changes):
    service, board, _, _, courses, _ = env
    cid = courses["1-1"]["id"]
    service.set_lesson(cid, "base-1", changes, service.get_course(cid)["version"], "변경")
    with pytest.raises(ValidationError):
        toggle(service, board, cid, "base-1", True)


@pytest.mark.parametrize("bad", ["true", 1, None, [], {}])
def test_browser_bool_type_is_checked(env, bad):
    service, board, _, _, courses, _ = env
    with pytest.raises(ValidationError):
        toggle(service, board, courses["1-1"]["id"], "base-1", bad)


def test_student_and_unassigned_teacher_cannot_change_content_or_progress(env):
    service, board, store, users, courses, _ = env
    source = content(board)
    for uid in ("s1", "other"):
        other = TeachingBoardService(ClassroomService(store, users[uid], users.get))
        with pytest.raises(PermissionDenied):
            other.distribute(source["id"], [courses["1-1"]["id"]])
        with pytest.raises(PermissionDenied):
            other.set_completed(courses["1-1"]["id"], "base-1", True,
                                expected_version=courses["1-1"]["version"], actual_date="2026-10-01")
    with pytest.raises(PermissionDenied):
        content(TeachingBoardService(ClassroomService(store, users["s1"], users.get)))


def test_failed_recipient_validation_does_not_partly_apply(env):
    service, board, store, users, courses, _ = env
    outsider = ClassroomService(store, users["other"], users.get)
    foreign = outsider.create_course("다른 교사", "2026-2", "공통수학2", class_name="1-7")
    source = content(board)
    with pytest.raises(PermissionDenied):
        board.distribute(source["id"], [courses["1-1"]["id"], foreign["id"]])
    assert len(service.get_course(courses["1-1"]["id"])["lessons"]) == 2
    assert board._owned(source["id"])["published_course_ids"] == []


def test_partial_distribution_failure_is_retryable_and_not_published(env, monkeypatch):
    service, board, store, users, courses, _ = env
    source = content(board)
    one, two = courses["1-1"]["id"], courses["1-2"]["id"]
    original = store.put
    def fail_second(namespace, record_id, record, expected_version=None):
        if namespace == "courses" and record_id == two:
            raise StorageError("자료 배포 실패")
        return original(namespace, record_id, record, expected_version)
    monkeypatch.setattr(store, "put", fail_second)
    with pytest.raises(StorageError):
        board.distribute(source["id"], [one, two])
    assert board._owned(source["id"])["published_course_ids"] == []
    assert student(service, store, users, "s1").materials(one) == []
    with pytest.raises(ValidationError, match="배포"):
        toggle(service, board, one, source["lesson_id"], True)
    monkeypatch.setattr(store, "put", original)
    board.distribute(source["id"], [one, two])
    assert len(service.get_course(one)["lessons"]) == 3
    assert len(service.get_course(two)["lessons"]) == 3
    assert len(student(service, store, users, "s1").materials(one)) == 1


def test_storage_failure_does_not_change_saved_checkbox(env, monkeypatch):
    service, board, store, _, courses, _ = env
    cid = courses["1-1"]["id"]
    before = store.get("courses", cid)
    def fail(*args, **kwargs):
        raise StorageError("모의 GitHub 저장 실패")
    monkeypatch.setattr(store, "put", fail)
    with pytest.raises(StorageError):
        toggle(service, board, cid, "base-1", True)
    assert store.get("courses", cid) == before


def test_empty_selection_wrong_subject_duplicate_class_and_archived_rejected(env):
    service, board, _, _, courses, _ = env
    source = content(board)
    with pytest.raises(ValidationError):
        board.distribute(source["id"], [])
    wrong = service.create_course("다른 과목", "2026-2", "공통수학1", class_name="1-1")
    with pytest.raises(ValidationError):
        board.distribute(source["id"], [wrong["id"]])
    duplicate = service.create_course("동일 반", "2026-2", "공통수학2", class_name="1-1")
    with pytest.raises(ValidationError):
        board.distribute(source["id"], [courses["1-1"]["id"], duplicate["id"]])
    original = courses["1-1"]
    service.archive_course(original["id"], original["version"])
    with pytest.raises(ArchivedError):
        board.distribute(source["id"], [original["id"]])


def test_apply_curriculum_preserves_uploaded_content_and_progress(env):
    service, board, _, _, courses, plan = env
    source = content(board)
    cid = courses["1-1"]["id"]
    board.distribute(source["id"], [cid])
    toggle(service, board, cid, source["lesson_id"], True)
    service.apply_curriculum(cid, plan["id"], service.get_course(cid)["version"], "수업안 재적용")
    latest = service.get_course(cid)
    assert len(latest["lessons"]) == 3 and latest["lesson_records"][source["lesson_id"]]["progress"] == "completed"


def test_next_term_copy_is_private_independent_and_has_no_old_progress(env):
    service, board, store, users, courses, _ = env
    source = content(board, files=[{"filename": "학습지.txt", "data": b"sample"}])
    cid = courses["1-1"]["id"]
    board.distribute(source["id"], [cid])
    toggle(service, board, cid, source["lesson_id"], True)
    copied = service.copy_course(cid, "새 학기", "2027-1", class_name="1-1")
    assert copied["lesson_records"] == {} and copied["student_ids"] == []
    template = copied["copied_material_templates"][0]
    assert not template["published"] and template["attachments"][0]["filename"] == "학습지.txt"
    lesson = next(x for x in copied["lessons"] if x["id"] == source["lesson_id"])
    assert "board_content_id" not in lesson and lesson["resources"][0]["id"] == template["id"]


def test_board_summaries_and_existing_shared_lessons_are_not_duplicated(env):
    service, board, _, _, courses, _ = env
    source = content(board)
    board.distribute(source["id"], [courses[cls]["id"] for cls in CLASSES])
    toggle(service, board, courses["1-1"]["id"], source["lesson_id"], True)
    model = board_model(fresh_map(service, courses), board.contents("2026-2", "공통수학2"))
    assert len(model["rows"]) == 3 and len(model["cards"]) == 7
    assert model["cards"][0]["percent"] == 33.3
    assert model["cards"][1]["percent"] == 0
    row = next(r for r in model["rows"] if r.get("content_id") == source["id"])
    assert len(row["cells"]) == 7 and row["cells"]["1-1"]["completed"]
    assert not row["cells"]["1-2"]["completed"]


def test_class_transfer_does_not_expose_previous_distribution(env):
    service, board, store, users, courses, _ = env
    source = content(board)
    cid = courses["1-1"]["id"]
    board.distribute(source["id"], [cid])
    c = store.get("courses", cid)
    c["class_name"], c["student_ids"] = "1-2", ["s2"]
    store.put("courses", cid, c, c["version"])
    assert student(service, store, users, "s2").materials(cid) == []
    with pytest.raises(ValidationError):
        board.distribute(source["id"], [cid])


def test_shared_material_cannot_be_overridden_from_individual_material_form(env):
    service, board, _, _, courses, _ = env
    source = content(board)
    cid = courses["1-1"]["id"]
    board.distribute(source["id"], [cid])
    with pytest.raises(ValidationError, match="공통"):
        WorkService(service).save_material(cid, "덮어쓰기", body="변경", material_id="board:" + source["id"])


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://name:password@example.com", "file:///etc/passwd"])
def test_invalid_links_rejected(env, url):
    _, board, *_ = env
    with pytest.raises(ValidationError):
        board.create("링크", term="2026-2", subject="공통수학2", url=url, request_id="bad")


def test_mock_github_restart_file_access_and_checkboxes_persist():
    from test_classroom_work import MockGitHub
    remote = MockGitHub()
    users = {"t": {"id": "t", "role": "teacher"}, "s": {"id": "s", "role": "student", "class": "1-1"}}
    def instance():
        store = GitHubStore("test-owner/mydashboard", "data", "synthetic-not-a-token", session=remote)
        return ClassroomService(store, users["t"], users.get)
    service = instance()
    course = service.create_course("수학", "2026-2", "공통수학2", class_name="1-1", student_ids=["s"])
    board = TeachingBoardService(service)
    item = content(board, files=[{"filename": "검사.txt", "data": b"remote bytes"}])
    board.distribute(item["id"], [course["id"]])
    toggle(service, board, course["id"], item["lesson_id"], True)
    restarted = instance()
    assert restarted.progress_summary(course["id"])["completed"] == 1
    saved = WorkService(restarted).download_material(course["id"], "board:" + item["id"], 0)
    assert saved["data"] == b"remote bytes"
    assert any("/teaching_contents/" in path for path in remote.files)
    assert not any("/materials/" in path for path in remote.files)
