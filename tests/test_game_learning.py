"""Offline regression tests: real engine/store, fake UI only. No live accounts."""
from copy import deepcopy
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
import io
import json
import random
import re
import sys
import threading
import types
from pathlib import Path

import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_core import bank,engine,curriculum,presentation
from test_concept_quiz import FakeST,load


class Rerun(BaseException):pass
class GameST(FakeST):
    def rerun(self,**kw):raise Rerun()
    def metric(self,*args,**kw):self._out('metric',args,**kw)
    def file_uploader(self,label,*args,key=None,**kw):return self.session_state.get(key)
    def number_input(self,label,value=0,key=None,**kw):return self.session_state.setdefault(key,value)
    def form_submit_button(self,label,*args,**kw):return self.button(label,key='submit:'+label,**kw)
    def divider(self):pass
    def link_button(self,*args,**kw):self._out('link',args,**kw)


@pytest.fixture
def game_env(monkeypatch,tmp_path):
    st=GameST();monkeypatch.setitem(sys.modules,'streamlit',st)
    db=load('storage',ROOT/'storage.py',monkeypatch)
    backend=db.LocalBackend(str(tmp_path/'data'))
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    rt=types.ModuleType('realtime');rt.locked=False;rt.messages=[];rt.is_locked=lambda _:rt.locked;rt.push=lambda *args:rt.messages.append(args)
    monkeypatch.setitem(sys.modules,'realtime',rt)
    svc=load('game_core.service',ROOT/'game_core/service.py',monkeypatch)
    import game_core
    monkeypatch.setattr(game_core,'service',svc,raising=False)
    view=load('game_core.view',ROOT/'game_core/view.py',monkeypatch)
    monkeypatch.setattr(game_core,'view',view,raising=False)
    t=dict(id='teacher',name='가상교사',role='teacher',must_change='0',**{'class':''})
    other=dict(t,id='other-teacher')
    students=[dict(id=f'100{i}',name=f'가상학생{i}',role='student',must_change='0',**{'class':f'1-{1 if i<3 else 2}'}) for i in range(1,5)]
    for u in [t,other]+students:backend.append('users',u)
    def actor(u):st.session_state['user']=deepcopy(u);return u
    def profile(u=None):return svc.profile(u or students[0])
    def start(u=None,tid='move.reflection',mode='puzzle',mission=''):
        u=u or students[0];actor(u);return svc.start(u,tid,mode,profile(u)['revision'],mission_id=mission)
    def raw(u=None):
        u=u or students[0]
        return json.loads(next(r['state_json'] for r in backend.read('game_profiles') if r['student_id']==u['id']))
    def action(sid,kind,u=None,**args):
        u=u or students[0];p=profile(u);s=next(s for s in p['sessions'] if s['id']==sid)
        return svc.lesson_action(u,sid,s['index'],p['revision'],kind,**args)
    def complete(sid,u=None):
        u=u or students[0]
        for i in range(5):
            s=engine.active(raw(u),sid)
            action(sid,'answer',u,choice=s['questions'][i]['answer'])
            action(sid,'advance',u)
    actor(t)
    return types.SimpleNamespace(st=st,db=db,b=backend,rt=rt,svc=svc,view=view,t=t,other=other,ss=students,actor=actor,profile=profile,start=start,raw=raw,action=action,complete=complete,monkeypatch=monkeypatch)


@pytest.mark.parametrize('topic_id',curriculum.TOPICS)
@pytest.mark.parametrize('level',['천천히','기본','한 걸음 더'])
def test_all_concepts_five_unique_questions(topic_id,level):
    for seed in range(18):
        qs=bank.generate(topic_id,seed,level=level)
        assert len(qs)==5 and len({q['prompt'] for q in qs})==5
        assert [q['id'] for q in qs]==['q1','q2','q3','q4','q5']
        assert all(q['topic_id']==topic_id and bank.validate(q)==q for q in qs)
        assert qs==bank.generate(topic_id,seed,level=level)


