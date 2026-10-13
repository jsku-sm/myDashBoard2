"""Exercise curriculum changes and activity saves through real Streamlit widgets."""
import io
import json
import zipfile
import pytest
from types import SimpleNamespace
from streamlit.testing.v1 import AppTest

from think_app import classroom_ui
from think_app.classroom import Classroom
from think_app.courses import CourseManager, now
from think_app.curriculum import criteria_text, standards_for, selection_metadata, unit_names
from think_app.storage import MemoryStore
from think_app.ai import AI
from think_app.config import Settings
from think_app.question_files import QuestionFiles


@pytest.fixture
def activity_app(monkeypatch):
    room = Classroom(MemoryStore())
    cid = CourseManager(room.store).create("수행평가", "#123456", ["1-1"])
    monkeypatch.setattr(classroom_ui, "_form_test_room", room, raising=False)
    monkeypatch.setattr(classroom_ui, "_form_test_task", {}, raising=False)
    source = ("from think_app import classroom_ui as view\n"
              "from think_app.ai import AI\n"
              "from think_app.integration import resolve_settings\n"
              f"view.activity_form(view._form_test_room, {cid!r}, task=view._form_test_task, "
              "ai=AI(resolve_settings({}, {})))\n")
    return room, cid, source


def test_new_form_saves_selected_standards_and_defaults_to_two_attempts(activity_app):
    room, cid, source = activity_app
    app = AppTest.from_string(source).run()
    prefix = "activity_form_" + cid
    assert not app.exception
    assert app.number_input(key=prefix + "_maximum").value == 2
    code = standards_for("공통수학1", unit_names("공통수학1")[0])[0]["code"]
    app.text_input(key=prefix + "_title").set_value("다항식 평가")
    app.text_area(key=prefix + "_prompt").set_value("다항식을 계산하세요.")
    app.text_area(key=prefix + "_expected").set_value("모범 풀이")
    app.multiselect(key=prefix + "_standards").set_value([code])
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error
    task = room.activities(cid)[0]
    assert task["status"] == "배포 전"
    assert not task.get("distributed_at")
    assert task["max_attempts"] == 2
    assert task["criteria"] == criteria_text("공통수학1", unit_names("공통수학1")[0], [code])
    assert task["curriculum"] == selection_metadata("공통수학1", unit_names("공통수학1")[0], [code])


def test_subject_and_unit_changes_clear_unrelated_standard_selections(activity_app):
    _, cid, source = activity_app
    app = AppTest.from_string(source).run()
    prefix = "activity_form_" + cid
    first_unit = unit_names("공통수학1")[0]
    code = standards_for("공통수학1", first_unit)[0]["code"]
    app.multiselect(key=prefix + "_standards").set_value([code]).run()
    app.selectbox(key=prefix + "_unit").set_value(unit_names("공통수학1")[1]).run()
    assert not app.exception
    assert app.multiselect(key=prefix + "_standards").value == []
    app.selectbox(key=prefix + "_subject").set_value("공통수학2").run()
    assert not app.exception
    assert app.selectbox(key=prefix + "_unit").value in unit_names("공통수학2")
    assert app.multiselect(key=prefix + "_standards").value == []


def test_legacy_activity_keeps_its_attempt_limit_and_custom_criteria(activity_app, monkeypatch):
    room, cid, source = activity_app
    aid = room.save_activity(cid, "기존 활동", "문제", "답", ["기존 평가 기준"], 5, now()[:10], None)
    monkeypatch.setattr(classroom_ui, "_form_test_task", room.activity(aid))
    app = AppTest.from_string(source).run()
    prefix = "activity_form_" + aid
    assert not app.exception
    assert app.number_input(key=prefix + "_maximum").value == 5
    assert app.text_area(key=prefix + "_criteria").value == "기존 평가 기준"
    app.text_input(key=prefix + "_title").set_value("기존 활동 수정")
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error
    assert room.activity(aid)["max_attempts"] == 5
    assert room.activity(aid)["criteria"] == ["기존 평가 기준"]


