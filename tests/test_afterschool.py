"""Local persistence, authorization and UI-control doubles; no production accounts."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,date,time
from pathlib import Path
from types import ModuleType, SimpleNamespace
import importlib.util
import json
import sys
import threading

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from test_concept_quiz import FakeST,Session,load

class Rerun(BaseException):
    """Match Streamlit's ScriptControlException, not a normal Exception."""
    pass

class TestST(FakeST):
    __test__=False
    def __init__(self):
        super().__init__();self.current_form=''
    def rerun(self,**kw): raise Rerun()
    @contextmanager
    def form(self,key,**kw):
        old=self.current_form;self.current_form=key
        yield
        self.current_form=old
    def form_submit_button(self,label,**kw):return self.button(label,key=self.current_form+':'+label,**kw)
    def tabs(self,labels):
        from contextlib import nullcontext
        self._out('tabs',labels);return [nullcontext() for _ in labels]
    def text(self,body,**kw): self._out('text',body,**kw)
    def number_input(self,label,value=0,key=None,**kw):return self.session_state.setdefault(key,value)
    def date_input(self,label,value=None,key=None,**kw):return self.session_state.setdefault(key,value)
    time_input=date_input
    def file_uploader(self,label,key=None,accept_multiple_files=False,**kw):return self.session_state.setdefault(key,[] if accept_multiple_files else None)
    def text_input(self,label,value='',key=None,**kw):
        self._out('text_input',label,key=key)
        return super().text_input(label,value,key,**kw)
    text_area=text_input
    def checkbox(self,label,value=False,key=None,**kw):
        self._out('checkbox',label,key=key)
        return super().checkbox(label,value,key,**kw)

class Upload:
    def __init__(self,name='학습지.txt',data='가상 수업자료'.encode(),mime='text/plain'):
        self.name=name; self.data=data;self.type=mime
    def getvalue(self):return self.data

@pytest.fixture
def env(monkeypatch,tmp_path):
    st=TestST();monkeypatch.setitem(sys.modules,'streamlit',st)
    db=load('storage',ROOT/'storage.py',monkeypatch)
    backend=db.LocalBackend(str(tmp_path/'data'))
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    clock={'now':'2026-10-22 09:00:00'};monkeypatch.setattr(db,'now_str',lambda:clock['now'])
    svc=load('afterschool_core.service',ROOT/'afterschool_core/service.py',monkeypatch)
    import afterschool_core
    monkeypatch.setattr(afterschool_core,'service',svc,raising=False)
    view=load('views.afterschool',ROOT/'views/afterschool.py',monkeypatch)
    teacher={'id':'test-teacher','role':'teacher','name':'시험교사','class':'','must_change':'0'}
    other=dict(teacher,id='other-teacher',name='다른교사')
    students=[{'id':f'10{i:03}','role':'student','name':f'가상학생{i}','class':f'1-{(i-1)%7+1}','must_change':'0'} for i in range(1,26)]
    for u in [teacher,other]+students:backend.append('users',u)
    def actor(u):st.session_state['user']=deepcopy(u);return u
    actor(teacher)
    def cohort(name='1기',members=None,state='active',year='2026',request=None):
        actor(teacher)
        cid=svc.create_cohort(teacher,dict(name=name,year=year,state=state),request or 'create-'+name+'-code') if request else svc.create_cohort(teacher,dict(name=name,year=year,state=state),'create-'+str(len(backend.read('as_cohorts'))).zfill(8))
        if members is not None:svc.set_members(teacher,cid,[u['id'] for u in members],svc.get_cohort(teacher,cid)['revision'])
        return cid
    def post(cid,kind='material',who=None,files=None,request='post-request-01',**changes):
        who=who or teacher;actor(who)
        p={'kind':kind,'title':'시험 제목','body':'수업 원문','published':True}
        p.update(changes)
        return svc.create_post(who,cid,p,files or [],request)
    def state(cid,value):
        actor(teacher);c=svc.get_cohort(teacher,cid)
        svc.update_cohort(teacher,cid,dict(c,state=value),c['revision'])
    return SimpleNamespace(st=st,db=db,svc=svc,b=backend,t=teacher,other=other,s=students,actor=actor,
                           cohort=cohort,post=post,state=state,clock=clock,view=view,mp=monkeypatch,tmp=tmp_path)


