"""Shared assessment timer controls; only the timer refreshes every two seconds."""
import math

import streamlit as st

from .storage import AppError


def _timer_view(room, task):
    timer = room.timer_state(task)
    phase = timer["phase"]
    if phase == "unlimited":
        st.caption("풀이 시간 · 시간 제한 없음")
    elif phase == "waiting":
        st.info(f"평가 시작 대기 · 풀이 시간 {timer['duration_minutes']}분")
        st.caption("선생님이 평가를 시작하면 모든 학생에게 같은 타이머가 표시됩니다.")
    else:
        seconds = timer["remaining_seconds"]
        minutes, seconds = divmod(seconds, 60)
        st.metric("남은 풀이 시간", f"{minutes:02d}:{seconds:02d}")
        if phase == "ended":
            st.warning("선생님이 평가를 종료했습니다.")
        elif phase == "expired":
            st.warning("풀이 시간이 끝났습니다. 선생님이 시간을 늘리면 다시 제출할 수 있습니다.")
        else:
            st.caption("교사가 조정한 시간이 자동으로 반영됩니다.")
    return timer


@st.fragment(run_every="2s")
def student_timer(room, aid, *, require_visible=False):
    task = room.activity(aid)
    availability = room._can_submit(task)
    visibility = room.student_activity_available(task)
    state_key = "timer_submission_available_" + aid
    visibility_key = "timer_student_activity_available_" + aid
    previous = st.session_state.get(state_key)
    previous_visibility = st.session_state.get(visibility_key)
    st.session_state[state_key] = availability
    st.session_state[visibility_key] = visibility
    _timer_view(room, task)
    if ((require_visible and not visibility) or
            (previous is not None and previous != availability) or
            (previous_visibility is not None and previous_visibility != visibility)):
        # Recheck the submission button on start, expiry, or extension. Editor
        # widget keys stay unchanged and ordinary countdown ticks stay isolated.
        st.rerun(scope="app")


@st.fragment(run_every="2s")
def student_availability_watch(room, course_id=None, aid=None, *, closed=False):
    """Refresh a closed student screen when its assessment is reopened."""
    state = room.store.read()
    courses = state.get("courses", {})
    course_ids = [course_id] if course_id is not None else sorted(courses)
    watched_courses = set(course_ids)
    signature = (
        tuple((cid, tuple(courses.get(cid, {}).get("classes", []))) for cid in course_ids),
        tuple(sorted((task["id"], room.student_activity_available(task), task.get("status"),
                      task.get("timer_ended_at"), task.get("timer_resumed_at"))
                     for task in state.get("course_activities", {}).values()
                     if task.get("course_id") in watched_courses and (aid is None or task["id"] == aid))),
    )
    key = "student_availability_watch_" + (course_id or "all") + "_" + (aid or "all")
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    st.empty()
    reopened = closed and any(task[1] for task in signature[1])
    if reopened or (previous is not None and previous != signature):
        st.rerun(scope="app")


def _teacher_timer_changed(room, aid, message):
    st.session_state["timer_teacher_notice_" + aid] = message
    task = room.activity(aid)
    st.session_state["timer_submission_available_" + aid] = room._can_submit(task)
    st.session_state["timer_student_activity_available_" + aid] = room.student_activity_available(task)
    st.rerun(scope="app")


@st.fragment(run_every="2s")
def teacher_timer_controls(room, task):
    task = room.activity(task["id"])
    aid = task["id"]
    timer = room.timer_state(task)
    with st.expander("수행평가 타이머", expanded=timer["phase"] != "unlimited"):
        notice = st.session_state.pop("timer_teacher_notice_" + aid, None)
        if notice:
            st.success(notice)
        if timer["phase"] in ("unlimited", "waiting"):
            duration = st.number_input("평가 풀이 시간(분)", min_value=1, max_value=1440,
                                       value=timer["duration_minutes"] or 30,
                                       key="timer_distribution_minutes_" + aid + str(timer["duration_minutes"]),
                                       help="배포된 활동에서 평가 시작을 누르면 모든 학생의 타이머가 시작됩니다.")
            if not room.is_distributed(task):
                st.caption("학생에게 배포하면 설정한 풀이 시간으로 평가 타이머가 시작됩니다.")
            if st.button("평가 시작", type="primary", key="timer_start_" + aid,
                         disabled=not room._within_submission_period(task)):
                try:
                    room.start_timer(aid, int(duration))
                    _teacher_timer_changed(room, aid, "평가가 시작되었습니다. 학생 화면에 타이머가 표시됩니다.")
                except AppError as error:
                    st.error(str(error))
        elif timer["phase"] == "ended":
            version = task.get("timer_ended_at", "")
            remaining = st.number_input("재개 후 풀이 시간(분)", min_value=1, max_value=1440,
                                        value=room.timer_resume_minutes(task),
                                        key="timer_resume_minutes_" + aid + version,
                                        help="종료 전에 남았던 시간을 기본으로 표시합니다. 재개하면 지금부터 이 시간만큼 풀 수 있습니다.")
            if not room.activity_within_dates(task):
                st.caption("평가를 재개하면 시작일·마감일이 오늘을 포함하도록 조정됩니다.")
            if st.button("평가 재개", type="primary", key="timer_resume_" + aid,
                         disabled=not room.is_distributed(task)):
                try:
                    room.resume_timer(aid, int(remaining))
                    _teacher_timer_changed(room, aid, "평가를 재개했습니다. 학생이 다시 답안을 작성할 수 있습니다.")
                except AppError as error:
                    st.error(str(error))
        else:
            # The deadline changes only after teacher actions, so countdown
            # refreshes never overwrite a teacher's input.
            version = task.get("timer_deadline", "")
            remaining = st.number_input("남은 풀이 시간(분)", min_value=0, max_value=1440,
                                        value=max(1, math.ceil(timer["remaining_seconds"] / 60)),
                                        key="timer_minutes_" + aid + version,
                                        help="지금부터 남은 시간을 설정합니다. 0분이면 즉시 시간이 종료됩니다.")
            left, right = st.columns(2)
            if left.button("남은 시간 적용", key="timer_adjust_" + aid):
                try:
                    room.adjust_timer(aid, int(remaining))
                    _teacher_timer_changed(room, aid, "학생 타이머에 조정한 시간이 반영되었습니다.")
                except AppError as error:
                    st.error(str(error))
            if right.button("평가 종료", key="timer_end_" + aid):
                try:
                    room.end_timer(aid)
                    _teacher_timer_changed(room, aid, "평가를 종료했습니다. 학생 화면에 종료 안내가 표시됩니다.")
                except AppError as error:
                    st.error(str(error))
        _timer_view(room, room.activity(aid))
