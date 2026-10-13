"""Question attachment ownership, integrity, persistence and input boundaries."""
import base64
import copy
import io
import sys
from types import SimpleNamespace
import zipfile

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app.courses import CourseManager
from think_app.question_files import (MAX_FILE_BYTES, QuestionFiles, captured_question_files,
                                     display_question_files, owned_question_files, render_question_files)
from think_app.storage import AppError, LocalStore, MemoryStore


def image_file(format="PNG"):
    result = io.BytesIO()
    Image.new("RGB", (48, 32), "#40765f").save(result, format)
    return result.getvalue()


def make_course(store, title="문제 파일 평가"):
    return CourseManager(store).create(title, "#123456", ["1반"])


def capture(raw=None, name="capture.png", mime="image/png"):
    raw = image_file() if raw is None else raw
    return {"event_id": "a" * 32, "files": [{"name": name, "size": len(raw), "type": mime,
            "data_uri": "data:" + mime + ";base64," + base64.b64encode(raw).decode()}]}


def test_question_original_and_normalized_image_survive_encrypted_store_restart(tmp_path):
    key = Fernet.generate_key().decode()
    store = LocalStore(tmp_path, key)
    course = make_course(store)
    raw = image_file()
    record = QuestionFiles(store).save(course, raw, "../문제.png")
    assert record["filename"] == "문제.png"
    assert record["original_mime"] == "image/png"
    assert record["mime"] == "image/jpeg"
    assert record["kind"] == "image"
    assert raw not in (tmp_path / (record["original_ref"] + ".enc")).read_bytes()
    restarted = QuestionFiles(LocalStore(tmp_path, key))
    assert restarted.get(record["id"], course) == record
    assert restarted.read(record, course, original=True) == raw
    with Image.open(io.BytesIO(restarted.read(record, course))) as image:
        assert image.format == "JPEG"


def test_questions_are_course_owned_canonical_and_deduplicated():
    store = MemoryStore()
    course, other = make_course(store), make_course(store, "다른 평가")
    files = QuestionFiles(store)
    raw = image_file()
    first = files.save(course, raw, "first.png")
    assert files.save(course, raw, "second.png") == first
    second = files.save(other, raw, "same.png")
    assert first["id"] != second["id"]
    assert owned_question_files(store.read(), [first["id"]], course) == [first]
    with pytest.raises(AppError, match="다른 수업"):
        files.read(first, other)
    tampered = dict(first, filename="changed.png", blob_ref=second["blob_ref"])
    with pytest.raises(AppError, match="저장 내용과 다릅니다"):
        files.read(tampered, course)
    with pytest.raises(AppError, match="중복"):
        owned_question_files(store.read(), [first, first], course)
    store.transaction(lambda state: state["course_question_files"].pop(first["id"]))
    with pytest.raises(AppError, match="다시 업로드"):
        files.read(first, course)


def test_corrupt_blobs_and_deleted_courses_are_not_returned():
    store = MemoryStore()
    course = make_course(store)
    files = QuestionFiles(store)
    record = files.save(course, image_file(), "problem.png")
    original = store.blobs[record["original_ref"]]
    store.blobs[record["original_ref"]] = b"corrupt"
    with pytest.raises(AppError, match="저장된 문제 파일"):
        files.read(record, course, original=True)
    store.blobs[record["original_ref"]] = original
    store.blobs[record["blob_ref"]] = b"corrupt"
    with pytest.raises(AppError, match="저장된 문제 파일"):
        files.read(record, course)
    store.transaction(lambda state: state["courses"].pop(course))
    with pytest.raises(AppError, match="수업을 찾을"):
        files.get(record["id"], course)


