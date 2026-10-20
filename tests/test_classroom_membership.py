"""Classroom membership is scoped by fresh accounts and teacher approval codes."""
import copy
from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from classroom_core import (ArchivedError, ClassroomService, ConflictError, MemoryStore,
                            PermissionDenied, StorageError, ValidationError)
from classroom_core.work import WorkService


@pytest.fixture
def members():
    users = {
        "t": {"id": "t", "role": "teacher"},
        "other_teacher": {"id": "other_teacher", "role": "teacher"},
        "s": {"id": "s", "role": "student", "class": "1-1"},
        "other": {"id": "other", "role": "student", "class": "1-2"},
        "blank": {"id": "blank", "role": "student", "class": ""},
    }
    store = MemoryStore()

    def service(uid, **kwargs):
        return ClassroomService(store, users[uid], users.get,
                                lock_checker=kwargs.get("lock_checker", lambda _: False))

    teacher = service("t")
    course = teacher.create_course("1-1", "2026-2", "수학", class_name="1-1")
    return users, store, service, teacher, course


def legacy_course(store, course, **changes):
    updated = copy.deepcopy(course)
    updated.pop("join_code", None)
    updated.update(changes)
    return store.put("courses", updated["id"], updated, updated["version"])


def test_new_and_copied_courses_have_distinct_persisted_numeric_codes(members):
    _, store, _, teacher, course = members
    copied = teacher.copy_course(course["id"], "1-2", "2027-1", class_name="1-2")
    assert copied["join_code"] != course["join_code"]
    for record in (course, copied):
        code = record["join_code"]
        assert isinstance(code, str) and len(code) == 6 and code.isascii() and code.isdecimal()
        assert store.get("course_join_codes", code)["course_id"] == record["id"]
        assert store.get("courses", record["id"])["join_code"] == code


def test_leading_zeros_are_preserved_and_collisions_reserve_another_number(monkeypatch):
    store = MemoryStore()
    user = {"id": "t", "role": "teacher"}
    teacher = ClassroomService(store, user, lambda uid: user, lock_checker=lambda _: False)
    numbers = iter([1, 1, 2])
    monkeypatch.setattr("classroom_core.progress.secrets.randbelow", lambda _: next(numbers))
    first = teacher.create_course("첫 수업", "2026-2", "수학", class_name="1-1")
    second = teacher.create_course("다음 수업", "2026-2", "수학", class_name="1-1")
    assert first["join_code"] == "000001"
    assert second["join_code"] == "000002"
    assert store.get("course_join_codes", "000001")["course_id"] == first["id"]


def test_valid_code_immediately_approves_and_repeated_join_is_read_only(members):
    _, store, service, _, course = members
    student = service("s")
    result = student.join_course(course["join_code"])
    assert result == {"status": "approved", "course_id": course["id"]}
    saved = store.get("courses", course["id"])
    assert saved["student_ids"] == ["s"] and saved["pending_student_ids"] == []
    assert student.join_course(course["join_code"]) == result
    assert store.get("courses", course["id"]) == saved
    assert student.get_course(course["id"])["membership_status"] == "approved"


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "１２３４５６", 123456, None])
def test_code_requires_six_ascii_digits_as_text(members, code):
    _, store, service, _, course = members
    with pytest.raises(ValidationError):
        service("s").join_course(code)
    assert store.get("courses", course["id"])["student_ids"] == []


def test_legacy_request_api_rejects_internal_course_ids(members):
    _, _, service, _, course = members
    with pytest.raises(ValidationError):
        service("s").request_join(course["id"])
    assert service("s").request_join(course["join_code"])["status"] == "approved"


@pytest.mark.parametrize("uid", ["other", "blank"])
def test_wrong_or_blank_account_class_cannot_join_even_with_valid_code(members, uid):
    _, store, service, _, course = members
    with pytest.raises(PermissionDenied):
        service(uid).join_course(course["join_code"])
    assert store.get("courses", course["id"])["student_ids"] == []


