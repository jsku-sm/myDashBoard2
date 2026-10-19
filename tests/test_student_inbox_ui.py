"""Saved answer uploads and submitted answers appear in the teacher inbox."""
import io
from types import SimpleNamespace

from cryptography.fernet import Fernet
from pypdf import PdfWriter
import pytest
from streamlit.testing.v1 import AppTest

from snorkl_navigation import REQUESTED_COURSE
from think_app import classroom_ui, embedded
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager, now
from think_app.storage import LocalStore, MemoryStore
from think_app.uploads import UploadedFiles


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def make_assessment(store):
    room = Classroom(store)
    manager = CourseManager(store)
    cid = manager.create("파일 제출 평가", "#123456", ["1-1", "1-2"])
    aid = room.save_activity(cid, "파일로 풀이 제출", "문제를 풀고 답안 파일을 올리세요.", "모범 풀이",
                             ["풀이 근거"], 2, now()[:10], now()[:10])
    room.distribute_activity(aid)
    return room, manager.get(cid), room.activity(aid)


@pytest.fixture
def inbox_ui(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    store = LocalStore(tmp_path, key)
    room, course, task = make_assessment(store)
    selected, downloads = [], []
    file_uploader = classroom_ui.st.file_uploader
    download_button = classroom_ui.st.download_button

    def uploader(label, **kwargs):
        if label == "답안 이미지·PDF 첨부 · 최대 2개":
            return list(selected)
        return file_uploader(label, **kwargs)

    def download(label, data, **kwargs):
        if label.startswith("업로드 파일 내려받기"):
            downloads.append((label, data, kwargs["file_name"], kwargs["mime"]))
        return download_button(label, data, **kwargs)

    ai = SimpleNamespace(available=True, settings=Settings())
    monkeypatch.setattr(classroom_ui.st, "file_uploader", uploader)
    monkeypatch.setattr(classroom_ui.st, "download_button", download)
    monkeypatch.setattr(embedded, "get_store", lambda settings: store)
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: Settings())
    monkeypatch.setattr(embedded, "_inbox_user", dict(
        id="10101", name="시험학생", role="student", **{"class": "1-1"}), raising=False)
    monkeypatch.setattr(classroom_ui, "_inbox_teacher_store", LocalStore(tmp_path, key), raising=False)
    monkeypatch.setattr(classroom_ui, "_inbox_course", course, raising=False)
    monkeypatch.setattr(classroom_ui, "_inbox_task", task, raising=False)
    monkeypatch.setattr(classroom_ui, "_inbox_ai", ai, raising=False)

    def student():
        app = AppTest.from_string("from think_app import embedded\nembedded.render(embedded._inbox_user)\n")
        app.session_state[REQUESTED_COURSE] = course["id"]
        return app.run()

    def teacher():
        return AppTest.from_string(
            "from think_app import classroom_ui as view\n"
            "from think_app.classroom import Classroom\n"
            "view.response_gallery(Classroom(view._inbox_teacher_store), view._inbox_course, "
            "view._inbox_task, view._inbox_ai)\n").run()

    return room, task["id"], selected, downloads, student, teacher


def displayed(app):
    return "\n".join(str(item.value) for kind in (app.markdown, app.caption, app.info, app.warning, app.subheader)
                     for item in kind)


