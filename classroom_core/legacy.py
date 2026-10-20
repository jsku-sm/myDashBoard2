"""Authorized references to existing records; never copies answers or grades."""
from __future__ import annotations

from . import ClassroomService, ClassroomError, PermissionDenied, get_store


def _context(user, course_id, teacher=False):
    service = ClassroomService(get_store(), user)
    actor = service.actor()
    course = service._course(course_id, teacher=teacher)
    return service, actor, course


def _native():
    from think_app.embedded import get_store as native_store
    from think_app.integration import load_embedded_settings
    return native_store(load_embedded_settings())


def _student_linked(service, course, aid):
    from .work import WorkService
    work = WorkService(service)
    assignments = work.assignments(course["id"])
    materials = work.materials(course["id"])
    scoped = {"material": {r["id"]: r for r in materials},
              "assignment": {r["id"]: r for r in assignments}}
    for row in assignments + materials:
        if row.get("activity_id") == aid:
            return True
    for lesson in course.get("lessons", []):
        effective = dict(lesson, **course.get("lesson_records", {}).get(lesson["id"], {}))
        if not effective.get("applied", True):
            continue
        if effective.get("activity_id") == aid:
            return True
        for resource in effective.get("resources", []):
            kind = resource.get("kind")
            if kind in scoped:
                if scoped[kind].get(resource.get("id"), {}).get("activity_id") == aid:
                    return True
            elif kind == "snorkl" and (resource.get("activity_id") or resource.get("id")) == aid:
                return True
    return False


def get_snorkl_activity(user, course_id, activity_id, *, require_available=False):
    service, actor, course = _context(user, course_id)
    try:
        store = _native()
        state = store.read()
        activity = state.get("course_activities", {}).get(activity_id)
        native_course = state.get("courses", {}).get((activity or {}).get("course_id"))
        if not activity or not native_course:
            raise PermissionDenied("소노클 활동이 없거나 접근 권한이 없습니다.")
        if actor["role"] == "teacher":
            from think_app.ownership import owns_course
            if not owns_course(actor, native_course):
                raise PermissionDenied("본인이 담당하거나 공유받은 소노클 활동만 연결할 수 있습니다.")
        else:
            from think_app.integration import student_identity
            from think_app.classroom import Classroom
            student_identity(actor, native_course)
            if not _student_linked(service, course, activity_id):
                raise PermissionDenied("수업에 공개된 소노클 활동만 볼 수 있습니다.")
            if require_available and not Classroom.student_activity_available(activity):
                raise PermissionDenied("이 소노클 활동은 현재 열 수 없습니다. 제출 기록은 클래스룸에서 확인할 수 있습니다.")
        # Model answers, other students' work and grading never cross this adapter.
        return {key: activity.get(key, "") for key in ("id", "course_id", "title", "status", "start", "end")}
    except ClassroomError:
        raise
    except Exception:
        raise ClassroomError("소노클 활동 연결을 확인하지 못했습니다. 기존 소노클 저장 설정과 활동 공개 상태를 확인하세요.") from None


def list_snorkl_activities(user, course_id):
    _, actor, _ = _context(user, course_id, teacher=True)
    try:
        from think_app.ownership import owns_course
        state = _native().read()
        courses = state.get("courses", {})
        return [{"id": item["id"], "course_id": item["course_id"], "title": item["title"],
                 "course_title": courses[item["course_id"]]["title"], "status": item["status"]}
                for item in state.get("course_activities", {}).values()
                if owns_course(actor, courses.get(item.get("course_id")))]
    except ClassroomError:
        raise
    except Exception:
        raise ClassroomError("소노클 활동 목록을 불러오지 못했습니다. 기존 소노클 메뉴에서 연결을 확인하세요.") from None


def snorkl_status(user, course_id, activity_id, student_id=None):
    activity = get_snorkl_activity(user, course_id, activity_id)
    _, actor, course = _context(user, course_id)
    if student_id is not None:
        if student_id not in course["student_ids"] or (actor["role"] != "teacher" and student_id != actor["id"]):
            raise PermissionDenied("다른 학생의 소노클 제출 기록에는 접근할 수 없습니다.")
    elif actor["role"] == "student":
        student_id = actor["id"]
    state = _native().read()
    attempts = [a for a in state.get("course_attempts", {}).values()
                if a.get("activity_id") == activity_id and not a.get("preview")
                and (student_id is None or a.get("student_id") == student_id)]
    attempts.sort(key=lambda a: (a.get("created", ""), a.get("number", 0)))
    latest = attempts[-1] if attempts else {}
    return dict(source="snorkl", activity_id=activity_id, course_id=activity["course_id"],
                title=activity["title"], status="제출 완료" if latest else "미제출",
                submitted_at=latest.get("created", ""), version=latest.get("number", 0),
                submission_id=latest.get("id", ""), count=len(attempts),
                connection="저장된 답안", updated_at=latest.get("created", ""))


def launch_snorkl(user, course_id, activity_id):
    activity = get_snorkl_activity(user, course_id, activity_id, require_available=True)
    import streamlit as st
    from classroom_navigation import PENDING
    st.session_state[PENDING] = {"menu": "snorkl", "user_id": user["id"],
                                 "course_id": activity["course_id"], "activity_id": activity_id}


def resolve_reference(user, course_id, kind, record_id):
    service, actor, course = _context(user, course_id, teacher=kind == "observation")
    import storage as db
    if kind not in {"sudanote", "observation", "submission", "question", "material"}:
        raise PermissionDenied("지원하지 않는 기존 기록 참조입니다.")
    table = {"sudanote": "sudanotes", "observation": "observations", "submission": "submissions",
             "question": "questions", "material": "materials"}[kind]
    record = next((r for r in db.read(table) if r.get("id") == record_id), None)
    if not record and kind == "observation":
        # Global legacy reads remain author-only. A shared teacher can resolve
        # one original only through an explicitly shared classroom reference
        # owned by its original author, rechecked on every read.
        from .work import WorkService
        from think_app.ownership import legacy_teacher_id
        references = [r for r in WorkService(service).observations(course_id)
                      if r.get("legacy_ref") == record_id and actor["id"] in r.get("shared_teacher_ids", [])]
        if references:
            original = next((r for r in db._ready_backend().read(table) if r.get("id") == record_id), None)
            if original and any((original.get("author_id") or legacy_teacher_id()) == r.get("teacher_id")
                                and original.get("student_id") == r.get("student_id") for r in references):
                record = original
    if not record:
        raise PermissionDenied("기존 기록이 없거나 접근 권한이 없습니다.")
    if kind == "material":
        allowed = record.get("subject") == course["subject"]
    else:
        allowed = record.get("student_id") in course["student_ids"]
        if actor["role"] == "student":
            allowed = allowed and record.get("student_id") == actor["id"]
        if kind != "observation":
            allowed = allowed and record.get("subject") == course["subject"]
    if not allowed:
        raise PermissionDenied("해당 수업과 본인에게 허용된 기존 기록만 연결할 수 있습니다.")
    return record


def validate_reference(user, course_id, kind, record_id):
    row = resolve_reference(user, course_id, kind, record_id)
    return {key: row.get(key, "") for key in ("id", "student_id", "subject", "created_at")}
