"""Create, distribute and submit through the actual teacher and student widgets."""
import base64
import copy
from datetime import date, timedelta
import io
from types import SimpleNamespace
import wave

from PIL import Image
from pypdf import PdfWriter
import pytest
from streamlit.testing.v1 import AppTest

from think_app import classroom_ui, embedded
from think_app.classroom import Classroom
from think_app.courses import CourseManager, now
from think_app.storage import MemoryStore


@pytest.fixture
def distribution_ui(monkeypatch):
    store = MemoryStore()
    manager = CourseManager(store)
    cid = manager.create("수행평가 배포", "#123456", ["1-1"])
    course = manager.get(cid)
    for module in (classroom_ui, embedded):
        monkeypatch.setattr(module, "_distribution_test_store", store, raising=False)
        monkeypatch.setattr(module, "_distribution_test_course", course, raising=False)

    def app(role):
        if role == "teacher":
            source = ("from think_app import classroom_ui as view\n"
                      "from think_app.config import Settings\n"
                      "view.course_detail(view._distribution_test_store, view._distribution_test_course, Settings())\n")
        else:
            source = ("from think_app import embedded as view\n"
                      "from think_app.config import Settings\n"
                      "from think_app.courses import CourseManager\n"
                      "view.student_view(view._distribution_test_store, CourseManager(view._distribution_test_store), "
                      "Settings(), {'id': '10101', 'name': '학생', 'class': '1-1', 'role': 'student'}, "
                      "view._distribution_test_course['id'])\n")
        return AppTest.from_string(source).run()

    return Classroom(store), cid, app


def create_task(room, cid, **changes):
    values = dict(title="세부 활동", prompt="2+2의 값을 구하세요.", expected="4",
                  criteria=["풀이의 근거를 설명한다."], max_attempts=2, start=now()[:10], end=now()[:10])
    values.update(changes)
    return room.save_activity(cid, **values)


@pytest.mark.parametrize("duration", [0, 15])
def test_teacher_saves_distributes_and_student_submits(distribution_ui, duration):
    room, cid, make_app = distribution_ui
    teacher = make_app("teacher")
    next(button for button in teacher.button if button.label == "＋ 활동 추가하기").click().run()
    prefix = "activity_form_" + cid
    teacher.text_input(key=prefix + "_title").set_value("계산과 설명")
    teacher.text_area(key=prefix + "_prompt").set_value("2+2의 값을 구하세요.")
    teacher.text_area(key=prefix + "_expected").set_value("4")
    teacher.text_area(key=prefix + "_criteria").set_value("풀이의 근거를 설명한다.")
    teacher.number_input(key=prefix + "_duration").set_value(duration)
    teacher.button(key=prefix + "_save").click().run()
    assert not teacher.exception and not teacher.error
    task = room.activities(cid)[0]
    aid = task["id"]
    assert task["status"] == "배포 전" and not room._can_submit(task)
    student = make_app("student")
    assert not student.exception
    assert "수행평가 기간이 아닙니다." in [item.value for item in student.info]
    assert not student.text_area and not student.get("download_button")

    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    task = room.activity(aid)
    assert task["status"] == "진행 중" and task["distributed_at"]
    assert room.timer_state(task)["phase"] == ("running" if duration else "unlimited")
    assert teacher.button(key="distribute_activity_" + aid).disabled
    assert any("학생에게 배포했습니다." in item.value for item in teacher.success)
    student.run()
    assert not student.exception
    answer = next(item for item in student.text_area if item.label == "나의 답안")
    answer.set_value("2개와 2개를 더하면 4개입니다.")
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    attempts = room.attempts(aid)
    assert len(attempts) == 1 and attempts[0]["student_id"] == "10101"
    assert attempts[0]["activity_snapshot"]["distributed_at"] == task["distributed_at"]