@pytest.mark.parametrize('kind',['divide','high_equation','quadratic_system','linear_system','quadratic_inequality','line_distance','circle_line','set_meaning','proof'])
def test_extra_templates_independent_math_oracle(kind):
    import math
    for seed in range(60):
        q=bank._extra(kind,random.Random(seed),15);text=q['prompt'];nums=[int(n) for n in re.findall(r'(?<![A-Za-z])[−-]?\d+',text)]
        # Parse the displayed problem and solve independently of generator state.
        if kind=='divide':
            m=re.search(r'P\(x\)=(\d+)x²\+\(([−-]?\d+)\)x\+\(([−-]?\d+)\).*?x−(\d+)',text)
            b,c,d,a=map(int,m.groups());expected=c+a*b
        elif kind=='high_equation':
            expected=sum({int(x) for x in re.findall(r'x−(\d+)',text)})
        elif kind=='quadratic_system':
            total,product=map(int,re.search(r'x\+y=(\d+), xy=(\d+)',text).groups())
            possible=[x for x in range(1,total) if x*(total-x)==product and x>total-x];assert len(possible)==1;expected=possible[0]
        elif kind=='linear_system':
            c,d,h=map(int,re.search(r'x\+(\d+)>(\d+), 2x≤(\d+)',text).groups())
            expected=sum(x+c>d and 2*x<=h for x in range(-100,101))
        elif kind=='quadratic_inequality':
            a,b,c=map(int,re.search(r'x−(\d+)\)\(x−(\d+)\)≤0, x≥(\d+)',text).groups())
            expected=sum((x-a)*(x-b)<=0 and x>=c for x in range(-100,101))
        elif kind=='line_distance':
            x,y,k=map(int,re.search(r'점 \((-?\d+), (-?\d+)\).*3x\+4y\+\((-?\d+)\)',text).groups());expected=abs(3*x+4*y+k)/5
        elif kind=='circle_line':
            a,b,r2,line=map(int,re.search(r'x−(\d+)\).*y−(\d+)\)²=(\d+).*x=(\d+)',text).groups())
            value=r2-(line-a)**2;expected=2 if value>0 else 1 if value==0 else 0
        elif kind=='set_meaning':expected=len(set(re.findall(r'\d+',text)))
        elif kind=='proof':
            square,root=map(int,re.search(r'x²=(\d+)이면 x=(\d+)',text).groups());expected=-math.sqrt(square);assert expected!=root
        assert float(q['options'][q['answer']])==expected, q


def test_toc_subject_mapping_and_disclosure():
    ids=set()
    for ed in curriculum.EDITIONS:
        for subject in ['공통수학1','공통수학2']:
            rr=curriculum.rows(ed,subject)
            assert rr and all(r['subject']==subject and r['major'] and r['middle'] and r['small'] for r in rr)
            assert len({r['id'] for r in rr})==len(rr)
            ids.update(r['id'] for r in rr)
    assert ids==set(curriculum.TOPICS)
    assert curriculum.HONG!=curriculum.JEON


def test_answers_protected_and_new_account_no_writes(game_env):
    e=game_env;u=e.ss[0];e.actor(u)
    assert e.profile()['sessions']==[] and not e.b.read('game_profiles')
    sid=e.start();p=e.profile();s=p['sessions'][0]
    assert 'answer' not in s['question'] and 'explanation' not in s['question'] and 'questions' not in s
    assert s['question']['hints']==[] and e.db.read('game_profiles')==[]
    assert e.db.read('game_questions')==[]
    with pytest.raises(PermissionError):e.svc.profile(u,e.ss[1]['id'])
    with pytest.raises(PermissionError):e.db.append('game_profiles',{})
    with pytest.raises(PermissionError):e.db.update('game_profiles','x',{})


