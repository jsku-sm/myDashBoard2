"""Submitted PDF answers retain bytes and are included in consented AI grading."""
import base64
import copy
import io
from types import SimpleNamespace
import zipfile

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app.ai import AI, Feedback
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager, now
from think_app.storage import AppError, LocalStore, MemoryStore, student_pdf_attachments
from think_app.uploads import UploadedFiles


def pdf_answer(large=False):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Subject": "student answer" + ("x" * 700_000 if large else "")})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_answer():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    return output.getvalue()


def assessment(store=None):
    store = MemoryStore() if store is None else store
    cid = CourseManager(store).create("PDF 수행평가", "#123456", ["1반", "2반"])
    room = Classroom(store)
    aid = room.save_activity(cid, "풀이 설명", "2+2의 값을 구하세요.", "4", ["풀이를 설명한다."],
                             2, now()[:10], None)
    room.distribute_activity(aid)
    return store, room, UploadedFiles(store), cid, aid


def upload_pdf(files, aid, raw=None):
    return files.save(aid, "1001", "학생", "1반", "학생풀이.pdf", pdf_answer() if raw is None else raw)


def submit_pdf(room, aid, record, consent=False, request="a" * 32):
    return room.submit(aid, "1001", "학생", "1반", "", [], consent, request, upload_ids=[record["id"]])


def test_pdf_only_answer_is_submitted_as_document_and_pdf_bytes_are_packaged():
    store, room, files, _, aid = assessment()
    raw = pdf_answer(large=True)
    assert len(raw) > 600_000
    record = upload_pdf(files, aid, raw)
    request = submit_pdf(room, aid, record)
    attempt = store.read()["course_attempts"][request]
    assert attempt["text"] == "" and attempt["images"] == []
    assert attempt["upload_ids"] == [record["id"]]
    assert attempt["documents"] == [record]
    assert student_pdf_attachments(store, attempt) == [(record, raw)]
    bundle = store.get_student_submission(attempt)
    assert bundle["submission"]["documents"] == [record]
    asset = bundle["assets"][record["blob_ref"]]
    assert asset["mime_type"] == "application/pdf"
    assert base64.b64decode(asset["base64"]) == raw
    assert asset["sha256"] == record["sha256"]


def test_pdf_snapshot_and_export_survive_encrypted_store_restart_and_shared_metadata_removal(tmp_path):
    key = Fernet.generate_key().decode()
    store, room, files, cid, aid = assessment(LocalStore(tmp_path, key))
    raw = pdf_answer()
    record = upload_pdf(files, aid, raw)
    request = submit_pdf(room, aid, record)
    attempt = store.read()["course_attempts"][request]
    snapshot = copy.deepcopy(attempt["documents"])
    store.transaction(lambda state: state["course_uploads"].pop(record["id"]))
    restarted = LocalStore(tmp_path, key)
    persisted = restarted.read()["course_attempts"][request]
    assert persisted["documents"] == snapshot
    assert student_pdf_attachments(restarted, persisted) == [(record, raw)]
    bundle = restarted.get_student_submission(persisted)
    assert base64.b64decode(bundle["assets"][record["blob_ref"]]["base64"]) == raw
    with zipfile.ZipFile(io.BytesIO(Classroom(restarted).export(cid, aid))) as archive:
        name = f"답안/{request}/첨부-1-학생풀이.pdf"
        assert archive.read(name) == raw
        assert not any(name.endswith(".jpg") for name in archive.namelist())
    assert raw not in (tmp_path / (record["blob_ref"] + ".enc")).read_bytes()