def test_cohorts_created_on_demand_multiple_memberships_and_natural_sort(env):
    assert env.svc.list_cohorts(env.t)==[]
    c1=env.cohort('1기',[env.s[0]])
    env.cohort('10기',[env.s[1]])
    c2=env.cohort('2기',[env.s[0]])
    assert [c['name'] for c in env.svc.list_cohorts(env.t)]==['1기','2기','10기']
    env.actor(env.s[0]); visible=env.svc.list_cohorts(env.s[0])
    assert {c['id'] for c in visible}=={c1,c2}
    assert all('members_json' not in c and 'owner_id' not in c and 'member_count' not in c for c in visible)
    assert env.svc.has_access(env.s[0])
    env.actor(env.s[2]);assert env.svc.list_cohorts(env.s[2])==[] and not env.svc.has_access(env.s[2])


def test_years_and_duplicate_names(env):
    env.cohort('1기');env.cohort('1기',year='2027')
    with pytest.raises(ValueError):env.cohort('1기')
    cid=env.cohort('2기');c=env.svc.get_cohort(env.t,cid)
    with pytest.raises(ValueError):env.svc.update_cohort(env.t,cid,dict(c,name='1기'),c['revision'])


@pytest.mark.parametrize('state,visible,writable',[('draft',False,False),('active',True,True),('archived',True,False),('closed',False,False)])
def test_cohort_state_permissions(env,state,visible,writable):
    cid=env.cohort(members=[env.s[0]]);pid=env.post(cid,files=[Upload()]);aid=env.post(cid,'assignment',request='assignment-request')
    env.state(cid,state);env.actor(env.s[0])
    assert bool(env.svc.list_cohorts(env.s[0]))==visible
    for action in [lambda:env.svc.add_comment(env.s[0],pid,'댓글','comment-0001'),
                   lambda:env.svc.submit(env.s[0],aid,'답',[],'submit-0001'),
                   lambda:env.svc.create_post(env.s[0],cid,{'kind':'question','title':'질문','body':'질문 내용'},[],'question-0001')]:
        if writable:action()
        else:
            with pytest.raises(PermissionError):action()
    if visible:
        assert env.svc.download_attachment(env.s[0],'post',pid,0)[0]==Upload().getvalue()
    else:
        with pytest.raises(PermissionError):env.svc.get_post(env.s[0],pid)
        with pytest.raises(PermissionError):env.svc.download_attachment(env.s[0],'post',pid,0)


def test_revocation_readd_and_retained_attempts(env):
    cid=env.cohort(members=[env.s[0],env.s[1]])
    p=env.post(cid,'assignment',files=[Upload()]);env.actor(env.s[0])
    rid=env.svc.submit(env.s[0],p,'답안',[Upload('답안.txt')],'submit-original')
    env.actor(env.t);c=env.svc.get_cohort(env.t,cid);env.svc.set_members(env.t,cid,[env.s[1]['id']],c['revision'])
    env.actor(env.s[0]);assert not env.svc.has_access(env.s[0])
    with pytest.raises(PermissionError):env.svc.submissions(env.s[0],p)
    with pytest.raises(PermissionError):env.svc.download_attachment(env.s[0],'submission',rid,0)
    env.actor(env.t);assert env.svc.submissions(env.t,p)[0]['id']==rid
    c=env.svc.get_cohort(env.t,cid);env.svc.set_members(env.t,cid,[env.s[0]['id']],c['revision'])
    env.actor(env.s[0]);assert len(env.svc.submissions(env.s[0],p))==1


@pytest.mark.parametrize('action',['read','download','comment','submit','roster','update','members'])
def test_other_cohort_cannot_be_accessed_by_id(env,action):
    cid=env.cohort(members=[env.s[1]])
    p=env.post(cid,'assignment',files=[Upload()]);env.actor(env.s[0])
    ops={
      'read':lambda:env.svc.get_post(env.s[0],p),
      'download':lambda:env.svc.download_attachment(env.s[0],'post',p,0),
      'comment':lambda:env.svc.add_comment(env.s[0],p,'읽기','request-12345'),
      'submit':lambda:env.svc.submit(env.s[0],p,'답',[],'request-12345'),
      'roster':lambda:env.svc.roster(env.s[0],cid),
      'update':lambda:env.svc.update_cohort(env.s[0],cid,{'year':'2026','name':'fake'},'2'),
      'members':lambda:env.svc.set_members(env.s[0],cid,[env.s[0]['id']],'2'),
    }
    with pytest.raises(PermissionError):ops[action]()


