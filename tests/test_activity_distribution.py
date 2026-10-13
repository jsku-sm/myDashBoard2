"""Explicit publication, Korean calendar dates and shared assessment clocks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import think_app.classroom as backend
from think_app.classroom import Classroom, STATUSES
from think_app.courses import CourseManager
from think_app.storage import AppError, MemoryStore


@pytest.fixture
def assessment(monkeypatch):
    instant = ["2026-10-14T09:00:00+09:00"]
    monkeypatch.setattr(backend, "now", lambda: instant[0])
    store = MemoryStore()
    manager = CourseManager(store)
    course_id = manager.create("명시 배포 수행평가", "#123456", ["1반"])
    return Classroom(store), course_id, instant


def save_activity(room, course_id, **changes):
    values = dict(title="풀이 평가", prompt="2+2의 값을 구하세요.", expected="4",
                  criteria=["풀이를 근거와 함께 설명한다."], max_attempts=2,
                  start="2026-10-14", end="2026-10-14")
    values.update(changes)
    return room.save_activity(course_id, **values)


def submit(room, aid, request="a" * 32):
    return room.submit(aid, "1001", "학생", "1반", "답은 4입니다.", [], False, request)


def test_saved_activity_requires_distribution_before_any_student_access(assessment):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    task = room.activity(aid)
    assert "배포 전" in STATUSES
    assert task["status"] == "배포 전" and task["distribution_required"] is True
    assert not room.is_distributed(task)
    assert not room.student_activity_available(task) and not room._can_submit(task)
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        submit(room, aid)
    with pytest.raises(AppError, match="배포한 뒤"):
        room.start_timer(aid)
    # Manually changing a status never substitutes for explicit publication.
    for status in ("진행 중", "보기만 가능", "숨김"):
        room.set_status(aid, status)
        assert not room.student_activity_available(room.activity(aid))
    assert not room.store.read().get("course_attempts")


def test_default_desmos_activity_is_also_saved_as_an_unpublished_draft(assessment):
    room, _, _ = assessment
    manager = CourseManager(room.store)
    cid = manager.create("Desmos 수업", "#123456", ["1반"])
    aid = room.ensure_desmos_activity(manager.get(cid))
    assert room.activity(aid)["status"] == "배포 전"
    assert not room.student_activity_available(room.activity(aid))
    room.distribute_activity(aid)
    assert room.student_activity_available(room.activity(aid))


def test_distributing_unlimited_activity_publishes_once_and_permits_submission(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid)
    first = room.distribute_activity(aid)
    assert first["status"] == "진행 중" and first["distributed_at"] == instant[0]
    assert "timer_started_at" not in first
    assert room.student_activity_available(first) and room._can_submit(first)
    submit(room, aid)
    instant[0] = "2026-10-14T09:01:00+09:00"
    room.set_status(aid, "숨김")
    assert room.is_distributed(room.activity(aid))
    second = room.distribute_activity(aid)
    assert second["status"] == "진행 중" and second["distributed_at"] == first["distributed_at"]
    assert room.student_activity_available(second)


def test_publication_starts_one_shared_timer_even_when_distribution_is_retried(assessment, monkeypatch):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    calls = []
    begin = room._begin_timer

    def tracked_begin(task, duration):
        calls.append(duration)
        begin(task, duration)

    monkeypatch.setattr(room, "_begin_timer", tracked_begin)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(room.distribute_activity, [aid, aid]))
    assert calls == [10]
    assert first["distributed_at"] == second["distributed_at"]
    assert first["timer_started_at"] == second["timer_started_at"]
    start = datetime.fromisoformat(first["timer_started_at"])
    assert datetime.fromisoformat(first["timer_deadline"]) == start + timedelta(minutes=10)
    assert room.timer_state(first)["remaining_seconds"] == 600
    instant[0] = "2026-10-14T09:03:00+09:00"
    room.distribute_activity(aid)
    assert room.activity(aid)["timer_deadline"] == first["timer_deadline"]
    assert room.timer_state(room.activity(aid))["remaining_seconds"] == 420


def test_distribution_and_timer_start_roll_back_together_on_failure(assessment, monkeypatch):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    before = room.activity(aid)

    def fail_timer(task, duration):
        raise OSError("timer update failed")

    monkeypatch.setattr(room, "_begin_timer", fail_timer)
    with pytest.raises(OSError, match="timer update failed"):
        room.distribute_activity(aid)
    assert room.activity(aid) == before


def test_future_distribution_waits_for_the_period_and_teacher_timer_start(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, start="2026-10-15", end="2026-10-16", duration_minutes=20)
    scheduled = room.distribute_activity(aid)
    assert room.is_distributed(scheduled) and scheduled["status"] == "진행 중"
    assert room.timer_state(scheduled)["phase"] == "waiting"
    assert not room.student_activity_available(scheduled)
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        submit(room, aid)
    with pytest.raises(AppError, match="시작일·마감일"):
        room.start_timer(aid)
    instant[0] = "2026-10-15T09:00:00+09:00"
    assert room.activity_within_dates(room.activity(aid))
    assert not room.student_activity_available(room.activity(aid))
    room.start_timer(aid)
    assert room.student_activity_available(room.activity(aid))
    assert room.timer_state(room.activity(aid))["remaining_seconds"] == 1200
    submit(room, aid)


def test_korean_date_boundaries_are_inclusive_even_when_clock_is_utc(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid)
    instant[0] = "2026-10-13T14:59:59+00:00"  # October 13, 23:59:59 in Korea.
    room.distribute_activity(aid)
    assert not room.student_activity_available(room.activity(aid))
    instant[0] = "2026-10-13T15:00:00+00:00"
    assert room.student_activity_available(room.activity(aid))
    instant[0] = "2026-10-14T14:59:59+00:00"
    assert room.student_activity_available(room.activity(aid))
    instant[0] = "2026-10-14T15:00:00+00:00"
    assert not room.student_activity_available(room.activity(aid))
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        submit(room, aid)


def test_expired_period_rejects_distribution_without_publishing_partial_state(assessment):
    room, cid, _ = assessment
    aid = save_activity(room, cid, start="2026-10-12", end="2026-10-13", duration_minutes=5)
    before = room.activity(aid)
    with pytest.raises(AppError, match="마감일이 지난 활동"):
        room.distribute_activity(aid)
    assert room.activity(aid) == before
    assert not room.student_activity_available(before)


def test_read_only_is_visible_but_cannot_submit_and_hidden_is_never_visible(assessment):
    room, cid, _ = assessment
    aid = save_activity(room, cid)
    room.distribute_activity(aid)
    room.set_status(aid, "보기만 가능")
    assert room.student_activity_available(room.activity(aid))
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        submit(room, aid)
    room.set_status(aid, "숨김")
    assert not room.student_activity_available(room.activity(aid))


def test_timer_expiry_extension_and_teacher_end_control_student_visibility(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=5)
    room.distribute_activity(aid)
    room.set_status(aid, "보기만 가능")
    instant[0] = "2026-10-14T09:05:00+09:00"
    assert room.timer_state(room.activity(aid))["phase"] == "expired"
    assert not room.student_activity_available(room.activity(aid))
    room.distribute_activity(aid)
    assert room.timer_state(room.activity(aid))["phase"] == "expired"
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        submit(room, aid)
    room.adjust_timer(aid, 3)
    assert room.student_activity_available(room.activity(aid))
    room.end_timer(aid)
    assert not room.student_activity_available(room.activity(aid))
    room.distribute_activity(aid)
    assert room.timer_state(room.activity(aid))["phase"] == "ended"
    assert not room.student_activity_available(room.activity(aid))


def test_student_timer_refreshes_on_read_only_change_and_on_read_only_expiry(assessment, monkeypatch):
    from think_app import timer_ui

    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=5)
    room.distribute_activity(aid)
    reruns = []
    monkeypatch.setattr(timer_ui, "st", SimpleNamespace(
        session_state={}, rerun=lambda **kwargs: reruns.append(kwargs)))
    monkeypatch.setattr(timer_ui, "_timer_view", lambda *args: None)
    timer_ui.student_timer.__wrapped__(room, aid)
    assert reruns == []
    room.set_status(aid, "보기만 가능")
    timer_ui.student_timer.__wrapped__(room, aid)
    assert reruns == [{"scope": "app"}]
    instant[0] = "2026-10-14T09:05:00+09:00"
    timer_ui.student_timer.__wrapped__(room, aid)
    assert reruns == [{"scope": "app"}, {"scope": "app"}]


@pytest.mark.parametrize("status,visible,can_submit", [
    ("진행 중", True, True), ("보기만 가능", True, False), ("숨김", False, False)
])
def test_legacy_activities_do_not_require_a_distribution_timestamp(assessment, status, visible, can_submit):
    room, cid, _ = assessment
    aid = save_activity(room, cid)

    def legacy(state):
        task = state["course_activities"][aid]
        task.pop("distribution_required")
        task["status"] = status

    room.store.transaction(legacy)
    task = room.activity(aid)
    assert "distributed_at" not in task and room.is_distributed(task)
    assert room.student_activity_available(task) is visible
    assert room._can_submit(task) is can_submit
    # Editing a legacy activity keeps its existing publication behavior.
    save_activity(room, cid, aid=aid, title="기존 활동 수정")
    assert room.activity(aid)["status"] == status
    assert room.activity(aid)["distribution_required"] is False
    assert room.student_activity_available(room.activity(aid)) is visible
