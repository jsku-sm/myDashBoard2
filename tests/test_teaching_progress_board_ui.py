"""Native Streamlit form tests; skipped when the runtime is unavailable.

The custom component is replaced with an event bridge here; its actual browser
implementation is covered separately by test_teaching_progress_grid_browser.py.
"""
import pytest
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

SCRIPT = '''
import streamlit as st
from classroom_core import ClassroomService, MemoryStore, StorageError
from classroom_core.teaching_board import CLASSES
from views import classroom_progress_board as view

class TestStore(MemoryStore):
    fail = False
    def put(self, *args, **kwargs):
        if self.fail:
            raise StorageError("GitHub 모의 저장 실패")
        return super().put(*args, **kwargs)
users={"t":{"id":"t","role":"teacher","name":"시험 교사"}}
if "store" not in st.session_state:
    store=TestStore()
    service=ClassroomService(store, users["t"], users.get)
    for cls in CLASSES:
        service.create_course(cls, "2026-2", "공통수학2", class_name=cls)
    st.session_state.store=store
    st.session_state.teaching_board_t_subject="공통수학2"
store=st.session_state.store
service=ClassroomService(store, users["t"], users.get)
def grid(model, **kwargs):
    st.session_state.model=model
    return st.session_state.pop("browser_event",None)
view.render_grid=grid
view.render_board(service, service.list_courses(), users["t"])
'''


def element(items, label):
    return next(item for item in items if item.label == label)


def test_native_default_form_and_seven_class_model():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert len(app.session_state["model"]["cards"]) == 7
    assert element(app.text_input, "수업내용")
    assert element(app.multiselect, "배포할 학급").value == []


def test_native_private_upload_then_selective_distribution():
    app = AppTest.from_string(SCRIPT).run()
    element(app.text_input, "수업내용").set_value("원의 방정식")
    element(app.button, "수업내용만 저장").click().run()
    assert not app.exception
    content = app.session_state["store"].list("teaching_contents")[0]
    assert content["published_course_ids"] == []
    element(app.multiselect, "추가 배포할 학급").set_value(["1-1", "1-3"])
    element(app.button, "선택 반에 배포").click().run()
    assert not app.exception
    model = app.session_state["model"]
    assert set(model["rows"][0]["cells"]) == {"1-1", "1-3"}
    assert all(not cell["completed"] for cell in model["rows"][0]["cells"].values())


def test_native_component_event_updates_same_course_record():
    app = AppTest.from_string(SCRIPT).run()
    element(app.text_input, "수업내용").set_value("함수")
    element(app.multiselect, "배포할 학급").set_value(["1-1"])
    element(app.button, "등록하고 선택 반에 배포").click().run()
    assert not app.exception
    cell = app.session_state["model"]["rows"][0]["cells"]["1-1"]
    app.session_state["browser_event"] = dict(cell, type="toggle", event_id="first", completed=True)
    app.run()
    assert not app.exception
    assert app.session_state["model"]["cards"][0]["percent"] == 100.0
    app.session_state["store"].fail = True
    cell = app.session_state["model"]["rows"][0]["cells"]["1-1"]
    app.session_state["browser_event"] = dict(cell, type="toggle", event_id="second", completed=False)
    app.run()
    assert not app.exception
    assert app.session_state["model"]["cards"][0]["percent"] == 100.0
    assert any("실패" in error.value for error in app.error)
