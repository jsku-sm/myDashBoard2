"""Teacher question documents and pasted images in the encrypted course store."""
import base64
import binascii
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image

from .ai import normalized_image
from .courses import now
from .storage import AppError


MAX_FILE_BYTES = 10_000_000
MAX_FILES = 5
FILE_TYPES = ["pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "webp", "gif"]
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_MIMES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
DATA_URI = re.compile(r"data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/]*={0,2})\Z")
MAX_DATA_URI_CHARS = 4 * ((MAX_FILE_BYTES + 2) // 3) + 40
_question_capture = None


def _capture_component(**kwargs):
    from streamlit.components.v1 import declare_component
    global _question_capture
    if _question_capture is None:
        _question_capture = declare_component("think_question_capture", path=str(Path(__file__).parent / "question_capture"))
    return _question_capture(**kwargs)


def owned_question_files(state, selected, course_id):
    """Resolve stored course records rather than accepting caller-selected blobs."""
    if not isinstance(selected, (list, tuple)) or len(selected) > MAX_FILES:
        raise AppError("문제 파일은 최대 5개까지 첨부하세요.")
    if course_id not in state.get("courses", {}):
        raise AppError("문제 파일을 저장한 수업을 찾을 수 없습니다.")
    records, seen = [], set()
    for value in selected:
        file_id = value.get("id") if isinstance(value, dict) else value
        if not isinstance(file_id, str) or not re.fullmatch(r"[a-f0-9]{32}", file_id):
            raise AppError("문제 파일 식별자를 확인하세요.")
        if file_id in seen:
            raise AppError("같은 문제 파일을 중복 첨부할 수 없습니다.")
        seen.add(file_id)
        record = state.get("course_question_files", {}).get(file_id)
        if not isinstance(record, dict) or not record.get("saved"):
            raise AppError("저장된 문제 파일을 찾을 수 없습니다. 다시 업로드하세요.")
        if record.get("course_id") != course_id:
            raise AppError("다른 수업의 문제 파일을 사용할 수 없습니다.")
        if isinstance(value, dict) and value != record:
            raise AppError("문제 파일이 저장 내용과 다릅니다. 다시 업로드하세요.")
        records.append(copy.deepcopy(record))
    return records


def _filename(value):
    if not isinstance(value, str):
        raise AppError("문제 파일 이름을 확인하세요.")
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = "".join(character for character in value if character.isprintable()).strip()
    if not value or len(value) > 200 or Path(value).suffix.lower().lstrip(".") not in FILE_TYPES:
        raise AppError("문제 파일은 PDF, DOCX, TXT, MD 또는 이미지로 올려주세요. 파일 이름은 200자 이내로 설정하세요.")
    return value


def _document_mime(raw, suffix):
    if suffix in (".txt", ".md"):
        encodings = ["utf-16"] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "cp949"]
        for encoding in encodings:
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise AppError("문제 텍스트 파일은 UTF-8 또는 한글(CP949)로 저장해 주세요.")
        if not text.strip() or any(ord(character) < 32 and character not in "\n\r\t" for character in text):
            raise AppError("문제 텍스트 파일에 읽을 수 있는 글이 없습니다. 파일 형식을 확인하세요.")
        return "text/markdown" if suffix == ".md" else "text/plain"
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise AppError("문제 PDF 파일 형식이 올바르지 않습니다.")
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError:
            raise AppError("PDF 기능을 사용할 수 없습니다. 이미지 또는 DOCX 파일로 올려주세요.") from None
        try:
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise AppError("문제 PDF는 암호 없이 저장한 파일로 올려주세요.")
            if not 1 <= len(reader.pages) <= 200:
                raise AppError("문제 PDF는 1~200쪽으로 올려주세요.")
        except AppError:
            raise
        except (PdfReadError, ValueError, TypeError, KeyError, OSError, RuntimeError, RecursionError):
            raise AppError("문제 PDF 파일을 읽지 못했습니다. 다시 저장한 파일로 올려주세요.") from None
        return "application/pdf"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 4_000_000:
                raise AppError("문제 Word 문서가 너무 큽니다. 필요한 부분만 별도 파일로 저장해 주세요.")
            with archive.open(info) as source:
                xml = source.read(4_000_001)
            if len(xml) > 4_000_000:
                raise AppError("문제 Word 문서가 너무 큽니다. 필요한 부분만 별도 파일로 저장해 주세요.")
        upper_xml = xml.replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
            raise ValueError()
        document = ET.fromstring(xml)
        if document.tag != "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document":
            raise ValueError()
    except AppError:
        raise
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError, ET.ParseError, ValueError, NotImplementedError):
        raise AppError("문제 Word 파일 형식을 확인하세요. DOCX로 다시 저장해 주세요.") from None
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class QuestionFiles:
    def __init__(self, store):
        self.store = store

    def save(self, course_id, raw, filename):
        if not isinstance(course_id, str) or not course_id:
            raise AppError("문제 파일을 저장할 수업을 확인하세요.")
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise AppError("문제로 첨부할 파일을 선택하세요.")
        if len(raw) > MAX_FILE_BYTES:
            raise AppError("문제 파일은 파일당 10MB 이하로 올려주세요.")
        filename, raw = _filename(filename), bytes(raw)
        suffix = Path(filename).suffix.lower()
        is_image = suffix in IMAGE_TYPES
        normalized = normalized_image(raw) if is_image else raw
        if is_image:
            with Image.open(io.BytesIO(raw)) as image:
                original_mime = IMAGE_MIMES.get(image.format)
            if not original_mime:
                raise AppError("문제 이미지는 PNG, JPG, WebP 또는 GIF로 올려주세요.")
        else:
            original_mime = _document_mime(raw, suffix)
        state = self.store.read()
        if course_id not in state.get("courses", {}):
            raise AppError("수업을 찾을 수 없습니다.")
        original_sha = hashlib.sha256(raw).hexdigest()
        identity = json.dumps(["teacher-question", course_id, original_sha], separators=(",", ":"))
        file_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
        if file_id in state.get("course_question_files", {}):
            record = self.get(file_id, course_id)
            self.read(record, course_id)
            self.read(record, course_id, original=True)
            return record
        original_ref = hashlib.sha256(("original:" + identity).encode()).hexdigest()[:32]
        blob_ref = hashlib.sha256(("normalized:" + identity).encode()).hexdigest()[:32] if is_image else original_ref
        candidate = dict(id=file_id, course_id=course_id, filename=filename, kind="image" if is_image else "document",
                         original_ref=original_ref, blob_ref=blob_ref, original_mime=original_mime,
                         mime="image/jpeg" if is_image else original_mime, original_sha256=original_sha,
                         sha256=hashlib.sha256(normalized).hexdigest(), original_bytes=len(raw), bytes=len(normalized),
                         created=now(), saved=True)
        try:
            self.store.put_blob(original_ref, raw)
            if is_image:
                self.store.put_blob(blob_ref, normalized)

            def change(current):
                if course_id not in current.get("courses", {}):
                    raise AppError("수업을 찾을 수 없습니다.")
                records = current.setdefault("course_question_files", {})
                if file_id in records:
                    return owned_question_files(current, [file_id], course_id)[0]
                records[file_id] = candidate
                return candidate

            return self.store.transaction(change)
        except OSError:
            raise AppError("문제 파일 저장에 실패했습니다. 다시 업로드하세요.") from None

    def get(self, file_id, course_id):
        return owned_question_files(self.store.read(), [file_id], course_id)[0]

    def read(self, metadata, course_id, original=False):
        record = owned_question_files(self.store.read(), [metadata], course_id)[0]
        ref, digest = ("original_ref", "original_sha256") if original else ("blob_ref", "sha256")
        limit = MAX_FILE_BYTES if original or record["kind"] != "image" else 600_000
        raw = self.store.get_blob(record[ref])
        if (not raw or len(raw) > limit or len(raw) != record["original_bytes" if original else "bytes"] or
                hashlib.sha256(raw).hexdigest() != record[digest]):
            raise AppError("저장된 문제 파일을 확인할 수 없습니다. 다시 업로드하세요.")
        return raw