def test_document_uploads_keep_readable_originals_and_allow_scanned_pdf():
    store = MemoryStore()
    course = make_course(store)
    files = QuestionFiles(store)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = io.BytesIO()
    writer.write(pdf)
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>문제</w:t></w:r></w:p></w:body></w:document>')
    candidates = [("problem.pdf", pdf.getvalue(), "application/pdf"),
                  ("problem.docx", docx.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                  ("problem.txt", "문제를 해결하세요.".encode("cp949"), "text/plain"),
                  ("problem.md", "# 문제\n$x^2=4$".encode(), "text/markdown")]
    for name, raw, mime in candidates:
        record = files.save(course, raw, name)
        assert record["kind"] == "document"
        assert record["original_mime"] == mime
        assert files.read(record, course) == files.read(record, course, original=True) == raw


@pytest.mark.parametrize("name,raw", [("bad.exe", b"anything"), ("bad.pdf", b"fake pdf"),
                                      ("bad.docx", b"fake word"), ("bad.txt", b"\x00binary"),
                                      ("bad.png", b"fake image"), ("empty.txt", b"")])
def test_invalid_documents_and_images_never_publish_metadata(name, raw):
    store = MemoryStore()
    course = make_course(store)
    with pytest.raises(AppError):
        QuestionFiles(store).save(course, raw, name)
    assert not store.read().get("course_question_files")


def test_file_and_selection_limits_and_failure_before_metadata_publication():
    store = MemoryStore()
    course = make_course(store)
    files = QuestionFiles(store)
    with pytest.raises(AppError, match="10MB"):
        files.save(course, b"x" * (MAX_FILE_BYTES + 1), "large.txt")
    record = files.save(course, image_file(), "problem.png")
    with pytest.raises(AppError, match="최대 5개"):
        owned_question_files(store.read(), [record] * 6, course)
    failing = MemoryStore()
    failing_course = make_course(failing)
    calls = []

    def fail_second_blob(name, raw):
        calls.append(name)
        if len(calls) == 2:
            raise OSError("disk unavailable")
        failing.blobs[name] = raw

    failing.put_blob = fail_second_blob
    with pytest.raises(AppError, match="저장에 실패"):
        QuestionFiles(failing).save(failing_course, image_file(), "capture.png")
    assert not failing.read().get("course_question_files")


def test_word_entities_and_zip_bombs_are_rejected():
    store = MemoryStore()
    course = make_course(store)
    for xml in (b'<!DOCTYPE document [<!ENTITY example "bad">]><document/>', b"x" * 4_000_001):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", xml)
        with pytest.raises(AppError):
            QuestionFiles(store).save(course, raw.getvalue(), "problem.docx")
    assert not store.read().get("course_question_files")


def test_capture_validates_id_uri_mime_size_count_and_actual_image():
    value = capture()
    assert captured_question_files(value) == [("capture.png", image_file())]
    invalid = []
    bad = copy.deepcopy(value); bad["event_id"] = "../../blob"; invalid.append(bad)
    bad = copy.deepcopy(value); bad["files"] *= 6; invalid.append(bad)
    bad = copy.deepcopy(value); bad["files"][0]["size"] += 1; invalid.append(bad)
    bad = copy.deepcopy(value); bad["files"][0]["size"] = True; invalid.append(bad)
    bad = copy.deepcopy(value); bad["files"][0]["data_uri"] = "https://example.invalid/image.png"; invalid.append(bad)
    bad = copy.deepcopy(value); bad["files"][0]["type"] = "image/jpeg"; invalid.append(bad)
    invalid.append(capture(b"not an image"))
    invalid.append(capture(image_file("JPEG"), mime="image/png"))
    for candidate in invalid:
        with pytest.raises(AppError):
            captured_question_files(candidate)


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.uploads = []
        self.errors = []
        self.images = []
        self.downloads = []
        self.remove = False

    def file_uploader(self, *args, **kwargs):
        return self.uploads

    def markdown(self, *args, **kwargs): pass
    def caption(self, *args, **kwargs): pass
    def error(self, message): self.errors.append(message)
    def image(self, raw, **kwargs): self.images.append(raw)
    def download_button(self, label, raw, **kwargs): self.downloads.append((label, raw))
    def button(self, *args, **kwargs): return self.remove
    def rerun(self): pass


def test_native_upload_persists_before_save_and_removal_is_preserved_on_rerun(monkeypatch):
    import think_app.question_files as module
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    monkeypatch.setattr(module, "_capture_component", lambda **kwargs: None)
    store = MemoryStore()
    course = make_course(store)
    raw = image_file()
    fake.uploads = [SimpleNamespace(name="problem.png", getvalue=lambda: raw)]
    key = render_question_files({}, "form", SimpleNamespace(store=store), course)
    assert len(store.read()["course_question_files"]) == 1
    assert len(fake.session_state[key]) == 1
    fake.remove = True
    render_question_files({}, "form", SimpleNamespace(store=store), course)
    assert fake.session_state[key] == []
    fake.remove = False
    render_question_files({}, "form", SimpleNamespace(store=store), course)
    assert fake.session_state[key] == []
    assert not fake.errors


def test_capture_event_replay_does_not_readd_removed_attachment(monkeypatch):
    import think_app.question_files as module
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    event = capture()
    monkeypatch.setattr(module, "_capture_component", lambda **kwargs: event)
    store = MemoryStore()
    course = make_course(store)
    key = render_question_files({}, "capture", SimpleNamespace(store=store), course)
    assert len(fake.session_state[key]) == 1
    fake.remove = True
    render_question_files({}, "capture", SimpleNamespace(store=store), course)
    fake.remove = False
    render_question_files({}, "capture", SimpleNamespace(store=store), course)
    assert fake.session_state[key] == []
    assert not fake.errors


def test_student_presentation_rejects_files_from_another_activity_and_never_displays_answers(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    store = MemoryStore()
    course = make_course(store)
    files = QuestionFiles(store)
    question = files.save(course, image_file(), "problem.png")
    private = files.save(course, image_file("JPEG"), "private_answer.jpg")
    task = {"id": "b" * 32, "course_id": course, "question_files": [question], "expected_images": [private]}
    store.transaction(lambda state: state.setdefault("course_activities", {}).update({task["id"]: task}))
    display_question_files(store, task)
    assert len(fake.images) == len(fake.downloads) == 1
    assert fake.downloads[0][1] == image_file()
    assert not fake.errors
    fake.images.clear(); fake.downloads.clear()
    display_question_files(store, dict(task, question_files=[private]))
    assert not fake.images and not fake.downloads
    assert "배정된 문제 파일" in fake.errors[-1]
