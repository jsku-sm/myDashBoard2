"""Authorized common curricula and independent per-course operating records."""
from __future__ import annotations

import copy
import random
import re
import secrets
import time
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .store import ClassroomError, ConflictError

TZ = ZoneInfo("Asia/Seoul")
PROGRESS_STATES = {"unassigned", "scheduled", "in_progress", "completed"}
SCHEDULE_STATES = {"normal", "changed", "cancelled"}


class PermissionDenied(ClassroomError):
    pass


class ValidationError(ClassroomError):
    pass


class ArchivedError(ClassroomError):
    pass


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def _id():
    return uuid.uuid4().hex


def _is_join_code(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{6}", value) is not None


def _same_class(actor, course):
    """Current account metadata, never a cached membership, scopes students."""
    student_class = str(actor.get("class") or "").strip()
    course_class = str(course.get("class_name") or "").strip()
    return bool(student_class and course_class and student_class == course_class)


def _text(value, field):
    value = str(value or "").strip()
    if not value:
        raise ValidationError(field + "을(를) 입력하세요.")
    return value


def _date(value):
    if not value:
        return ""
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValidationError("날짜는 YYYY-MM-DD 형식으로 입력하세요.") from None


def _resources(resources):
    if not isinstance(resources, list) or any(not isinstance(r, dict) for r in resources):
        raise ValidationError("연결 자료는 자료 정보 목록이어야 합니다.")
    result = []
    for resource in resources:
        # Old scoped references retain only their classroom identity. Removed
        # external activities never become calendar buttons or ordinary URLs.
        if resource.get("kind") in {"material", "assignment"}:
            result.append({key: copy.deepcopy(resource[key]) for key in ("kind", "id", "title") if key in resource})
            continue
        if resource.get("kind") in {"snorkl", "activity"} or resource.get("activity_id"):
            continue
        url = str(resource.get("url", ""))
        if url and not url.startswith(("https://", "http://")):
            raise ValidationError("자료 주소는 http 또는 https 주소여야 합니다.")
        result.append(copy.deepcopy(resource))
    return result


def _present_lesson(lesson):
    result = copy.deepcopy(lesson)
    result.pop("activity_id", None)
    result["resources"] = _resources(result.get("resources", []))
    return result


def _present_course(course):
    result = copy.deepcopy(course)
    result["lessons"] = [_present_lesson(lesson) for lesson in result.get("lessons", [])]
    result["lesson_records"] = {lid: _present_lesson(record) for lid, record in result.get("lesson_records", {}).items()}
    return result


def _lessons(lessons):
    result, seen = [], set()
    for lesson in lessons:
        item = {"id": str(lesson.get("id") or _id()), "title": _text(lesson.get("title"), "차시명"),
                "unit": str(lesson.get("unit", "")), "objective": str(lesson.get("objective", "")),
                "resources": _resources(lesson.get("resources", []))}
        if item["id"] in seen:
            raise ValidationError("차시 ID가 중복되었습니다.")
        seen.add(item["id"])
        result.append(item)
    return result


def calculate_progress(course, as_of=None, unit=None):
    """Unique applied lessons; missed planned lessons never offset by early ones."""
    as_of = _date(as_of or datetime.now(TZ).date().isoformat())
    records = course.get("lesson_records", {})
    lessons = [_present_lesson(dict(lesson, **records.get(lesson["id"], {}))) for lesson in course.get("lessons", [])
               if records.get(lesson["id"], {}).get("applied", True)
               and (unit is None or lesson.get("unit", "") == unit)]
    completed = {lesson["id"] for lesson in lessons if lesson.get("progress") == "completed"
                 and lesson.get("actual_date") and lesson["actual_date"] <= as_of}
    due = [lesson["id"] for lesson in lessons if lesson.get("planned_date")
           and lesson["planned_date"] <= as_of and lesson["id"] not in completed]
    early = [lesson["id"] for lesson in lessons if lesson["id"] in completed
             and lesson.get("planned_date", "") > as_of]
    ongoing = [lesson for lesson in lessons if lesson.get("progress") == "in_progress"]
    remaining = [lesson for lesson in lessons if lesson["id"] not in completed]
    recently_done = sorted([lesson for lesson in lessons if lesson["id"] in completed],
                           key=lambda lesson: lesson.get("actual_date", ""), reverse=True)
    planned = any(lesson.get("planned_date") for lesson in lessons)
    total = len(lessons)
    return {"course_id": course["id"], "title": course["title"], "class_name": course.get("class_name", ""),
            "subject": course.get("subject", ""), "kind": course.get("kind", "regular"),
            "curriculum_id": course.get("curriculum_id", ""), "curriculum_title": course.get("curriculum_title", ""),
            "version": course.get("version"), "archived": course.get("archived", False),
            "completed": len(completed), "total": total,
            "percent": round(len(completed) / total * 100, 1) if total else None,
            "label": f"{len(completed)}/{total}차시 완료" if total else "수업안 미설정",
            "plan_label": ("계획 미설정" if not planned else f"예정 차시 미완료 {len(due)}개"),
            "due_incomplete": due, "early_completed": early, "due_incomplete_count": len(due),
            "early_completed_count": len(early), "current_lesson": ongoing[0] if ongoing else None,
            "next_lesson": remaining[0] if remaining else None,
            "recent_completed": recently_done[0] if recently_done else None,
            "makeup_needed": any(lesson.get("makeup_needed", False) for lesson in lessons),
            "reschedule_needed": [lesson["id"] for lesson in lessons
                                  if lesson.get("schedule_status") == "cancelled" and lesson["id"] not in completed],
            "updated_at": course.get("updated_at", ""), "as_of": as_of}


class ClassroomService:
    def __init__(self, store, user, user_lookup=None, lock_checker=None):
        self.store = store
        self._user_id = str(user.get("id", "")) if isinstance(user, dict) else str(user or "")
        if user_lookup is None:
            import auth
            import storage

            def user_lookup(uid):
                # Account edits must affect access immediately, even while
                # ordinary user lists retain their shared display cache.
                storage.invalidate("users")
                return auth.get_user(uid)
        self._lookup = user_lookup
        self._lock_checker = lock_checker

    def actor(self):
        user = self._lookup(self._user_id)
        if not user or user.get("role") not in {"teacher", "student"}:
            raise PermissionDenied("로그인이 필요합니다. 다시 로그인해 주세요.")
        if str(user.get("must_change", "0")) == "1":
            raise PermissionDenied("비밀번호를 변경한 뒤 수업에 참여하세요.")
        return user

    def require_teacher(self):
        actor = self.actor()
        if actor["role"] != "teacher":
            raise PermissionDenied("담당 교사만 사용할 수 있습니다.")
        return actor

    def _course(self, course_id, teacher=False, write=False):
        actor = self.actor()
        record = self.store.get("courses", course_id, fresh=True)
        if not record:
            raise PermissionDenied("수업이 없거나 접근 권한이 없습니다.")
        is_teacher = actor["role"] == "teacher" and actor["id"] in record.get("teacher_ids", [])
        is_student = (actor["role"] == "student" and actor["id"] in record.get("student_ids", [])
                      and _same_class(actor, record))
        if not is_teacher and (teacher or not is_student):
            raise PermissionDenied("수업 참여 승인 또는 담당 교사 권한이 필요합니다.")
        if write and record.get("archived"):
            raise ArchivedError("보관된 수업은 읽기 전용입니다. 새 학기로 복사해 사용하세요.")
        return record

    def course(self, course_id, edit=False):
        return self._course(course_id, teacher=True, write=True) if edit else self.get_course(course_id)

    def _write(self, namespace, record_id, record, expected_version, action, reason=""):
        actor = self.actor()
        if action == "member_joined" and (actor["role"] != "student" or not _same_class(actor, record)):
            raise PermissionDenied("학생 계정과 수업의 학급을 다시 확인하세요.")
        if actor["role"] == "student":
            self._check_student_lock(actor)
            if namespace == "courses" and not _same_class(actor, record):
                raise PermissionDenied("수업과 계정의 학급을 확인하세요.")
        previous = self.store.get(namespace, record_id, fresh=True)
        actual = previous.get("version") if previous else None
        if actual != expected_version:
            raise ConflictError("다른 창에서 기록이 변경되었습니다. 새로 불러온 뒤 다시 저장해 주세요.")
        result = copy.deepcopy(record)
        result["updated_at"] = now()
        result.setdefault("created_at", result["updated_at"])
        old = previous or {}
        changed = [key for key in result if key not in {"audit", "version", "updated_at", "created_at"}
                   and old.get(key) != result.get(key)]
        entry = {"id": _id(), "actor_id": actor["id"], "at": result["updated_at"], "action": action,
                 "reason": str(reason), "fields": changed, "from_version": actual}
        # Preserve exact scheduling/progress changes without duplicating student
        # attachments or ever recursively copying a previous audit array.
        if "lesson_records" in changed:
            before_records, after_records = old.get("lesson_records", {}), result.get("lesson_records", {})
            entry["lesson_changes"] = {key: {"before": before_records.get(key), "after": value}
                                       for key, value in after_records.items() if before_records.get(key) != value}
        if "lessons" in changed:
            entry["curriculum_change"] = {"before": old.get("lessons", []), "after": result["lessons"]}
        settings = {key: {"before": old.get(key), "after": result.get(key)} for key in changed
                    if key in {"title", "term", "subject", "class_name", "kind", "archived", "teacher_ids", "student_ids", "pending_student_ids", "comments_enabled"}}
        if settings:
            entry["settings_changes"] = settings
        result["audit"] = old.get("audit", []) + [entry]
        return self.store.put(namespace, record_id, result, expected_version)

    def _check_student_lock(self, actor):
        checker = self._lock_checker
        if checker is None:
            import realtime
            checker = realtime.is_locked
        if checker(actor.get("class", "")):
            raise PermissionDenied("지금은 입력 잠금 중입니다. 작성 중인 내용을 유지하고 잠금 해제 후 다시 저장하세요.")

    def _people(self, ids, role):
        result = []
        for uid in dict.fromkeys(str(uid) for uid in (ids or [])):
            user = self._lookup(uid)
            if not user or user.get("role") != role:
                raise ValidationError("대상 계정과 역할을 확인하세요.")
            result.append(uid)
        return result

    def list_courses(self):
        actor = self.actor()
        result = []
        for course in self.store.list("courses"):
            # Cached teaching metadata must not prolong revoked membership.
            course = self.store.get("courses", course["id"], fresh=True)
            if not course:
                continue
            if actor["role"] == "teacher" and actor["id"] in course.get("teacher_ids", []):
                result.append(_present_course(course))
            elif (actor["role"] == "student" and _same_class(actor, course)
                  and actor["id"] in course.get("student_ids", [])):
                result.append(self._student_course(course))
            elif (actor["role"] == "student" and _same_class(actor, course)
                  and actor["id"] in course.get("pending_student_ids", [])):
                result.append({k: course.get(k) for k in ("id", "title", "term", "subject", "kind", "class_name", "archived")}
                              | {"membership_status": "pending"})
        return result

    def _student_course(self, course):
        result = _present_course(course)
        result["member_count"] = len(course.get("student_ids", []))
        # Scoped resource permissions are resolved by WorkService at display
        # time. Cached calendar metadata must never expose private resource
        # details before that check.
        for item in result.get("lessons", []) + list(result.get("lesson_records", {}).values()):
            item["resources"] = [({"kind": r["kind"], "id": r.get("id", "")}
                                  if r.get("kind") in {"material", "assignment"} else r)
                                 for r in item.get("resources", [])]
        for key in ("audit", "pending_student_ids", "student_ids", "join_code", "approval_code",
                    "join_code_reservation", "copied_material_templates", "copied_assignment_templates"):
            result.pop(key, None)
        # Operating notes and support reasons are teacher-only observations.
        for record in result.get("lesson_records", {}).values():
            for key in ("memo", "next_note", "makeup_reason", "sessions"):
                record.pop(key, None)
        result["membership_status"] = "approved"
        return result

    def get_course(self, course_id):
        record = self._course(course_id)
        actor = self.actor()
        if actor["role"] == "teacher" and actor["id"] in record.get("teacher_ids", []):
            return _present_course(record)
        if (actor["role"] == "student" and actor["id"] in record.get("student_ids", [])
                and _same_class(actor, record)):
            return self._student_course(record)
        raise PermissionDenied("수업 참여 승인 또는 담당 교사 권한이 필요합니다.")

    def members(self, course_id):
        course = self._course(course_id, teacher=True)
        return [{k: user.get(k, "") for k in ("id", "name", "class", "role")}
                for uid in course["student_ids"] if (user := self._lookup(uid)) and user.get("role") == "student"]

    def _reserve_join_code(self, course_id, preferred=""):
        """Reserve before updating a course; a lost course write is recoverable.

        The store hashes record IDs in filenames. A reservation is never enough
        to join: the authoritative course must publish the same code, too.
        Per-code CAS makes collisions safe across independent app processes.
        """
        candidates = [preferred] if _is_join_code(preferred) else []
        candidates += [record.get("id") for record in self.store.list("course_join_codes", fresh=True)
                       if record.get("course_id") == course_id and _is_join_code(record.get("id"))
                       and record.get("id") not in candidates]
        for attempt in range(24):
            code = candidates.pop(0) if candidates else f"{secrets.randbelow(1_000_000):06d}"
            reservation = self.store.get("course_join_codes", code, fresh=True)
            if reservation:
                if reservation.get("course_id") == course_id:
                    return code
                continue
            try:
                self.store.put("course_join_codes", code,
                               {"id": code, "course_id": course_id}, None)
                return code
            except ConflictError:
                # Another process claimed this number. The next iteration
                # chooses a different candidate without overwriting its owner.
                continue
        raise ConflictError("승인코드를 발급하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    def get_join_code(self, course_id):
        """Explicit teacher action also upgrades older courses without a code."""
        for attempt in range(6):
            course = self._course(course_id, teacher=True)
            if course.get("archived"):
                code = course.get("join_code")
                reservation = self.store.get("course_join_codes", code, fresh=True) if _is_join_code(code) else None
                if reservation and reservation.get("course_id") == course_id:
                    return code
                raise ArchivedError("보관된 수업에는 승인코드를 발급할 수 없습니다. 새 학기로 복사해 사용하세요.")
            code = self._reserve_join_code(course_id, course.get("join_code", ""))
            if course.get("join_code") == code:
                return code
            course["join_code"] = code
            try:
                self._write("courses", course_id, course, course["version"], "join_code_create")
                return code
            except ConflictError:
                continue
        raise ConflictError("수업 정보가 변경되었습니다. 새로 불러온 뒤 승인코드를 다시 확인하세요.")

    def create_course(self, title, term, subject, kind="regular", class_name="", curriculum_id="", teacher_ids=None, student_ids=None):
        actor = self.require_teacher()
        if kind not in {"regular", "after_school"}:
            raise ValidationError("정규 또는 방과후 수업을 선택하세요.")
        course_id = _id()
        course = {"id": course_id, "owner_id": actor["id"], "title": _text(title, "수업명"), "term": _text(term, "학기"),
                  "subject": _text(subject, "과목"), "kind": kind, "class_name": str(class_name),
                  "teacher_ids": list(dict.fromkeys([actor["id"]] + self._people(teacher_ids, "teacher"))),
                  "student_ids": self._people(student_ids, "student"), "pending_student_ids": [], "archived": False,
                  "comments_enabled": True, "curriculum_id": "", "curriculum_title": "", "lessons": [], "lesson_records": {}}
        if any(not _same_class(self._lookup(uid) or {}, course) for uid in course["student_ids"]):
            raise ValidationError("수업과 같은 학급의 학생만 구성원으로 추가할 수 있습니다.")
        if curriculum_id:
            curriculum = self.get_curriculum(curriculum_id)
            if curriculum["subject"] != subject:
                raise ValidationError("수업과 공통 수업안의 과목이 다릅니다.")
            course.update(curriculum_id=curriculum_id, curriculum_title=curriculum["title"],
                          curriculum_version=curriculum["version"], lessons=copy.deepcopy(curriculum["lessons"]))
        course["join_code"] = self._reserve_join_code(course_id)
        return self._write("courses", course_id, course, None, "course_create")

    def update_course(self, course_id, changes, expected_version, reason):
        course = self._course(course_id, teacher=True, write=True)
        if set(changes) - {"title", "term", "subject", "class_name", "comments_enabled"}:
            raise ValidationError("수정할 수 없는 수업 항목입니다.")
        if "subject" in changes and changes["subject"] != course["subject"] and course["curriculum_id"]:
            raise ValidationError("공통 수업안이 연결된 수업의 과목은 변경할 수 없습니다.")
        _text(reason, "변경 사유")
        for key, value in changes.items():
            course[key] = bool(value) if key == "comments_enabled" else _text(value, key)
        return self._write("courses", course_id, course, expected_version, "course_update", reason)

    def join_course(self, code):
        """A teacher's six-digit approval code approves a same-class student."""
        actor = self.actor()
        if actor["role"] != "student":
            raise PermissionDenied("학생 계정으로 수업에 참여하세요.")
        self._check_student_lock(actor)
        if not _is_join_code(code):
            raise ValidationError("교사가 알려 준 숫자 6자리 승인코드를 입력하세요.")
        reservation = self.store.get("course_join_codes", code, fresh=True)
        course_id = reservation.get("course_id") if reservation else None
        if not course_id:
            raise PermissionDenied("참여 가능한 승인코드와 계정의 학급을 확인하세요.")
        for attempt in range(32):
            # Re-read both identity and authoritative membership on every CAS
            # retry. Transfer, archive, and concurrent enrollments take effect
            # even if a previous page still contains a course ID.
            actor = self.actor()
            course = self.store.get("courses", course_id, fresh=True)
            if (actor["role"] != "student" or not course or course.get("archived")
                    or course.get("join_code") != code or not _same_class(actor, course)):
                raise PermissionDenied("참여 가능한 승인코드와 계정의 학급을 확인하세요.")
            if actor["id"] in course.get("student_ids", []):
                return {"status": "approved", "course_id": course_id}
            course.setdefault("student_ids", []).append(actor["id"])
            course["pending_student_ids"] = [uid for uid in course.get("pending_student_ids", [])
                                             if uid != actor["id"]]
            try:
                self._write("courses", course_id, course, course["version"], "member_joined")
                return {"status": "approved", "course_id": course_id}
            except ConflictError:
                # A whole class often joins together. Jitter avoids keeping
                # each process in lockstep while bounded CAS retries retain
                # every successful enrollment in this single durable record.
                time.sleep(random.uniform(0.01, min(0.05 * (attempt + 1), 0.3)))
                continue
        raise ConflictError("참여 정보가 변경되었습니다. 잠시 후 승인코드를 다시 입력하세요.")

    def request_join(self, code):
        # Old callers must also provide an approval code, never an internal ID.
        return self.join_course(code)

    def approve_member(self, course_id, student_id, approve=True):
        course = self._course(course_id, teacher=True, write=True)
        self._people([student_id], "student")
        if student_id not in course["pending_student_ids"]:
            raise ValidationError("대기 중인 참여 신청이 없습니다.")
        if approve and not _same_class(self._lookup(student_id) or {}, course):
            raise ValidationError("수업과 같은 학급의 학생만 참여를 승인할 수 있습니다.")
        course["pending_student_ids"].remove(student_id)
        if approve and student_id not in course["student_ids"]:
            course["student_ids"].append(student_id)
        return self._write("courses", course_id, course, course["version"], "member_approved" if approve else "member_rejected")

    def remove_member(self, course_id, student_id, expected_version):
        course = self._course(course_id, teacher=True, write=True)
        course["student_ids"] = [uid for uid in course["student_ids"] if uid != student_id]
        course["pending_student_ids"] = [uid for uid in course["pending_student_ids"] if uid != student_id]
        return self._write("courses", course_id, course, expected_version, "member_removed")

    def list_curricula(self):
        actor = self.require_teacher()
        return [dict(record, lessons=[_present_lesson(lesson) for lesson in record.get("lessons", [])])
                for record in self.store.list("curricula")
                if actor["id"] == record["owner_id"] or actor["id"] in record["shared_teacher_ids"]]

    def _curriculum(self, curriculum_id):
        actor = self.require_teacher()
        record = self.store.get("curricula", curriculum_id, fresh=True)
        if not record or (actor["id"] != record["owner_id"] and actor["id"] not in record["shared_teacher_ids"]):
            raise PermissionDenied("공통 수업안의 공유 권한이 없습니다.")
        return record

    def get_curriculum(self, curriculum_id):
        record = self._curriculum(curriculum_id)
        return dict(record, lessons=[_present_lesson(lesson) for lesson in record.get("lessons", [])])

    def create_curriculum(self, title, subject, lessons, shared_teacher_ids=None):
        actor = self.require_teacher()
        curriculum_id = _id()
        record = {"id": curriculum_id, "owner_id": actor["id"], "title": _text(title, "수업안명"),
                  "subject": _text(subject, "과목"), "lessons": _lessons(lessons),
                  "shared_teacher_ids": self._people(shared_teacher_ids, "teacher")}
        return self._write("curricula", curriculum_id, record, None, "curriculum_create")

    def preview_curriculum_changes(self, curriculum_id, lessons):
        self.get_curriculum(curriculum_id)
        new = {lesson["id"] for lesson in _lessons(lessons)}
        result = []
        for course in self.list_courses():
            if course["curriculum_id"] != curriculum_id:
                continue
            old = {lesson["id"] for lesson in course["lessons"]}
            result.append({"course_id": course["id"], "title": course["title"], "added": sorted(new - old),
                           "removed": sorted(old - new), "completed_removed": [lid for lid in old - new
                           if course.get("lesson_records", {}).get(lid, {}).get("progress") == "completed"]})
        return result

    def update_curriculum(self, curriculum_id, changes, expected_version, reason):
        record = self._curriculum(curriculum_id)
        _text(reason, "변경 사유")
        if set(changes) - {"title", "lessons", "shared_teacher_ids"}:
            raise ValidationError("수정할 수 없는 수업안 항목입니다.")
        if "shared_teacher_ids" in changes and self.actor()["id"] != record["owner_id"]:
            raise PermissionDenied("수업안 소유자만 공유 교사를 변경할 수 있습니다.")
        for key, value in changes.items():
            record[key] = _lessons(value) if key == "lessons" else (self._people(value, "teacher") if key == "shared_teacher_ids" else _text(value, "수업안명"))
        # Operating courses retain their snapshot until individually confirmed.
        return self._write("curricula", curriculum_id, record, expected_version, "curriculum_update", reason)

    def apply_curriculum(self, course_id, curriculum_id, expected_version, reason):
        course = self._course(course_id, teacher=True, write=True)
        curriculum = self.get_curriculum(curriculum_id)
        _text(reason, "적용 사유")
        if curriculum["subject"] != course["subject"]:
            raise ValidationError("수업과 공통 수업안의 과목이 다릅니다.")
        if course["curriculum_id"] and course["curriculum_id"] != curriculum_id and course["lesson_records"]:
            raise ValidationError("운영 기록이 있는 수업은 다른 수업안으로 덮어쓸 수 없습니다. 새 수업으로 개설하세요.")
        course.update(curriculum_id=curriculum_id, curriculum_title=curriculum["title"],
                      curriculum_version=curriculum["version"], lessons=copy.deepcopy(curriculum["lessons"]))
        # Retain removed lesson operating records for audit and future restore;
        # only the explicit snapshot participates in the denominator.
        return self._write("courses", course_id, course, expected_version, "curriculum_apply", reason)

    def set_lesson(self, course_id, lesson_id, changes, expected_version, reason):
        course = self._course(course_id, teacher=True, write=True)
        _text(reason, "변경 사유")
        if lesson_id not in {lesson["id"] for lesson in course["lessons"]}:
            raise ValidationError("이 수업에 적용된 차시가 아닙니다.")
        allowed = {"planned_date", "actual_date", "progress", "schedule_status", "makeup_needed", "makeup_reason",
                   "memo", "next_note", "applied", "period", "resources"}
        if set(changes) - allowed:
            raise ValidationError("수정할 수 없는 차시 항목입니다.")
        record = course["lesson_records"].setdefault(lesson_id, {"progress": "unassigned", "schedule_status": "normal", "applied": True})
        for key, value in changes.items():
            if key in {"planned_date", "actual_date"}:
                value = _date(value)
            elif key == "progress" and value not in PROGRESS_STATES:
                raise ValidationError("진행 상태를 확인하세요.")
            elif key == "schedule_status" and value not in SCHEDULE_STATES:
                raise ValidationError("일정 상태를 확인하세요.")
            elif key in {"makeup_needed", "applied"} and not isinstance(value, bool):
                raise ValidationError("적용 여부와 보충 필요는 참/거짓으로 입력하세요.")
            elif key == "resources":
                value = _resources(value)
            record[key] = value
        if record.get("progress") == "completed" and not record.get("actual_date"):
            raise ValidationError("수업 완료에는 실제 수업일이 필요합니다.")
        if record.get("schedule_status") == "cancelled" and record.get("progress") == "completed":
            raise ValidationError("휴강과 수업 완료를 동시에 지정할 수 없습니다. 보충 수업 기록을 별도로 입력하세요.")
        record["updated_at"] = now()
        return self._write("courses", course_id, course, expected_version, "lesson_update", reason)

    def add_session(self, course_id, lesson_id, planned_date, actual_date="", kind="makeup", note="", expected_version=None):
        """Split/repeat/makeup meetings never create a second completed lesson."""
        course = self._course(course_id, teacher=True, write=True)
        if lesson_id not in {lesson["id"] for lesson in course["lessons"]} or kind not in {"makeup", "repeat", "split"}:
            raise ValidationError("보충·재수업·분할 수업의 차시와 종류를 확인하세요.")
        if expected_version is None:
            expected_version = course["version"]
        record = course["lesson_records"].setdefault(lesson_id, {"progress": "unassigned", "schedule_status": "normal", "applied": True})
        record.setdefault("sessions", []).append({"id": _id(), "kind": kind, "planned_date": _date(planned_date),
                                                   "actual_date": _date(actual_date), "note": str(note)})
        return self._write("courses", course_id, course, expected_version, "session_add", str(note))

    def progress_summary(self, course_id, as_of=None, unit=None):
        course = self._course(course_id, teacher=True)
        return calculate_progress(course, as_of, unit=unit)

    def list_progress(self, as_of=None):
        self.require_teacher()
        return [calculate_progress(course, as_of) for course in self.list_courses()]

    def comparison(self, course_ids, as_of=None):
        courses = [self._course(cid, teacher=True) for cid in course_ids]
        if len({(course["subject"], course["curriculum_id"], course.get("curriculum_version")) for course in courses}) > 1:
            raise ValidationError("같은 과목과 같은 공통 수업안 버전을 적용한 수업끼리 비교하세요.")
        return [{"course": _present_course(course), "summary": calculate_progress(course, as_of)} for course in courses]

    def archive_course(self, course_id, expected_version):
        course = self._course(course_id, teacher=True, write=True)
        course["archived"] = True
        return self._write("courses", course_id, course, expected_version, "course_archive")

    def copy_course(self, course_id, title, term, class_name=""):
        source = self._course(course_id, teacher=True)
        # Copy the applied teaching snapshot only, never memberships, private
        # student work, actual dates, notes, or completion records.
        actor = self.require_teacher()
        record = {"id": _id(), "owner_id": actor["id"], "title": _text(title, "수업명"), "term": _text(term, "학기"),
                  "subject": source["subject"], "kind": source["kind"], "class_name": str(class_name),
                  "teacher_ids": [actor["id"]], "student_ids": [], "pending_student_ids": [], "archived": False,
                  "comments_enabled": source.get("comments_enabled", True), "curriculum_id": source.get("curriculum_id", ""),
                  "curriculum_title": source.get("curriculum_title", ""), "curriculum_version": source.get("curriculum_version"),
                  "lessons": copy.deepcopy(source["lessons"]), "lesson_records": {}}
        # Template copies and ID remapping are part of the same new course CAS
        # record. Oversized/failed writes create no partly copied classroom.
        copies = {"material": {}, "assignment": {}}
        for namespace, embedded_key, fields in (
                ("materials", "copied_material_templates", ("title", "body", "unit", "url", "attachments")),
                ("assignments", "copied_assignment_templates", ("title", "instructions", "kind", "methods", "max_points", "rubric", "allow_late", "resubmit_policy", "material_ids"))):
            templates = {item["id"]: item for item in source.get(embedded_key, [])}
            templates.update({item["id"]: item for item in self.store.list(namespace, fresh=True)
                              if item.get("course_id") == course_id})
            output = []
            for original_id, item in templates.items():
                if item.get("activity_id") or "snorkl" in item.get("methods", []):
                    continue  # Disabled external work is never converted to new answers.
                new_id = _id()
                copies[namespace[:-1]][original_id] = new_id
                template = {key: copy.deepcopy(item[key]) for key in fields if key in item}
                template.update(id=new_id, course_id=record["id"], published=False, publish_at=None,
                                target_student_ids=[], created_at=now(), updated_at=now())
                if namespace == "assignments":
                    template["due_at"] = None
                    template["methods"] = [method for method in template.get("methods", []) if method in {"text", "file"}] or ["text"]
                    template["material_ids"] = [copies["material"][mid] for mid in template.get("material_ids", []) if mid in copies["material"]]
                output.append(template)
            record[embedded_key] = output
        for lesson in record["lessons"]:
            lesson.pop("activity_id", None)
            resources = []
            for resource in lesson.get("resources", []):
                item = copy.deepcopy(resource)
                if item.get("kind") in {"material", "assignment"}:
                    mapping = copies[item["kind"]]
                    if item.get("id") not in mapping:
                        continue
                    item = {"kind": item["kind"], "id": mapping[item["id"]], "title": item.get("title", "")}
                elif item.get("kind") in {"snorkl", "activity"} or item.get("activity_id"):
                    continue  # A previous course's permission is never inherited.
                resources.append(item)
            lesson["resources"] = resources
        record["join_code"] = self._reserve_join_code(record["id"])
        return self._write("courses", record["id"], record, None, "course_copy")