def test_progress_switch_pause_restart_and_same_reward(game_env):
    e=game_env;u=e.ss[0];sid=e.start();raw=e.raw();s=engine.active(raw,sid)
    e.action(sid,'hint');e.action(sid,'answer',choice=s['questions'][0]['answer']);e.action(sid,'advance')
    e.action(sid,'switch',mode='adventure');e.action(sid,'pause')
    assert e.profile()['active_id']=='' and e.profile()['coins']==2
    fresh=e.db.LocalBackend(e.b.root)
    e.monkeypatch.setattr(e.db,'get_backend',lambda:fresh)
    p=e.profile();assert p['sessions'][0]['index']==1 and p['sessions'][0]['answers'][0]['kind']=='supported'
    e.svc.resume(u,sid,p['revision']);p=e.profile()
    assert p['sessions'][0]['mode']=='adventure' and p['sessions'][0]['modes_used']==['puzzle','adventure']
    assert p['active_id']==sid and p['sessions'][0]['status']=='working'
    row=fresh.read('game_profiles')[0]
    path=e.db.GitHubBackend._path('game_profiles',row)
    assert u['id'] not in path and path.endswith('.csv')


def test_reward_idempotency_conflict_and_locked_mutations(game_env):
    e=game_env;u=e.ss[0];sid=e.start();q=e.raw()['sessions'][0]['questions'][0]
    e.action(sid,'answer',choice=q['answer']);p=e.profile();rev=p['revision']
    e.svc.lesson_action(u,sid,0,rev,'advance');assert e.profile()['coins']==2
    with pytest.raises(engine.Conflict):e.svc.lesson_action(u,sid,0,rev,'advance')
    with pytest.raises(engine.Conflict):e.svc.lesson_action(u,sid,0,e.profile()['revision'],'advance')
    assert e.profile()['coins']==2
    e.rt.locked=True
    for kind,kwargs in [('hint',{}),('answer',{'choice':0}),('switch',{'mode':'puzzle'}),('pause',{})]:
        with pytest.raises(PermissionError):e.action(sid,kind,**kwargs)
    with pytest.raises(PermissionError):e.svc.buy(u,'coat_mint',e.profile()['revision'])
    assert e.profile()['coins']==2


def test_completion_wardrobe_and_unified_growth(game_env):
    e=game_env;u=e.ss[0];sid=e.start();e.complete(sid)
    p=e.profile();assert p['coins']==12 and p['growth'][0]['independent']==5
    assert e.b.read('points')==[]
    e.svc.buy(u,'coat_lilac',p['revision']);p=e.profile();assert p['coins']==0 and p['equipped']['coat']=='coat_lilac'
    e.svc.buy(u,'coat_lilac',p['revision']);assert e.profile()['coins']==0
    with pytest.raises(engine.GameError):e.svc.buy(u,'back_sky',e.profile()['revision'])
    sid2=e.start(mode='adventure');e.complete(sid2)
    p=e.profile();assert p['coins']==12 and len(p['growth'])==1 and p['growth'][0]['completed']==10
    assert len(p['sessions'])==2 and 'answer' in p['sessions'][0]['review'][0]


def test_hints_wrong_and_explanation_not_independent(game_env):
    e=game_env;sid=e.start();q=e.raw()['sessions'][0]['questions'][0]
    e.action(sid,'answer',choice=(q['answer']+1)%4)
    assert e.profile()['coins']==0
    e.action(sid,'reveal')
    with pytest.raises(engine.GameError):e.action(sid,'reflect_solution',text='네')
    e.action(sid,'reflect_solution',text='x축 대칭에서는 y좌표의 부호만 바뀝니다.')
    e.action(sid,'advance');p=e.profile()
    assert p['coins']==2 and p['growth'][0]['explained']==1 and p['growth'][0]['independent']==0


def test_teacher_authorization_and_review_gate(game_env):
    e=game_env;q=bank.generate('circle.line',1)[0];e.actor(e.t)
    with pytest.raises(engine.GameError):e.svc.save_question(e.t,q,published=True)
    qid=e.svc.save_question(e.t,q,published=True,reviewed=True)
    qs=e.svc.teacher_questions(e.t,'circle.line');assert qs[0]['id']==qid
    e.actor(e.other)
    with pytest.raises(PermissionError):e.svc.save_question(e.other,q,qid=qid,revision=1)
    e.actor(e.ss[0])
    with pytest.raises(PermissionError):e.svc.teacher_questions(e.ss[0],'circle.line')
    forged=dict(e.ss[0],role='teacher')
    with pytest.raises(PermissionError):e.svc.save_question(forged,q)
    e.actor(e.t);e.b.update('users',e.t['id'],{'must_change':'1'})
    with pytest.raises(PermissionError):e.svc.save_question(e.t,q)


