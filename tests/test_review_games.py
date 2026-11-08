"""Offline classroom simulations: real service/storage; no user accounts/network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import sys
import threading
import types
from pathlib import Path
import zipfile

import pytest
from test_concept_quiz import FakeST, load
from test_student_record_vault import gh
from review_core import engine, generator

ROOT=Path(__file__).resolve().parents[1]
QUESTIONS=[dict(prompt='점 (2,3)의 x축 대칭점은?', options=['(2,-3)','(-2,3)','(3,2)','(-2,-3)'],answer=0,explanation='y좌표의 부호만 바꿉니다.'),
           dict(prompt='점 (1,2)를 x축 방향으로 3만큼 옮긴 점은?', options=['(1,5)','(4,2)','(3,2)','(-2,2)'],answer=1,explanation='x좌표에 3을 더해 (4,2)입니다.')]

@pytest.fixture
def env(monkeypatch,tmp_path):
    st=FakeST();monkeypatch.setitem(sys.modules,'streamlit',st)
    db=load('storage',ROOT/'storage.py',monkeypatch)
    b=db.LocalBackend(str(tmp_path/'data'));monkeypatch.setattr(db,'get_backend',lambda:b)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    rt=types.ModuleType('realtime');rt.locked=False;rt.is_locked=lambda _:rt.locked
    monkeypatch.setitem(sys.modules,'realtime',rt)
    svc=load('review_core.service',ROOT/'review_core/service.py',monkeypatch)
    import review_core
    monkeypatch.setattr(review_core,'service',svc,raising=False)
    t=dict(id='teacher',name='시험교사',role='teacher',must_change='0',**{'class':''})
    other=dict(t,id='teacher2')
    students=[dict(id=f'101{i:02}',name=f'가상학생{i}',role='student',must_change='0',**{'class':'1-1'}) for i in range(1,26)]
    outsider=dict(students[0],id='10201',name='다른반',**{'class':'1-2'})
    for u in [t,other,outsider]+students:b.append('users',u)
    def actor(u):st.session_state['user']=deepcopy(u);return u
    def create(mode='race',questions=QUESTIONS):
        return svc.create(actor(t),title='대칭이동 복습',questions=questions,mode=mode,classes=['1-1'],duration=300)
    def begin(mode='race',n=1):
        code=create(mode)
        for s in students[:n]:svc.join(actor(s),code)
        svc.control(actor(t),code,'start')
        return code
    return types.SimpleNamespace(st=st,db=db,b=b,svc=svc,t=t,other=other,ss=students,out=outsider,actor=actor,create=create,begin=begin,rt=rt)

@pytest.mark.parametrize('mode',list(engine.MODES))
def test_end_to_end_scores_and_unanswered(env,mode):
    e=env;code=e.begin(mode,2)
    s=e.ss[0];e.actor(s)
    e.svc.submit(s,code,0,0)
    if mode in ('treasure','fishing'):e.svc.submit(s,code,0,0,'reward')
    e.svc.submit(s,code,1,0)
    e.svc.control(e.actor(e.t),code,'end')
    v=e.svc.snapshot(e.t,code);row=next(r for r in v['report']['rows'] if r['student_id']==s['id'])
    assert (row['answered'],row['correct'],row['wrong'],row['unanswered'])==(2,1,1,0)
    untouched=next(r for r in v['report']['rows'] if r['student_id']!=s['id'])
    assert (untouched['wrong'],untouched['unanswered'])==(0,2)
    assert v['report']['questions'][0]['choices']==[1,0,0,0]
    assert v['report']['questions'][1]['wrong']==1
    mine=e.svc.snapshot(e.actor(s),code)
    assert 'report' not in mine and 'paper' not in mine and 'individuals' not in mine
    assert mine['answers'][0]['answer']==0
    if mode=='practice':assert mine['leaderboard']==[]


def test_25_concurrent_participants_and_duplicate_tab_submissions(env):
    e=env;code=e.create('treasure')
    def join(s):e.svc.join(e.actor(s),code)
    with ThreadPoolExecutor(max_workers=25) as pool:list(pool.map(join,e.ss))
    assert len(e.b.read('review_attempts'))==25
    e.svc.control(e.actor(e.t),code,'start')
    def play(s):
        e.actor(s)
        e.svc.submit(s,code,0,0);e.svc.submit(s,code,0,0)
        e.svc.submit(s,code,0,2,'reward');e.svc.submit(s,code,0,2,'reward')
        e.svc.submit(s,code,1,1)
        e.svc.submit(s,code,1,1,'reward')
    with ThreadPoolExecutor(max_workers=25) as pool:list(pool.map(play,e.ss))
    v=e.svc.snapshot(e.actor(e.t),code)
    assert v['status']=='ended' and v['report']['correct']==50
    assert v['report']['completed']==25
    assert all(240<=r['score']<=400 for r in v['report']['rows'])
    assert len({a['alias'] for a in e.b.read('review_attempts')})==25


def test_auth_target_and_answer_key_isolation(env):
    e=env;code=e.create()
    with pytest.raises(PermissionError):e.svc.join(e.actor(e.out),code)
    with pytest.raises(PermissionError):e.svc.snapshot(e.actor(e.other),code)
    with pytest.raises(PermissionError):e.svc.control(e.actor(e.ss[0]),code,'start')
    with pytest.raises(PermissionError):e.svc.create(e.ss[0],title='x',questions=QUESTIONS,mode='race',classes=['1-1'],duration=300)
    e.svc.join(e.actor(e.ss[0]),code);e.svc.control(e.actor(e.t),code,'start')
    v=e.svc.snapshot(e.actor(e.ss[0]),code)
    assert 'answer' not in v['question'] and 'explanation' not in v['question']
    serialized=json.dumps(v,ensure_ascii=False)
    assert '10101' not in serialized and '가상학생' not in serialized and 'questions_json' not in serialized
    assert e.db.read('review_rooms')==[] and e.db.read('review_attempts')==[]
    with pytest.raises(PermissionError):e.db.append('review_rooms',{})
    with pytest.raises(PermissionError):e.svc.csv_export(e.ss[0],code)
    e.rt.locked=True
    with pytest.raises(PermissionError):e.svc.submit(e.ss[0],code,0,0)


def test_server_timer_rejects_late_answers(env,monkeypatch):
    e=env;code=e.begin();s=e.actor(e.ss[0])
    room=e.b.read('review_rooms')[0]
    monkeypatch.setattr(e.svc.time,'time',lambda:float(room['started_at'])+301)
    with pytest.raises(engine.ReviewError):e.svc.submit(s,code,0,0)
    v=e.svc.snapshot(s,code)
    assert v['status']=='ended' and v['unanswered']==2 and v['wrong']==0


def test_reconnect_no_duplicate_and_late_join_blocked(env):
    e=env;code=e.begin(n=2);s=e.actor(e.ss[0])
    e.svc.submit(s,code,0,0)
    e.svc.join(s,code)
    assert e.svc.snapshot(s,code)['answered']==1
    with pytest.raises(engine.ReviewError):e.svc.join(e.actor(e.ss[2]),code)
    e.b.update('users',s['id'],{'class':'1-2'})
    with pytest.raises(PermissionError):e.svc.snapshot(e.actor(s),code)


def test_teacher_shared_review_and_reveal(env):
    e=env;code=e.begin();e.svc.control(e.actor(e.t),code,'end')
    e.svc.control(e.t,code,'review','q1',False)
    v=e.svc.snapshot(e.actor(e.ss[0]),code)
    assert v['review']['id']=='q1' and 'answer' not in v['review']
    e.svc.control(e.actor(e.t),code,'review','q1',True)
    assert e.svc.snapshot(e.actor(e.ss[0]),code)['review']['answer']==0
    e.svc.control(e.actor(e.t),code,'review','',False)
    assert 'review' not in e.svc.snapshot(e.actor(e.ss[0]),code)


def test_team_balance_and_joint_ranks(env):
    e=env;code=e.begin('team',25)
    attempts=e.b.read('review_attempts')
    assert sorted([sum(a['team']==t for a in attempts) for t in ('핑크 팀','민트 팀')])==[12,13]
    e.svc.control(e.actor(e.t),code,'end')
    v=e.svc.snapshot(e.t,code)
    assert {r['rank'] for r in v['report']['rows']}=={1}
    assert all(t['score']==0 for t in v['teams'])


def test_reward_hidden_and_cannot_forge_points_or_skip(env):
    e=env;code=e.begin('treasure');s=e.actor(e.ss[0])
    with pytest.raises(engine.ReviewError):e.svc.submit(s,code,1,1)
    with pytest.raises(engine.ReviewError):e.svc.submit(s,code,0,99)
    e.svc.submit(s,code,0,0)
    v=e.svc.snapshot(s,code)
    assert 'reward_options' not in json.dumps(v)
    with pytest.raises(engine.ReviewError):e.svc.submit(s,code,1,1)
    with pytest.raises(engine.ReviewError):e.svc.submit(s,code,0,1000,'reward')
    e.svc.control(e.actor(e.t),code,'end')
    assert e.svc.snapshot(e.actor(s),code)['score'] in (120,150,200)


def test_restart_preserves_paper_answers_and_reports(env):
    e=env;code=e.begin();s=e.actor(e.ss[0]);e.svc.submit(s,code,0,0)
    reloaded=e.db.LocalBackend(e.b.root)
    e.b=reloaded;e.svc.db.get_backend=lambda:reloaded
    assert e.svc.snapshot(s,code)['correct']==1
    e.svc.control(e.actor(e.t),code,'end')
    csv=e.svc.csv_export(e.t,code).decode('utf-8-sig')
    assert '미응답' in csv and '가상학생1' in csv


def test_remote_atomic_archive_and_retry(gh):
    b=gh.b
    q=engine.validate_questions(QUESTIONS)
    room=dict(id='room',owner_id='teacher',code='123456',questions_json=json.dumps(q),targets_json='[{"id":"other-private-student"}]',title='복습')
    a=dict(id='attempt',room_id='room',student_id='10101',answers_json='[]')
    b.append('review_rooms',room);b.append('review_attempts',a)
    assert ('review_attempts','10101') in b.archive_dirty
    gh.control['deny']=True
    with pytest.raises(RuntimeError):b.flush()
    assert b.dirty and b.archive_dirty
    gh.control['deny']=False;b.flush()
    assert not b.dirty and not b.archive_dirty
    path=next(p for p in gh.remote if '/games/' in p and p.endswith('current.json.enc'))
    bundle=b.archive_crypto.open_bundle(gh.remote[path],'10101',path)
    payload=bundle['payload']
    assert payload['table']=='review_attempts'
    assert payload['review_rooms'][0]['questions_json']==json.dumps(q)
    assert 'targets_json' not in payload['review_rooms'][0]
    assert any(p.startswith('data/review_rooms/') for p in gh.remote)
    b.update('review_rooms','room',{'status':'ended'})
    assert ('review_attempts','10101') in b.archive_dirty


def test_validation_and_supported_file_extraction():
    assert generator.prepare_file('수업.txt','수업: 대칭이동'.encode())['content'][0]['type']=='input_text'
    doc=io.BytesIO()
    with zipfile.ZipFile(doc,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="urn:test"><w:t>원의 중심</w:t></w:document>')
    assert '원의 중심' in generator.prepare_file('자료.docx',doc.getvalue())['content'][0]['text']
    ppt=io.BytesIO()
    with zipfile.ZipFile(ppt,'w') as z:z.writestr('ppt/slides/slide1.xml','<a:slide xmlns:a="urn:test"><a:t>함수</a:t></a:slide>')
    assert '함수' in generator.prepare_file('자료.pptx',ppt.getvalue())['content'][0]['text']
    for name,data in [('bad.pdf',b'not a PDF'),('bad.docx',b'not a doc'),('x.hwp',b'a')]:
        with pytest.raises(engine.ReviewError):generator.prepare_file(name,data)
    with pytest.raises(engine.ReviewError):engine.validate_questions([QUESTIONS[0],QUESTIONS[0]])
    with pytest.raises(engine.ReviewError):generator.generate('대칭이동',[],config=generator.Settings())


def test_builtin_bank_and_ai_request_contract(monkeypatch):
    assert len(generator.bank_questions('move.reflection',8))==8
    from record_core.ai import RecordAI
    calls=[]
    def fake(self,instructions,contents,schema,consent):
        calls.append((contents,schema,consent));return {'questions':QUESTIONS},{}
    monkeypatch.setattr(RecordAI,'_call',fake)
    qs,source=generator.generate('대칭이동',[],2,consent=True,config=generator.Settings('fake'))
    assert len(qs)==2 and source['kind']=='title_ai' and calls[0][2]
    with pytest.raises(engine.ReviewError):generator.generate('대칭이동',[],2,consent=False,config=generator.Settings('fake'))
