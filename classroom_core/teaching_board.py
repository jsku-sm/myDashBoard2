"""Seven-class teaching-content board; reuses course lesson_records and GitHub CAS.

Shared attachments are stored once. Distribution prepares idempotent per-course
lesson references, then publishes a single shared record. A partial preparation
never announces a successful distribution and can be safely retried.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from urllib.parse import urlsplit

from .progress import PermissionDenied, ValidationError, TZ, now, calculate_progress
from .store import ConflictError
from .work import prepare_attachments, attachment_bytes

CLASSES = tuple(f"1-{i}" for i in range(1, 8))
NAMESPACE = "teaching_contents"
LESSON_PREFIX = "board_"
MATERIAL_PREFIX = "board:"


def _text(value, label, max_length=160, required=True):
    if not isinstance(value, str) or len(value) > max_length or (required and not value.strip()):
        raise ValidationError(f"{label}을(를) 확인하세요. (최대 {max_length:,}자)")
    return value.strip()


def _identity(actor_id, request_id):
    _text(request_id, "저장 요청 번호", 120)
    return hashlib.sha256(json.dumps([actor_id, request_id]).encode()).hexdigest()[:32]


class TeachingBoardService:
    def __init__(self, classroom):
        self.service = classroom
        self.store = classroom.store

    def _owned(self, content_id):
        actor = self.service.require_teacher()
        record = self.store.get(NAMESPACE, str(content_id), fresh=True)
        if not record or record.get("owner_id") != actor["id"]:
            raise PermissionDenied("작성한 교사만 이 수업내용을 관리할 수 있습니다.")
        return record

    def contents(self, term, subject):
        actor = self.service.require_teacher()
        result = []
        for entry in self.store.list(NAMESPACE, fresh=True):
            if entry.get("owner_id") != actor["id"] or entry.get("term") != term or entry.get("subject") != subject:
                continue
            current = self.store.get(NAMESPACE, entry["id"], fresh=True)
            if current and current.get("owner_id") == actor["id"] and current.get("term") == term and current.get("subject") == subject:
                result.append(current)
        return sorted(result, key=lambda item: (item.get("created_at", ""), item["id"]))

    def create(self, title, *, term, subject, body="", url="", files=None, request_id):
        actor = self.service.require_teacher()
        url = _text(url, "자료 링크", 2000, False)
        try:
            parsed = urlsplit(url)
            valid_url = not url or (parsed.scheme in ("https", "http") and parsed.netloc and not parsed.username)
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValidationError("자료 링크는 http 또는 https 주소여야 합니다.")
        fields = dict(title=_text(title, "수업내용"), term=_text(term, "학기"), subject=_text(subject, "과목"),
                      body=_text(body, "수업 설명", 10000, False), url=url,
                      attachments=prepare_attachments(files))
        # A title alone is useful as a teacher's lesson checklist; files are optional.
        fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        content_id = _identity(actor["id"], request_id)
        previous = self.store.get(NAMESPACE, content_id, fresh=True)
        if previous:
            if previous.get("owner_id") != actor["id"] or previous.get("fingerprint") != fingerprint:
                raise ConflictError("이 요청으로 이미 저장한 내용이 다릅니다. 저장된 수업내용을 확인하고 새 입력을 시작하세요.")
            return previous
        record = dict(fields, id=content_id, owner_id=actor["id"], fingerprint=fingerprint,
                      lesson_id=LESSON_PREFIX + content_id, course_ids=[], published_course_ids=[],
                      distribution_classes={}, created_at=now())
        try:
            return self.service._write(NAMESPACE, content_id, record, None, "teaching_content_create")
        except ConflictError:
            previous = self._owned(content_id)
            if previous.get("fingerprint") != fingerprint:
                raise
            return previous

    def distribute(self, content_id, course_ids):
        content = self._owned(content_id)
        if (not isinstance(course_ids, (list, tuple)) or not course_ids
                or any(not isinstance(cid, str) for cid in course_ids)):
            raise ValidationError("배포할 학급의 수업을 선택하세요.")
        course_ids = list(dict.fromkeys(course_ids))
        if len(course_ids) > 7:
            raise ValidationError("한 번에 1-1반부터 1-7반까지 배포할 수 있습니다.")
        courses = [self.service._course(cid, teacher=True, write=True) for cid in course_ids]
        seen = set()
        for course in courses:
            if (course.get("class_name") not in CLASSES or course.get("term") != content["term"]
                    or course.get("subject") != content["subject"]):
                raise ValidationError("같은 학기·과목의 1-1반~1-7반 수업을 선택하세요.")
            if course["class_name"] in seen:
                raise ValidationError("한 반에는 한 수업만 선택해 배포하세요.")
            seen.add(course["class_name"])
            original_class = content.get("distribution_classes", {}).get(course["id"])
            if original_class and original_class != course["class_name"]:
                raise ValidationError("배포 후 수업의 학급이 변경되었습니다. 원래 학급으로 복구하거나 새 수업을 선택하세요.")
        # No writes occur before all requested recipients pass authorization.
        for target in courses:
            for attempt in range(4):
                course = self.service._course(target["id"], teacher=True, write=True)
                if any(lesson["id"] == content["lesson_id"] for lesson in course.get("lessons", [])):
                    break
                course.setdefault("lessons", []).append({
                    "id": content["lesson_id"], "title": content["title"], "unit": "수업내용",
                    "objective": "", "board_content_id": content_id,
                    "resources": [{"kind": "material", "id": MATERIAL_PREFIX + content_id,
                                   "title": content["title"]}]})
                try:
                    self.service._write("courses", course["id"], course, course["version"],
                                        "teaching_content_apply", "전체 학급 진도에서 수업내용 배포")
                    break
                except ConflictError:
                    if attempt == 3:
                        raise
        # Commit publication only after every destination has a saved reference.
        for attempt in range(4):
            current = self._owned(content_id)
            for cid in course_ids:
                course = self.service._course(cid, teacher=True, write=True)
                if (course.get("term") != current["term"] or course.get("subject") != current["subject"]
                        or course.get("class_name") != next(c["class_name"] for c in courses if c["id"] == cid)):
                    raise ConflictError("배포 도중 수업 정보가 변경됐습니다. 학급 설정을 다시 확인하세요.")
            already = set(current.get("published_course_ids", []))
            if set(course_ids) <= already:
                return current
            current["course_ids"] = list(dict.fromkeys(current.get("course_ids", []) + course_ids))
            current["published_course_ids"] = list(dict.fromkeys(current.get("published_course_ids", []) + course_ids))
            current.setdefault("distribution_classes", {}).update({c["id"]: c["class_name"] for c in courses})
            try:
                return self.service._write(NAMESPACE, content_id, current, current["version"],
                                           "teaching_content_distribute", "선택한 학급의 승인 학생에게 자료 배포")
            except ConflictError:
                if attempt == 3:
                    raise

    def materials(self, course_id):
        course = self.service._course(course_id)
        ids = [lesson.get("board_content_id") for lesson in course.get("lessons", []) if lesson.get("board_content_id")]
        result = []
        for content_id in dict.fromkeys(ids):
            material = self.material(course_id, content_id)
            if material:
                result.append(material)
        return result

    def material(self, course_id, content_id):
        """A course-scoped public projection; no other-class IDs or private audit."""
        course = self.service._course(course_id)
        entry = self.store.get(NAMESPACE, content_id, fresh=True)
        if (not entry or course_id not in entry.get("published_course_ids", [])
                or entry.get("distribution_classes", {}).get(course_id) != course.get("class_name")):
            return None
        # Only the allowlisted instructional content travels to a student.
        result = {key: copy.deepcopy(entry.get(key)) for key in ("title", "body", "url", "attachments", "created_at", "updated_at")}
        result.update(id=MATERIAL_PREFIX + content_id, course_id=course_id, unit="수업내용",
                      published=True, publish_at=None, target_student_ids=[], board_content_id=content_id)
        return result

    def download(self, content_id, index):
        entry = self._owned(content_id)
        if type(index) is not int or not 0 <= index < len(entry.get("attachments", [])):
            raise ValidationError("첨부 파일을 확인하세요.")
        item = entry["attachments"][index]
        return dict(filename=item["filename"], mime=item["mime"], data=attachment_bytes(item))

    def set_completed(self, course_id, lesson_id, completed, *, expected_version, actual_date):
        if type(completed) is not bool or type(expected_version) is not int:
            raise ValidationError("수업 완료 체크 값을 확인하세요.")
        course = self.service._course(course_id, teacher=True, write=True)
        if course.get("class_name") not in CLASSES:
            raise ValidationError("1-1반~1-7반의 수업만 수정할 수 있습니다.")
        if course["version"] != expected_version:
            raise ConflictError("다른 창에서 진도가 변경되었습니다. 최신 체크 상태를 확인하고 다시 클릭하세요.")
        lesson = next((row for row in course.get("lessons", []) if row["id"] == lesson_id), None)
        if not lesson:
            raise ValidationError("해당 반에 적용되지 않은 수업내용입니다.")
        if lesson.get("board_content_id") and not self.material(course_id, lesson["board_content_id"]):
            raise ValidationError("자료 배포를 먼저 완료한 뒤 수업 여부를 체크하세요.")
        record = course.get("lesson_records", {}).get(lesson_id, {})
        if record.get("applied", True) is not True:
            raise ValidationError("미적용 차시는 달력·진도 상세에서 적용 후 체크하세요.")
        if completed and record.get("schedule_status") == "cancelled":
            raise ValidationError("휴강으로 기록된 수업입니다. 달력·진도 상세에서 일정 상태를 먼저 수정하세요.")
        if (record.get("progress") == "completed") == completed:
            return course
        if completed:
            try:
                day = date.fromisoformat(actual_date)
            except (TypeError, ValueError):
                raise ValidationError("실제 수업일을 확인하세요.") from None
            if day > datetime.now(TZ).date():
                raise ValidationError("미래 날짜에는 수업 완료를 표시할 수 없습니다.")
            changes = {"progress": "completed", "actual_date": day.isoformat()}
        else:
            changes = {"progress": "scheduled" if record.get("planned_date") else "unassigned", "actual_date": ""}
        return self.service.set_lesson(course_id, lesson_id, changes, expected_version,
                                       "전체 학급 진도 체크박스 · " + ("수업 완료" if completed else "완료 취소"))


def board_model(courses_by_class, contents, *, today=None):
    """Pure display model. Identical titles never merge unrelated lesson IDs."""
    rows, cards = {}, []
    for entry in contents:
        rows["board:" + entry["id"]] = {"id": "board:" + entry["id"], "content_id": entry["id"],
            "title": entry["title"], "subtitle": f"첨부 {len(entry.get('attachments', []))}개 · 수업내용",
            "cells": {}, "owner_id": entry.get("owner_id")}
    for cls in CLASSES:
        course = courses_by_class.get(cls)
        if not course:
            cards.append({"class_name": cls, "subject": "", "percent": None, "completed": 0,
                          "total": 0, "label": "수업 미개설"})
            continue
        summary = calculate_progress(course, today)
        cards.append({"class_name": cls, "subject": course.get("subject", ""), "percent": summary["percent"],
                      "completed": summary["completed"], "total": summary["total"],
                      "label": "수업내용 없음" if not summary["total"] else f"{summary['completed']} / {summary['total']} 수업 완료"})
        for lesson in course.get("lessons", []):
            content_id = lesson.get("board_content_id")
            identity = "board:" + content_id if content_id else "lesson:" + json.dumps(
                [course.get("curriculum_id") or course["id"], lesson["id"], lesson.get("title"), lesson.get("unit")], ensure_ascii=False)
            row = rows.setdefault(identity, {"id": identity, "content_id": content_id, "title": lesson["title"],
                                             "subtitle": lesson.get("unit") or "기존 수업안", "cells": {}})
            record = course.get("lesson_records", {}).get(lesson["id"], {})
            reason = "보관 수업" if course.get("archived") else ("미적용" if not record.get("applied", True) else "")
            entry = next((item for item in contents if item["id"] == content_id), None)
            if entry and course["id"] not in entry.get("published_course_ids", []):
                reason = "배포 대기"
            row["cells"][cls] = {"course_id": course["id"], "lesson_id": lesson["id"],
                                  "expected_version": course["version"], "completed": record.get("progress") == "completed",
                                  "actual_date": record.get("actual_date", ""), "disabled": bool(reason), "reason": reason,
                                  "makeup_needed": bool(record.get("makeup_needed"))}
    return {"classes": list(CLASSES), "cards": cards, "rows": list(rows.values())}
