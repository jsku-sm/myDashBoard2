"""Build student-home updates without reading storage or rendering UI.

Every returned row is a fresh, student-facing projection. Assessment answer
keys, activity snapshots, attachments and other students' records stay out of
the result even when callers supply the complete teacher-side state.
"""
from collections.abc import Mapping
from datetime import date, datetime
import json

from config import CLASSES, SUBJECTS, TZ
from think_app.classroom import Classroom
from think_app.integration import matching_class
from think_app.grading import assessment_score_published, student_feedback


def _text(value):
    return value if isinstance(value, str) else ""


def _rows(values):
    if isinstance(values, Mapping):
        values = values.values()
    if values is None or isinstance(values, (str, bytes)):
        return []
    try:
        return [row for row in values if isinstance(row, Mapping)]
    except TypeError:
        return []


def _instant(value):
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        try:
            instant = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return instant.replace(tzinfo=TZ) if instant.tzinfo is None else instant.astimezone(TZ)


def _updated(row, *fields):
    candidates = [(_instant(row.get(field)), _text(row.get(field))) for field in fields]
    valid = [(instant, value) for instant, value in candidates if instant is not None]
    return max(valid, key=lambda entry: entry[0])[1] if valid else ""


def _newest(rows, field="updated_at"):
    minimum = datetime.min.replace(tzinfo=TZ)
    return sorted(rows, key=lambda row: (_instant(row.get(field)) or minimum,
                                        _instant(row.get("created_at")) or minimum,
                                        row.get("id", "")), reverse=True)


def _integer(value, default=0):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default


def _is_preview(row):
    value = row.get("preview", False)
    return value not in (False, None, "", "0", "false", "False")


def _student_feedback(value):
    if not isinstance(value, Mapping):
        return ""
    return "\n".join(text for field in ("praise", "observation", "hint", "next_question", "uncertainty_reason")
                     if (text := _text(value.get(field))).strip())


def _feedback_row(row, source, title, updated_at):
    comment = _text(row.get("teacher_comment"))
    answer = _text(row.get("answer")) if source == "question" else ""
    safe_feedback = student_feedback(row) if source == "assessment" else None
    if source == "assessment" and "assessment_result" in row:
        comment = _text(safe_feedback.get("teacher_comment")) if isinstance(safe_feedback, Mapping) else ""
    feedback_text = _student_feedback(safe_feedback) if source == "assessment" else ""
    return dict(id=_text(row.get("id")), source=source, title=title,
                subject=_text(row.get("subject")), unit=_text(row.get("unit")),
                updated_at=updated_at, teacher_comment=comment, answer=answer,
                student_feedback=feedback_text, content=comment or answer or feedback_text,
                course_id="", course_title="", activity_id="")


def _phase(task, instant):
    duration = _integer(task.get("duration_minutes"))
    if not duration:
        return "unlimited"
    if task.get("timer_ended_at"):
        return "ended"
    if not task.get("timer_started_at"):
        return "waiting"
    value = task.get("timer_deadline")
    try:
        deadline = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        deadline = None
    # Shared timer deadlines must identify an instant, unlike naive CSV dates.
    if deadline is not None and deadline.tzinfo is None:
        deadline = None
    return "running" if deadline is not None and deadline > instant else "expired"


def _period(task, today):
    try:
        start = date.fromisoformat(task.get("start", ""))
        end = date.fromisoformat(task["end"]) if task.get("end") else None
    except (TypeError, ValueError):
        return "invalid"
    if end is not None and end < start:
        return "invalid"
    if today < start:
        return "scheduled"
    if end is not None and today > end:
        return "closed"
    return "current"


def _public_activities(user, state):
    courses = state.get("courses", {})
    activities = state.get("course_activities", {})
    if not isinstance(courses, Mapping) or not isinstance(activities, Mapping):
        return {}
    visible = {}
    for aid, task in activities.items():
        if not isinstance(aid, str) or not isinstance(task, Mapping):
            continue
        course_id = task.get("course_id")
        if not isinstance(course_id, str):
            continue
        course = courses.get(course_id)
        if not isinstance(course, Mapping):
            continue
        classes = course.get("classes")
        if (not isinstance(classes, (list, tuple)) or not all(isinstance(value, str) for value in classes) or
                task.get("status") not in ("진행 중", "보기만 가능") or not Classroom.is_distributed(task)):
            continue
        classroom = matching_class(user, course)
        if classroom is not None:
            visible[aid] = (task, course, classroom)
    return visible


def _announcements(user, rows):
    visible = []
    for row in _rows(rows):
        if row.get("active") not in (True, "1", "true", "True"):
            continue
        classes = row.get("classes")
        if isinstance(classes, str):
            try:
                classes = json.loads(classes)
            except (ValueError, TypeError):
                continue
        if (not isinstance(classes, list) or not all(isinstance(value, str) and value in CLASSES for value in classes) or
                len(classes) != len(set(classes)) or classes and user["class"] not in classes):
            continue
        visible.append(dict(id=_text(row.get("id")), title=_text(row.get("title")),
                            content=_text(row.get("content")), created_at=_text(row.get("created_at")),
                            updated_at=_updated(row, "updated_at", "created_at"),
                            author_name=_text(row.get("author_name"))))
    return _newest(visible)


