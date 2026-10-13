"""Student PDF drafts preserve originals and the image upload ownership rules."""
import io

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app import classroom as classroom_module
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.storage import AppError, LocalStore, MemoryStore
from think_app.uploads import MAX_PDF_BYTES, UploadedFiles, upload_kind, validated_pdf


def pdf_bytes(pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("test-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_bytes(format="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (40, 30), "blue").save(output, format)
    return output.getvalue()


@pytest.fixture
def clock(monkeypatch):
    instant = ["2026-10-14T09:00:00+09:00"]
    monkeypatch.setattr(classroom_module, "now", lambda: instant[0])
    return instant


def published_activity(store):
    room = Classroom(store)
    cid = CourseManager(store).create("PDF 답안 평가", "#123456", ["1반", "2반"])
    aid = room.save_activity(cid, "풀이 설명", "2+2?", "4", ["풀이 근거"], 2,
                             "2026-10-14", "2026-10-14")
    room.distribute_activity(aid)
    return room, cid, aid


@pytest.fixture
def assessment(clock):
    store = MemoryStore()
    room, cid, aid = published_activity(store)
    return store, room, UploadedFiles(store), cid, aid


def save_pdf(files, aid, raw=None, **changes):
    values = dict(aid=aid, student_id="1001", name="학생", class_id="1반",
                  filename="풀이.pdf", raw=pdf_bytes() if raw is None else raw)
    values.update(changes)
    return files.save(**values)


def test_pdf_original_and_individual_metadata_survive_encrypted_restart(tmp_path, clock):
    key = Fernet.generate_key().decode()
    store = LocalStore(tmp_path, key)
    _, _, aid = published_activity(store)
    raw = pdf_bytes()
    record = save_pdf(UploadedFiles(store), aid, raw, filename="../풀이.PDF")
    assert record["filename"] == "풀이.PDF"
    assert record["kind"] == "pdf" and upload_kind(record) == "pdf"
    assert record["mime"] == record["original_mime"] == "application/pdf"
    assert record["original_ref"] == record["blob_ref"]
    assert record["sha256"] == record["original_sha256"]
    assert record["bytes"] == record["original_bytes"] == len(raw)
    assert not (tmp_path / (record["original_ref"] + ".enc")).read_bytes().startswith(b"%PDF-")
    assert b'"student_id": "1001"' not in (tmp_path / record["upload_file"]).read_bytes()
    restarted_store = LocalStore(tmp_path, key)
    restarted = UploadedFiles(restarted_store)
    assert restarted.get(record["id"], aid, "1001", "1반") == record
    assert restarted_store.get_uploaded_file(record) == record
    assert restarted.read(record, aid, "1001", "1반") == raw
    assert restarted.read(record["id"], aid, "1001", "1반", original=True) == raw


@pytest.mark.parametrize("pages", [1, 200])
def test_pdf_uses_one_blob_and_is_deduplicated_for_one_student(assessment, pages):
    store, _, files, _, aid = assessment
    raw = pdf_bytes(pages)
    first = save_pdf(files, aid, raw)
    assert files.read(first, aid, "1001", "1반") == validated_pdf(raw) == raw
    assert save_pdf(files, aid, raw, filename="다시올린답안.pdf") == first
    assert len(store.blobs) == len(store.read()["course_uploads"]) == len(store.uploads) == 1
    other = save_pdf(files, aid, raw, student_id="1002")
    assert other["id"] != first["id"] and other["blob_ref"] != first["blob_ref"]


@pytest.mark.parametrize("raw,message", [
    (b"", "PDF 파일을 선택"), (b"not a pdf", "PDF 파일 형식"),
    (b"%PDF-1.7\nnot a readable PDF", "PDF 파일을 읽지 못"),
    (pdf_bytes(0), "1~200쪽"), (pdf_bytes(201), "1~200쪽"),
    (pdf_bytes(encrypted=True), "암호 없이"),
    (b"%PDF-1.7\n" + b"x" * MAX_PDF_BYTES, "10MB"),
])
def test_invalid_oversized_empty_and_encrypted_pdf_never_publish(assessment, raw, message):
    store, _, files, _, aid = assessment
    with pytest.raises(AppError, match=message):
        validated_pdf(raw)
    with pytest.raises(AppError):
        save_pdf(files, aid, raw)
    assert not store.read().get("course_uploads") and not store.blobs and not store.uploads


def test_file_extension_and_content_cannot_impersonate_pdf(assessment):
    store, _, files, _, aid = assessment
    for name, raw in (("이미지.pdf", image_bytes()), ("문서.png", pdf_bytes())):
        with pytest.raises(AppError):
            files.save(aid, "1001", "학생", "1반", name, raw)
    assert not store.read().get("course_uploads") and not store.blobs


@pytest.mark.parametrize("identity", [
    {"student_id": "1002"}, {"class_id": "2반"}, {"preview": True}, {"aid": "b" * 32}
])
def test_pdf_read_rejects_another_student_class_preview_or_activity(assessment, identity):
    _, _, files, _, aid = assessment
    record = save_pdf(files, aid)
    values = dict(aid=aid, student_id="1001", class_id="1반")
    values.update(identity)
    with pytest.raises(AppError, match="다른 학생이나 활동"):
        files.read(record, **values)


def test_pdf_read_rejects_caller_tampered_metadata(assessment):
    _, _, files, _, aid = assessment
    record = save_pdf(files, aid)
    for field, value in (("filename", "정답.pdf"), ("blob_ref", "b" * 32),
                         ("kind", "image"), ("bytes", record["bytes"] + 1)):
        with pytest.raises(AppError, match="저장 내용과 다릅니다"):
            files.read(dict(record, **{field: value}), aid, "1001", "1반")


@pytest.mark.parametrize("change", ["hash", "size", "missing"])
def test_pdf_read_and_duplicate_save_refuse_corrupt_or_missing_blobs(assessment, change):
    store, _, files, _, aid = assessment
    raw = pdf_bytes()
    record = save_pdf(files, aid, raw)
    if change == "missing":
        del store.blobs[record["blob_ref"]]
    else:
        store.blobs[record["blob_ref"]] = (b"x" * len(raw) if change == "hash" else raw + b"extra")
    for original in (False, True):
        with pytest.raises(AppError, match="저장된 업로드 파일"):
            files.read(record, aid, "1001", "1반", original=original)
    with pytest.raises(AppError, match="저장된 업로드 파일"):
        save_pdf(files, aid, raw)


@pytest.mark.parametrize("format,name", [("PNG", "풀이.png"), ("JPEG", "풀이.jpg")])
def test_image_uploads_keep_normalization_and_legacy_records_without_kind(assessment, format, name):
    store, _, files, _, aid = assessment
    raw = image_bytes(format)
    record = files.save(aid, "1001", "학생", "1반", name, raw)
    assert record["kind"] == upload_kind(record) == "image"
    assert record["mime"] == "image/jpeg"
    assert files.read(record, aid, "1001", "1반", original=True) == raw
    with Image.open(io.BytesIO(files.read(record, aid, "1001", "1반"))) as image:
        assert image.format == "JPEG"
    store.transaction(lambda state: state["course_uploads"][record["id"]].pop("kind"))
    store.uploads[record["upload_file"]]["upload"].pop("kind")
    legacy = files.get(record["id"], aid, "1001", "1반")
    assert upload_kind(legacy) == "image"
    assert files.read(legacy, aid, "1001", "1반", original=True) == raw
    assert files.save(aid, "1001", "학생", "1반", name, raw) == legacy


def test_pdf_keeps_distribution_and_period_save_guard_but_can_be_read_later(assessment, clock):
    store, room, files, cid, aid = assessment
    draft = room.save_activity(cid, "미배포 문제", "문제", "답", ["기준"], 2,
                               "2026-10-14", "2026-10-14")
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는"):
        save_pdf(files, draft)
    assert not store.blobs
    record = save_pdf(files, aid)
    clock[0] = "2026-10-15T00:00:00+09:00"
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는"):
        save_pdf(files, aid)
    assert files.read(record, aid, "1001", "1반") == pdf_bytes()


def test_pdf_metadata_is_not_published_when_individual_file_storage_fails(assessment, monkeypatch):
    store, _, files, _, aid = assessment
    original_save = store.save_uploaded_file

    def fail_save(candidate):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "save_uploaded_file", fail_save)
    with pytest.raises(AppError, match="저장에 실패"):
        save_pdf(files, aid)
    assert not store.read().get("course_uploads") and not store.uploads
    monkeypatch.setattr(store, "save_uploaded_file", original_save)
    assert save_pdf(files, aid)["saved"]
    assert len(store.blobs) == len(store.uploads) == 1