@pytest.mark.parametrize('actor',['student','other','forged','revoked','missing','must_change'])
def test_current_identity_checked_on_management(env,actor):
    cid=env.cohort(members=[env.s[0]])
    user=env.t
    if actor=='student':user=env.s[0]
    if actor=='other':user=env.other
    if actor=='forged':user=dict(env.s[0],role='teacher')
    env.actor(user)
    if actor=='revoked':env.b.update('users',user['id'],{'role':'student'})
    if actor=='missing':env.st.session_state.pop('user')
    if actor=='must_change':env.b.update('users',user['id'],{'must_change':'1'})
    with pytest.raises(PermissionError):env.svc.roster(user,cid)
    with pytest.raises(PermissionError):env.svc.set_members(user,cid,[], '2')
    if actor!='other':
        with pytest.raises(PermissionError):env.svc.create_cohort(user,{'name':'2기','year':'2026'},'new-cohort-01')
    else: assert env.svc.list_cohorts(user)==[]


def test_private_questions_comments_inherit_visibility(env):
    cid=env.cohort(members=env.s[:2]);p=env.post(cid,'question',env.s[0])
    env.actor(env.s[0]);env.svc.add_comment(env.s[0],p,'내 질문 댓글','question-comment')
    env.actor(env.s[1]);assert env.svc.list_posts(env.s[1],cid)==[]
    with pytest.raises(PermissionError):env.svc.comments(env.s[1],p)
    env.actor(env.t);env.svc.add_comment(env.t,p,'교사 답변','teacher-answer');assert len(env.svc.comments(env.t,p))==2
    row=env.svc.get_post(env.t,p);env.svc.resolve_question(env.t,p,True,row['revision'])
    env.actor(env.s[0]);assert env.svc.get_post(env.s[0],p)['resolved']=='1'


def test_public_questions_draft_visibility_and_closed_comments(env):
    cid=env.cohort(members=env.s[:2]);p=env.post(cid,'question',env.s[0],visibility='cohort')
    env.actor(env.s[1]);env.svc.add_comment(env.s[1],p,'나도 궁금해요','public-comment')
    assert len(env.svc.list_posts(env.s[1],cid))==1
    draft=env.post(cid,published=False,request='draft-post-001')
    env.actor(env.s[0])
    assert draft not in [p['id'] for p in env.svc.list_posts(env.s[0],cid)]
    with pytest.raises(PermissionError):env.svc.get_post(env.s[0],draft)
    no=env.post(cid,comments_enabled=False,request='no-comments-01');env.actor(env.s[0])
    with pytest.raises(PermissionError):env.svc.add_comment(env.s[0],no,'no','attempt-comment')


def test_submission_private_versioned_feedback_and_archive(env):
    cid=env.cohort(members=env.s[:2]);p=env.post(cid,'assignment')
    env.actor(env.s[0]);r1=env.svc.submit(env.s[0],p,'첫 답안',[Upload()],'submit-first-01')
    r2=env.svc.submit(env.s[0],p,'수정 답안',[],'submit-second-01')
    assert [r['attempt'] for r in env.svc.submissions(env.s[0],p)]==['2','1']
    env.actor(env.s[1]);assert env.svc.submissions(env.s[1],p)==[]
    with pytest.raises(PermissionError):env.svc.download_attachment(env.s[1],'submission',r1,0)
    env.actor(env.t);env.svc.feedback(env.t,r2,'이제 이해했군요','1')
    with pytest.raises(env.svc.ConflictError):env.svc.feedback(env.t,r2,'stale','1')
    env.state(cid,'archived');env.actor(env.s[0]);rows=env.svc.submissions(env.s[0],p)
    assert rows[0]['feedback']=='이제 이해했군요' and rows[1]['body']=='첫 답안'
    with pytest.raises(PermissionError):env.svc.submit(env.s[0],p,'cannot',[],'submit-archived')