@pytest.mark.parametrize("account_class", ["1-2", "", None])
def test_legacy_memberships_and_pending_rows_do_not_bypass_current_class(members, account_class):
    users, store, service, _, course = members
    course = legacy_course(store, course, student_ids=["s"], pending_student_ids=["other"])
    users["s"]["class"] = account_class
    assert service("s").list_courses() == []
    assert service("other").list_courses() == []
    with pytest.raises(PermissionDenied):
        service("s").get_course(course["id"])


def test_course_without_class_never_grants_student_membership(members):
    _, store, service, _, course = members
    legacy_course(store, course, class_name="", student_ids=["s"])
    assert service("s").list_courses() == []
    with pytest.raises(PermissionDenied):
        service("s").get_course(course["id"])


def test_student_projection_hides_codes_and_audit_after_join(members):
    _, store, service, _, course = members
    course["approval_code"] = "654321"
    store.put("courses", course["id"], course, course["version"])
    student = service("s")
    student.join_course(course["join_code"])
    for visible in (student.get_course(course["id"]), student.list_courses()[0]):
        assert not {"join_code", "approval_code", "audit", "student_ids", "pending_student_ids"} & visible.keys()


def test_only_explicit_course_teachers_can_read_or_generate_codes(members):
    _, _, service, _, course = members
    for uid in ("s", "other_teacher"):
        with pytest.raises(PermissionDenied):
            service(uid).get_join_code(course["id"])


def test_ordinary_reads_do_not_upgrade_legacy_courses(members):
    _, store, _, teacher, course = members
    before = legacy_course(store, course)
    teacher.get_course(course["id"])
    teacher.list_courses()
    assert store.get("courses", course["id"]) == before
    code = teacher.get_join_code(course["id"])
    after = store.get("courses", course["id"])
    assert after["join_code"] == code
    assert teacher.get_join_code(course["id"]) == code
    assert store.get("courses", course["id"]) == after


def test_legacy_code_generation_recovers_same_reservation_after_failed_course_save(members, monkeypatch):
    _, store, _, teacher, course = members
    legacy_course(store, course)
    put = store.put
    fail_once = True

    def interrupted(namespace, record_id, record, expected_version=None):
        nonlocal fail_once
        if namespace == "courses" and fail_once:
            fail_once = False
            raise StorageError("저장 중단")
        return put(namespace, record_id, record, expected_version)

    monkeypatch.setattr(store, "put", interrupted)
    with pytest.raises(StorageError):
        teacher.get_join_code(course["id"])
    reserved = [r for r in store.list("course_join_codes") if r["course_id"] == course["id"]]
    # The original create reservation is reused for the legacy record, too.
    assert len(reserved) == 1
    assert teacher.get_join_code(course["id"]) == reserved[0]["id"]


def test_unpublished_or_missing_course_reservations_do_not_allow_join(members):
    _, store, service, _, course = members
    codes = [f"{value:06d}" for value in range(3) if f"{value:06d}" != course["join_code"]][:2]
    for code, cid in zip(codes, (course["id"], "missing")):
        store.put("course_join_codes", code, {"id": code, "course_id": cid}, None)
        with pytest.raises(PermissionDenied):
            service("s").join_course(code)
    assert store.get("courses", course["id"])["student_ids"] == []


def test_failed_join_never_claims_success_and_retry_is_durable(members, monkeypatch):
    _, store, service, _, course = members
    put = store.put

    def fail(namespace, *args, **kwargs):
        if namespace == "courses":
            raise StorageError("저장 실패")
        return put(namespace, *args, **kwargs)

    monkeypatch.setattr(store, "put", fail)
    with pytest.raises(StorageError):
        service("s").join_course(course["join_code"])
    assert store.get("courses", course["id"])["student_ids"] == []
    monkeypatch.setattr(store, "put", put)
    service("s").join_course(course["join_code"])
    assert service("s").get_course(course["id"])["id"] == course["id"]


def test_join_retries_version_conflicts_without_duplicate_memberships(members, monkeypatch):
    _, store, service, _, course = members
    put = store.put
    conflicts = 2

    def competing(namespace, *args, **kwargs):
        nonlocal conflicts
        if namespace == "courses" and conflicts:
            conflicts -= 1
            raise ConflictError("다른 학생 참여")
        return put(namespace, *args, **kwargs)

    monkeypatch.setattr(store, "put", competing)
    service("s").join_course(course["join_code"])
    assert conflicts == 0
    assert store.get("courses", course["id"])["student_ids"] == ["s"]


