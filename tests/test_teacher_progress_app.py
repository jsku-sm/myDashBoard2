"""Real Streamlit page checks. Skipped only when runtime is unavailable."""
import threading
from datetime import date
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
st=pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
import storage as db

TEACHER={'id':'app-test-teacher','name':'시험교사','role':'teacher','must_change':'0'}
STUDENT={'id':'app-test-student','name':'가상학생','role':'student','must_change':'0'}

@pytest.fixture
def app_store(monkeypatch,tmp_path):
    backend=db.LocalBackend(str(tmp_path/'data'))
    cache={'data':{},'lock':threading.Lock()}
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    monkeypatch.setattr(db,'_cache',lambda:cache)
    backend.append('users',TEACHER);backend.append('users',STUDENT)
    return backend

def run_page(user):
    app=AppTest.from_string('import streamlit as st\nfrom views.teaching_progress import page\npage(st.session_state["user"])')
    app.session_state['user']=dict(user)
    return app.run()

def test_real_page_teacher_form(app_store):
    app=run_page(TEACHER)
    assert not app.exception and not app.error
    assert any(x.label=='수업내용' for x in app.text_area)
    assert any(x.label=='수행평가명' for x in app.text_input)
    assert any(x.label=='수업일 기준' for x in app.radio)==False
    assert any('수행평가일 기준' in x.options for x in app.radio)

def test_real_page_student_denied(app_store):
    app=run_page(STUDENT)
    assert not app.exception and app.error
    assert not app.text_area and not app.text_input

def test_real_page_submission_persists(app_store):
    app=run_page(TEACHER)
    content=next(x for x in app.text_area if x.label=='수업내용')
    content.set_value('실제 Streamlit 양식 검사')
    next(x for x in app.button if x.label=='선택 학급에 기록 저장').click().run()
    assert not app.exception and not app.error
    rows=app_store.read('teaching_progress')
    assert len(rows)==1 and rows[0]['content']=='실제 Streamlit 양식 검사'
