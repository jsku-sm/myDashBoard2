"""Actual Streamlit observation submit/retry; no real student data."""
import threading
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def observation_ui(tmp_path,monkeypatch):
    import streamlit
    import storage as db
    import views.teacher as view
    import auth
    b=db.LocalBackend(str(tmp_path/'data'))
    teacher=dict(id='teacher',role='teacher',must_change='0',name='가상교사')
    b.append('users',teacher);b.append('users',dict(id='10101',role='student',name='가상학생',**{'class':'1-1'}))
    monkeypatch.setattr(view,'st',streamlit);monkeypatch.setattr(db,'st',streamlit)
    monkeypatch.setattr(view,'db',db);monkeypatch.setattr(db,'_ready_backend',lambda:b)
    monkeypatch.setattr(db,'get_backend',lambda:b)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    monkeypatch.setattr(auth,'students',lambda cls:[r for r in b.read('users') if r['role']=='student' and r['class']==cls])
    state={'fail':False}
    def flush():
        if state['fail']:raise RuntimeError('simulated GitHub failure')
    monkeypatch.setattr(db,'flush_now',flush)
    app=AppTest.from_string('from views.teacher import tab_observe\ntab_observe()',default_timeout=20)
    app.session_state['user']=teacher;app.run()
    assert not app.exception
    return SimpleNamespace(app=app,b=b,state=state)


def pick(elements,label):return next(e for e in elements if e.label==label)


def test_subject_save_and_delete_survive_reopen(observation_ui):
    u=observation_ui;a=u.app
    pick(a.selectbox,'관찰 과목').select('공통수학2')
    pick(a.text_area,'관찰 내용').set_value('대칭 좌표를 비교해 오류를 수정함.')
    pick(a.button,'기록 저장').click().run()
    assert not a.exception and not a.error
    r=u.b.read('observations')[0]
    assert r['subject']=='공통수학2' and r['author_id']=='teacher'
    assert any('공통수학2' in c.value for c in a.caption)
    pick(a.button,'삭제').click().run()
    assert not a.exception and not u.b.read('observations')


def test_failed_confirmation_retry_keeps_one_observation(observation_ui):
    u=observation_ui;a=u.app;u.state['fail']=True
    pick(a.selectbox,'관찰 과목').select('공통수학2')
    pick(a.text_area,'관찰 내용').set_value('저장 확인을 기다리는 관찰기록입니다.')
    pick(a.button,'기록 저장').click().run()
    assert not a.exception and len(u.b.read('observations'))==1
    assert a.warning
    u.state['fail']=False
    pick(a.button,'관찰기록 저장 재시도 (중복 등록 안 함)').click().run()
    assert not a.exception and len(u.b.read('observations'))==1
