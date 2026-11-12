"""Synthetic 25-session checks. No real accounts, GitHub traffic or AI calls."""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

from cryptography.fernet import Fernet
import pytest
from streamlit.testing.v1 import AppTest

from test_assessment_cloud_persistence import FakePrivateRepository, STATE_PATH, cloud_store
from test_student_record_vault import gh

REAL_SLEEP = time.sleep


class ConcurrentRepo(FakePrivateRepository):
    def __init__(self):
        super().__init__()
        self.mutex = threading.RLock()
        self.conflicts = 0
        self.fail_next = False
        self.external_write = None

    def request(self, method, url, timeout, **kwargs):
        with self.mutex:
            if method == 'PUT' and url.endswith(STATE_PATH):
                if self.fail_next:
                    self.fail_next = False
                    return self.response(503)
                if self.external_write:
                    self.external_write(); self.external_write = None
            reply = super().request(method, url, timeout, **kwargs)
            if reply.status_code == 409: self.conflicts += 1
            if method == 'PUT' and reply.status_code in (200, 201):
                path = url.split('/contents/', 1)[1]
                return self.response(reply.status_code, {'content': {'sha': hashlib.sha256(self.files[path]).hexdigest()}})
            return reply


def test_25_simultaneous_assessment_writes_survive_without_local_conflicts():
    repo = ConcurrentRepo(); store = cloud_store(repo, Fernet.generate_key().decode())
    gate = threading.Barrier(25)
    def save(i):
        gate.wait(timeout=10)
        return store.transaction(lambda state: state['users'].setdefault(str(i), {'answer':f'답안 {i}'}))
    with ThreadPoolExecutor(max_workers=25) as pool:
        result = list(pool.map(save, range(25)))
    persisted = json.loads(store.fernet.decrypt(repo.files[STATE_PATH]))
    assert len(persisted['users']) == 25 and len(result) == 25
    assert repo.conflicts == 0
    state_gets = [c for c in repo.calls if c[0] == 'GET' and c[1].endswith(STATE_PATH)]
    assert len(state_gets) == 1
    before = len(repo.calls)
    with ThreadPoolExecutor(max_workers=25) as pool:
        states = list(pool.map(lambda _:store.read(), range(25)))
    assert len(repo.calls) == before
    states[0]['users'].clear()
    assert len(store.read()['users']) == 25


def test_external_conflict_merges_latest_state_and_failed_write_is_not_cached():
    repo = ConcurrentRepo(); store = cloud_store(repo, Fernet.generate_key().decode())
    store.transaction(lambda s:s['users'].update({'first':{'answer':'A'}}))
    def external():
        state = json.loads(store.fernet.decrypt(repo.files[STATE_PATH]))
        state['users']['external'] = {'answer':'외부 저장'}
        repo.files[STATE_PATH] = store.fernet.encrypt(json.dumps(state).encode())
    repo.external_write = external
    store.transaction(lambda s:s['users'].update({'next':{'answer':'B'}}))
    assert repo.conflicts == 1
    assert set(store.read()['users']) == {'first','external','next'}
    repo.fail_next = True
    with pytest.raises(Exception, match='GitHub 저장 실패'):
        store.transaction(lambda s:s['users'].update({'failed':{'answer':'미저장'}}))
    assert 'failed' not in store.read()['users']


def test_noop_avoids_state_write_but_retries_a_pending_archive(monkeypatch):
    repo = ConcurrentRepo(); store = cloud_store(repo, Fernet.generate_key().decode())
    store.transaction(lambda s:s['users'].update({'first':{}}))
    calls = len(repo.calls); hook = []
    monkeypatch.setattr('record_core.assessment.after_commit', lambda *args:hook.append(True))
    store._archive_retry = True
    store.transaction(lambda s:s['users'].setdefault('first',{}))
    assert hook == [True]
    assert not [c for c in repo.calls[calls:] if c[0] == 'PUT']