def test_missions_targeting_and_points_require_explicit_teacher_approval(game_env):
    e=game_env;e.actor(e.t)
    mid=e.svc.create_mission(e.t,'우리 반 대칭','move.reflection',['1-1'],allow_points=True)
    e.actor(e.ss[2]);assert e.svc.missions(e.ss[2])==[]
    with pytest.raises(PermissionError):e.start(e.ss[2],mission=mid)
    sid=e.start(mission=mid);e.complete(sid);u=e.ss[0]
    e.svc.request_points(u,sid,e.profile()['revision']);assert not e.b.read('points')
    e.actor(e.other)
    with pytest.raises(PermissionError):e.svc.approve_points(e.other,u['id'],sid,2,'과정 확인')
    e.actor(e.t);assert e.svc.approve_points(e.t,u['id'],sid,2,'과정 확인')
    assert not e.svc.approve_points(e.t,u['id'],sid,2,'중복 클릭')
    assert len(e.b.read('points'))==1 and e.b.read('points')[0]['score']=='2'
    assert len(e.rt.messages)==1
    e.actor(u);assert e.profile()['coins']==12
    with pytest.raises(engine.GameError):e.svc.start(u,'move.reflection','puzzle',e.profile()['revision'],mission_id=mid)


def test_default_mission_no_point_request_and_teacher_feedback(game_env):
    e=game_env;e.actor(e.t);mid=e.svc.create_mission(e.t,'나의 속도','move.reflection',['1-1'])
    sid=e.start(mission=mid);e.complete(sid)
    with pytest.raises(PermissionError):e.svc.request_points(e.ss[0],sid,e.profile()['revision'])
    e.actor(e.t);e.svc.save_feedback(e.t,e.ss[0]['id'],'힌트로 배운 규칙을 다음에 스스로 적용했어요.')
    e.actor(e.ss[0]);assert len(e.profile()['feedback'])==1
    e.actor(e.ss[1]);assert e.profile(e.ss[1])['feedback']==[]
    assert not e.b.read('points')


def test_resource_class_permission_type_and_hide(game_env):
    e=game_env;e.actor(e.t)
    args=(e.t,'move.reflection','대칭 학습지',['1-1'],'worksheet.pdf',b'%PDF-1.7\nfake-test')
    with pytest.raises(engine.GameError):e.svc.upload_resource(*args)
    rid=e.svc.upload_resource(*args,confirmed=True)
    e.actor(e.ss[2]);assert not e.svc.resources(e.ss[2],'move.reflection')
    with pytest.raises(PermissionError):e.svc.download_resource(e.ss[2],rid)
    e.actor(e.ss[0]);assert e.svc.download_resource(e.ss[0],rid)[0].startswith(b'%PDF')
    e.rt.locked=True
    with pytest.raises(PermissionError):e.svc.download_resource(e.ss[0],rid)
    e.rt.locked=False;e.actor(e.t);e.svc.remove_resource(e.t,rid)
    e.actor(e.ss[0]);assert not e.svc.resources(e.ss[0],'move.reflection')
    e.actor(e.t)
    with pytest.raises(engine.GameError):e.svc.upload_resource(*args[:-1],b'<script>test</script>',confirmed=True)


def test_csv_import_validation_and_draft_only(game_env):
    e=game_env;e.actor(e.t);qs=bank.parse_csv(bank.csv_template(),'move.reflection')
    assert len(qs)==1 and qs[0]['answer']==0
    e.svc.import_questions(e.t,qs);assert e.b.read('game_questions')[0]['published']=='0'
    q=deepcopy(qs[0]);q['options']=['2','2.0','3','4']
    with pytest.raises(ValueError):bank.validate(q)
    bad=bank.csv_template().replace(b',1,',b',9,')
    with pytest.raises(ValueError):bank.parse_csv(bad,'move.reflection')