@pytest.mark.parametrize('due,late,allowed',[('2026-10-22 09:00:00',False,True),('2026-10-22 08:59:59',False,False),('2026-10-22 08:00:00',True,True),('',False,True)])
def test_deadline(env,due,late,allowed):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,'assignment',due_at=due,allow_late=late);env.actor(env.s[0])
    if allowed:
        env.svc.submit(env.s[0],p,'답',[],'due-submit-01')
        r=env.svc.submissions(env.s[0],p)[0];assert (r['late']=='1')==bool(due and due<env.clock['now'])
    else:
        with pytest.raises(PermissionError):env.svc.submit(env.s[0],p,'답',[],'due-submit-01')


def test_idempotency_flush_failure_retry(env):
    cid=env.cohort(members=[env.s[0]])
    fail=lambda:(_ for _ in ()).throw(IOError('offline'))
    env.mp.setattr(env.db,'flush_now',fail)
    with pytest.raises(env.svc.SavePendingError):env.post(cid,files=[Upload()])
    assert len(env.b.read('as_posts'))==1
    assert len(list(Path(env.b.files_dir).iterdir()))==1
    env.mp.setattr(env.db,'flush_now',lambda:None)
    pid=env.post(cid,files=[Upload()]);assert len(env.b.read('as_posts'))==1
    assert len(list(Path(env.b.files_dir).iterdir()))==1
    with pytest.raises(env.svc.ConflictError):env.post(cid,body='different')
    env.actor(env.s[0]);one=env.svc.add_comment(env.s[0],pid,'반가워요','same-comment-01')
    assert one==env.svc.add_comment(env.s[0],pid,'반가워요','same-comment-01')
    assert len(env.svc.comments(env.s[0],pid))==1


def test_persistence_partitioned_and_restart(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,'assignment',files=[Upload()]);env.actor(env.s[0])
    r=env.svc.submit(env.s[0],p,'답',[Upload('답안.txt')],'persist-submit');env.svc.add_comment(env.s[0],p,'댓글','persist-comment')
    fresh=env.db.LocalBackend(env.b.root)
    for table in ('as_cohorts','as_posts','as_comments','as_submissions'):assert len(fresh.read(table))==1
    env.mp.setattr(env.db,'get_backend',lambda:fresh)
    assert env.svc.download_attachment(env.s[0],'post',p,0)[0]==Upload().getvalue()
    assert env.svc.download_attachment(env.s[0],'submission',r,0)[1]=='답안.txt'
    assert len(list(Path(env.b.root,'as_submissions').glob('*.csv')))==1
    for name in Path(env.b.files_dir).iterdir():assert '학습지' not in name.name and '답안' not in name.name


@pytest.mark.parametrize('table',['as_cohorts','as_posts','as_comments','as_submissions'])
def test_generic_store_cannot_bypass_service(env,table):
    env.cohort(members=[env.s[0]])
    for who in (env.t,env.s[0],env.other):
        env.actor(who)
        for op in (lambda:env.db.append(table,{}),lambda:env.db.append_many(table,[{}]),
                   lambda:env.db.update(table,'fake',{}),lambda:env.db.delete(table,'fake')):
            with pytest.raises(PermissionError):op()
        if who!=env.t:assert env.db.read(table)==[]


@pytest.mark.parametrize('name,data',[('a.html',b'<html>'),('x.svg',b'<svg>'),('../data.txt',b'x'),('C:\\x.txt',b'x'),
                                     ('x.exe',b'MZ'),('x.pdf',b'not pdf'),('x.docx',b'bad'),('x.txt',b''),('x.txt',b'a'*(10*1024*1024+1))])
def test_bad_upload_no_post(env,name,data):
    cid=env.cohort()
    with pytest.raises(ValueError):env.post(cid,files=[Upload(name,data)])
    assert not env.b.read('as_posts')


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/plain,abc','file:///etc/passwd','https://user:pw@host/path','https://exa mple.com','ftp://example.com'])
def test_unsafe_links(env,url):
    cid=env.cohort()
    with pytest.raises(ValueError):env.post(cid,links=url)


def test_file_request_index_and_corruption(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,files=[Upload()]);env.actor(env.s[0])
    for index in (-1,True,'0',50):
        with pytest.raises(PermissionError):env.svc.download_attachment(env.s[0],'post',p,index)
    env.mp.setattr(env.b,'load_file',lambda _:b'changed')
    with pytest.raises(ValueError):env.svc.download_attachment(env.s[0],'post',p,0)


