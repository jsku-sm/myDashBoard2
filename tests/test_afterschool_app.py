"""Optional REAL Streamlit smoke checks; skipped if Streamlit is not installed."""
import threading
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
import storage as db

T={'id':'as-runtime-teacher','name':'시험교사','role':'teacher','must_change':'0','class':''}
S={'id':'as-runtime-student','name':'가상학생','role':'student','must_change':'0','class':'1-1'}

@pytest.fixture
def backend(monkeypatch,tmp_path):
    b=db.LocalBackend(str(tmp_path/'data'))
    monkeypatch.setattr(db,'get_backend',lambda:b)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    b.append('users',T);b.append('users',S)
    return b

def page(user,name='teacher_page'):
    app=AppTest.from_string('import streamlit as st\nfrom views.afterschool import '+name+'\n'+name+'(st.session_state["user"])')
    app.session_state['user']=dict(user)
    return app.run()

def test_real_teacher_empty_state_and_create(backend):
    app=page(T)
    assert not app.exception and not app.error
    next(x for x in app.text_input if x.label=='기수명').set_value('1기')
    next(x for x in app.button if x.label=='기수 추가').click().run()
    assert not app.exception and not app.error
    assert backend.read('as_cohorts')[0]['name']=='1기'

def test_real_student_cannot_open_teacher_settings(backend):
    app=page(S)
    assert not app.exception and app.error
    assert not app.text_input

def test_real_unassigned_student_has_no_board_content(backend):
    app=page(S,'student_board')
    assert not app.exception and not app.error and not app.radio