def captured_question_files(value):
    """Validate the bounded component payload before decoding any image bytes."""
    if not isinstance(value, dict) or not isinstance(value.get("event_id"), str) or not re.fullmatch(
            r"[a-f0-9]{32}", value["event_id"]):
        raise AppError("문제 이미지 첨부 이벤트를 확인하세요.")
    files = value.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise AppError("문제 이미지는 한 번에 최대 5개까지 첨부하세요.")
    decoded = []
    for upload in files:
        if not isinstance(upload, dict):
            raise AppError("문제 이미지 첨부 형식을 확인하세요.")
        uri = upload.get("data_uri")
        if not isinstance(uri, str) or len(uri) > MAX_DATA_URI_CHARS:
            raise AppError("문제 이미지는 파일당 10MB 이하로 첨부하세요.")
        match = DATA_URI.fullmatch(uri)
        if not match or upload.get("type") != match.group(1):
            raise AppError("파일이나 캡처한 이미지를 첨부하세요. 웹 주소는 먼저 이미지 파일로 저장해 주세요.")
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except (ValueError, binascii.Error):
            raise AppError("문제 이미지 데이터를 읽지 못했습니다. 다시 첨부하세요.") from None
        size = upload.get("size")
        if type(size) is not int or not raw or size != len(raw) or len(raw) > MAX_FILE_BYTES:
            raise AppError("문제 이미지 파일의 크기를 확인하세요. 파일당 10MB 이하로 첨부하세요.")
        filename = _filename(upload.get("name"))
        if Path(filename).suffix.lower() not in IMAGE_TYPES:
            raise AppError("문제 영역에는 이미지 파일을 끌어 놓거나 캡처 이미지를 붙여넣으세요.")
        # Check content before publishing any files in a multi-image event.
        normalized_image(raw)
        with Image.open(io.BytesIO(raw)) as image:
            if IMAGE_MIMES.get(image.format) != match.group(1):
                raise AppError("문제 이미지의 형식과 파일 내용이 일치하지 않습니다.")
        decoded.append((filename, raw))
    return decoded