def test_teacher_attachments_edit_delete_and_concurrency(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,files=[Upload()]);old=env.svc.get_post(env.t,p)
    payload=dict(old,body='수정',published=True,pinned=False,comments_enabled=True,links='')
    env.svc.update_post(env.t,p,payload,old['revision'])
    assert env.svc.download_attachment(env.t,'post',p,0)[0]==Upload().getvalue()
    with pytest.raises(env.svc.ConflictError):env.svc.update_post(env.t,p,payload,old['revision'])
    new=env.svc.get_post(env.t,p);env.svc.delete_post(env.t,p,new['revision'])
    with pytest.raises(PermissionError):env.svc.get_post(env.t,p)


def test_cannot_delete_assignment_with_work(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,'assignment');env.actor(env.s[0]);env.svc.submit(env.s[0],p,'답',[],'answer-00001')
    env.actor(env.t)
    with pytest.raises(ValueError):env.svc.delete_post(env.t,p,env.svc.get_post(env.t,p)['revision'])


def test_student_cannot_publish_material_or_assignment(env):
    cid=env.cohort(members=[env.s[0]]);env.actor(env.s[0])
    for kind in ('material','assignment'):
        with pytest.raises(PermissionError):env.svc.create_post(env.s[0],cid,{'kind':kind,'title':'hack','body':'hack'},[],'student-create')


def test_twentyfive_concurrent_submissions_no_loss(env):
    cid=env.cohort(members=env.s);p=env.post(cid,'assignment')
    def work(i):
        u=env.s[i];env.actor(u)
        return env.svc.submit(u,p,'답안 '+str(i),[],'concurrent-submit')
    with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(work,range(25)))
    assert len(set(ids))==25 and len(env.b.read('as_submissions'))==25
    with ThreadPoolExecutor(max_workers=8) as pool:again=list(pool.map(work,range(25)))
    assert ids==again and len(env.b.read('as_submissions'))==25
    env.actor(env.t);assert len(env.svc.submissions(env.t,p))==25


def test_hidden_tab_integration_source_and_runtime_double(env):
    fakeui=ModuleType('ui');fakeui.page_title=lambda *a:None
    env.mp.setitem(sys.modules,'ui',fakeui)
    fakeauth=ModuleType('auth');env.mp.setitem(sys.modules,'auth',fakeauth)
    math=load('views.math_class',ROOT/'views/math_class.py',env.mp)
    for fn in ('tab_plan','tab_sheets','tab_board','tab_questions'):env.mp.setattr(math,fn,lambda *a:None)
    cid=env.cohort(members=[env.s[0]])
    board=ModuleType('views.afterschool');board.student_board=lambda user,subject='공통수학2':env.st._out('as_called',user['id'])
    env.mp.setitem(sys.modules,'views.afterschool',board)
    for user,subject,expected in [(env.s[0],'공통수학2',True),(env.s[1],'공통수학2',False),(env.s[0],'공통수학1',False),(env.t,'공통수학2',True)]:
        env.actor(user);env.st.outputs=[];math.page(user,subject)
        tabs=[v for k,v,*_ in env.st.outputs if k=='tabs'][0]
        assert ('🌙 방과후 게시판' in tabs)==expected
        assert any(k=='as_called' for k,*_ in env.st.outputs)==expected
    source=(ROOT/'views/teacher.py').read_text();assert '🌙 방과후 관리' in source and 'tab_afterschool(user)' in source


def test_teacher_ui_menu_views_and_student_board_no_admin_controls(env):
    cid=env.cohort(members=[env.s[0]])
    env.post(cid);env.post(cid,'assignment',request='ui-assignment')
    env.post(cid,'question',env.s[0],request='ui-question')
    env.actor(env.s[0]);env.svc.submit(env.s[0],next(r['id'] for r in env.b.read('as_posts') if r['kind']=='assignment'),'답',[],'ui-submit-01')
    env.actor(env.t)
    for menu in ('기수 설정','참여 학생','자료·과제','질문·댓글','제출 확인'):
        env.st.outputs=[];env.st.session_state['as_manage_menu']=menu
        env.view.teacher_page(env.t)
        assert not [x for x in env.st.outputs if x[0]=='error'],env.st.outputs
    env.actor(env.s[0])
    for menu in ('자료·과제','질문·댓글','내 제출 확인'):
        env.st.outputs=[];env.st.session_state['as_board_section_math2_'+cid]=menu;env.view.student_board(env.s[0])
        assert not [x for x in env.st.outputs if x[0]=='error'],env.st.outputs
        buttons=[x[1] for x in env.st.outputs if x[0]=='button']
        assert '학생 배정 저장' not in buttons and '기수 추가' not in buttons and '피드백 저장 · 학생에게 공개' not in buttons


