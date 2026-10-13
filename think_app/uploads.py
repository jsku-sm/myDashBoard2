"""Durable image drafts, saved before a student submits an answer."""
import hashlib
import io
import json
import re

from PIL import Image

from .ai import normalized_image
from .courses import now
from .storage import AppError, uploaded_file_path


def _identity(student_id, name, class_id):
    if not all(isinstance(value, str) for value in (student_id, name, class_id)):
        raise AppError("파일 저장 전에 학급, 학번과 이름을 입력하세요.")
    student_id, name, class_id = student_id.strip(), name.strip(), class_id.strip()
    if not student_id or not name or not class_id or len(student_id) > 40 or len(name) > 40:
        raise AppError("파일 저장 전에 학번과 이름을 40자 이내로 입력하세요.")
    return student_id, name, class_id


def _activity(state, aid, class_id):
    task = state.get("course_activities", {}).get(aid)
    if not task:
        raise AppError("파일을 저장할 활동을 찾을 수 없습니다.")
    course = state.get("courses", {}).get(task["course_id"])
    if not course or class_id not in course.get("classes", []):
        raise AppError("파일을 저장할 참여 대상 학급을 확인하세요.")
    # Keep a draft even if the teacher's timer expired while the capture was
    # being made. Classroom.submit remains the authority for the deadline.
    if task.get("status") == "숨김" or task.get("start", "") > now()[:10]:
        raise AppError("현재 파일을 저장할 수 없는 활동입니다.")
    return task


def owned_uploads(state, upload_ids, aid, student_id, class_id, preview=False):
    """Resolve only published uploads belonging to this student's activity."""
    if not isinstance(upload_ids, (list, tuple)) or len(upload_ids) > 3:
        raise AppError("업로드 파일은 최대 3개까지 선택하세요.")
    if not all(isinstance(value, str) and value.strip() for value in (student_id, class_id)):
        raise AppError("업로드 파일의 학급과 학번을 확인하세요.")
    if any(not isinstance(upload_id, str) or not re.fullmatch(r"[a-f0-9]{32}", upload_id)
           for upload_id in upload_ids):
        raise AppError("업로드 파일 식별자를 확인하세요.")
    if len(set(upload_ids)) != len(upload_ids):
        raise AppError("같은 업로드 파일을 중복 선택할 수 없습니다.")
    uploads = []
    for upload_id in upload_ids:
        upload = state.get("course_uploads", {}).get(upload_id)
        if not upload or not upload.get("saved"):
            raise AppError("저장된 업로드 파일을 찾을 수 없습니다. 파일을 다시 올려주세요.")
        if (upload.get("activity_id") != aid or upload.get("student_id") != student_id.strip() or
                upload.get("class_id") != class_id.strip() or bool(upload.get("preview")) != bool(preview)):
            raise AppError("다른 학생이나 활동의 업로드 파일을 사용할 수 없습니다.")
        task = state.get("course_activities", {}).get(aid)
        if not task or upload.get("course_id") != task.get("course_id"):
            raise AppError("업로드 파일의 수업을 확인하세요.")
        uploads.append(upload.copy())
    return uploads


class UploadedFiles:
    def __init__(self, store):
        self.store = store

    def save(self, aid, student_id, name, class_id, filename, raw, preview=False):
        student_id, name, class_id = _identity(student_id, name, class_id)
        if not isinstance(aid, str) or not aid:
            raise AppError("파일을 저장할 활동을 확인하세요.")
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise AppError("업로드할 PNG 또는 JPG 파일을 선택하세요.")
        raw = bytes(raw)
        normalized = normalized_image(raw)
        with Image.open(io.BytesIO(raw)) as image:
            original_mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image.format)
        if not original_mime:
            raise AppError("PNG 또는 JPG 파일만 업로드할 수 있습니다.")
        if not isinstance(filename, str) or not filename.strip():
            raise AppError("업로드 파일 이름을 확인하세요.")
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        filename = "".join(character for character in filename if character.isprintable()).strip()
        if not filename or len(filename) > 200:
            raise AppError("업로드 파일 이름은 200자 이내로 설정하세요.")
        state = self.store.read()
        task = _activity(state, aid, class_id)
        original_sha = hashlib.sha256(raw).hexdigest()
        identity = json.dumps([task["course_id"], aid, class_id, student_id, bool(preview), original_sha],
                              ensure_ascii=False, separators=(",", ":"))
        upload_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
        existing = state.get("course_uploads", {}).get(upload_id)
        if existing:
            return owned_uploads(state, [upload_id], aid, student_id, class_id, preview)[0]
        original_ref = hashlib.sha256(("original:" + identity).encode()).hexdigest()[:32]
        blob_ref = hashlib.sha256(("normalized:" + identity).encode()).hexdigest()[:32]
        try:
            self.store.put_blob(original_ref, raw)
            self.store.put_blob(blob_ref, normalized)
        except OSError:
            raise AppError("업로드 파일 저장에 실패했습니다. 파일을 유지한 채 다시 시도하세요.") from None
        candidate = dict(id=upload_id, activity_id=aid, course_id=task["course_id"], student_id=student_id,
                         name=name, class_id=class_id, preview=bool(preview), filename=filename,
                         original_ref=original_ref, blob_ref=blob_ref, original_mime=original_mime,
                         mime="image/jpeg", original_sha256=original_sha,
                         sha256=hashlib.sha256(normalized).hexdigest(), original_bytes=len(raw),
                         bytes=len(normalized), created=now(), saved=True)
        candidate["upload_file"] = uploaded_file_path(candidate)

        def change(current_state):
            current_task = _activity(current_state, aid, class_id)
            if current_task["course_id"] != candidate["course_id"]:
                raise AppError("파일을 저장할 수업이 변경되었습니다. 다시 올려주세요.")
            uploads = current_state.setdefault("course_uploads", {})
            if upload_id in uploads:
                return owned_uploads(current_state, [upload_id], aid, student_id, class_id, preview)[0]
            # Save the individual file before publishing its shared record.
            # An interrupted state write can retry using the original metadata.
            saved = self.store.save_uploaded_file(candidate)
            uploads[upload_id] = saved
            return saved

        try:
            return self.store.transaction(change)
        except OSError:
            raise AppError("업로드 파일 저장에 실패했습니다. 파일을 유지한 채 다시 시도하세요.") from None

    def for_student(self, aid, student_id, class_id, preview=False):
        if not all(isinstance(value, str) and value.strip() for value in (student_id, class_id)):
            return []
        state = self.store.read()
        return sorted([upload.copy() for upload in state.get("course_uploads", {}).values()
                       if upload.get("saved") and upload.get("activity_id") == aid and
                       upload.get("student_id") == student_id.strip() and
                       upload.get("class_id") == class_id.strip() and
                       bool(upload.get("preview")) == bool(preview)], key=lambda upload: upload["created"])

    def get(self, upload_id, aid, student_id, class_id, preview=False):
        return owned_uploads(self.store.read(), [upload_id], aid, student_id, class_id, preview)[0]