def test_25_note_submissions_share_a_durable_commit_and_keep_archives(gh,monkeypatch):
    b=gh.b; gate=threading.Barrier(25)
    monkeypatch.setattr(gh.m.time,'sleep',REAL_SLEEP)
    def save(i):
        gate.wait(timeout=10)
        REAL_SLEEP(i*.001)
        b.append('sudanotes',{'id':f'n{i}', 'student_id':f'10{i:03}', 'subject':'공통수학2', 'q1':f'개념 설명 {i}'})
        b.flush()
    with ThreadPoolExecutor(max_workers=25) as pool:
        list(pool.map(save, range(25)))
    assert b.pending_count()==0
    assert len([p for p in gh.remote if p.startswith('data/sudanotes/')])==25
    packets=[p for p in gh.remote if p.endswith('/current.json.enc')]
    assert len(packets)==25
    for i in range(25):
        sid=f'10{i:03}'; path=next(p for p in packets if p.startswith(b.archive_crypto.student_dir(sid)+'/'))
        assert b.archive_crypto.open_bundle(gh.remote[path],sid,path)['payload']['rows'][0]['q1']==f'개념 설명 {i}'
    # A slow test host may need a second group; still never one commit per student.
    assert len([c for c in gh.calls if c[0]=='PATCH']) < 25


def test_25_repeated_release_checks_do_not_reread_assets(monkeypatch):
    import quiz_pop.release as release
    release._file_digest.cache_clear()
    root=Path(__file__).resolve().parents[1]/'quiz_pop'
    original=Path.read_bytes; reads=[]
    def counted(path):
        reads.append(path); return original(path)
    monkeypatch.setattr(Path,'read_bytes',counted)
    assert release.release_issues(root)==[]
    initial=len(reads)
    with ThreadPoolExecutor(max_workers=25) as pool:
        results=list(pool.map(lambda _:release.release_issues(root),range(25)))
    assert all(r==[] for r in results) and len(reads)==initial


def test_teacher_only_selected_tab_executes_and_text_survives_tab_change(monkeypatch):
    import streamlit as st
    import ui
    import views.teacher as view
    hits=[]
    monkeypatch.setattr(view,'st',st);monkeypatch.setattr(ui,'st',st)
    monkeypatch.setattr(ui,'page_title',lambda *args:None)
    def section(name):
        def render(*args):
            hits.append(name)
            st.text_input('작성 중 메모',key='memo_'+name)
        return render
    for name in ('tab_teaching_progress','tab_teacher_diary','tab_afterschool','tab_lock','tab_announcements',
                 'tab_observe','tab_points','tab_record','tab_roster','tab_settings'):
        monkeypatch.setattr(view,name,section(name))
    app=AppTest.from_string("from views.teacher import page\npage({'role':'teacher'})").run()
    assert not app.exception and hits==['tab_teaching_progress']
    app.text_input[0].set_value('저장 전 작성 내용').run()
    hits.clear();app.session_state['teacher_active_tab']='📝 생기부 생성기';app.run()
    assert not app.exception and hits==['tab_record']
    hits.clear();app.session_state['teacher_active_tab']='📅 진도관리';app.run()
    assert not app.exception and app.text_input[0].value=='저장 전 작성 내용'
    assert hits==['tab_teaching_progress']


def test_student_course_skips_hidden_assignments_and_calendar(monkeypatch):
    import streamlit as st
    import ui
    import views.classroom as view
    hits=[]
    monkeypatch.setattr(view,'st',st);monkeypatch.setattr(ui,'st',st)
    monkeypatch.setattr(view,'_teacher',lambda user:False)
    monkeypatch.setattr(view,'_work_tab',lambda name,*args:hits.append(name))
    monkeypatch.setattr(view,'_calendar',lambda *args,**kwargs:hits.append('calendar'))
    app=AppTest.from_string("from views.classroom import _course_detail\n_course_detail(None,{'id':'demo'},{'id':'s','role':'student'})").run()
    assert not app.exception and hits==['render_stream']
    hits.clear();app.session_state['classroom_s_course_tab_demo']='과제·퀴즈·수행평가';app.run()
    assert not app.exception and hits==['render_assignments']