def question_file_key(form_key):
    return form_key + "_question_files"


def _attach_files(service, course_id, key, files):
    import streamlit as st
    current = owned_question_files(service.store.read(), st.session_state.get(key, []), course_id)
    existing = {record["original_sha256"] for record in current}
    incoming = {hashlib.sha256(raw).hexdigest() for _, raw in files}
    if len(current) + len(incoming - existing) > MAX_FILES:
        raise AppError("문제 파일은 최대 5개까지 첨부하세요. 기존 첨부를 제거한 뒤 다시 올려주세요.")
    for filename, raw in files:
        digest = hashlib.sha256(raw).hexdigest()
        if digest in existing:
            continue
        current.append(service.save(course_id, raw, filename))
        existing.add(digest)
        st.session_state[key] = current
    return current


def render_question_files(task, form_key, room, course_id):
    """Keep saved selected references while the teacher edits an activity."""
    import streamlit as st
    key = question_file_key(form_key)
    st.session_state.setdefault(key, list(task.get("question_files", [])))
    service = QuestionFiles(room.store)
    st.markdown("**문제 파일·이미지 첨부**")
    uploads = st.file_uploader("학생에게 제시할 문제 파일", type=FILE_TYPES, accept_multiple_files=True,
                               key=form_key + "_question_upload", help="최대 5개 · 파일당 10MB · PDF, DOCX, TXT, MD, PNG/JPG/WebP/GIF. HWP 또는 그림·도형이 포함된 Word 문제는 PDF나 이미지로 저장해 올려주세요.")
    incoming_key = key + "_incoming"
    incoming = [(upload.name, upload.getvalue()) for upload in (uploads or [])]
    digests = [hashlib.sha256(raw).hexdigest() for _, raw in incoming]
    previous = st.session_state.get(incoming_key, [])
    new_files = [item for item, digest in zip(incoming, digests) if digest not in previous]
    if new_files:
        try:
            _attach_files(service, course_id, key, new_files)
            st.session_state[incoming_key] = digests
        except AppError as error:
            st.error(str(error))
    elif previous != digests:
        st.session_state[incoming_key] = digests
    value = _capture_component(max_file_bytes=MAX_FILE_BYTES, max_files=MAX_FILES, key=form_key + "_question_capture", default=None)
    event_key = key + "_capture_event"
    if value is not None and (not isinstance(value, dict) or value.get("event_id") != st.session_state.get(event_key)):
        try:
            files = captured_question_files(value)
            _attach_files(service, course_id, key, files)
            st.session_state[event_key] = value["event_id"]
        except AppError as error:
            st.error(str(error))
    st.caption("첨부한 문제는 학생 화면에도 표시됩니다. 아래에서 첨부를 제거할 수 있습니다.")
    for record in list(st.session_state.get(key, [])):
        try:
            canonical = service.get(record.get("id"), course_id)
            if canonical != record:
                raise AppError("문제 파일이 저장 내용과 다릅니다. 다시 업로드하세요.")
            if record["kind"] == "image":
                st.image(service.read(record, course_id), caption=record["filename"], use_container_width=True)
            st.download_button("문제 원본 내려받기 · " + record["filename"], service.read(record, course_id, original=True),
                               file_name=record["filename"], mime=record["original_mime"], key=form_key + "_question_download_" + record["id"])
            if st.button("첨부 제거 · " + record["filename"], key=form_key + "_question_remove_" + record["id"]):
                st.session_state[key] = [item for item in st.session_state[key] if item["id"] != record["id"]]
                st.rerun()
        except AppError as error:
            st.error(str(error))
    return key


def display_question_files(store, task, teacher=False):
    """Display only the attachments of the task resolved by the classroom guard."""
    import streamlit as st
    selected = task.get("question_files", [])
    if not selected:
        return
    course_id = task.get("course_id")
    try:
        records = owned_question_files(store.read(), selected, course_id)
        if not teacher:
            # A task supplied by the student lookup must match its stored activity.
            canonical = store.read().get("course_activities", {}).get(task.get("id"))
            if (not canonical or canonical.get("course_id") != course_id or
                    canonical.get("question_files", []) != selected):
                raise AppError("이 활동에 배정된 문제 파일을 확인할 수 없습니다.")
        service = QuestionFiles(store)
        for record in records:
            if record["kind"] == "image":
                st.image(service.read(record, course_id), caption=record["filename"], use_container_width=True)
            st.download_button("문제 파일 내려받기 · " + record["filename"], service.read(record, course_id, original=True),
                               file_name=record["filename"], mime=record["original_mime"],
                               key=("teacher" if teacher else "student") + "_question_file_" + str(task.get("id")) + "_" + record["id"])
    except AppError as error:
        st.error(str(error))
