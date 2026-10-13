"""Student-safe published score projections and the authenticated score view."""
from collections.abc import Mapping
from datetime import datetime

import streamlit as st

from .classroom import Classroom
from .grading import assessment_score_published, public_score, student_feedback
from .integration import matching_class
from .storage import AppError


_FEEDBACK_FIELDS = ("teacher_comment", "praise", "observation", "hint", "next_question", "uncertainty_reason")


def _text(value):
    return value if isinstance(value, str) else ""


def feedback_text(value):
    """Only feedback written for the student is included in reports."""
    if not isinstance(value, Mapping):
        return ""
    return "\n".join(text for field in _FEEDBACK_FIELDS
                     if (text := _text(value.get(field))).strip())


def _number(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _preview(attempt):
    return attempt.get("preview", False) not in (False, None, "", "0", "false", "False")


def _attempt_projection(attempt):
    row = dict(number=_number(attempt.get("number")), submitted_at=_text(attempt.get("created")),
               status="review" if "assessment_result" in attempt else "waiting")
    if assessment_score_published(attempt):
        result = attempt["assessment_result"]
        row.update(status="published", score=public_score(attempt), max_score=100,
                   feedback=feedback_text(student_feedback(attempt)), published_at=_text(result.get("published_at")))
    return row


def build_student_scores(user, state):
    """Return own score histories for currently enrolled, public activities.

    Assessment dates and timers do not restrict published score access. Draft
    grades, answer keys, raw attempts and other students' identifiers are never
    included in the returned projections.
    """
    if (not isinstance(user, Mapping) or user.get("role") != "student" or
            not _text(user.get("id")).strip() or not _text(user.get("class")).strip() or
            not isinstance(state, Mapping)):
        return []
    courses, activities, attempts = (state.get(key, {}) for key in ("courses", "course_activities", "course_attempts"))
    if not all(isinstance(value, Mapping) for value in (courses, activities, attempts)):
        return []
    rows = []
    for aid, task in activities.items():
        if not isinstance(aid, str) or not isinstance(task, Mapping):
            continue
        cid = task.get("course_id")
        course = courses.get(cid) if isinstance(cid, str) else None
        if not isinstance(course, Mapping):
            continue
        classes = course.get("classes")
        if (not isinstance(classes, (list, tuple)) or not all(isinstance(value, str) for value in classes) or
                course.get("archived") or task.get("status") not in ("진행 중", "보기만 가능") or
                not Classroom.is_distributed(task)):
            continue
        classroom = matching_class(user, course)
        if classroom is None:
            continue
        own = [_attempt_projection(attempt) for attempt in attempts.values()
               if isinstance(attempt, Mapping) and attempt.get("activity_id") == aid and
               attempt.get("course_id") == cid and attempt.get("student_id") == user["id"] and
               attempt.get("class_id") == classroom and not _preview(attempt)]
        own.sort(key=lambda attempt: (attempt["number"], attempt["submitted_at"]), reverse=True)
        latest = next((attempt for attempt in own if attempt["status"] == "published"), None)
        rows.append(dict(course_id=cid, course_title=_text(course.get("title")), activity_id=aid,
                         title=_text(task.get("title")), attempts=own, latest_published=latest,
                         status="published" if latest else own[0]["status"] if own else "not_submitted"))
    return sorted(rows, key=lambda row: (row["course_title"], row["title"], row["activity_id"]))


def _current_student(user):
    """Resolve the current account before every report refresh, including polls."""
    import auth
    import storage as db

    if not isinstance(user, Mapping) or user.get("role") != "student" or not _text(user.get("id")).strip():
        raise AppError("학생 계정으로 로그인하면 내 점수를 확인할 수 있습니다.")
    db.invalidate("users")
    current = auth.get_user(user["id"])
    if (not isinstance(current, Mapping) or current.get("id") != user["id"] or
            current.get("role") != "student" or not _text(current.get("class")).strip() or
            not _text(current.get("name")).strip() or current.get("must_change") == "1"):
        raise AppError("로그인한 학생 정보를 다시 확인해 주세요.")
    return current


def _date(value):
    from config import TZ

    try:
        instant = datetime.fromisoformat(value)
        instant = instant.replace(tzinfo=TZ) if instant.tzinfo is None else instant.astimezone(TZ)
        return instant.strftime("%m.%d %H:%M")
    except (TypeError, ValueError):
        return ""


def _show_attempt(attempt):
    st.caption(f"{attempt['number']}차 제출 · {_date(attempt['submitted_at'])}")
    if attempt["status"] == "published":
        st.write(f"{attempt['score']:g} / 100점")
        if attempt["feedback"]:
            st.write(attempt["feedback"])
    else:
        st.write("선생님 검토 중" if attempt["status"] == "review" else "채점 대기")


@st.fragment(run_every="10s")
def render_student_scores(store, user):
    """Render freshly authorized published scores without opening an editor."""
    try:
        current = _current_student(user)
        reports = build_student_scores(current, store.read())
    except AppError as error:
        st.error(str(error))
        return
    st.title("내 점수 확인하기")
    st.caption("선생님이 공개한 점수와 피드백을 확인하세요. 평가가 끝난 뒤에도 볼 수 있어요.")
    if not reports:
        st.info("아직 우리 반에 배포된 수행평가가 없습니다.")
        return
    for report in reports:
        with st.container(border=True):
            st.subheader(report["title"])
            st.caption(report["course_title"])
            latest = report["latest_published"]
            if latest:
                st.caption(f"최근 공개 점수 · {latest['number']}차 제출")
                st.metric("점수", f"{latest['score']:g} / 100")
                if published_at := _date(latest["published_at"]):
                    st.caption("공개 · " + published_at)
                if latest["feedback"]:
                    st.write(latest["feedback"])
                if report["attempts"][0]["status"] != "published":
                    _show_attempt(report["attempts"][0])
            elif report["attempts"]:
                _show_attempt(report["attempts"][0])
            else:
                st.write("아직 제출하지 않았어요.")
            if len(report["attempts"]) > 1:
                with st.expander("제출 회차별 점수·피드백"):
                    for attempt in report["attempts"]:
                        _show_attempt(attempt)