def test_pdf_evaluation_includes_every_page_as_one_file_input_after_consent():
    store, room, files, _, aid = assessment()
    raw = pdf_answer()
    record = upload_pdf(files, aid, raw)
    request = submit_pdf(room, aid, record, consent=True)
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_parsed=Feedback.model_validate({
            "correctness": "correct", "explanation_score": 4,
            "praise": "근거를 설명했습니다.", "observation": "두 수를 더했습니다.",
            "hint": "계산을 다시 확인하세요.", "next_question": "다른 방법으로 설명할까요?",
            "criteria": [{"criterion": "풀이를 설명한다.", "level": "met", "evidence": "PDF의 풀이"}],
            "misconceptions": [], "needs_teacher_review": False, "uncertainty_reason": "",
        }))

    ai = AI(Settings(ai_enabled=True, api_key="mock-test-key"),
            client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    # Submitted documents retain their original snapshot even if the editable
    # shared draft metadata later changes or disappears.
    store.transaction(lambda state: state["course_uploads"].pop(record["id"]))
    room.evaluate(request, ai)
    assert len(calls) == 1 and calls[0]["store"] is False
    content = calls[0]["input"][1]["content"]
    assert not any(item["type"] == "input_image" for item in content)
    pdf = next(item for item in content if item["type"] == "input_file")
    assert pdf == {"type": "input_file", "filename": "학생풀이.pdf",
                   "file_data": "data:application/pdf;base64," + base64.b64encode(raw).decode()}
    assert store.read()["course_attempts"][request]["feedback"]["correctness"] == "correct"


def test_pdf_evaluation_does_not_call_ai_without_student_consent():
    store, room, files, _, aid = assessment()
    request = submit_pdf(room, aid, upload_pdf(files, aid), consent=False)
    ai = SimpleNamespace(available=True, feedback=lambda *args, **kwargs: pytest.fail("Consent is required"))
    with pytest.raises(AppError, match="동의"):
        room.evaluate(request, ai)
    assert store.read()["course_attempts"][request]["feedback"] is None


def test_legacy_image_answers_keep_three_argument_feedback_and_jpg_export():
    store, room, files, cid, aid = assessment()
    record = files.save(aid, "1001", "학생", "1반", "사진.png", image_answer())
    store.transaction(lambda state: state["course_uploads"][record["id"]].pop("kind"))
    legacy = store.read()["course_uploads"][record["id"]]
    normalized = files.read(legacy, aid, "1001", "1반")
    request = room.submit(aid, "1001", "학생", "1반", "", [], True, "b" * 32, upload_ids=[record["id"]])
    attempt = store.read()["course_attempts"][request]
    assert attempt["documents"] == [] and attempt["images"] == [record["blob_ref"]]
    calls = []

    def feedback(task, actual, images):
        calls.append((task, actual, images))
        return {"correctness": "correct"}

    room.evaluate(request, SimpleNamespace(available=True, feedback=feedback))
    assert len(calls) == 1 and calls[0][2] == [normalized]
    with zipfile.ZipFile(io.BytesIO(room.export(cid, aid))) as archive:
        assert archive.read(f"답안/{request}/1.jpg") == normalized
        assert not any(name.endswith(".pdf") for name in archive.namelist())


@pytest.mark.parametrize("identity", [("1002", "1반", False), ("1001", "2반", False), ("1001", "1반", True)])
def test_pdf_upload_cannot_be_submitted_by_another_identity(identity):
    store, room, files, _, aid = assessment()
    record = upload_pdf(files, aid)
    student_id, class_id, preview = identity
    with pytest.raises(AppError, match="다른 학생이나 활동"):
        room.submit(aid, student_id, "학생", class_id, "", [], False, "c" * 32,
                    preview=preview, upload_ids=[record["id"]])
    assert not store.read().get("course_attempts")


def test_pdf_integrity_is_rechecked_when_submission_metadata_is_committed(monkeypatch):
    store, room, files, _, aid = assessment()
    record = upload_pdf(files, aid)
    drawing = files.save(aid, "1001", "학생", "1반", "사진.png", image_answer())
    put_blob = store.put_blob
    changed = False

    def corrupt_pdf_during_drawing_save(name, raw):
        nonlocal changed
        put_blob(name, raw)
        if not changed:
            changed = True
            put_blob(record["blob_ref"], b"corrupt")

    monkeypatch.setattr(store, "put_blob", corrupt_pdf_during_drawing_save)
    with pytest.raises(AppError, match="확인"):
        room.submit(aid, "1001", "학생", "1반", "", [files.read(drawing, aid, "1001", "1반")],
                    False, "d" * 32, upload_ids=[record["id"]])
    assert changed and not store.read().get("course_attempts")