def test_archived_ui_read_only(env):
    cid=env.cohort(members=[env.s[0]]);env.post(cid,'assignment');env.state(cid,'archived');env.actor(env.s[0])
    env.st.session_state['as_board_section_math2_'+cid]='자료·과제';env.view.student_board(env.s[0])
    buttons=[x[1] for x in env.st.outputs if x[0]=='button']
    assert '과제 제출' not in buttons and '댓글 등록' not in buttons
    assert any('읽고' in x[1] for x in env.st.outputs if x[0]=='info')


def test_teacher_can_create_cohort_through_form(env):
    env.view.teacher_page(env.t)
    op=env.st.session_state['_as_op_create_cohort']
    env.st.session_state['as_new_'+op+'name']='방학 1기'
    env.st.session_state['as_new_'+op+'state']='active'
    env.st.events.add('as_new_'+op+':기수 추가')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert env.svc.list_cohorts(env.t)[0]['name']=='방학 1기'


def test_roster_filter_addition_preserves_students_in_other_classes(env):
    cid=env.cohort(members=env.s[:2]);c=env.svc.get_cohort(env.t,cid)
    env.st.session_state['as_manage_menu']='참여 학생'
    env.st.session_state['as_bulk_class_'+cid]='1-1'
    key=f'as_bulk_ids_{cid}_{c["revision"]}_1-1'
    env.st.session_state[key]=[env.s[7]['id']]
    env.st.events.add('as_bulk_add_'+cid)
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    selected={r['id'] for r in env.svc.roster(env.t,cid) if r['selected']}
    assert selected=={env.s[0]['id'],env.s[1]['id'],env.s[7]['id']}


def test_student_question_submit_form_then_home_has_no_settings(env):
    cid=env.cohort(members=[env.s[0]]);env.actor(env.s[0]);env.st.session_state['as_board_section_math2_'+cid]='질문·댓글'
    env.view.student_board(env.s[0]);op=env.st.session_state['_as_op_question_'+cid]
    env.st.session_state['as_q_title_'+op]='역함수 질문'
    env.st.session_state['as_q_body_'+op]='x와 y를 바꾸는 이유가 궁금해요.'
    env.st.events.add('as_q_'+op+':질문 올리기')
    with pytest.raises(Rerun):env.view.student_board(env.s[0])
    p=env.svc.list_posts(env.s[0],cid)[0]
    assert p['visibility']=='private' and p['kind']=='question'


def test_student_submission_ui_produces_receipt(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,'assignment');env.actor(env.s[0])
    env.st.session_state['as_board_section_math2_'+cid]='자료·과제';env.view.student_board(env.s[0])
    op=env.st.session_state['_as_op_submit_'+p];env.st.session_state['as_answer_'+op]='내 풀이'
    env.st.events.add('as_submit_'+op+':과제 제출')
    with pytest.raises(Rerun):env.view.student_board(env.s[0])
    env.st.outputs=[];env.view.student_board(env.s[0])
    assert any(x[0]=='success' and '저장' in x[1] for x in env.st.outputs)
    assert len(env.svc.submissions(env.s[0],p))==1


def test_save_failure_ui_keeps_pending_and_no_success(env):
    cid=env.cohort(members=[env.s[0]])
    env.mp.setattr(env.db,'flush_now',lambda:(_ for _ in ()).throw(IOError()))
    with pytest.raises(Rerun):env.view._action(lambda:env.post(cid),'저장 완료','newpost')
    assert env.st.session_state.get('_as_pending')
    env.st.outputs=[];env.view.teacher_page(env.t)
    assert any(x[0]=='warning' and '영구 저장' in x[1] for x in env.st.outputs)
    assert not any(x[0]=='success' for x in env.st.outputs)
    env.mp.setattr(env.db,'flush_now',lambda:None);env.st.events.add('as_retry')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert not env.st.session_state.get('_as_pending')