def test_activity_detail_has_distribution_button(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    teacher = make_app("teacher")
    teacher.button(key="activity_" + aid).click().run()
    assert not teacher.exception
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.student_activity_available(room.activity(aid))


def test_student_submission_does_not_request_ai_feedback_with_saved_consent(distribution_ui, monkeypatch):
    from think_app.config import Settings
    room, cid, make_app = distribution_ui
    def unexpected_ai_call(*args, **kwargs):
        pytest.fail("The student editor must not send an answer or audio for AI analysis.")
    ai = SimpleNamespace(settings=Settings(), available=True, feedback=unexpected_ai_call,
                         transcribe=unexpected_ai_call)
    monkeypatch.setattr(embedded, "AI", lambda settings: ai)
    aid = create_task(room, cid)
    room.distribute_activity(aid)
    student = make_app("student")
    prefix = f"student_{aid}_1-1_10101_0"
    student.session_state[prefix + "_consent"] = True
    student.text_area(key=prefix + "_text").set_value("4입니다.")
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    assert not any("AI 피드백" in item.label for item in student.checkbox)
    assert not any(item.label == "녹음한 말을 글로 바꾸기" for item in student.button)
    attempt = room.attempts(aid)[0]
    assert attempt["text"] == "4입니다." and attempt["consent"] is False
    assert attempt["feedback"] is None


def test_teacher_workbench_also_has_distribution_button(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    teacher = make_app("teacher")
    teacher.radio(key="workspace_" + cid).set_value("작업하기").run()
    assert not teacher.exception
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.student_activity_available(room.activity(aid))


def test_teacher_end_button_shows_exact_student_notice_and_hides_editor(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=15)
    room.distribute_activity(aid)
    student = make_app("student")
    assert not student.exception and student.text_area
    teacher = make_app("teacher")
    teacher.button(key="timer_end_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["timer_ended_at"]
    assert "선생님이 평가를 종료했습니다." in [item.value for item in teacher.warning]
    student.run()
    assert not student.exception and not student.error
    assert "선생님이 평가를 종료했습니다." in [item.value for item in student.info]
    assert "수행평가 기간이 아닙니다." not in [item.value for item in student.info]
    assert not student.text_area and not student.get("file_uploader") and not student.get("download_button")


def test_teacher_can_resume_repeatedly_and_keep_submissions_and_current_answer(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=15)
    room.distribute_activity(aid)
    student = make_app("student")
    student.text_area(key=f"student_{aid}_1-1_10101_0_text").set_value("첫 답안")
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    room.comment(room.attempts(aid)[0]["id"], "근거를 추가해 보세요.")
    submitted = copy.deepcopy(room.attempts(aid))
    text_key = f"student_{aid}_1-1_10101_1_text"
    student.text_area(key=text_key).set_value("재개 후 이어서 쓸 두 번째 답안").run()
    teacher = make_app("teacher")
    for _ in range(2):
        teacher.button(key="timer_end_" + aid).click().run()
        assert not teacher.exception and not teacher.error
        student.run()
        assert not student.exception and not student.text_area
        assert "선생님이 평가를 종료했습니다." in [item.value for item in student.info]
        ended = room.activity(aid)
        assert teacher.button(key="timer_resume_" + aid).label == "평가 재개"
        teacher.number_input(key="timer_resume_minutes_" + aid + ended["timer_ended_at"]).set_value(5)
        teacher.button(key="timer_resume_" + aid).click().run()
        assert not teacher.exception and not teacher.error
        assert room.timer_state(room.activity(aid))["phase"] == "running"
        assert room.attempts(aid) == submitted
        student.run()
        assert not student.exception and not student.error
        assert student.text_area(key=text_key).value == "재개 후 이어서 쓸 두 번째 답안"
        assert not next(button for button in student.button if button.label == "답안 제출").disabled
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    assert len(room.attempts(aid)) == 2 and room.attempts(aid)[0] == submitted[0]
    assert room.attempts(aid)[1]["text"] == "재개 후 이어서 쓸 두 번째 답안"
    assert not any(item.label == "나의 답안" for item in student.text_area)


def test_resume_button_reopens_an_assessment_after_its_end_date(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=15)
    room.distribute_activity(aid)
    room.end_timer(aid)
    yesterday = (date.fromisoformat(now()[:10]) - timedelta(days=1)).isoformat()
    room.store.transaction(lambda state: state["course_activities"][aid].update(start=yesterday, end=yesterday))
    teacher = make_app("teacher")
    assert not teacher.button(key="timer_resume_" + aid).disabled
    assert any("오늘을 포함" in item.value for item in teacher.caption)
    teacher.button(key="timer_resume_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["end"] == now()[:10]
    student = make_app("student")
    assert not student.exception and any(item.label == "나의 답안" for item in student.text_area)


def test_resume_restores_unsubmitted_drawing_pdf_audio_and_transcript(distribution_ui, monkeypatch):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=15)
    room.distribute_activity(aid)
    image = io.BytesIO()
    Image.new("RGB", (20, 15), "black").save(image, "PNG")
    drawing = {"image": "data:image/png;base64," + base64.b64encode(image.getvalue()).decode(),
               "hasInk": True, "revision": 1}
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = io.BytesIO()
    writer.write(pdf)
    raw_pdf = pdf.getvalue()
    recording = io.BytesIO()
    with wave.open(recording, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    raw_audio = recording.getvalue()
    current = {"drawing": drawing, "uploads": [SimpleNamespace(name="풀이.pdf", getvalue=lambda: raw_pdf)],
               "audio": SimpleNamespace(getvalue=lambda: raw_audio)}
    restored_images = []
    def board(**kwargs):
        restored_images.append(kwargs.get("initial_image"))
        return current["drawing"] or kwargs.get("default")
    original_uploader = classroom_ui.st.file_uploader
    def uploader(label, **kwargs):
        if label == "답안 이미지·PDF 첨부 · 최대 2개":
            return current["uploads"]
        return original_uploader(label, **kwargs)
    monkeypatch.setattr(classroom_ui, "board", board)
    monkeypatch.setattr(classroom_ui.st, "file_uploader", uploader)
    monkeypatch.setattr(classroom_ui.st, "audio_input", lambda *args, **kwargs: current["audio"])
    student = make_app("student")
    text_key = f"student_{aid}_1-1_10101_0_text"
    transcript_key = f"student_{aid}_1-1_10101_0_transcript"
    student.text_area(key=text_key).set_value("그림과 파일을 보세요.")
    student.text_area(key=transcript_key).set_value("음성 설명을 수정했어요.").run()
    assert not student.exception and not student.error
    teacher = make_app("teacher")
    teacher.button(key="timer_end_" + aid).click().run()
    current.update(drawing=None, uploads=[], audio=None)
    student.run()
    assert not student.exception and not student.text_area
    teacher.button(key="timer_resume_" + aid).click().run()
    student.run()
    assert not student.exception and not student.error
    assert student.text_area(key=text_key).value == "그림과 파일을 보세요."
    assert student.text_area(key=transcript_key).value == "음성 설명을 수정했어요."
    assert restored_images[-1] == drawing["image"]
    selected = next(item for item in student.multiselect if item.label.startswith("답안에 첨부할 저장 파일"))
    assert len(selected.value) == 1
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    attempt = room.attempts(aid)[0]
    assert attempt["text"] == "그림과 파일을 보세요." and attempt["transcript"] == "음성 설명을 수정했어요."
    assert len(attempt["images"]) == 1 and len(attempt["documents"]) == 1
    assert room.store.get_blob(attempt["documents"][0]["original_ref"]) == raw_pdf
    assert room.store.get_blob(attempt["audio"]) == raw_audio


def test_teacher_can_republish_hidden_activity_without_stale_status_override(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    room.distribute_activity(aid)
    distributed = room.activity(aid)["distributed_at"]
    room.set_status(aid, "숨김")
    teacher = make_app("teacher")
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 다시 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["status"] == "진행 중"
    assert room.activity(aid)["distributed_at"] == distributed
    teacher.run()
    assert not teacher.exception and room.activity(aid)["status"] == "진행 중"


def test_future_activity_can_be_distributed_but_students_wait_for_period(distribution_ui):
    room, cid, make_app = distribution_ui
    today = date.fromisoformat(now()[:10])
    aid = create_task(room, cid, start=(today + timedelta(days=2)).isoformat(),
                      end=(today + timedelta(days=3)).isoformat())
    teacher = make_app("teacher")
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["distributed_at"]
    assert any("예약 배포" in item.value for item in teacher.success)
    student = make_app("student")
    assert not student.exception and not student.text_area
    assert "수행평가 기간이 아닙니다." in [item.value for item in student.info]


def test_direct_student_preview_hides_question_after_period_ends(distribution_ui, monkeypatch):
    room, cid, _ = distribution_ui
    aid = create_task(room, cid)
    room.distribute_activity(aid)
    monkeypatch.setattr(classroom_ui, "_distribution_test_aid", aid, raising=False)
    student = AppTest.from_string(
        "from think_app import classroom_ui as view\n"
        "from think_app.ai import AI\n"
        "from think_app.config import Settings\n"
        "from think_app.classroom import Classroom\n"
        "room = Classroom(view._distribution_test_store)\n"
        "view.student_preview(room, view._distribution_test_course, room.activity(view._distribution_test_aid), "
        "AI(Settings()), identity=('10101', '학생', '1-1'))\n"
    ).run()
    assert not student.exception and student.text_area
    yesterday = (date.fromisoformat(now()[:10]) - timedelta(days=1)).isoformat()
    room.store.transaction(lambda state: state["course_activities"][aid].update(start=yesterday, end=yesterday))
    student.run()
    assert not student.exception and not student.text_area and not student.get("component_instance")
    assert [item.value for item in student.info] == ["수행평가 기간이 아닙니다."]


@pytest.mark.parametrize("phase", ["expired", "ended"])
def test_redistributing_closed_timer_reports_students_are_still_blocked(distribution_ui, phase):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=1)
    room.distribute_activity(aid)
    if phase == "expired":
        room.adjust_timer(aid, 0)
    else:
        room.end_timer(aid)
    room.set_status(aid, "숨김")
    teacher = make_app("teacher")
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert not room.student_activity_available(room.activity(aid))
    assert any("학생에게 표시되지 않습니다." in item.value for item in teacher.success)
    assert not any("학생 메뉴에 활동이 표시됩니다." in item.value for item in teacher.success)
