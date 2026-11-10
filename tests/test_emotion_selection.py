"""The login picker must reach the student's own saved mood, not a blank home."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import threading

import pytest
from streamlit.testing.v1 import AppTest

import storage as db
from config import EMOTIONS, TZ
from views import emotion


USER = dict(id="10101", name="테스트 학생", role="student", must_change="0", **{"class":"1-1"})
OTHER = dict(USER, id="10102", name="다른 학생")
TEACHER = dict(USER, id="teacher", role="teacher", name="선생님")
APP = '''
import streamlit as st
from views import emotion, home
user=st.session_state['user']
if emotion.done_today(user):
    home._summary(user)
else:
    emotion.emotion_page(user)
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    backend=db.LocalBackend(str(tmp_path))
    for user in (USER,OTHER,TEACHER):backend.append('users',user)
    db._cache.clear()
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    clock={'now':datetime(2026,11,10,9,0,tzinfo=TZ)}
    monkeypatch.setattr(db,'now',lambda:clock['now'])
    try:yield backend,clock
    finally:db._cache.clear()


def app_for(user=USER):
    app=AppTest.from_string(APP)
    app.session_state['user']=dict(user)
    return app.run()


def text(app):
    assert not app.exception
    return '\n'.join(m.value for m in app.markdown)


@pytest.mark.parametrize('key,icon,label,_,message',EMOTIONS)
def test_each_login_choice_is_saved_shown_and_restored_after_new_session(env,key,icon,label,_,message):
    backend,_clock=env
    app=app_for()
    app.button(key='emo_'+key).click().run()
    assert f'<strong>{label}</strong>' in text(app)
    assert icon in text(app) and '아직 선택하지 않았어요' not in text(app)
    assert backend.read('emotions')[-1]['emotion']==key
    # A fresh login reads persistent data, even with no completion flag/toast.
    restored=app_for()
    assert f'<strong>{label}</strong>' in text(restored)
    assert not restored.button


def test_changed_mood_uses_latest_record_and_next_day_requires_new_choice(env):
    backend,clock=env
    app=app_for();app.button(key='emo_happy').click().run()
    # Exercise the production change picker as well as the production summary.
    changed=AppTest.from_string("import streamlit as st\nfrom views import emotion,home\n"
        "home._summary(st.session_state['user'])\n"
        "emotion.picker(st.session_state['user'],key_prefix='emo_again')\n")
    changed.session_state['user']=dict(USER)
    changed.run();changed.button(key='emo_again_tired').click().run()
    assert '<strong>피곤해요</strong>' in text(changed)
    assert len(backend.read('emotions'))==2
    assert '<strong>피곤해요</strong>' in text(app_for())
    clock['now']+=timedelta(days=1)
    app.session_state['_emo_done']=True  # Previous releases left this unscoped flag.
    app.run()
    assert len(app.button)==len(EMOTIONS)
    app.button(key='emo_calm').click().run()
    assert '<strong>편안해요</strong>' in text(app)
    assert backend.read('emotions')[-1]['date']=='2026-11-11'


def test_student_cannot_read_peer_mood_or_skip_their_picker(env,monkeypatch):
    backend,_=env
    with monkeypatch.context() as scoped:
        scoped.setattr(emotion,'st',SimpleNamespace(session_state={'user':dict(USER),'_emo_done':True}))
        scoped.setattr(db,'st',SimpleNamespace(session_state={'user':dict(USER)}))
        emotion.save(USER,'happy')
        with pytest.raises(PermissionError):emotion.save(OTHER,'sad')
        assert emotion.today_emotion(OTHER) is None
        with pytest.raises(ValueError):emotion.save(USER,'invalid')
        assert db.read('emotions')==[]  # General student access still stays blocked.
        assert len(backend.read('emotions'))==1
    peer=app_for(OTHER)
    peer.session_state['_emo_done']=True
    peer.run()
    assert len(peer.button)==len(EMOTIONS)


def test_failed_write_never_marks_mood_complete(env,monkeypatch):
    session={'user':dict(USER)}
    monkeypatch.setattr(emotion,'st',SimpleNamespace(session_state=session))
    def fail(*args):raise OSError('test write failure')
    monkeypatch.setattr(db,'append',fail)
    with pytest.raises(OSError):emotion.save(USER,'happy')
    assert not emotion.done_today(USER)
    assert '_emo_msg' not in session


def test_teacher_still_sees_saved_emotion_records(env,monkeypatch):
    session={'user':dict(USER)}
    monkeypatch.setattr(emotion,'st',SimpleNamespace(session_state=session))
    monkeypatch.setattr(db,'st',SimpleNamespace(session_state=session))
    emotion.save(USER,'worried')
    session['user']=dict(TEACHER)
    assert db.read('emotions')[0]['emotion']=='worried'
    assert emotion.today_emotion(USER) is None
    with pytest.raises(PermissionError):emotion.save(USER,'calm')


def test_github_buffer_is_visible_immediately_without_waiting_for_commit(env,monkeypatch):
    # Real production read/append methods; no GitHub credentials or network.
    from cryptography.fernet import Fernet
    from record_core.archive import ArchiveCrypto
    backend=db.GitHubBackend.__new__(db.GitHubBackend)
    backend.lock=threading.RLock()
    backend.rows={table:[] for table in db.SCHEMAS}
    backend.rows['users']=[db._norm(USER,'users')]
    backend.dirty={};backend.ver=0;backend.archive_dirty={}
    backend.archive_crypto=ArchiveCrypto(Fernet.generate_key().decode())
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    session={'user':dict(USER)}
    monkeypatch.setattr(emotion,'st',SimpleNamespace(session_state=session))
    monkeypatch.setattr(db,'st',SimpleNamespace(session_state=session))
    assert db.read('emotions')==[]  # Prime the generic read cache before saving.
    emotion.save(USER,'excited')
    assert emotion.today_emotion(USER)=='excited'
    assert emotion.done_today(USER)
    assert 'data/emotions/2026-11.csv' in backend.dirty
    assert 'excited' in backend._csv('data/emotions/2026-11.csv')
    assert db.read('emotions')==[]