def test_invalid_placement_cannot_earn(game_env):
    e=game_env;sid=e.start();q=e.raw()['sessions'][0]['questions'][0]
    with pytest.raises(engine.GameError):e.action(sid,'advance')
    e.action(sid,'answer',choice=q['answer'])
    with pytest.raises(engine.GameError):e.action(sid,'advance',placement=(99,99,0))
    assert e.profile()['coins']==0 and e.profile()['sessions'][0]['index']==0


def test_simultaneous_students_have_separate_profiles(game_env):
    e=game_env
    def work(u):
        e.actor(u);sid=e.start(u);e.complete(sid,u);return e.profile(u)['coins']
    with ThreadPoolExecutor(max_workers=4) as executor:assert list(executor.map(work,e.ss))==[12]*4
    assert len(e.b.read('game_profiles'))==4
    assert len(list(Path(e.b.root,'game_profiles').glob('*.csv')))==4


@pytest.mark.parametrize('role,child,action',[
    ('student','개념 학습게임',None),('student','나의 성장기록',None),
    ('teacher','개념 학습게임','학생 화면 미리보기'),('teacher','개념 학습게임','문항·학습지 관리'),
    ('teacher','개념 학습게임','미션 배포'),('teacher','개념 학습게임','교과서 설정'),('teacher','나의 성장기록',None)])
def test_page_branches_with_fake_widgets(game_env,role,child,action):
    e=game_env;u=e.t if role=='teacher' else e.ss[0];e.actor(u)
    e.st.session_state['_gg_child']=child
    if action:e.st.session_state['_gg_teacher_action']=action
    e.view.page(u)
    assert not [x for x in e.st.outputs if x[0]=='error'],e.st.outputs


def test_ui_full_student_attempt_and_preview(game_env):
    e=game_env;u=e.ss[0];sid=e.start()
    for i in range(5):
        p=e.profile();s=p['sessions'][0]
        e.view._lesson(u,p,s)
        q=e.raw()['sessions'][0]['questions'][i]
        key=f'learn_{sid}_{i}'
        e.st.session_state[key+'_choice']=q['answer'];e.st.events.add('submit:내 생각 확인하기')
        with pytest.raises(Rerun):e.view._lesson(u,p,s)
        p=e.profile();e.view._lesson(u,p,p['sessions'][0]);e.st.events.add(key+'_next')
        with pytest.raises(Rerun):e.view._lesson(u,p,p['sessions'][0])
    p=e.profile();e.view._lesson(u,p,p['sessions'][0]);assert p['coins']==12
    assert not [x for x in e.st.outputs if x[0]=='error']
    e.actor(e.t);e.st.events.add('gg_demo_start')
    with pytest.raises(Rerun):e.view._teacher_preview(e.t)
    e.view._teacher_preview(e.t)
    assert not [x for x in e.st.outputs if x[0]=='error']


def test_menu_order_and_submenu_ast():
    import ast
    text=(ROOT/'views/tools.py').read_text();tree=ast.parse(text)
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOOLS' for t in n.targets))
    tools=ast.literal_eval(node.value)
    assert [x[0] for x in tools]==['tool_desmos','snorkl','tool_games','tool_quiz','tool_apps']
    assert [x[1] for x in tools]==['1. 데스모스','2. 수행평가','3. 게임으로 배우기','4. 퀴즈','5. 앱 (by Good쌤)']
    assert '"데스모스 하위 메뉴", ["tool_desmos", "tool_activity"]' in text


def test_markup_escapes_student_content():
    assert '<script>' not in presentation.note('<script>alert(1)</script>')
    assert 'onload' not in presentation.avatar({'coat':'onload=bad'},12)
    assert 'aria-label' in presentation.puzzle([[0]*6 for _ in range(6)])
    assert 'aria-label' in presentation.adventure([[0,0],[1,0]])


def test_puzzle_completed_line_clears_without_bonus_or_penalty():
    p=engine.new_profile();sid=engine.start(p,'move.reflection','puzzle',bank.generate('move.reflection',9),'t');s=engine.active(p,sid)
    s['board'][0]=[5,5,0,0,0,0]
    engine.submit(s,0,s['questions'][0]['answer']);engine.advance(p,s,0,'later',(2,0,0))
    assert s['board'][0]==[0]*6 and s['lines_cleared']==1 and p['earned']==2