def test_upload_then_submission_moves_pdf_from_pending_files_to_gradable_teacher_answer(inbox_ui):
    room, aid, selected, downloads, make_student, make_teacher = inbox_ui
    student, teacher = make_student(), make_teacher()
    assert not student.exception and not teacher.exception
    assert teacher.button(key="grade_pending_" + aid).disabled
    selected.append(SimpleNamespace(name="학생풀이.pdf", getvalue=pdf_bytes))

    student.run()
    teacher.run()

    assert not student.exception and not student.error and not teacher.exception and not teacher.error
    assert any("파일 저장 완료 · 아직 제출 전" in item.value for item in student.warning)
    assert "업로드된 답안 파일 · 제출 대기 1개" in displayed(teacher)
    assert "시험학생 · 10101 · 1-1" in displayed(teacher)
    assert "업로드됨 · 제출 완료 대기" in displayed(teacher)
    assert downloads[-1] == ("업로드 파일 내려받기 · 학생풀이.pdf", pdf_bytes(), "학생풀이.pdf", "application/pdf")
    assert not room.attempts(aid)
    assert teacher.button(key="grade_pending_" + aid).label.endswith("0개")

    next(button for button in student.button if button.label == "답안 제출").click().run()
    selected.clear()
    teacher.run()

    assert not student.exception and not student.error and not teacher.exception and not teacher.error
    assert any("교사의 학생 제출함에 접수되었습니다" in item.value for item in student.success)
    assert "업로드됨 · 제출 완료 대기" not in displayed(teacher)
    assert "PDF 답안 · 학생풀이.pdf" in displayed(teacher)
    assert "평가 대기 · 1" in displayed(teacher)
    assert teacher.button(key="grade_pending_" + aid).label.endswith("1개")
    assert not teacher.button(key="grade_pending_" + aid).disabled
    attempt = room.attempts(aid)[0]
    assert attempt["student_id"] == "10101" and attempt["documents"][0]["filename"] == "학생풀이.pdf"
    teacher.button(key="open_answer_" + attempt["id"]).click().run()
    assert not teacher.exception and not teacher.error
    assert any(item.label == "업로드한 원본 내려받기 · 학생풀이.pdf" for item in teacher.get("download_button"))


def test_teacher_pending_file_cards_follow_selected_class_and_hide_preview_uploads(inbox_ui):
    room, aid, _, _, _, make_teacher = inbox_ui
    files = UploadedFiles(room.store)
    files.save(aid, "10101", "우리 반 학생", "1-1", "우리반.pdf", pdf_bytes())
    files.save(aid, "10201", "다른 반 학생", "1-2", "다른반.pdf", pdf_bytes())
    files.save(aid, "preview", "체험 학생", "1-1", "체험.pdf", pdf_bytes(), preview=True)
    teacher = make_teacher()
    teacher.selectbox(key="class_filter_" + aid).set_value("1-1").run()

    assert not teacher.exception and not teacher.error
    assert "우리반.pdf" in displayed(teacher)
    assert "다른반.pdf" not in displayed(teacher) and "체험.pdf" not in displayed(teacher)
    assert "업로드된 답안 파일 · 제출 대기 1개" in displayed(teacher)
    assert teacher.button(key="grade_pending_" + aid).disabled


def test_teacher_inbox_observer_reruns_only_for_changed_real_uploads_and_submissions(monkeypatch):
    store = MemoryStore()
    room, _, task = make_assessment(store)
    files = UploadedFiles(store)
    reruns = []
    monkeypatch.setattr(classroom_ui, "st", SimpleNamespace(
        session_state={}, empty=lambda: None, rerun=lambda **kwargs: reruns.append(kwargs)))
    watch = classroom_ui.teacher_submission_watch.__wrapped__
    watch(room, task, "1-1")
    watch(room, task, "1-1")
    files.save(task["id"], "10201", "다른 반", "1-2", "다른반.pdf", pdf_bytes())
    files.save(task["id"], "preview", "체험", "1-1", "체험.pdf", pdf_bytes(), preview=True)
    watch(room, task, "1-1")
    assert not reruns

    record = files.save(task["id"], "10101", "학생", "1-1", "풀이.pdf", pdf_bytes())
    watch(room, task, "1-1")
    watch(room, task, "1-1")
    assert reruns == [{"scope": "app"}]

    room.submit(task["id"], "10101", "학생", "1-1", "", [], False, "a" * 32,
                upload_ids=[record["id"]])
    watch(room, task, "1-1")
    watch(room, task, "1-1")
    assert reruns == [{"scope": "app"}, {"scope": "app"}]