def build_student_updates(user, materials, submissions, questions, announcements, assessment_state, now=None):
    """Return newest-first documents, feedback, assessments and announcements.

    ``now`` accepts an aware/naive datetime or ISO timestamp; naive values use
    Korea time, as do dashboard CSV timestamps. Distributed activities remain
    in the overview outside their submission period, and their own feedback
    remains visible after the teacher ends the assessment.
    """
    result = dict(documents=[], feedback=[], assessments=[], announcements=[])
    if (not isinstance(user, Mapping) or user.get("role") != "student" or
            not _text(user.get("id")).strip() or not _text(user.get("class")).strip()):
        return result
    instant = _instant(now) if now is not None else datetime.now(TZ)
    if instant is None:
        raise ValueError("now must be a datetime or ISO timestamp")
    student_id = user["id"]
    document_fields = ("id", "title", "subject", "category", "unit", "description", "uploaded_at",
                       "file_id", "file_name", "file_url", "mime")
    result["documents"] = _newest([
        {field: _text(row.get(field)) for field in document_fields}
        for row in _rows(materials)
        if row.get("subject") in SUBJECTS and row.get("category") in ("평가계획", "학습지")
    ], "uploaded_at")

    feedback = []
    for row in _rows(submissions):
        if (row.get("student_id") == student_id and row.get("subject") in SUBJECTS and
                _text(row.get("teacher_comment")).strip()):
            feedback.append(_feedback_row(row, "submission", _text(row.get("title")),
                                          _updated(row, "teacher_comment_at", "updated_at", "created_at")))
    for row in _rows(questions):
        if (row.get("student_id") == student_id and row.get("subject") in SUBJECTS and
                _text(row.get("answer")).strip()):
            feedback.append(_feedback_row(row, "question", _text(row.get("title")),
                                          _updated(row, "answered_at", "updated_at", "created_at")))

    state = assessment_state if isinstance(assessment_state, Mapping) else {}
    public = _public_activities(user, state)
    own_attempts = {}
    for attempt in _rows(state.get("course_attempts")):
        aid = attempt.get("activity_id")
        if (not isinstance(aid, str) or aid not in public or
                attempt.get("student_id") != student_id or _is_preview(attempt)):
            continue
        task, course, classroom = public[aid]
        if attempt.get("class_id") != classroom or attempt.get("course_id") != task.get("course_id"):
            continue
        own_attempts.setdefault(aid, []).append(attempt)
        if "assessment_result" in attempt and not assessment_score_published(attempt):
            continue
        safe_feedback = student_feedback(attempt)
        comment = (_text(safe_feedback.get("teacher_comment")) if isinstance(safe_feedback, Mapping) else "") \
            if "assessment_result" in attempt else _text(attempt.get("teacher_comment"))
        if (comment.strip() or _student_feedback(safe_feedback)):
            grade = attempt.get("assessment_result")
            published = {"published_at": grade.get("published_at")} if isinstance(grade, Mapping) else {}
            projected = _feedback_row(attempt, "assessment", _text(task.get("title")),
                                      _updated(published, "published_at") if published else
                                      _updated(attempt, "reviewed", "feedback_at", "updated", "created"))
            projected.update(course_id=_text(task.get("course_id")), course_title=_text(course.get("title")),
                             activity_id=aid, attempt_number=_integer(attempt.get("number")))
            feedback.append(projected)
    result["feedback"] = _newest(feedback)

    for aid, (task, course, _) in public.items():
        attempts = own_attempts.get(aid, [])
        phase = _phase(task, instant)
        period = _period(task, instant.date())
        available = period == "current" and phase in ("running", "unlimited")
        timestamps = [_updated(attempt, "created") for attempt in attempts]
        last_submitted = max(timestamps, key=lambda value: _instant(value) or datetime.min.replace(tzinfo=TZ)) if timestamps else ""
        result["assessments"].append(dict(
            id=aid, course_id=_text(task.get("course_id")), course_title=_text(course.get("title")),
            title=_text(task.get("title")), status=_text(task.get("status")), start=_text(task.get("start")),
            end=_text(task.get("end")), duration_minutes=_integer(task.get("duration_minutes")),
            phase=phase, period=period, available=available, can_submit=available and task.get("status") == "진행 중",
            notice="" if available else Classroom.student_unavailable_notice(task),
            attempt_count=len(attempts), max_attempts=_integer(task.get("max_attempts")),
            last_submitted_at=last_submitted,
            updated_at=_updated(task, "timer_resumed_at", "distributed_at", "updated", "created")))
    result["assessments"] = _newest(result["assessments"])
    result["announcements"] = _announcements(user, announcements)
    return result