def question_generation_app(activity_app, monkeypatch, uploads):
    room, cid, _ = activity_app
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return {"status": "completed", "output_text": "2+2=4입니다. 두 개씩 더하면 네 개가 됩니다."}

    ai = AI(Settings(ai_enabled=True, api_key="test-key"),
            client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(classroom_ui, "_form_test_ai", ai, raising=False)
    monkeypatch.setattr(classroom_ui.st, "file_uploader",
                        lambda label, **kwargs: uploads if label == "학생에게 제시할 문제 파일"
                        else ([] if kwargs.get("accept_multiple_files") else None))
    source = ("from think_app import classroom_ui as view\n"
              f"view.activity_form(view._form_test_room, {cid!r}, task=view._form_test_task, "
              "ai=view._form_test_ai)\n")
    return AppTest.from_string(source), calls


def form_teacher_openai(monkeypatch):
    import think_app.ai as ai_module
    connections, requests = [], []

    def create(**kwargs):
        requests.append(kwargs)
        return {"status": "completed", "output_text": "2+2=4입니다. 두 개씩 더하면 네 개가 됩니다."}

    def factory(**kwargs):
        connections.append(kwargs)
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    monkeypatch.setattr(ai_module, "OpenAI", factory)
    return connections, requests


def test_form_question_auto_answer_uses_teacher_key_with_student_ai_disabled(activity_app, monkeypatch):
    _, cid, _ = activity_app
    uploads = [SimpleNamespace(name="문제.txt", getvalue=lambda: "2+2의 값을 구하세요.".encode())]
    app, _ = question_generation_app(activity_app, monkeypatch, uploads)
    original = AI(Settings(ai_enabled=False, api_key="server-test-key"))
    monkeypatch.setattr(classroom_ui, "_form_test_ai", original)
    connections, requests = form_teacher_openai(monkeypatch)
    app.run()
    prefix = "activity_form_" + cid
    assert not app.exception
    assert not app.checkbox(key=prefix + "_question_ai_consent").disabled
    app.checkbox(key=prefix + "_question_ai_consent").check().run()
    assert not app.exception and len(requests) == 1
    assert connections[0]["api_key"] == "server-test-key"
    assert app.text_area(key=prefix + "_expected").value.startswith("2+2=4")
    assert original.available is False
    app.text_area(key=prefix + "_expected").set_value("교사가 검토한 답: 4").run()
    assert not app.exception and len(requests) == 1
    assert app.text_area(key=prefix + "_expected").value == "교사가 검토한 답: 4"


def test_form_key_entry_generates_answer_without_saving_key_to_activity_or_export(activity_app, monkeypatch):
    room, cid, _ = activity_app
    uploads = [SimpleNamespace(name="문제.txt", getvalue=lambda: "2+2의 값을 구하세요.".encode())]
    app, _ = question_generation_app(activity_app, monkeypatch, uploads)
    original = AI(Settings(ai_enabled=False, api_key=""))
    monkeypatch.setattr(classroom_ui, "_form_test_ai", original)
    connections, requests = form_teacher_openai(monkeypatch)
    app.run()
    prefix = "activity_form_" + cid
    assert not app.exception and not app.checkbox(key=prefix + "_question_ai_consent").disabled
    app.checkbox(key=prefix + "_question_ai_consent").check().run()
    assert not app.exception and app.checkbox(key=prefix + "_question_ai_consent").value
    key_input = app.text_input(key=prefix + "_question_api_key")
    assert key_input.proto.type == key_input.proto.PASSWORD and not requests
    assert not connections
    key_input.set_value("session-test-key").run()
    assert not app.exception and len(requests) == 1
    assert connections[0]["api_key"] == "session-test-key"
    assert app.text_area(key=prefix + "_expected").value.startswith("2+2=4")
    assert app.checkbox(key=prefix + "_question_ai_consent").value
    app.text_area(key=prefix + "_expected").set_value("교사가 보완한 답: 4").run()
    assert not app.exception and len(requests) == 1
    app.text_input(key=prefix + "_title").set_value("문제 파일 평가")
    app.text_area(key=prefix + "_criteria").set_value("풀이 과정을 설명한다.")
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error
    task = room.activities(cid)[0]
    assert task["expected"] == "교사가 보완한 답: 4"
    assert task["status"] == "배포 전" and len(requests) == 1
    assert original.available is False and original.settings.api_key == ""
    assert "session-test-key" not in json.dumps(room.store.read(), ensure_ascii=False)
    assert all(b"session-test-key" not in raw for raw in room.store.blobs.values())
    with zipfile.ZipFile(io.BytesIO(room.export(cid, task["id"]))) as archive:
        assert all(b"session-test-key" not in archive.read(name) for name in archive.namelist())


def test_question_upload_generates_editable_answer_once_and_saves_file_only_problem(activity_app, monkeypatch):
    room, cid, _ = activity_app
    uploads = [SimpleNamespace(name="문제.txt", getvalue=lambda: "2+2의 값을 구하세요.".encode())]
    app, calls = question_generation_app(activity_app, monkeypatch, uploads)
    app.run()
    prefix = "activity_form_" + cid
    assert not app.exception and calls == []
    app.checkbox(key=prefix + "_question_ai_consent").check().run()
    assert not app.exception and len(calls) == 1
    assert app.text_area(key=prefix + "_expected").value.startswith("2+2=4")
    app.text_area(key=prefix + "_expected").set_value("교사가 검토한 답: 4").run()
    assert not app.exception and len(calls) == 1
    assert app.text_area(key=prefix + "_expected").value == "교사가 검토한 답: 4"
    code = standards_for("공통수학1", unit_names("공통수학1")[0])[0]["code"]
    app.text_input(key=prefix + "_title").set_value("파일로 출제한 평가")
    app.multiselect(key=prefix + "_standards").set_value([code])
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error and len(calls) == 1
    task = room.activities(cid)[0]
    assert task["status"] == "배포 전"
    assert not task.get("distributed_at")
    assert task["prompt"] == ""
    assert task["expected"] == "교사가 검토한 답: 4"
    assert task["question_files"][0]["filename"] == "문제.txt"
    assert task["max_attempts"] == 2


def test_opening_saved_question_preserves_answer_without_automatic_ai_call(activity_app, monkeypatch):
    room, cid, _ = activity_app
    record = QuestionFiles(room.store).save(cid, b"2+2?", "question.txt")
    aid = room.save_activity(cid, "기존 활동", "", "기존에 검토한 답안", ["풀이 설명"],
                             5, now()[:10], None, question_files=[record])
    monkeypatch.setattr(classroom_ui, "_form_test_task", room.activity(aid))
    app, calls = question_generation_app(activity_app, monkeypatch, [])
    app.run()
    assert not app.exception and calls == []
    assert app.text_area(key="activity_form_" + aid + "_expected").value == "기존에 검토한 답안"


def test_new_activity_can_save_teacher_entered_criteria_without_curriculum_selection(activity_app):
    room, cid, source = activity_app
    app = AppTest.from_string(source).run()
    prefix = "activity_form_" + cid
    app.text_input(key=prefix + "_title").set_value("교사 기준 평가")
    app.text_area(key=prefix + "_prompt").set_value("문제")
    app.text_area(key=prefix + "_expected").set_value("답안")
    app.text_area(key=prefix + "_criteria").set_value("풀이를 자신의 말로 설명한다.")
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error
    assert room.activities(cid)[0]["criteria"] == ["풀이를 자신의 말로 설명한다."]


def test_next_activity_starts_without_previous_files_answer_or_attempt_limit(activity_app, monkeypatch):
    room, cid, _ = activity_app
    uploads = [SimpleNamespace(name="문제.txt", getvalue=lambda: b"2+2?")]
    monkeypatch.setattr(classroom_ui.st, "file_uploader",
                        lambda label, **kwargs: uploads if label == "학생에게 제시할 문제 파일"
                        else ([] if kwargs.get("accept_multiple_files") else None))
    monkeypatch.setattr(classroom_ui, "_form_test_course", CourseManager(room.store).get(cid), raising=False)
    monkeypatch.setattr(classroom_ui, "_form_test_settings", Settings(), raising=False)
    app = AppTest.from_string(
        "from think_app import classroom_ui as view\n"
        "view.course_detail(view._form_test_room.store, view._form_test_course, view._form_test_settings)\n"
    ).run()
    next(button for button in app.button if button.label == "＋ 활동 추가하기").click().run()
    prefix = "activity_form_" + cid
    assert not app.exception and len(app.session_state[prefix + "_question_files"]) == 1
    app.text_input(key=prefix + "_title").set_value("첫 활동")
    app.text_area(key=prefix + "_expected").set_value("교사가 입력한 풀이")
    app.text_area(key=prefix + "_criteria").set_value("풀이 근거를 설명한다.")
    app.number_input(key=prefix + "_maximum").set_value(5)
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error and len(room.activities(cid)) == 1
    uploads.clear()
    next(button for button in app.button if button.label == "＋ 활동 추가하기").click().run()
    assert not app.exception
    assert app.session_state[prefix + "_question_files"] == []
    assert app.text_area(key=prefix + "_expected").value == ""
    assert app.text_area(key=prefix + "_criteria").value == ""
    assert app.number_input(key=prefix + "_maximum").value == 2
