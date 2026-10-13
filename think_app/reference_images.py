"""Private teacher reference images stored in the existing encrypted blob store."""
import copy
import hashlib
import io
import json
import re
from urllib.parse import urlsplit

from PIL import Image

from .ai import normalized_image
from .courses import now
from .storage import AppError


def owned_reference_images(state, selected, course_id):
    """Resolve canonical course records; callers cannot choose arbitrary blobs."""
    if not isinstance(selected, (list, tuple)) or len(selected) > 3:
        raise AppError("모범답안 이미지는 최대 3개까지 첨부하세요.")
    records, seen = [], set()
    for value in selected:
        image_id = value.get("id") if isinstance(value, dict) else value
        if not isinstance(image_id, str) or not re.fullmatch(r"[a-f0-9]{32}", image_id):
            raise AppError("모범답안 이미지 식별자를 확인하세요.")
        if image_id in seen:
            raise AppError("같은 모범답안 이미지를 중복 첨부할 수 없습니다.")
        seen.add(image_id)
        record = state.get("course_reference_images", {}).get(image_id)
        if not record or not record.get("saved"):
            raise AppError("저장된 모범답안 이미지를 찾을 수 없습니다. 다시 업로드하세요.")
        if record.get("course_id") != course_id:
            raise AppError("다른 수업의 모범답안 이미지를 사용할 수 없습니다.")
        if isinstance(value, dict) and value != record:
            raise AppError("모범답안 이미지가 저장 내용과 다릅니다. 다시 확인하세요.")
        records.append(copy.deepcopy(record))
    return records


def _provenance(source_url, page_url, title):
    if not isinstance(title, str) or len(title) > 500:
        raise AppError("모범답안 이미지 제목은 500자 이내로 입력하세요.")
    urls = []
    for value in (source_url, page_url):
        if not isinstance(value, str) or len(value) > 4000:
            raise AppError("모범답안 이미지의 출처 주소를 확인하세요.")
        value = value.strip()
        try:
            parts = urlsplit(value)
            invalid = (value and (parts.scheme not in ("https", "http") or not parts.hostname or
                                  parts.username is not None or parts.password is not None))
        except ValueError:
            invalid = True
        if invalid or any(ord(character) < 32 for character in value):
            raise AppError("모범답안 이미지의 출처 주소를 확인하세요.")
        urls.append(value)
    return *urls, title.strip()


class ReferenceImages:
    def __init__(self, store):
        self.store = store

    def save(self, course_id, raw, filename, source_url="", title="", page_url=""):
        if not isinstance(course_id, str) or not course_id:
            raise AppError("모범답안 이미지를 저장할 수업을 확인하세요.")
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise AppError("모범답안으로 첨부할 이미지 파일을 선택하세요.")
        if not isinstance(filename, str) or not filename.strip():
            raise AppError("모범답안 이미지 파일 이름을 확인하세요.")
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        filename = "".join(character for character in filename if character.isprintable()).strip()
        if not filename or len(filename) > 200:
            raise AppError("모범답안 이미지 파일 이름은 200자 이내로 설정하세요.")
        source_url, page_url, title = _provenance(source_url, page_url, title)
        raw = bytes(raw)
        normalized = normalized_image(raw)
        with Image.open(io.BytesIO(raw)) as image:
            original_mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp",
                             "GIF": "image/gif"}.get(image.format)
        if not original_mime:
            raise AppError("모범답안은 PNG, JPG, WebP 또는 GIF 이미지로 첨부하세요.")
        state = self.store.read()
        if course_id not in state.get("courses", {}):
            raise AppError("수업을 찾을 수 없습니다.")
        original_sha = hashlib.sha256(raw).hexdigest()
        identity = json.dumps(["teacher-reference", course_id, original_sha], separators=(",", ":"))
        image_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
        if image_id in state.get("course_reference_images", {}):
            record = self.get(image_id, course_id)
            self.read(record, course_id)
            return record
        original_ref = hashlib.sha256(("original:" + identity).encode()).hexdigest()[:32]
        blob_ref = hashlib.sha256(("normalized:" + identity).encode()).hexdigest()[:32]
        candidate = dict(id=image_id, course_id=course_id, filename=filename,
                         original_ref=original_ref, blob_ref=blob_ref, original_mime=original_mime,
                         mime="image/jpeg", original_sha256=original_sha,
                         sha256=hashlib.sha256(normalized).hexdigest(), original_bytes=len(raw),
                         bytes=len(normalized), source_url=source_url, page_url=page_url, title=title,
                         created=now(), saved=True)
        try:
            # Publish the metadata only after both encrypted files are saved.
            self.store.put_blob(original_ref, raw)
            self.store.put_blob(blob_ref, normalized)

            def change(current):
                if course_id not in current.get("courses", {}):
                    raise AppError("수업을 찾을 수 없습니다.")
                records = current.setdefault("course_reference_images", {})
                if image_id in records:
                    return owned_reference_images(current, [image_id], course_id)[0]
                records[image_id] = candidate
                return candidate

            return self.store.transaction(change)
        except OSError:
            raise AppError("모범답안 이미지 저장에 실패했습니다. 다시 업로드하세요.") from None

    def get(self, image_id, course_id):
        return owned_reference_images(self.store.read(), [image_id], course_id)[0]

    def read(self, metadata, course_id, original=False):
        record = owned_reference_images(self.store.read(), [metadata], course_id)[0]
        ref, digest, limit = (("original_ref", "original_sha256", 12_000_000) if original else
                              ("blob_ref", "sha256", 600_000))
        raw = self.store.get_blob(record[ref])
        if not raw or len(raw) > limit or hashlib.sha256(raw).hexdigest() != record[digest]:
            raise AppError("저장된 모범답안 이미지를 확인할 수 없습니다. 다시 업로드하세요.")
        return raw
