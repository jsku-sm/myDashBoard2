"""Announcement boards stay bound to the selected course, across workers."""
from datetime import datetime, timedelta, timezone

import pytest

from classroom_core import ClassroomService, GitHubStore, PermissionDenied
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub, environment


def _boards(store=None):
    store, users, teacher, first_id, work = environment(store)
    users["s3"] = dict(id="s3", role="student", name="다른 반 학생", **{"class": "1-2"})
    # Identical titles must never merge the two classes' announcements.
    second = teacher.create_course("수학", "2026-2", "수학", class_name="1-2", student_ids=["s3"])
    return store, users, teacher, first_id, second["id"], work


def test_same_teacher_and_title_keep_each_class_announcement_board_separate():
    _, _, teacher, first_id, second_id, work = _boards()
    first = work("teacher").save_post(first_id, "1-1 공지", "첫 번째 학급만", published=True)
    second = work("teacher").save_post(second_id, "1-2 공지", "두 번째 학급만", published=True)
    for actor, course_id, expected in (("teacher", first_id, first["id"]),
                                       ("teacher", second_id, second["id"]),
                                       ("s0", first_id, first["id"]),
                                       ("s3", second_id, second["id"])):
        assert [post["id"] for post in work(actor).posts(course_id)] == [expected]
    # A separate course for the same class still owns an independent board.
    extra = teacher.create_course("수학", "2026-2", "수학", class_name="1-1", student_ids=["s0"])
    assert work("teacher").posts(extra["id"]) == []
    assert work("s0").posts(extra["id"]) == []


@pytest.mark.parametrize("actor", ["teacher", "s3"])
def test_other_class_post_id_cannot_comment_on_or_retarget_announcement(actor):
    store, _, _, first_id, second_id, work = _boards()
    post = work("teacher").save_post(first_id, "1-1 공지", "원본 보존", published=True)
    before = store.get("stream", post["id"])
    with pytest.raises(PermissionDenied):
        work(actor).add_comment(second_id, post["id"], "다른 반에서 댓글", "cross-class-comment")
    with pytest.raises(PermissionDenied):
        work(actor).save_post(second_id, "다른 반으로 옮기기", "변경", post_id=post["id"], published=True)
    assert store.get("stream", post["id"]) == before
    assert work("teacher").posts(second_id) == []


def test_student_class_change_and_revoked_membership_immediately_hide_cached_announcements():
    _, users, teacher, first_id, second_id, work = _boards()
    post = work("teacher").save_post(first_id, "1-1 공지", "학급 비공개 내용", published=True)
    student = work("s0")
    assert [row["id"] for row in student.posts(first_id)] == [post["id"]]
    with pytest.raises(PermissionDenied):
        student.posts(second_id)
    users["s0"]["class"] = "1-2"
    for action in (lambda: student.posts(first_id),
                   lambda: student.add_comment(first_id, post["id"], "이동 후 댓글", "class-changed")):
        with pytest.raises(PermissionDenied):
            action()
    users["s0"]["class"] = "1-1"
    current = teacher.get_course(first_id)
    current["student_ids"].remove("s0")
    teacher._write("courses", first_id, current, current["version"], "membership.revoke")
    with pytest.raises(PermissionDenied):
        student.posts(first_id)


def test_draft_and_scheduled_announcements_never_enter_student_board_or_allow_comments():
    store, _, _, first_id, _, work = _boards()
    draft = work("teacher").save_post(first_id, "비공개 초안", "아직 교사만")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    scheduled = work("teacher").save_post(first_id, "예약 공지", "공개 전", published=True, publish_at=future)
    assert {row["id"] for row in work("teacher").posts(first_id)} == {draft["id"], scheduled["id"]}
    assert work("s0").posts(first_id) == []
    for post in (draft, scheduled):
        before = store.get("stream", post["id"])
        with pytest.raises(PermissionDenied):
            work("s0").add_comment(first_id, post["id"], "숨겨진 글의 댓글", "not-yet-public")
        assert store.get("stream", post["id"]) == before


def test_new_announcements_from_another_worker_are_immediately_visible_only_on_their_board():
    remote = MockGitHub()
    writer = GitHubStore("school/data", "main", "test-token", session=remote)
    _, users, _, first_id, second_id, work = _boards(writer)
    reader = GitHubStore("school/data", "main", "test-token", session=remote)
    student = WorkService(ClassroomService(reader, users["s0"], users.get, lock_checker=lambda _: False))
    assert student.posts(first_id) == []  # This worker has cached the pre-post tree.
    work("teacher").save_post(second_id, "다른 학급 공지", "다른 게시판", published=True)
    work("teacher").save_post(first_id, "비공개 초안", "교사만")
    published = work("teacher").save_post(first_id, "방금 작성한 우리 반 공지", "공개 본문", published=True)
    assert [row["id"] for row in student.posts(first_id)] == [published["id"]]


def test_other_worker_withdrawing_or_moving_post_cannot_leave_stale_cross_class_content():
    remote = MockGitHub()
    writer = GitHubStore("school/data", "main", "test-token", session=remote)
    _, users, _, first_id, second_id, work = _boards(writer)
    post = work("teacher").save_post(first_id, "처음 공개", "본문", published=True)
    reader = GitHubStore("school/data", "main", "test-token", session=remote)
    student = WorkService(ClassroomService(reader, users["s0"], users.get, lock_checker=lambda _: False))
    assert student.posts(first_id)
    work("teacher").save_post(first_id, "비공개로 회수", "본문", post_id=post["id"])
    assert student.posts(first_id) == []
    # Even a stored record whose course scope changes cannot leak through the
    # reader's previously discovered ID/body. No operating data is changed here.
    current = writer.get("stream", post["id"], fresh=True)
    writer.put("stream", post["id"], dict(current, course_id=second_id, published=True), current["version"])
    assert student.posts(first_id) == []
    with pytest.raises(PermissionDenied):
        student.add_comment(first_id, post["id"], "이전 게시판 댓글", "scope-changed")
    assert [row["id"] for row in work("s3").posts(second_id)] == [post["id"]]
