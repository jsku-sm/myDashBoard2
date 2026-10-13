"""Teachers can see the exact criteria that will be stored as selections change."""
from streamlit.testing.v1 import AppTest

from think_app import curriculum_ui
from think_app.curriculum import criteria_text, selection_metadata


def curriculum_app(monkeypatch, task=None):
    monkeypatch.setattr(curriculum_ui, "_test_task", task or {}, raising=False)
    return AppTest.from_string(
        "import streamlit as st\n"
        "from think_app import curriculum_ui as view\n"
        "st.session_state['result'] = view.render_curriculum_criteria(view._test_task, 'criteria_test')\n"
    ).run()


def test_selected_criteria_are_automatically_displayed_with_custom_criteria(monkeypatch):
    app = curriculum_app(monkeypatch)
    code = "10공수1-01-01"
    app.multiselect(key="criteria_test_standards").set_value([code]).run()
    app.text_area(key="criteria_test_criteria").set_value("풀이 과정을 설명한다.").run()
    assert not app.exception
    expected = criteria_text("공통수학1", "다항식", [code]) + ["풀이 과정을 설명한다."]
    preview = app.text_area(key="criteria_test_criteria_preview")
    assert preview.label == "평가 기준 · 한 줄에 하나"
    assert preview.value == "\n".join(expected)
    assert preview.disabled
    assert app.session_state["result"][0] == expected
    app.multiselect(key="criteria_test_standards").set_value([]).run()
    assert not app.exception
    assert app.text_area(key="criteria_test_criteria_preview").value == "풀이 과정을 설명한다."


def test_changing_subject_removes_the_old_standards_from_preview(monkeypatch):
    app = curriculum_app(monkeypatch)
    app.multiselect(key="criteria_test_standards").set_value(["10공수1-01-01"]).run()
    app.selectbox(key="criteria_test_subject").set_value("공통수학2").run()
    assert not app.exception
    assert app.text_area(key="criteria_test_criteria_preview").value == ""
    assert app.session_state["result"] == ([], {})


def test_saved_official_and_legacy_criteria_are_restored_without_duplicates(monkeypatch):
    codes = ["10공수1-01-01", "10공수1-01-03"]
    official = criteria_text("공통수학1", "다항식", codes)
    task = {
        "criteria": official + ["풀이 과정을 설명한다."],
        "curriculum": selection_metadata("공통수학1", "다항식", codes),
    }
    app = curriculum_app(monkeypatch, task)
    assert not app.exception
    assert app.multiselect(key="criteria_test_standards").value == codes
    assert app.text_area(key="criteria_test_criteria").value == "풀이 과정을 설명한다."
    assert app.text_area(key="criteria_test_criteria_preview").value == "\n".join(task["criteria"])
    assert app.session_state["result"] == (task["criteria"], task["curriculum"])
