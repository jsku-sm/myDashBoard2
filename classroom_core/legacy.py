"""Authorized references to existing records; never copies answers or grades."""
from __future__ import annotations

from . import ClassroomService, PermissionDenied, get_store


def _context(user, course_id, teacher=False):
    service = ClassroomService(get_store(), user)
    actor = service.actor()
    course = service._course(course_id, teacher=teacher)
    return service, actor, course


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
