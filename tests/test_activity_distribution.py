"""Explicit publication, Korean calendar dates and shared assessment clocks."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta
import io
from types import SimpleNamespace

from PIL import Image
from pypdf import PdfWriter
import pytest

import think_app.classroom as backend
from think_app.classroom import Classroom, STATUSES
from think_app.courses import CourseManager
from think_app.storage import AppError, MemoryStore
from think_app.uploads import UploadedFiles


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


@pytest.mark.parametrize("require_visible,rerun_count", [(True, 1), (False, 0)])
def test_first_timer_render_rechecks_visibility_without_rerunning_teacher_preview(assessment, monkeypatch, require_visible, rerun_count):
    from think_app import timer_ui

    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=5)
    room.distribute_activity(aid)
    rendered_task = room.activity(aid)
    assert room.student_activity_available(rendered_task)
    # The teacher ends the task between the parent screen's visibility guard
    # and the fragment's first read, before it has any previous state.
    room.end_timer(aid)
    reruns = []
    monkeypatch.setattr(timer_ui, "st", SimpleNamespace(
        session_state={}, rerun=lambda **kwargs: reruns.append(kwargs)))
    monkeypatch.setattr(timer_ui, "_timer_view", lambda *args: None)
    if require_visible:
        timer_ui.student_timer.__wrapped__(room, aid, require_visible=True)
    else:
        timer_ui.student_timer.__wrapped__(room, aid)
        timer_ui.student_timer.__wrapped__(room, aid)
    assert reruns == [{"scope": "app"}] * rerun_count


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


def test_explicit_end_saves_remaining_time_and_resume_preserves_original_clock(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    published = room.distribute_activity(aid)
    instant[0] = "2026-10-14T09:03:15+09:00"
    room.end_timer(aid)
    ended = room.activity(aid)
    assert ended["timer_remaining_seconds_at_end"] == 405
    assert room.timer_resume_minutes(ended) == 7
    instant[0] = "2026-10-14T10:00:00+09:00"
    room.end_timer(aid)
    assert room.activity(aid) == ended
    resumed = room.resume_timer(aid)
    assert resumed["status"] == "진행 중" and resumed["timer_ended_at"] is None
    assert resumed["duration_minutes"] == 10
    assert resumed["distributed_at"] == published["distributed_at"]
    assert resumed["timer_started_at"] == published["timer_started_at"]
    assert datetime.fromisoformat(resumed["timer_deadline"]) == datetime.fromisoformat(resumed["timer_resumed_at"]) + timedelta(minutes=7)
    assert room.timer_state(resumed)["remaining_seconds"] == 420
    assert room.student_activity_available(resumed) and room._can_submit(resumed)
    assert room.student_unavailable_notice(resumed) != "선생님이 평가를 종료했습니다."


def test_multiple_end_resume_cycles_and_natural_expiry_choose_current_defaults(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    instant[0] = "2026-10-14T09:01:00+09:00"
    room.end_timer(aid)
    room.resume_timer(aid, 3)
    instant[0] = "2026-10-14T09:02:30+09:00"
    room.end_timer(aid)
    assert room.activity(aid)["timer_remaining_seconds_at_end"] == 90
    assert room.timer_resume_minutes(room.activity(aid)) == 2
    room.resume_timer(aid)
    instant[0] = "2026-10-14T09:04:30+09:00"
    assert room.timer_state(room.activity(aid))["phase"] == "expired"
    assert room.timer_resume_minutes(room.activity(aid)) == 10
    room.resume_timer(aid)
    assert room.timer_state(room.activity(aid))["remaining_seconds"] == 600
    instant[0] = "2026-10-14T09:14:30+09:00"
    room.end_timer(aid)
    assert room.activity(aid)["timer_remaining_seconds_at_end"] == 0
    assert room.timer_resume_minutes(room.activity(aid)) == 10


def test_end_with_less_than_one_second_remaining_uses_original_duration_default(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    instant[0] = "2026-10-14T09:09:59.500000+09:00"
    room.end_timer(aid)
    assert room.activity(aid)["timer_remaining_seconds_at_end"] == 0.5
    assert room.timer_resume_minutes(room.activity(aid)) == 10


@pytest.mark.parametrize("saved_seconds", [None, 0, 0.5])
def test_legacy_end_records_fall_back_to_original_duration(assessment, saved_seconds):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=8)
    room.distribute_activity(aid)
    room.end_timer(aid)

    def legacy(state):
        task = state["course_activities"][aid]
        task.pop("distribution_required")
        task.pop("distributed_at")
        if saved_seconds is None:
            task.pop("timer_remaining_seconds_at_end")
        else:
            task["timer_remaining_seconds_at_end"] = saved_seconds

    room.store.transaction(legacy)
    assert room.timer_resume_minutes(room.activity(aid)) == 8
    resumed = room.resume_timer(aid)
    assert room.student_activity_available(resumed)
    assert room.timer_state(resumed)["remaining_seconds"] == 480
    assert "distributed_at" not in resumed


@pytest.mark.parametrize("clock_value,start,end,expected_start,expected_end", [
    ("2026-10-15T09:00:00+09:00", "2026-10-14", "2026-10-14", "2026-10-14", "2026-10-15"),
    ("2026-10-15T09:00:00+09:00", "2026-10-16", "2026-10-18", "2026-10-15", "2026-10-18"),
    ("2026-10-15T09:00:00+09:00", "2026-10-14", None, "2026-10-14", None),
    ("2026-10-14T15:00:00+00:00", "2026-10-14", "2026-10-14", "2026-10-14", "2026-10-15"),
    ("2026-10-14T14:59:59+00:00", "2026-10-14", "2026-10-14", "2026-10-14", "2026-10-15"),
])
def test_resume_extends_dates_to_include_korean_today(assessment, clock_value, start, end, expected_start, expected_end):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    original = room.distribute_activity(aid)
    room.end_timer(aid)
    task = room.activity(aid)
    save_activity(room, cid, aid=aid, start=start, end=end, duration_minutes=task["duration_minutes"])
    instant[0] = clock_value
    resumed = room.resume_timer(aid, 4)
    assert resumed["start"] == expected_start and resumed["end"] == expected_end
    assert resumed["distributed_at"] == original["distributed_at"]
    assert room.student_activity_available(resumed) and room._can_submit(resumed)


def test_resuming_a_published_hidden_activity_reopens_it_and_keeps_content(assessment):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    room.end_timer(aid)
    room.set_status(aid, "숨김")
    hidden = room.activity(aid)
    resumed = room.resume_timer(aid, 3)
    assert resumed["status"] == "진행 중" and room.student_activity_available(resumed)
    for field in ("prompt", "expected", "criteria", "question_files", "curriculum", "max_attempts", "duration_minutes"):
        assert resumed[field] == hidden[field]


def test_resume_after_late_night_end_keeps_period_open_until_next_day_deadline(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=15)
    instant[0] = "2026-10-14T23:40:00+09:00"
    room.distribute_activity(aid)
    instant[0] = "2026-10-14T23:50:00+09:00"
    room.end_timer(aid)
    resumed = room.resume_timer(aid, 30)
    assert resumed["start"] == "2026-10-14" and resumed["end"] == "2026-10-15"
    assert datetime.fromisoformat(resumed["timer_deadline"]) == datetime.fromisoformat("2026-10-15T00:20:00+09:00")
    instant[0] = "2026-10-15T00:10:00+09:00"
    assert room.student_activity_available(room.activity(aid)) and room._can_submit(room.activity(aid))
    assert room.timer_state(room.activity(aid))["remaining_seconds"] == 600
    submit(room, aid)


def test_resume_retries_and_concurrent_calls_do_not_extend_a_running_deadline(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    room.end_timer(aid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda minutes: room.resume_timer(aid, minutes), [3, 7]))
    assert first == second
    assert room.timer_state(first)["remaining_seconds"] in (180, 420)
    instant[0] = "2026-10-14T09:01:00+09:00"
    assert room.resume_timer(aid, 30) == first


@pytest.mark.parametrize("minutes", [0, -1, 1441, True, "5", 2.5])
def test_invalid_resume_minutes_cannot_change_an_ended_assessment(assessment, minutes):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    room.end_timer(aid)
    ended = room.activity(aid)
    with pytest.raises(AppError, match="1~1440분"):
        room.resume_timer(aid, minutes)
    assert room.activity(aid) == ended


def test_resume_requires_distribution_and_a_stopped_timed_assessment(assessment):
    room, cid, _ = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    with pytest.raises(AppError, match="배포한 활동만"):
        room.resume_timer(aid, 3)
    future = save_activity(room, cid, start="2026-10-15", end="2026-10-16", duration_minutes=10)
    room.distribute_activity(future)
    with pytest.raises(AppError, match="종료되었거나"):
        room.resume_timer(future, 3)
    unlimited = save_activity(room, cid)
    room.distribute_activity(unlimited)
    with pytest.raises(AppError, match="종료되었거나"):
        room.resume_timer(unlimited, 3)
    room.distribute_activity(aid)
    room.end_timer(aid)
    CourseManager(room.store).delete(cid)
    with pytest.raises(AppError, match="수업을 찾을"):
        room.resume_timer(aid, 3)
    with pytest.raises(AppError, match="활동을 찾을"):
        room.resume_timer("f" * 32, 3)


def test_failed_resume_publication_is_atomic(assessment, monkeypatch):
    import think_app.storage as storage_module

    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    room.end_timer(aid)
    instant[0] = "2026-10-15T09:00:00+09:00"
    ended = room.activity(aid)

    def fail_publication(store, previous, state):
        assert state["course_activities"][aid]["timer_ended_at"] is None
        assert state["course_activities"][aid]["end"] == "2026-10-15"
        raise OSError("state publication failed")

    monkeypatch.setattr(storage_module, "_prepare_submissions", fail_publication)
    with pytest.raises(OSError, match="state publication failed"):
        room.resume_timer(aid, 3)
    assert room.activity(aid) == ended


def test_resume_keeps_attempts_pdf_images_snapshots_and_maximum_attempt_count(assessment):
    room, cid, instant = assessment
    aid = save_activity(room, cid, duration_minutes=10)
    room.distribute_activity(aid)
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf)
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(image, "PNG")
    files = UploadedFiles(room.store)
    document = files.save(aid, "1001", "학생", "1반", "풀이.pdf", pdf.getvalue())
    picture = files.save(aid, "1001", "학생", "1반", "풀이.png", image.getvalue())
    request = room.submit(aid, "1001", "학생", "1반", "풀이", [], False, "a" * 32,
                          upload_ids=[document["id"], picture["id"]])
    snapshot = copy.deepcopy(room.store.read()["course_attempts"][request])
    saved_uploads = copy.deepcopy(room.store.read()["course_uploads"])
    blobs = copy.deepcopy(room.store.blobs)
    room.end_timer(aid)
    instant[0] = "2026-10-15T09:00:00+09:00"
    room.resume_timer(aid, 5)
    assert room.store.read()["course_attempts"][request] == snapshot
    assert room.store.read()["course_uploads"] == saved_uploads
    assert room.store.blobs == blobs
    assert room.store.get_student_submission(snapshot)["submission"] == snapshot
    assert room.activity(aid)["max_attempts"] == 2
    second = submit(room, aid, "b" * 32)
    assert room.store.read()["course_attempts"][second]["number"] == 2
    with pytest.raises(AppError, match="최대 시도 횟수"):
        submit(room, aid, "c" * 32)