@pytest.mark.parametrize('tab',['기본 문제·직접 추가','내 문항 수정','CSV 일괄 등록','학습지 업로드'])
def test_teacher_content_tabs_render(game_env,tab):
    e=game_env;e.actor(e.t);tid='poly.add';q=bank.generate(tid,3)[0]
    e.svc.save_question(e.t,q,published=True,reviewed=True)
    e.st.session_state['gg_content_tab']=tab
    e.view._content_manager(e.t)
    assert not [x for x in e.st.outputs if x[0]=='error']


def test_teacher_form_save_and_mission_buttons(game_env):
    e=game_env;e.actor(e.t);q=bank.generate('poly.add',7)[0]
    e.st.events.add('submit:검토 문항 저장')
    with pytest.raises(Rerun):e.view._question_form(e.t,'poly.add',q)
    assert len(e.svc.teacher_questions(e.t,'poly.add'))==1
    e.st.session_state['gg_mission_classes']=['1-1'];e.st.events.add('submit:5문제 미션 배포')
    with pytest.raises(Rerun):e.view._mission_manager(e.t)
    assert len(e.svc.missions(e.t))==1


def test_resume_mission_after_teacher_closes_but_reassigned_class_blocked(game_env):
    e=game_env;e.actor(e.t);mid=e.svc.create_mission(e.t,'계속하기','move.reflection',['1-1'])
    sid=e.start(mission=mid);e.actor(e.t);e.svc.close_mission(e.t,mid)
    e.actor(e.ss[0]);e.action(sid,'hint')
    e.b.update('users',e.ss[0]['id'],{'class':'1-2'})
    with pytest.raises(PermissionError):e.action(sid,'hint')


def test_remote_queue_roundtrip_without_live_github(game_env):
    e=game_env;sid=e.start();e.complete(sid);rows=e.b.read('game_profiles')
    b=object.__new__(e.db.GitHubBackend);b.lock=threading.RLock();b.flush_lock=threading.Lock();b.rows={t:[] for t in e.db.SCHEMAS};b.dirty={};b.ver=0;b.pending_files=[];b.repo='test/private';b.branch='main';b.last_error='';b.last_saved=''
    b.append_many('game_profiles',rows)
    path=e.db.GitHubBackend._path('game_profiles',rows[0]);assert path in b.dirty
    written={};head=['h0']
    class Reply:
        def __init__(self,body,status=200):self.body=body;self.status_code=status
        def json(self):return self.body
        def raise_for_status(self):assert self.status_code<400
    b._head=lambda:head[0]
    def req(method,endpoint,**kw):
        if method=='GET' and '/git/commits/' in endpoint:return Reply({'tree':{'sha':'tree0'}})
        if method=='POST' and endpoint.endswith('/trees'):
            written.update({r['path']:r['content'] for r in kw['json']['tree']});return Reply({'sha':'tree1'})
        if method=='POST' and endpoint.endswith('/commits'):return Reply({'sha':'h1'})
        if method=='PATCH':head[0]='h1';return Reply({})
        raise AssertionError(endpoint)
    b._req=req;b.flush();assert not b.dirty and path in written
    c=object.__new__(e.db.GitHubBackend);c.rows={};c.lock=threading.RLock();c.repo=b.repo;c._head=lambda:'h1'
    c._req=lambda *args,**kw:Reply({'tree':[{'type':'blob','path':path,'sha':'blob1'}]})
    c._blob=lambda sha:written[path].encode('utf-8')
    c._load_all();decoded=json.loads(c.rows['game_profiles'][0]['state_json'])
    assert decoded['earned']==12 and decoded['sessions'][0]['status']=='done'


def test_remote_failure_does_not_claim_saved(game_env):
    e=game_env;e.start();u=e.ss[0]
    def fail():raise RuntimeError('private credential must not display')
    e.monkeypatch.setattr(e.db,'flush_now',fail)
    with pytest.raises(engine.GameError) as err:e.svc.flush(u)
    assert 'private credential' not in str(err.value)
    assert len(e.profile()['sessions'])==1