def test_concurrent_students_and_duplicate_clicks_keep_one_membership_each(members, monkeypatch):
    users, store, service, _, course = members
    users.update({f"s{i}": {"id": f"s{i}", "role": "student", "class": "1-1"} for i in range(25)})
    get = store.get

    def delayed_snapshot(namespace, *args, **kwargs):
        snapshot = get(namespace, *args, **kwargs)
        if namespace == "courses":
            time.sleep(0.005)
        return snapshot

    monkeypatch.setattr(store, "get", delayed_snapshot)
    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(lambda uid: service(uid).join_course(course["join_code"]),
                                [f"s{i}" for i in range(25)] * 2))
    assert all(item["status"] == "approved" for item in results)
    assert sorted(store.get("courses", course["id"])["student_ids"]) == sorted(f"s{i}" for i in range(25))


def test_archive_blocks_join_and_new_code_generation(members):
    _, store, service, teacher, course = members
    teacher.archive_course(course["id"], course["version"])
    assert teacher.get_join_code(course["id"]) == course["join_code"]
    with pytest.raises(PermissionDenied):
        service("s").join_course(course["join_code"])
    archived = store.get("courses", course["id"])
    before = legacy_course(store, archived)
    with pytest.raises(ArchivedError):
        teacher.get_join_code(course["id"])
    assert store.get("courses", course["id"]) == before


def test_legacy_pending_approval_checks_current_class_and_join_consumes_pending(members):
    _, store, service, teacher, course = members
    course = legacy_course(store, course, pending_student_ids=["s", "other"])
    with pytest.raises(ValidationError):
        teacher.approve_member(course["id"], "other")
    teacher.approve_member(course["id"], "other", approve=False)
    code = teacher.get_join_code(course["id"])
    service("s").join_course(code)
    approved = store.get("courses", course["id"])
    assert approved["student_ids"] == ["s"] and approved["pending_student_ids"] == []


def test_teachers_cannot_seed_mismatched_student_memberships(members):
    _, _, _, teacher, _ = members
    with pytest.raises(ValidationError):
        teacher.create_course("1-1", "2026-2", "수학", class_name="1-1", student_ids=["other"])


def test_transferred_student_cannot_use_stale_ids_for_work(members):
    users, _, service, _, course = members
    student = service("s")
    student.join_course(course["join_code"])
    teacher_work = WorkService(service("t"))
    task = teacher_work.save_assignment(course["id"], "과제", "풀이", published=True)
    work = WorkService(student)
    assert work.assignment(course["id"], task["id"])["id"] == task["id"]
    users["s"]["class"] = "1-2"
    for read in (lambda: student.get_course(course["id"]),
                 lambda: work.materials(course["id"]),
                 lambda: work.assignment(course["id"], task["id"]),
                 lambda: work.assignments(course["id"]),
                 lambda: work.save_draft(course["id"], task["id"], text="우회")):
        with pytest.raises(PermissionDenied):
            read()
    assert student.list_courses() == []


def test_password_requirement_and_lock_precede_code_validation(members):
    users, _, service, _, _ = members
    with pytest.raises(PermissionDenied, match="잠금"):
        service("s", lock_checker=lambda _: True).join_course("invalid")
    users["s"]["must_change"] = "1"
    with pytest.raises(PermissionDenied, match="비밀번호"):
        service("s").join_course("invalid")


def test_default_actor_lookup_invalidates_cached_account_metadata(monkeypatch):
    import auth
    import storage

    users = {"s": {"id": "s", "role": "student", "class": "1-1"}}
    invalidated = []
    monkeypatch.setattr(storage, "invalidate", invalidated.append)
    monkeypatch.setattr(auth, "get_user", users.get)
    service = ClassroomService(MemoryStore(), {"id": "s", "class": "stale", "role": "teacher"})
    assert service.actor()["class"] == "1-1"
    users["s"]["class"] = "1-2"
    assert service.actor()["class"] == "1-2"
    assert invalidated == ["users", "users"]