def test_teacher_public_board_read_only_configuration_ui(env):
    cid=env.cohort(members=[env.s[0]]);env.post(cid,'assignment')
    env.st.session_state['as_board_section_math2_'+cid]='자료·과제';env.view.student_board(env.t)
    buttons=[x[1] for x in env.st.outputs if x[0]=='button']
    assert not any(x in buttons for x in ['기수 추가','기수 설정 저장','자료·과제 저장','댓글 등록','과제 제출'])


def test_current_student_role_or_deleted_identity_denied(env):
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid);env.actor(env.s[0])
    env.b.delete('users',env.s[0]['id'])
    assert not env.svc.has_access(env.s[0])
    with pytest.raises(PermissionError):env.svc.get_post(env.s[0],p)


def test_member_revision_conflict_and_student_id_validation(env):
    cid=env.cohort(members=[env.s[0]]);c=env.svc.get_cohort(env.t,cid)
    with pytest.raises(ValueError):env.svc.set_members(env.t,cid,['unknown'],c['revision'])
    with pytest.raises(ValueError):env.svc.set_members(env.t,cid,[env.t['id']],c['revision'])
    env.svc.set_members(env.t,cid,[env.s[1]['id']],c['revision'])
    with pytest.raises(env.svc.ConflictError):env.svc.set_members(env.t,cid,[],c['revision'])
    assert sum(r['selected'] for r in env.svc.roster(env.t,cid))==1


def test_other_students_comments_cannot_be_deleted(env):
    cid=env.cohort(members=env.s[:2]);p=env.post(cid)
    env.actor(env.s[0]);r=env.svc.add_comment(env.s[0],p,'댓글','unique-comment-1')
    env.actor(env.s[1])
    with pytest.raises(PermissionError):env.svc.delete_comment(env.s[1],r,'1')
    env.actor(env.t);env.svc.delete_comment(env.t,r,'1');assert env.svc.comments(env.t,p)==[]


def test_all_ten_supported_upload_extensions(env):
    cid=env.cohort(members=[env.s[0]])
    samples={'pdf':b'%PDF-1.4\n','png':b'\x89PNG\r\n\x1a\n','jpg':b'\xff\xd8','jpeg':b'\xff\xd8',
             'txt':b'text','docx':b'PK','hwpx':b'PK','xlsx':b'PK','pptx':b'PK','hwp':b'\xd0\xcf\x11\xe0'}
    # Minimal signature fixtures test only the basic checks, not full document validity.
    for ext,data in samples.items():
        pid=env.post(cid,files=[Upload('자료.'+ext,data)],request='upload-test-'+ext)
        env.actor(env.s[0]);assert env.svc.download_attachment(env.s[0],'post',pid,0)[0]==data


def test_download_component_checks_permission_before_file_data(env):
    # Isolate the Streamlit component bridge, NOT the authorization service.
    events={};rendered=[]
    component=ModuleType('streamlit.components.v1')
    def declare(name,path):
        def call(**kwargs):rendered.append(kwargs);return events.get('value')
        return call
    component.declare_component=declare
    parent=ModuleType('streamlit.components');parent.v1=component
    env.mp.setitem(sys.modules,'streamlit.components',parent);env.mp.setitem(sys.modules,'streamlit.components.v1',component)
    downloads=load('afterschool_core.downloads',ROOT/'afterschool_core/downloads.py',env.mp)
    cid=env.cohort(members=[env.s[0]]);p=env.post(cid,files=[Upload()]);env.actor(env.s[0])
    events['value']={'action':'prepare','request_id':'request-file-01'}
    with pytest.raises(Rerun):downloads.render(env.s[0],'post',p,0,'학습지.txt')
    value=next(v for k,v in env.st.session_state.data.items() if k.startswith('_as_download_'))
    assert value['result']['data']
    env.actor(env.t);c=env.svc.get_cohort(env.t,cid);env.svc.set_members(env.t,cid,[],c['revision'])
    env.actor(env.s[0]);events['value']={'action':'prepare','request_id':'request-file-02'}
    with pytest.raises(Rerun):downloads.render(env.s[0],'post',p,0,'학습지.txt')
    value=next(v for k,v in env.st.session_state.data.items() if k.startswith('_as_download_'))
    assert 'error' in value['result'] and 'data' not in value['result']
