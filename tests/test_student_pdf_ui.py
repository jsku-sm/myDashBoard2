"""PDF answer uploads survive the student editor, submission and teacher view."""
import io
from types import SimpleNamespace
import zipfile

from PIL import Image
from pypdf import PdfWriter
import pytest
from streamlit.testing.v1 import AppTest

from snorkl_navigation import REQUESTED_COURSE
from think_app import classroom_ui, embedded
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager, now
from think_app.storage import MemoryStore


def pdf_file():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_file():
    output = io.BytesIO()
    Image.new("RGB", (20, 15), "white").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def pdf_ui(monkeypatch):
    store = MemoryStore()
    manager = CourseManager(store)
    cid = manager.create("PDF 수행평가", "#123456", ["1-1"])
    room = Classroom(store)
    aid = room.save_activity(cid, "PDF 답안", "풀이를 첨부하세요.", "모범 풀이", ["풀이를 설명한다."],
                             2, now()[:10], now()[:10])
    room.distribute_activity(aid)
    user = {"role": "student", "id": "10101", "name": "시험학생", "class": "1-1"}
    selected = []
    uploader_types, displayed_images = [], []
    file_uploader = classroom_ui.st.file_uploader
    show_image = classroom_ui.st.image

    def uploader(label, **kwargs):
        if label == "답안 이미지·PDF 첨부 · 최대 2개":
            uploader_types.append(kwargs["type"])
            return list(selected)
        return file_uploader(label, **kwargs)

    def image(raw, **kwargs):
        if isinstance(raw, bytes):
            assert not raw.startswith(b"%PDF-"), "A PDF must never reach the image renderer."
            displayed_images.append(raw)
        return show_image(raw, **kwargs)

    monkeypatch.setattr(classroom_ui.st, "file_uploader", uploader)
    monkeypatch.setattr(classroom_ui.st, "image", image)
    monkeypatch.setattr(embedded, "get_store", lambda settings: store)
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: Settings())
    monkeypatch.setattr(embedded, "_pdf_ui_user", user, raising=False)
    monkeypatch.setattr(classroom_ui, "_pdf_ui_room", room, raising=False)
    monkeypatch.setattr(classroom_ui, "_pdf_ui_aid", aid, raising=False)

    def student():
        app = AppTest.from_string("from think_app import embedded\nembedded.render(embedded._pdf_ui_user)\n")
        app.session_state[REQUESTED_COURSE] = cid
        return app.run()

    def teacher():
        return AppTest.from_string(
            "from think_app import classroom_ui as view\n"
            "from think_app.ai import AI\n"
            "from think_app.config import Settings\n"
            "view.attempt_view(view._pdf_ui_room, view._pdf_ui_room.attempts(view._pdf_ui_aid)[0], AI(Settings()))\n"
        ).run()

    return room, aid, selected, uploader_types, displayed_images, student, teacher


@pytest.mark.parametrize("with_image", [False, True])
def test_student_can_submit_pdf_and_teacher_downloads_the_original(pdf_ui, with_image):
    room, aid, selected, uploader_types, images, student, teacher = pdf_ui
    raw = pdf_file()
    selected.append(SimpleNamespace(name="학생풀이.pdf", getvalue=lambda: raw))
    if with_image:
        selected.append(SimpleNamespace(name="추가풀이.png", getvalue=image_file))
    app = student()
    assert not app.exception and not app.error
    assert uploader_types and all("pdf" in types for types in uploader_types)
    assert any("PDF 첨부 · 학생풀이.pdf" == item.value for item in app.caption)
    assert any(item.label == "저장한 원본 파일 내려받기" for item in app.get("download_button"))
    next(button for button in app.button if button.label == "작업 파일 준비").click().run()
    assert not app.exception and not app.error
    key = f"student_{aid}_1-1_10101_0_work_file"
    with zipfile.ZipFile(io.BytesIO(app.session_state[key])) as archive:
        assert archive.read("첨부풀이-1.pdf") == raw
        assert ("첨부풀이-2.jpg" in archive.namelist()) is with_image

    next(button for button in app.button if button.label == "답안 제출").click().run()
    assert not app.exception and not app.error
    attempt = room.attempts(aid)[0]
    assert attempt["text"] == "" and len(attempt["images"]) == int(with_image)
    assert len(attempt["upload_ids"]) == 1 + int(with_image)
    assert attempt["documents"][0]["filename"] == "학생풀이.pdf"
    teacher_app = teacher()
    assert not teacher_app.exception and not teacher_app.error
    assert any(item.label == "업로드한 원본 내려받기 · 학생풀이.pdf"
               for item in teacher_app.get("download_button"))
    assert bool(images) is with_image


def test_pdf_teacher_download_survives_removed_draft_metadata(pdf_ui):
    room, aid, selected, _, _, student, teacher = pdf_ui
    selected.append(SimpleNamespace(name="학생풀이.pdf", getvalue=pdf_file))
    app = student()
    next(button for button in app.button if button.label == "답안 제출").click().run()
    assert not app.exception and not app.error
    uid = room.attempts(aid)[0]["upload_ids"][0]
    room.store.transaction(lambda state: state["course_uploads"].pop(uid))
    teacher_app = teacher()
    assert not teacher_app.exception and not teacher_app.error
    assert any(item.label == "업로드한 원본 내려받기 · 학생풀이.pdf"
               for item in teacher_app.get("download_button"))
