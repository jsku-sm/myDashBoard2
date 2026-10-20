"""Atomic multi-class notices keep independent, permission-checked boards."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone

import pytest

from classroom_core import (ArchivedError, ClassroomService, GitHubStore, MemoryStore,
                            PermissionDenied, StorageError, ValidationError)
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub, environment


def boards(store=None):
    store, users, teacher, first, work = environment(store)
    users["second"] = dict(id="second", role="student", **{"class": "1-2"})
    users["third"] = dict(id="third", role="student", **{"class": "1-3"})
    second = teacher.create_course("수학", "2026-2", "수학", class_name="1-2", student_ids=["second"])
    third = teacher.create_course("수학", "2026-2", "수학", class_name="1-3", student_ids=["third"])
    return store, users, teacher, [first, second["id"], third["id"]], work


def distribute(work, course_ids, request_id="announcement-1", **fields):
    return work.distribute_post(course_ids, fields.pop("title", "여러 학급 공지"),
                                fields.pop("body", "선택한 학급만 읽는 본문"), request_id=request_id, **fields)


def change_course(teacher, course_id, **changes):
    return teacher.update_course(course_id, changes, teacher.get_course(course_id)["version"], "회귀 검사")


def test_selected_classes_receive_one_shared_notice_with_independent_board_ids():
    store, _, _, ids, work = boards()
    receipt = distribute(work("teacher"), ids[:2])
    assert receipt["complete"] and receipt["target_course_ids"] == sorted(ids[:2])
    assert len(store.list("stream_distributions")) == 1
    assert store.list("stream") == []  # No partly copied per-course posts.
    first, second = work("s0").posts(ids[0]), work("second").posts(ids[1])
    assert len(first) == len(second) == 1
    assert first[0]["id"] != second[0]["id"]
    assert first[0]["course_id"] == ids[0] and second[0]["course_id"] == ids[1]
    assert work("third").posts(ids[2]) == []
    for row in (first[0], second[0]):
        assert not {"target_course_ids", "target_class_names", "request_id", "audit",
                    "distribution_id", "distribution_class"} & row.keys()


def test_all_is_an_explicit_creation_time_snapshot_and_does_not_reach_new_courses():
    _, _, teacher, ids, work = boards()
    distribute(work("teacher"), ids)
    extra = teacher.create_course("새 수업", "2026-2", "수학", class_name="1-1", student_ids=["s0"])
    assert len(work("s0").posts(ids[0])) == 1
    assert work("s0").posts(extra["id"]) == []


def test_retries_normalize_duplicate_targets_and_never_restore_individually_withdrawn_copy():
    store, _, _, ids, work = boards()
    teacher = work("teacher")
    first = distribute(teacher, [ids[1], ids[0], ids[1]])
    post = teacher.posts(ids[0])[0]
    teacher.save_post(ids[0], "개별 회수", "다른 학급 내용은 보존", post_id=post["id"], published=False)
    before = copy.deepcopy(store._records)
    assert distribute(teacher, ids[:2]) == first
    assert store._records == before
    assert work("s0").posts(ids[0]) == []
    assert work("second").posts(ids[1])[0]["title"] == "여러 학급 공지"


@pytest.mark.parametrize("changed", [dict(title="다른 제목"), dict(body="다른 내용"),
                                     dict(pinned=True), dict(comments_allowed=False), dict(published=False)])
def test_same_request_rejects_different_payload_without_mutating_existing_notice(changed):
    store, _, _, ids, work = boards()
    distribute(work("teacher"), ids[:2])
    before = copy.deepcopy(store._records)
    with pytest.raises(ValidationError, match="같은 작업 번호"):
        distribute(work("teacher"), ids[:2], **changed)
    assert store._records == before


def test_same_request_rejects_changed_targets_and_other_teachers_have_separate_request_ids():
    store, _, _, ids, work = boards()
    distribute(work("teacher"), ids[:2])
    with pytest.raises(ValidationError):
        distribute(work("teacher"), ids)
    # A co-teacher has authority on the first course only, and their work token
    # must not collide with the original teacher's token.
    distribute(work("shared"), [ids[0]])
    assert len(store.list("stream_distributions")) == 2
    assert len(work("s0").posts(ids[0])) == 2


@pytest.mark.parametrize("invalid", [None, "all", {}, [], [None], [True], [""], [" "], ["x" * 301], ["x"] * 501])
def test_invalid_targets_are_rejected_before_any_write(invalid):
    store, _, _, _, work = boards()
    before = copy.deepcopy(store._records)
    with pytest.raises(ValidationError):
        distribute(work("teacher"), invalid)
    assert store._records == before


@pytest.mark.parametrize("actor", ["s0", "stranger", "shared"])
def test_student_unassigned_teacher_or_partial_teacher_cannot_publish_to_target_set(actor):
    store, _, _, ids, work = boards()
    before = copy.deepcopy(store._records)
    with pytest.raises(PermissionDenied):
        distribute(work(actor), ids[:2])
    assert store._records == before


@pytest.mark.parametrize("invalid_kind", ["archived", "unassigned", "blank_class", "missing"])
def test_one_invalid_target_prevents_publication_to_every_target(invalid_kind):
    store, _, teacher, ids, work = boards()
    if invalid_kind == "archived":
        teacher.archive_course(ids[1], teacher.get_course(ids[1])["version"])
    elif invalid_kind == "unassigned":
        foreign = ClassroomService(store, dict(id="stranger"), work("teacher").service._lookup,
                                   lock_checker=lambda _: False)
        ids[1] = foreign.create_course("별도 교사", "2026-2", "수학", class_name="1-2")["id"]
    elif invalid_kind == "blank_class":
        ids[1] = teacher.create_course("미지정", "2026-2", "수학")["id"]
    else:
        ids[1] = "no-such-course"
    before = copy.deepcopy(store._records)
    with pytest.raises((ArchivedError, PermissionDenied, ValidationError)):
        distribute(work("teacher"), ids[:2])
    assert store._records == before
    assert work("s0").posts(ids[0]) == []


def test_foreign_projection_id_cannot_be_retargeted_even_by_teacher_of_both_courses():
    store, _, _, ids, work = boards()
    distribute(work("teacher"), ids[:2])
    first = work("teacher").posts(ids[0])[0]
    before = copy.deepcopy(store._records)
    for actor in ("teacher", "second"):
        with pytest.raises(PermissionDenied):
            work(actor).add_comment(ids[1], first["id"], "다른 반 댓글", "wrong-board")
        with pytest.raises(PermissionDenied):
            work(actor).save_post(ids[1], "다른 반으로 이동", "금지", post_id=first["id"], published=True)
    assert store._records == before


def test_comments_and_teacher_edits_are_independent_and_retryable_per_class():
    store, _, _, ids, work = boards()
    distribute(work("teacher"), ids[:2])
    first = work("s0").posts(ids[0])[0]
    second = work("second").posts(ids[1])[0]
    comment = work("s0").add_comment(ids[0], first["id"], "우리 반 댓글", "comment-1")
    assert "distribution_id" not in comment
    work("s0").add_comment(ids[0], first["id"], "우리 반 댓글", "comment-1")
    assert len(work("s1").posts(ids[0])[0]["comments"]) == 1
    assert work("second").posts(ids[1])[0]["comments"] == []
    work("shared").save_post(ids[0], "우리 반만 수정", "학급별 안내", post_id=first["id"], published=True)
    assert work("s0").posts(ids[0])[0]["title"] == "우리 반만 수정"
    assert work("second").posts(ids[1])[0]["title"] == second["title"]
    assert len(store.list("stream")) == 1


@pytest.mark.parametrize("with_override", [False, True])
def test_reassigning_course_class_never_releases_old_distribution_to_new_class(with_override):
    store, _, teacher, ids, work = boards()
    receipt = distribute(work("teacher"), ids[:2])
    post = work("s0").posts(ids[0])[0]
    if with_override:
        work("s0").add_comment(ids[0], post["id"], "이전 반 댓글", "before-reassignment")
    change_course(teacher, ids[0], class_name="1-2")
    current = teacher.get_course(ids[0])
    current["student_ids"].append("second")
    teacher._write("courses", ids[0], current, current["version"], "membership.test")
    assert work("second").posts(ids[0]) == []
    with pytest.raises(PermissionDenied):
        work("second").add_comment(ids[0], post["id"], "변경된 반", "after-reassignment")
    # Retry cannot change the old snapshot to the newly assigned class.
    assert distribute(work("teacher"), ids[:2]) == receipt
    assert work("second").posts(ids[0]) == []
    assert work("second").posts(ids[1])
    saved = store.get("stream_distributions", receipt["distribution_id"])
    assert saved["target_class_names"][ids[0]] == "1-1"


@pytest.mark.parametrize("restriction", ["comments", "archived", "class_change", "membership", "teacher_role"])
def test_current_role_class_membership_and_comment_policy_are_rechecked(restriction):
    store, users, teacher, ids, work = boards()
    distribute(work("teacher"), ids[:2])
    student = work("s0")
    post = student.posts(ids[0])[0]
    if restriction == "comments":
        change_course(teacher, ids[0], comments_enabled=False)
    elif restriction == "archived":
        teacher.archive_course(ids[0], teacher.get_course(ids[0])["version"])
    elif restriction == "class_change":
        users["s0"]["class"] = "1-2"
    elif restriction == "membership":
        current = teacher.get_course(ids[0])
        current["student_ids"].remove("s0")
        teacher._write("courses", ids[0], current, current["version"], "membership.test")
    else:
        users["s0"]["role"] = "teacher"
    before = copy.deepcopy(store._records)
    with pytest.raises((ArchivedError, PermissionDenied)):
        student.add_comment(ids[0], post["id"], "저장 금지", "revalidate")
    assert store._records == before


def test_drafts_schedules_and_disabled_comments_keep_existing_publication_rules():
    _, _, _, ids, work = boards()
    distribute(work("teacher"), ids[:2], "draft", published=False)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    distribute(work("teacher"), ids[:2], "scheduled", publish_at=future)
    distribute(work("teacher"), ids[:2], "no-comments", comments_allowed=False)
    assert len(work("teacher").posts(ids[0])) == 3
    posts = work("s0").posts(ids[0])
    assert len(posts) == 1 and not posts[0]["comments_allowed"]
    for row in work("teacher").posts(ids[0]):
        with pytest.raises(PermissionDenied):
            work("s0").add_comment(ids[0], row["id"], "금지된 댓글", "not-open")


def test_concurrent_first_comments_and_identical_distributions_never_lose_comments_or_duplicate():
    store, _, _, ids, work = boards()
    with ThreadPoolExecutor(max_workers=5) as pool:
        receipts = list(pool.map(lambda _: distribute(work("teacher"), ids[:2]), range(5)))
    assert receipts == [receipts[0]] * 5
    assert len(store.list("stream_distributions")) == 1
    post = work("s0").posts(ids[0])[0]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda i: work(f"s{i}").add_comment(ids[0], post["id"], f"학생 {i} 댓글", "first"), range(3)))
    assert len(work("s0").posts(ids[0])[0]["comments"]) == 3
    assert len(store.list("stream")) == 1
    assert work("second").posts(ids[1])[0]["comments"] == []


def test_failed_atomic_github_save_publishes_no_partial_board_then_lost_response_retry_is_idempotent():
    remote = MockGitHub()
    store = GitHubStore("school/data", "main", "test-token", session=remote)
    _, _, _, ids, work = boards(store)
    remote.fail = True
    with pytest.raises(StorageError):
        distribute(work("teacher"), ids[:2])
    assert not any("/stream_distributions/" in path or "/stream/" in path for path in remote.files)
    assert work("s0").posts(ids[0]) == work("second").posts(ids[1]) == []
    remote.fail = False
    remote.ambiguous_once = True
    first = distribute(work("teacher"), ids[:2])
    assert distribute(work("teacher"), ids[:2]) == first
    assert len([path for path in remote.files if "/stream_distributions/" in path]) == 1
    assert len(work("s0").posts(ids[0])) == len(work("second").posts(ids[1])) == 1


def test_other_workers_discover_atomic_distribution_and_fresh_class_scoped_overrides():
    remote = MockGitHub()
    writer = GitHubStore("school/data", "main", "test-token", session=remote)
    _, users, _, ids, work = boards(writer)
    reader = GitHubStore("school/data", "main", "test-token", session=remote)
    student = WorkService(ClassroomService(reader, users["s0"], users.get, lock_checker=lambda _: False))
    assert student.posts(ids[0]) == []
    distribute(work("teacher"), ids[:2])
    post = student.posts(ids[0])[0]
    work("teacher").save_post(ids[0], "이 학급만 회수", "공개하지 않음", post_id=post["id"], published=False)
    assert student.posts(ids[0]) == []
    assert len(work("second").posts(ids[1])) == 1
