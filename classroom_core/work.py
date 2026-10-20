"""Permission checked classroom work, with one atomic shard per student/task.

Submission content is append only. Drafts, reviews, notifications and audit changes
share its CAS record, so a failed save can never create a successful receipt.
Existing CSV records are referenced through ``legacy``; they are never copied here.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import PurePath
import uuid
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .progress import PermissionDenied, ValidationError
from .store import ConflictError, StorageError


DISABLED_ACTIVITY_MESSAGE = "이전 외부 활동 연결은 비활성화되었습니다. 새 자료나 과제를 등록하세요."


def _disabled_activity(record):
    """Recognize old external links without loading their provider or responses."""
    return bool(record.get("activity_id") or "snorkl" in record.get("methods", []))


MAX_FILES = 2
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_VERSIONS = 10
MAX_SHARD_BYTES = 12 * 1024 * 1024
MAX_ANNOUNCEMENT_COURSES = 500
_DISTRIBUTION_POST_PREFIX = "distribution:"
ALLOWED_FILE_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".txt": "text/plain", ".docx":
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".hwp": "application/x-hwp", ".hwpx": "application/hwp+zip",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value, label, maximum=10000, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValidationError(f"{label} 입력을 확인하세요. (최대 {maximum:,}자)")
    return value.strip()


def _instant(value, label):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{label}을 확인하세요.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValidationError(f"{label}에는 시간대가 포함된 날짜와 시간이 필요합니다.") from None
    return result.astimezone(timezone.utc).isoformat(timespec="seconds")


def _released(record, instant=None):
    return bool(record.get("published") and
                (not record.get("publish_at") or record["publish_at"] <= (instant or now())))


def _identity(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def _number(value, label, maximum=100000):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValidationError(f"{label}을 확인하세요.")
    return value


def prepare_attachments(files):
    """Encode bounded files inside the encrypted record, without public blobs."""
    if files is None:
        return []
    if not isinstance(files, (list, tuple)) or len(files) > MAX_FILES:
        raise ValidationError(f"첨부는 최대 {MAX_FILES}개까지 가능합니다.")
    output, total = [], 0
    for item in files:
        if not isinstance(item, dict):
            raise ValidationError("첨부 파일을 확인하세요.")
        filename = _text(item.get("filename", ""), "파일 이름", 180)
        if PurePath(filename).name != filename or any(c in filename for c in ("/", "\\")) or not all(c.isprintable() for c in filename):
            raise ValidationError("파일 이름을 확인하세요.")
        extension = PurePath(filename).suffix.lower()
        if extension not in ALLOWED_FILE_TYPES:
            raise ValidationError("PDF, 이미지, 텍스트, DOCX, HWP, HWPX 파일을 첨부하세요.")
        raw = item.get("data")
        if not isinstance(raw, bytes):
            # A previously encoded draft is still verified rather than trusted.
            try:
                raw = base64.b64decode(item.get("content", ""), validate=True)
            except (ValueError, TypeError):
                raise ValidationError("첨부 파일 내용을 확인하세요.") from None
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise ValidationError("파일 한 개는 2 MiB 이내로 첨부하세요.")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValidationError("첨부 파일의 합계는 2 MiB 이내여야 합니다.")
        signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n",
                      ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8",
                      ".docx": b"PK", ".hwpx": b"PK", ".hwp": b"\xd0\xcf\x11\xe0"}
        if extension in signatures and not raw.startswith(signatures[extension]):
            raise ValidationError("파일의 형식과 확장자가 일치하지 않습니다.")
        output.append(dict(filename=filename, mime=ALLOWED_FILE_TYPES[extension], bytes=len(raw),
                           sha256=hashlib.sha256(raw).hexdigest(), content=base64.b64encode(raw).decode()))
    return output


def attachment_bytes(item):
    """Only call on a permission checked service result, never a client record."""
    data = base64.b64decode(item["content"], validate=True)
    if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise StorageError("파일 무결성을 확인하지 못했습니다.")
    return data


class WorkService:
    def __init__(self, classroom_service, legacy=None):
        self.service = classroom_service
        self.store = classroom_service.store
        self._legacy = legacy

    @property
    def legacy(self):
        if self._legacy is None:
            from . import legacy
            return legacy
        return self._legacy

    def _course(self, course_id, teacher=False, write=False):
        return self.service._course(course_id, teacher=teacher, write=write)

    def _actor(self):
        return self.service.actor()

    def _teacher(self, course):
        actor = self._actor()
        return actor.get("role") == "teacher" and actor["id"] in course.get("teacher_ids", [])

    def _write(self, namespace, record_id, change, action, course_id, teacher=False):
        for attempt in range(5):
            self._course(course_id, teacher=teacher, write=True)
            old = self.store.get(namespace, record_id, fresh=True)
            # Next-term templates live atomically inside the copied course until
            # the first edit creates this resource's own CAS shard.
            embedded = self._embedded(namespace, course_id, record_id) if not old else None
            candidate = change(copy.deepcopy(old or embedded))
            if candidate is None:
                return copy.deepcopy(old)
            candidate.update(id=record_id, course_id=course_id)
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > MAX_SHARD_BYTES:
                raise ValidationError("이 기록의 저장 한도에 도달했습니다. 첨부 크기를 줄이거나 교사에게 문의하세요.")
            try:
                # Revalidate immediately before the durable CAS write too.
                self._course(course_id, teacher=teacher, write=True)
                return self.service._write(namespace, record_id, candidate,
                                           old.get("version") if old else None, action)
            except ConflictError:
                if attempt == 4:
                    raise ConflictError("다른 저장과 충돌했습니다. 입력은 유지됩니다. 다시 저장하세요.") from None

    def _records(self, namespace, course_id, *, fresh=False):
        course = self._course(course_id)
        records = {r["id"]: r for r in course.get("copied_" + namespace[:-1] + "_templates", [])}
        # Core uses plural namespace names in the embedded field.
        records.update({r["id"]: r for r in course.get("copied_" + namespace + "_templates", [])})
        # The shared tree/body cache is a discovery aid only. Re-read the
        # selected course's records before evaluating publication, recipients,
        # question privacy or observation sharing changed by another process.
        for discovered in self.store.list(namespace, fresh=fresh):
            if discovered.get("course_id") == course_id:
                current = self.store.get(namespace, discovered["id"], fresh=True)
                if current and current.get("course_id") == course_id:
                    records[current["id"]] = current
        return list(records.values())

    def _embedded(self, namespace, course_id, record_id):
        if namespace == "stream":
            # A distribution is published by one durable CAS write. Each board
            # gets its own identity; its first edit/comment materializes only
            # that board's override in the ordinary stream namespace.
            if not record_id.startswith(_DISTRIBUTION_POST_PREFIX):
                return None
            return next((row for row in self._distribution_posts(course_id)
                         if row["id"] == record_id), None)
        if namespace not in ("materials", "assignments"):
            return None
        course = self._course(course_id)
        rows = course.get("copied_" + namespace + "_templates", []) + course.get("copied_" + namespace[:-1] + "_templates", [])
        return next((r for r in rows if r.get("id") == record_id and r.get("course_id") == course_id), None)

    @staticmethod
    def _safe(record):
        result = copy.deepcopy(record)
        result.pop("audit", None)
        return result

    def _public_record(self, record):
        result = self._safe(record)
        if _disabled_activity(record):
            result.update(disabled=True, disabled_reason=DISABLED_ACTIVITY_MESSAGE)
        if self._actor()["role"] == "student":
            result.pop("target_student_ids", None)
        return result

    def _owned_record(self, namespace, record_id, course_id):
        self._course(course_id)
        record = self.store.get(namespace, record_id, fresh=True) or self._embedded(namespace, course_id, record_id)
        if not record or record.get("course_id") != course_id:
            raise PermissionDenied("자료가 없거나 접근 권한이 없습니다.")
        return record

    def _targets(self, course, ids):
        if not isinstance(ids, (list, tuple)) or any(not isinstance(i, str) for i in ids):
            raise ValidationError("배부 대상 학생을 확인하세요.")
        selected = list(dict.fromkeys(ids))
        if any(i not in course.get("student_ids", []) for i in selected):
            raise ValidationError("승인된 수업 참여자만 배부 대상으로 선택할 수 있습니다.")
        return selected

    def _visible(self, record, course):
        if self._teacher(course):
            return True
        actor = self._actor()
        if (record.get("distribution_id") or str(record.get("id", "")).startswith(_DISTRIBUTION_POST_PREFIX)):
            # Reassigning a classroom to another class must not redistribute
            # an earlier multi-class notice to the new class's students.
            original_class = str(record.get("distribution_class") or "").strip()
            if not original_class or original_class != str(course.get("class_name") or "").strip():
                return False
        return _released(record) and (not record.get("target_student_ids") or actor["id"] in record["target_student_ids"])

    def _public_post(self, record):
        result = self._safe(record)
        if self._actor()["role"] == "student":
            result.pop("distribution_id", None)
            result.pop("distribution_class", None)
        return result

    @staticmethod
    def _distribution_post(distribution, course_id):
        # Explicit projection excludes every sibling course, its class, and the
        # request/audit metadata even when this becomes a comment CAS shard.
        fields = ("title", "body", "published", "pinned", "comments_allowed", "publish_at",
                  "created_at", "updated_at", "author_id")
        post = {field: copy.deepcopy(distribution.get(field)) for field in fields}
        post.update(id=_DISTRIBUTION_POST_PREFIX + _identity(distribution["id"], course_id),
                    course_id=course_id, distribution_id=distribution["id"],
                    distribution_class=distribution.get("target_class_names", {}).get(course_id, ""),
                    comments=[])
        return post

    def _distribution_posts(self, course_id):
        self._course(course_id)
        result = []
        # Discover new distributions and re-read their current scope before
        # projection, including when another app process populated our cache.
        for discovered in self.store.list("stream_distributions", fresh=True):
            current = self.store.get("stream_distributions", discovered["id"], fresh=True)
            if current and course_id in current.get("target_course_ids", []):
                result.append(self._distribution_post(current, course_id))
        return result

    def distribute_post(self, course_ids, title, body, *, request_id, published=True,
                        pinned=False, comments_allowed=True, publish_at=None):
        """Publish one immutable notice to an explicit snapshot of class boards.

        One record makes publication atomic across every selected board. A
        stable teacher/request identity makes a lost-response retry harmless;
        later course-specific edits and comments remain independent stream
        records and never change the other classes' copies.
        """
        actor = self.service.require_teacher()
        request_id = _text(request_id, "작업 번호", 128)
        if (not isinstance(course_ids, (list, tuple)) or not course_ids
                or len(course_ids) > MAX_ANNOUNCEMENT_COURSES
                or any(not isinstance(cid, str) or not cid.strip() or len(cid) > 300 for cid in course_ids)):
            raise ValidationError(f"공지 대상 수업을 1~{MAX_ANNOUNCEMENT_COURSES}개 선택하세요.")
        selected = sorted(set(course_ids))
        fields = dict(title=_text(title, "공지 제목", 160), body=_text(body, "공지 내용"),
                      published=bool(published), pinned=bool(pinned), comments_allowed=bool(comments_allowed),
                      publish_at=_instant(publish_at, "공개 시각"))
        distribution_id = _identity("stream-distribution", actor["id"], request_id)

        def authorized_classes():
            classes = {}
            for course_id in selected:
                course = self._course(course_id, teacher=True, write=True)
                class_name = str(course.get("class_name") or "").strip()
                if not class_name:
                    raise ValidationError("대상 학급이 지정된 수업에만 공지를 함께 게시할 수 있습니다.")
                classes[course_id] = class_name
            return classes

        classes = authorized_classes()
        for attempt in range(5):
            current = self.store.get("stream_distributions", distribution_id, fresh=True)
            if current:
                expected = dict(fields, author_id=actor["id"], request_id=request_id,
                                target_course_ids=selected)
                if any(current.get(key) != value for key, value in expected.items()):
                    raise ValidationError("같은 작업 번호의 공지 내용이나 대상 수업이 다릅니다. 새 공지로 작성하세요.")
                # The original snapshot remains immutable on retries, including
                # a class rename or a teacher's individual edit/withdrawal.
                authorized_classes()
                return dict(distribution_id=distribution_id, request_id=request_id,
                            target_course_ids=list(current["target_course_ids"]), complete=True)
            record = dict(fields, id=distribution_id, author_id=actor["id"], request_id=request_id,
                          target_course_ids=selected, target_class_names=classes, created_at=now())
            try:
                fresh_classes = authorized_classes()
                if fresh_classes != classes:
                    raise ConflictError("대상 학급이 변경되었습니다. 수업 목록을 다시 확인하고 게시하세요.")
                self.service._write("stream_distributions", distribution_id, record, None, "stream.distribute")
                return dict(distribution_id=distribution_id, request_id=request_id,
                            target_course_ids=selected, complete=True)
            except ConflictError:
                if attempt == 4:
                    raise ConflictError("다른 저장과 충돌했습니다. 입력은 유지됩니다. 다시 저장하세요.") from None

    def save_post(self, course_id, title, body, *, post_id=None, published=False,
                  pinned=False, comments_allowed=True, publish_at=None):
        self._course(course_id, teacher=True, write=True)
        fields = dict(title=_text(title, "공지 제목", 160), body=_text(body, "공지 내용"),
                      published=bool(published), pinned=bool(pinned), comments_allowed=bool(comments_allowed),
                      publish_at=_instant(publish_at, "공개 시각"))
        post_id = post_id or uuid.uuid4().hex
        def change(old):
            if old and old.get("course_id") != course_id:
                raise PermissionDenied("다른 수업의 공지를 수정할 수 없습니다.")
            if not old and post_id.startswith(_DISTRIBUTION_POST_PREFIX):
                raise PermissionDenied("이 수업의 공지가 아닙니다.")
            return dict(old or {}, **fields, created_at=(old or {}).get("created_at", now()), updated_at=now(),
                        author_id=(old or {}).get("author_id", self._actor()["id"]))
        return self._public_post(self._write("stream", post_id, change, "stream.save", course_id, teacher=True))

    def posts(self, course_id):
        course = self._course(course_id)
        # Other app workers can publish after this worker cached the tree.
        # Discover new IDs while keeping every result scoped to this course.
        records = {row["id"]: row for row in self._distribution_posts(course_id)}
        records.update({row["id"]: row for row in self._records("stream", course_id, fresh=True)})
        return sorted([self._public_post(r) for r in records.values() if self._visible(r, course)],
                      key=lambda r: (r.get("pinned", False), r.get("created_at", "")), reverse=True)

    def add_comment(self, course_id, post_id, body, request_id):
        text = _text(body, "댓글", 2000)
        request_id = _text(request_id, "작업 번호", 128)
        def change(old):
            course = self._course(course_id, write=True)
            if not old or old.get("course_id") != course_id or not self._visible(old, course):
                raise PermissionDenied("공지를 볼 수 없습니다.")
            if not old.get("comments_allowed") or not course.get("comments_enabled", True):
                raise PermissionDenied("이 공지는 댓글을 허용하지 않습니다.")
            comments = old.setdefault("comments", [])
            actor_id = self._actor()["id"]
            existing = next((c for c in comments if c["request_id"] == request_id and c["author_id"] == actor_id), None)
            if existing:
                if existing["body"] != text:
                    raise ValidationError("같은 작업 번호의 댓글 내용이 다릅니다.")
                return None
            if len(comments) >= 200:
                raise ValidationError("이 공지의 댓글 한도에 도달했습니다.")
            comments.append(dict(id=uuid.uuid4().hex, request_id=request_id, author_id=actor_id, body=text, created_at=now()))
            return old
        return self._public_post(self._write("stream", post_id, change, "stream.comment", course_id))

    def save_material(self, course_id, title, *, body="", unit="", url="", files=None,
                      activity_id="", material_id=None, published=False, publish_at=None,
                      target_student_ids=()):
        course = self._course(course_id, teacher=True, write=True)
        url = _text(url, "자료 링크", 2000, False)
        if url and (urlsplit(url).scheme not in ("https", "http") or not urlsplit(url).netloc or urlsplit(url).username):
            raise ValidationError("자료 링크는 http 또는 https 주소로 입력하세요.")
        if activity_id:
            raise ValidationError("외부 활동 연결은 제거되었습니다. 설명, 파일 또는 링크를 등록하세요.")
        attachments = prepare_attachments(files)
        fields = dict(title=_text(title, "자료 제목", 160), body=_text(body, "자료 설명", required=False),
                      unit=_text(unit, "단원", 160, False), url=url, attachments=attachments,
                      published=bool(published), publish_at=_instant(publish_at, "공개 시각"),
                      target_student_ids=self._targets(course, target_student_ids))
        if not (body.strip() or url or attachments):
            raise ValidationError("설명, 파일 또는 링크를 등록하세요.")
        material_id = material_id or uuid.uuid4().hex
        def change(old):
            if old and old.get("course_id") != course_id:
                raise PermissionDenied("다른 수업의 자료를 수정할 수 없습니다.")
            if old and _disabled_activity(old):
                raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
            return dict(old or {}, **fields, created_at=(old or {}).get("created_at", now()), updated_at=now())
        return self._safe(self._write("materials", material_id, change, "material.save", course_id, teacher=True))

    def materials(self, course_id):
        course = self._course(course_id)
        # Another app worker may have distributed a new material since this
        # worker last cached the repository tree. Discover its ID immediately.
        return [self._public_record(r) for r in self._records("materials", course_id, fresh=True) if self._visible(r, course)]

    list_materials = materials

    def publish_material(self, course_id, material_id):
        """Distribute an existing draft without replacing its files or targets."""
        def change(old):
            if not old or old.get("course_id") != course_id:
                raise PermissionDenied("자료가 없거나 접근 권한이 없습니다.")
            if _disabled_activity(old):
                raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
            if old.get("published"):
                return None
            old.update(published=True, updated_at=now())
            return old
        return self._safe(self._write("materials", material_id, change, "material.publish", course_id, teacher=True))

    def save_assignment(self, course_id, title, instructions, *, assignment_id=None, kind="assignment",
                        methods=("text",), max_points=None, rubric=(), due_at=None, publish_at=None,
                        published=False, allow_late=True, resubmit_policy="requested", target_student_ids=(),
                        activity_id="", material_ids=()):
        course = self._course(course_id, teacher=True, write=True)
        if kind not in ("assignment", "quiz", "performance"):
            raise ValidationError("과제 유형을 확인하세요.")
        if not isinstance(methods, (list, tuple)) or not methods or any(m not in ("text", "file") for m in methods):
            raise ValidationError("텍스트 또는 파일 제출 방식을 선택하세요.")
        if resubmit_policy not in ("always", "requested", "never"):
            raise ValidationError("재제출 정책을 확인하세요.")
        maximum = _number(max_points, "배점")
        if not isinstance(rubric, (list, tuple)) or len(rubric) > 12:
            raise ValidationError("평가 기준은 최대 12개입니다.")
        criteria = []
        for row in rubric:
            if not isinstance(row, dict):
                raise ValidationError("평가 기준을 확인하세요.")
            criteria.append(dict(label=_text(row.get("label", ""), "평가 요소", 300),
                                 max_points=_number(row.get("max_points"), "요소 배점")))
        if maximum is not None and criteria and all(r["max_points"] is not None for r in criteria):
            if abs(sum(r["max_points"] for r in criteria) - maximum) > 0.00001:
                raise ValidationError("평가 요소 배점 합계가 과제 배점과 일치해야 합니다.")
        if activity_id:
            raise ValidationError("외부 활동 연결은 제거되었습니다. 텍스트 또는 파일 과제를 등록하세요.")
        if not isinstance(material_ids, (list, tuple)):
            raise ValidationError("연결 자료를 확인하세요.")
        for material_id in material_ids:
            material = self._owned_record("materials", material_id, course_id)
            if _disabled_activity(material):
                raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
        publication, due = _instant(publish_at, "공개 시각"), _instant(due_at, "마감 시각")
        if publication and due and due < publication:
            raise ValidationError("마감 시각은 공개 시각 이후로 설정하세요.")
        fields = dict(title=_text(title, "과제 제목", 160), instructions=_text(instructions, "과제 안내"), kind=kind,
                      methods=list(dict.fromkeys(methods)), max_points=maximum, rubric=criteria, due_at=due,
                      publish_at=publication, published=bool(published), allow_late=bool(allow_late),
                      resubmit_policy=resubmit_policy, target_student_ids=self._targets(course, target_student_ids),
                      material_ids=list(dict.fromkeys(material_ids)))
        assignment_id = assignment_id or uuid.uuid4().hex
        def change(old):
            if old and old.get("course_id") != course_id:
                raise PermissionDenied("다른 수업의 과제를 수정할 수 없습니다.")
            if old and _disabled_activity(old):
                raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
            return dict(old or {}, **fields, created_at=(old or {}).get("created_at", now()), updated_at=now())
        return self._safe(self._write("assignments", assignment_id, change, "assignment.save", course_id, teacher=True))

    def assignment(self, course_id, assignment_id):
        course = self._course(course_id)
        record = self._owned_record("assignments", assignment_id, course_id)
        if not self._visible(record, course):
            raise PermissionDenied("과제가 공개되지 않았거나 배부 대상이 아닙니다.")
        return self._public_record(record)

    def assignments(self, course_id):
        course = self._course(course_id)
        return [self._public_record(r) for r in self._records("assignments", course_id) if self._visible(r, course)]

    list_assignments = assignments

    def clone_assignment(self, source_course_id, assignment_id, target_course_id):
        self._course(source_course_id, teacher=True)
        self._course(target_course_id, teacher=True, write=True)
        source = self.assignment(source_course_id, assignment_id)
        if _disabled_activity(source):
            raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
        fields = {key: source.get(key) for key in ("kind", "methods", "max_points", "rubric", "allow_late", "resubmit_policy")}
        return self.save_assignment(target_course_id, source["title"], source["instructions"], **fields)

    def _student_context(self, course_id, assignment_id, student_id=None, write=False):
        course = self._course(course_id, write=write)
        actor = self._actor()
        student_id = student_id or actor["id"]
        if actor["id"] != student_id and not self._teacher(course):
            raise PermissionDenied("다른 학생의 답안에는 접근할 수 없습니다.")
        if student_id not in course.get("student_ids", []):
            raise PermissionDenied("승인된 수업 참여자의 기록만 확인할 수 있습니다.")
        assignment = self.assignment(course_id, assignment_id)
        if write and _disabled_activity(assignment):
            raise ValidationError(DISABLED_ACTIVITY_MESSAGE)
        if assignment.get("target_student_ids") and student_id not in assignment["target_student_ids"]:
            raise PermissionDenied("이 과제의 배부 대상이 아닙니다.")
        return course, assignment, student_id, _identity(course_id, assignment_id, student_id)

    @staticmethod
    def _payload(assignment, text, files):
        text = _text(text, "답안", 40000, False)
        attachments = prepare_attachments(files)
        if text and "text" not in assignment["methods"] or attachments and "file" not in assignment["methods"]:
            raise ValidationError("허용되지 않은 제출 방식입니다.")
        return dict(text=text, attachments=attachments)

    def save_draft(self, course_id, assignment_id, text="", files=None, *, expected_revision=None):
        _, assignment, sid, record_id = self._student_context(course_id, assignment_id, write=True)
        if self._actor().get("role") != "student":
            raise PermissionDenied("학생 본인만 답안을 작성할 수 있습니다.")
        payload = self._payload(assignment, text, files)
        def change(old):
            self._student_context(course_id, assignment_id, sid, write=True)
            old = old or dict(student_id=sid, assignment_id=assignment_id, versions=[], reviews={})
            revision = old.get("draft", {}).get("revision", 0)
            if expected_revision is not None and revision != expected_revision:
                raise ConflictError("다른 창에서 임시 저장한 답안이 있습니다. 새로 불러온 뒤 비교해 주세요.")
            old["draft"] = dict(payload, revision=revision + 1, saved_at=now(), permanent=True)
            return old
        saved = self._write("submissions", record_id, change, "submission.draft", course_id)
        return copy.deepcopy(saved["draft"])

    def submit(self, course_id, assignment_id, request_id, text="", files=None):
        _, assignment, sid, record_id = self._student_context(course_id, assignment_id, write=True)
        if self._actor().get("role") != "student":
            raise PermissionDenied("학생 본인만 제출할 수 있습니다.")
        request_id = _text(request_id, "제출 요청 번호", 128)
        payload = self._payload(assignment, text, files)
        if not payload["text"] and not payload["attachments"]:
            raise ValidationError("답안이나 첨부 파일을 작성한 뒤 제출하세요.")
        fingerprint = _identity(payload)
        def change(old):
            _, current_task, _, _ = self._student_context(course_id, assignment_id, sid, write=True)
            old = old or dict(student_id=sid, assignment_id=assignment_id, versions=[], reviews={})
            previous = next((v for v in old["versions"] if v["request_id"] == request_id), None)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValidationError("이미 사용한 제출 요청 번호의 답안이 다릅니다. 새 제출로 시도하세요.")
                return None
            # A stale form cannot bypass a policy or deadline the teacher changed.
            self._payload(current_task, payload["text"], payload["attachments"])
            submitted_at = now()
            late = bool(current_task.get("due_at") and submitted_at > current_task["due_at"])
            if late and not current_task.get("allow_late"):
                raise ValidationError("마감 시간이 지났고 늦은 제출이 허용되지 않았습니다.")
            if old["versions"]:
                policy = current_task["resubmit_policy"]
                if policy == "never" or policy == "requested" and not old.get("revision_requested"):
                    raise ValidationError("교사의 수정 요청이 있어야 다시 제출할 수 있습니다.")
            if len(old["versions"]) >= MAX_VERSIONS:
                raise ValidationError("제출 차수 한도(10회)에 도달했습니다.")
            version = dict(payload, number=len(old["versions"]) + 1, submitted_at=submitted_at,
                           submission_id=_identity(course_id, assignment_id, sid, request_id)[:32],
                           request_id=request_id, fingerprint=fingerprint, late=late,
                           assignment_version=current_task.get("version"), permanent=True,
                           assignment_snapshot={key: copy.deepcopy(current_task.get(key)) for key in
                               ("title", "instructions", "methods", "max_points", "rubric", "due_at")})
            old["versions"].append(version)
            old["revision_requested"] = False
            old.pop("draft", None)
            return old
        saved = self._write("submissions", record_id, change, "submission.submit", course_id)
        # Returned only after the store's synchronous durable CAS succeeded.
        return copy.deepcopy(next(v for v in saved["versions"] if v["request_id"] == request_id))

    def submission(self, course_id, assignment_id, student_id=None):
        course, assignment, sid, record_id = self._student_context(course_id, assignment_id, student_id)
        if _disabled_activity(assignment):
            return dict(source="disabled", disabled=True, disabled_reason=DISABLED_ACTIVITY_MESSAGE,
                        student_id=sid, assignment_id=assignment_id, versions=[], reviews={},
                        status="연결 비활성화", revision_requested=False)
        saved = self.store.get("submissions", record_id, fresh=True)
        if not saved:
            return dict(source="classroom", student_id=sid, assignment_id=assignment_id,
                        versions=[], reviews={}, status="미제출", revision_requested=False)
        result = self._safe(saved)
        if not self._teacher(course):
            # Draft feedback, grades, grader IDs and internal review history never
            # leave the service before an explicit publication transaction.
            result["reviews"] = {number: copy.deepcopy(review["published"])
                                 for number, review in result.get("reviews", {}).items() if review.get("published")}
            result.pop("notifications", None)
        result["source"] = "classroom"
        result["status"] = self.submission_status(result)
        return result

    @staticmethod
    def submission_status(record):
        versions = record.get("versions", [])
        if not versions:
            return "작성 중" if record.get("draft") else "미제출"
        if record.get("revision_requested"):
            return "수정 요청"
        latest = versions[-1]
        review = record.get("reviews", {}).get(str(latest["number"]), {})
        published = review.get("published", review)
        if published.get("review_status") == "reviewed":
            return "검토 완료"
        if len(versions) > 1:
            return "재제출 · 늦은 제출" if latest["late"] else "재제출"
        return "늦은 제출" if latest["late"] else "제출 완료"

    def download_submission(self, course_id, assignment_id, student_id, number, file_index):
        record = self.submission(course_id, assignment_id, student_id)
        version = next((v for v in record.get("versions", []) if v["number"] == number), None)
        if not version or type(file_index) is not int or not 0 <= file_index < len(version["attachments"]):
            raise PermissionDenied("첨부 파일이 없거나 접근할 수 없습니다.")
        attachment = version["attachments"][file_index]
        return dict(filename=attachment["filename"], mime=attachment["mime"], data=attachment_bytes(attachment))

    def download_material(self, course_id, material_id, file_index):
        course = self._course(course_id)
        material = self._owned_record("materials", material_id, course_id)
        if not self._visible(material, course) or type(file_index) is not int or not 0 <= file_index < len(material.get("attachments", [])):
            raise PermissionDenied("첨부 파일이 없거나 접근할 수 없습니다.")
        attachment = material["attachments"][file_index]
        return dict(filename=attachment["filename"], mime=attachment["mime"], data=attachment_bytes(attachment))

    def save_review(self, course_id, assignment_id, student_id, number, *, feedback="", score=None,
                    rubric_scores=(), review_status="in_review", score_status="draft", needs_check=False):
        self._course(course_id, teacher=True, write=True)
        _, assignment, sid, record_id = self._student_context(course_id, assignment_id, student_id, write=True)
        if review_status not in ("in_review", "reviewed") or score_status not in ("draft", "final"):
            raise ValidationError("검토·점수 상태를 확인하세요.")
        # Assessment remains tied to the criteria the student submitted against,
        # even if the teacher edits the assignment for a later attempt.
        existing_record = self.store.get("submissions", record_id, fresh=True)
        submitted_version = next((v for v in (existing_record or {}).get("versions", []) if v["number"] == number), None)
        if not submitted_version:
            raise PermissionDenied("평가할 제출 버전이 없습니다.")
        assessment = submitted_version.get("assignment_snapshot") or assignment
        maximum = assessment.get("max_points")
        score = _number(score, "점수", maximum if maximum is not None else 100000)
        if maximum is None and score is not None:
            raise ValidationError("무점수 과제에는 점수를 입력할 수 없습니다.")
        if needs_check and score == 0:
            raise ValidationError("판독 확인이 필요한 답안은 임의로 0점 처리하지 마세요.")
        if score_status == "final" and maximum is not None and score is None:
            raise ValidationError("점수를 입력한 뒤 확정하세요.")
        if not isinstance(rubric_scores, (list, tuple)) or len(rubric_scores) > len(assessment["rubric"]):
            raise ValidationError("평가 요소 점수를 확인하세요.")
        criteria = []
        for index, row in enumerate(rubric_scores):
            if not isinstance(row, dict):
                raise ValidationError("평가 요소별 결과를 확인하세요.")
            maximum_part = assessment["rubric"][index].get("max_points")
            criteria.append(dict(label=assessment["rubric"][index]["label"], level=_text(row.get("level", ""), "수준", 120, False),
                                 score=_number(row.get("score"), "요소 점수", maximum_part if maximum_part is not None else 100000),
                                 feedback=_text(row.get("feedback", ""), "요소 피드백", 2000, False)))
        if score_status == "final" and assessment["rubric"]:
            if len(criteria) != len(assessment["rubric"]):
                raise ValidationError("모든 평가 요소를 검토한 뒤 점수를 확정하세요.")
            if score is not None and all(c["score"] is not None for c in criteria) and abs(sum(c["score"] for c in criteria) - score) > 0.00001:
                raise ValidationError("평가 요소 점수 합계와 전체 점수가 일치해야 합니다.")
        draft = dict(feedback=_text(feedback, "피드백", required=False), score=score, rubric_scores=criteria,
                     review_status=review_status, score_status=score_status, needs_check=bool(needs_check),
                     saved_at=now(), teacher_id=self._actor()["id"])
        def change(old):
            self._student_context(course_id, assignment_id, sid, write=True)
            if not old or not any(v["number"] == number for v in old["versions"]):
                raise PermissionDenied("평가할 제출 버전이 없습니다.")
            entry = old.setdefault("reviews", {}).setdefault(str(number), {})
            entry["draft"] = draft
            return old
        saved = self._write("submissions", record_id, change, "review.draft", course_id, teacher=True)
        return copy.deepcopy(saved["reviews"][str(number)])

    def publish_review(self, course_id, assignment_id, student_id, number):
        self._course(course_id, teacher=True, write=True)
        _, _, sid, record_id = self._student_context(course_id, assignment_id, student_id, write=True)
        def change(old):
            self._student_context(course_id, assignment_id, sid, write=True)
            entry = (old or {}).get("reviews", {}).get(str(number))
            if not entry or not entry.get("draft"):
                raise ValidationError("평가 초안을 저장한 뒤 결과를 공개하세요.")
            draft = copy.deepcopy(entry["draft"])
            if draft["review_status"] != "reviewed":
                raise ValidationError("교사 검토를 완료한 뒤 결과를 공개하세요.")
            if entry.get("published") and all(entry["published"].get(k) == v for k, v in draft.items()):
                return None
            draft.update(published_at=now(), version=number)
            if entry.get("published"):
                entry.setdefault("history", []).append(entry["published"])
            entry["published"] = draft
            old.setdefault("notifications", []).append(dict(id=uuid.uuid4().hex, kind="feedback",
                student_id=sid, number=number, created_at=now(), message="피드백이 공개되었습니다."))
            return old
        saved = self._write("submissions", record_id, change, "review.publish", course_id, teacher=True)
        return copy.deepcopy(saved["reviews"][str(number)]["published"])

    def request_revision(self, course_id, assignment_id, student_id, reason):
        self._course(course_id, teacher=True, write=True)
        _, assignment, sid, record_id = self._student_context(course_id, assignment_id, student_id, write=True)
        reason = _text(reason, "수정 요청 사유", 2000)
        if assignment["resubmit_policy"] == "never":
            raise ValidationError("재제출 불가 정책을 먼저 변경하세요.")
        def change(old):
            self._student_context(course_id, assignment_id, sid, write=True)
            if not old or not old.get("versions"):
                raise ValidationError("제출된 답안이 없습니다.")
            old.update(revision_requested=True, revision_reason=reason)
            old.setdefault("notifications", []).append(dict(id=uuid.uuid4().hex, kind="revision",
                student_id=sid, created_at=now(), message=reason, number=old["versions"][-1]["number"]))
            return old
        return self._safe(self._write("submissions", record_id, change, "review.request_revision", course_id, teacher=True))

    def save_question(self, course_id, body, *, visibility="private", question_id=None):
        course = self._course(course_id, write=True)
        if visibility not in ("private", "course"):
            raise ValidationError("질문 공개 범위를 확인하세요.")
        if not course.get("comments_enabled", True) and not self._teacher(course):
            raise PermissionDenied("교사가 이 수업의 질문 작성을 중지했습니다.")
        body = _text(body, "질문", 5000)
        question_id = question_id or uuid.uuid4().hex
        def change(old):
            actor = self._actor()
            if old and (old.get("course_id") != course_id or old.get("student_id") != actor["id"]):
                raise PermissionDenied("다른 사람의 질문을 수정할 수 없습니다.")
            return dict(old or {}, body=body, visibility=visibility, student_id=actor["id"],
                        created_at=(old or {}).get("created_at", now()), resolved=False)
        return self._safe(self._write("questions", question_id, change, "question.save", course_id))

    def questions(self, course_id):
        course = self._course(course_id)
        actor_id = self._actor()["id"]
        return [self._safe(r) for r in self._records("questions", course_id)
                if self._teacher(course) or r.get("student_id") == actor_id or r.get("visibility") == "course"]

    def answer_question(self, course_id, question_id, body="", *, resolved=False):
        self._course(course_id, teacher=True, write=True)
        text = _text(body, "질문 답변", 5000, False)
        def change(old):
            if not old or old.get("course_id") != course_id:
                raise PermissionDenied("질문을 찾을 수 없습니다.")
            old.update(answer=text, resolved=bool(resolved), answered_at=now(), teacher_id=self._actor()["id"])
            return old
        return self._safe(self._write("questions", question_id, change, "question.answer", course_id, teacher=True))

    def save_reflection(self, course_id, body, *, assignment_id=None, lesson_id=None, legacy_ref=None):
        self._course(course_id, write=True)
        actor = self._actor()
        if actor.get("role") != "student":
            raise PermissionDenied("학생 본인만 성찰을 작성할 수 있습니다.")
        if assignment_id:
            self.assignment(course_id, assignment_id)
        course = self._course(course_id)
        if lesson_id and lesson_id not in {l.get("id") for l in course.get("lessons", [])}:
            raise ValidationError("연결할 차시를 확인하세요.")
        if legacy_ref:
            # A reference is validated through the adapter and contains no copied text.
            self.legacy.validate_reference(actor, course_id, "sudanote", legacy_ref)
            body = ""
        else:
            body = _text(body, "성찰", 10000)
        # The general "today" form retains one editable reflection per school
        # day; a later day must never replace the previous day's writing.
        day = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat() if not (assignment_id or lesson_id or legacy_ref) else None
        record_id = _identity(course_id, actor["id"], assignment_id, lesson_id, legacy_ref, day)
        def change(old):
            return dict(old or {}, student_id=actor["id"], body=body, assignment_id=assignment_id,
                        lesson_id=lesson_id, legacy_ref=legacy_ref, date=day, updated_at=now())
        return self._safe(self._write("reflections", record_id, change, "reflection.save", course_id))

    def reflections(self, course_id, student_id=None):
        course = self._course(course_id)
        actor_id = self._actor()["id"]
        if student_id and student_id != actor_id and not self._teacher(course):
            raise PermissionDenied("다른 학생의 성찰을 볼 수 없습니다.")
        return [self._safe(r) for r in self._records("reflections", course_id)
                if (self._teacher(course) or r.get("student_id") == actor_id)
                and (not student_id or r.get("student_id") == student_id)]

    def save_observation(self, course_id, student_id, body, *, observation_id=None,
                         shared_teacher_ids=(), assignment_id=None, legacy_ref=None):
        course = self._course(course_id, teacher=True, write=True)
        actor_id = self._actor()["id"]
        if student_id not in course["student_ids"] or any(t not in course["teacher_ids"] for t in shared_teacher_ids):
            raise PermissionDenied("관찰 대상과 공유 교사의 수업 권한을 확인하세요.")
        if assignment_id:
            self.assignment(course_id, assignment_id)
        if legacy_ref:
            reference = self.legacy.validate_reference(self._actor(), course_id, "observation", legacy_ref)
            if reference.get("student_id") != student_id:
                raise PermissionDenied("기존 관찰 기록과 연결 대상 학생이 일치하지 않습니다.")
            body = ""
        else:
            body = _text(body, "교사 개인 관찰", 10000)
        observation_id = observation_id or uuid.uuid4().hex
        def change(old):
            if old and (old.get("course_id") != course_id or old.get("teacher_id") != actor_id):
                raise PermissionDenied("관찰을 작성한 교사만 수정할 수 있습니다.")
            return dict(old or {}, student_id=student_id, teacher_id=actor_id, body=body,
                        shared_teacher_ids=list(dict.fromkeys(shared_teacher_ids)), assignment_id=assignment_id,
                        legacy_ref=legacy_ref, updated_at=now())
        return self._safe(self._write("observations", observation_id, change, "observation.save", course_id, teacher=True))

    def observations(self, course_id, student_id=None):
        self._course(course_id, teacher=True)
        actor_id = self._actor()["id"]
        return [self._safe(r) for r in self._records("observations", course_id)
                if (r.get("teacher_id") == actor_id or actor_id in r.get("shared_teacher_ids", []))
                and (not student_id or r.get("student_id") == student_id)]

    def notifications(self, course_id):
        """Derive the inbox from the same durable records as the underlying event."""
        course = self._course(course_id)
        actor_id = self._actor()["id"]
        if self._teacher(course):
            return []
        notices = []
        for assignment in self.assignments(course_id):
            if _disabled_activity(assignment):
                continue
            notices.append(dict(id="assignment:" + assignment["id"], kind="assignment", title=assignment["title"],
                                assignment_id=assignment["id"], created_at=assignment.get("publish_at") or assignment["created_at"],
                                message="새 과제가 공개되었습니다."))
            record = self.store.get("submissions", _identity(course_id, assignment["id"], actor_id), fresh=True)
            for notice in (record or {}).get("notifications", []):
                if notice.get("student_id") == actor_id:
                    notices.append(dict(notice, title=assignment["title"], assignment_id=assignment["id"]))
        return sorted(notices, key=lambda n: n["created_at"], reverse=True)

    def export_assignment(self, course_id, assignment_id):
        course = self._course(course_id, teacher=True)
        assignment = self.assignment(course_id, assignment_id)
        rows = []
        for sid in course["student_ids"]:
            if assignment["target_student_ids"] and sid not in assignment["target_student_ids"]:
                continue
            record = self.submission(course_id, assignment_id, sid)
            if record.get("disabled"):
                continue
            latest = record.get("versions", [])[-1:]
            number = latest[0]["number"] if latest else None
            entry = record.get("reviews", {}).get(str(number), {})
            draft = entry.get("draft", {})
            rows.append(dict(student_id=sid, status=record["status"], number=number,
                             submission_id=latest[0]["submission_id"] if latest else None,
                             submitted_at=latest[0]["submitted_at"] if latest else None,
                             review_status=draft.get("review_status", "unreviewed"), score=draft.get("score"),
                             score_status=draft.get("score_status", "draft"), published=bool(entry.get("published"))))
        return rows
