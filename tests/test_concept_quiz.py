"""Local/file and queued-backend tests. No real GitHub, student accounts or AI.
Streamlit is substituted only inside these tests, never in production files.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy
import base64
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import types

import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from quiz_core import bank
from config import SUBJECTS


class Session:
    def __init__(self): self.local=threading.local()
    @property
    def data(self):
        if not hasattr(self.local,'data'): self.local.data={}
        return self.local.data
    def get(self,k,d=None): return self.data.get(k,d)
    def __getitem__(self,k): return self.data[k]
    def __setitem__(self,k,v): self.data[k]=v
    def __contains__(self,k): return k in self.data
    def pop(self,k,d=None): return self.data.pop(k,d)
    def setdefault(self,k,d=None): return self.data.setdefault(k,d)
    def clear(self): self.data.clear()
    def __iter__(self): return iter(self.data)


class FakeST(types.ModuleType):
    def __init__(self):
        super().__init__('streamlit'); self.session_state=Session(); self.query_params={}; self.outputs=[]; self.events=set(); self.callbacks={}
    def cache_resource(self,*a,**kw): return lambda f:f
    cache_data=cache_resource
    def fragment(self,f=None,**kw): return f if f else lambda fn:fn
    def _out(self,kind,body='',**kw): self.outputs.append((kind,body,kw))
    def markdown(self,v,**kw): self._out('markdown',v,**kw)
    def caption(self,v,**kw): self._out('caption',v,**kw)
    def write(self,v,**kw): self._out('write',v,**kw)
    def subheader(self,v,**kw): self._out('subheader',v,**kw)
    def html(self,v,**kw): self._out('html',v,**kw)
    def error(self,v,**kw): self._out('error',v,**kw)
    def success(self,v,**kw): self._out('success',v,**kw)
    def warning(self,v,**kw): self._out('warning',v,**kw)
    def info(self,v,**kw): self._out('info',v,**kw)
    def dataframe(self,v,**kw): self._out('dataframe',v,**kw)
    def progress(self,v,**kw): self._out('progress',v,**kw)
    def download_button(self,label,data,**kw): self._out('download',data,**kw); return False
    def container(self,*a,**kw): return nullcontext()
    expander=container
    form=container
    def columns(self,widths,**kw): return [Column(self) for _ in range(widths if isinstance(widths,int) else len(widths))]
    def selectbox(self,label,options,index=0,key=None,**kw):
        values=list(options)
        if key not in self.session_state or self.session_state[key] not in values:
            self.session_state[key]=values[index] if values and index is not None else None
        self._out('selectbox',label,key=key,options=values)
        return self.session_state[key]
    def radio(self,label,options,index=0,key=None,on_change=None,args=(),**kw):
        v=self.selectbox(label,options,index=index,key=key,**kw)
        self._out('radio',label,key=key,options=list(options),disabled=kw.get('disabled',False))
        if on_change: self.callbacks[key]=(on_change,args)
        return v
    def checkbox(self,label,value=False,key=None,**kw): return self.session_state.setdefault(key,value)
    toggle=checkbox
    def multiselect(self,label,options,default=None,key=None,**kw): return self.session_state.setdefault(key,list(default or []))
    def slider(self,label,*a,key=None,**kw): return self.session_state.setdefault(key,a[2])
    def text_input(self,label,value='',key=None,**kw): return self.session_state.setdefault(key,value)
    text_area=text_input
    def button(self,label,key=None,on_click=None,args=(),disabled=False,**kw):
        self._out('button',label,key=key,disabled=disabled)
        if on_click:self.callbacks[key]=(on_click,args)
        if key in self.events and not disabled:
            self.events.remove(key)
            if on_click:on_click(*args)
            return True
        return False
    form_submit_button=button
    def rerun(self,**kw): raise Rerun()


class Rerun(Exception): pass
class Column:
    def __init__(self,st): self.st=st
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def __getattr__(self,k): return getattr(self.st,k)


def load(name,path,monkeypatch):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,mod); spec.loader.exec_module(mod); return mod


@pytest.fixture
def env(monkeypatch,tmp_path):
    st=FakeST(); monkeypatch.setitem(sys.modules,'streamlit',st)
    db=load('storage',ROOT/'storage.py',monkeypatch)
    backend=db.LocalBackend(str(tmp_path/'data'))
    monkeypatch.setattr(db,'get_backend',lambda:backend)
    cache={'data':{},'lock':threading.Lock()};monkeypatch.setattr(db,'_cache',lambda:cache)
    rt=types.ModuleType('realtime'); rt.locked=False; rt.is_locked=lambda _:rt.locked
    monkeypatch.setitem(sys.modules,'realtime',rt)
    svc=load('quiz_core.service',ROOT/'quiz_core/service.py',monkeypatch)
    import quiz_core
    monkeypatch.setattr(quiz_core,'service',svc,raising=False)
    view=load('views.quiz',ROOT/'views/quiz.py',monkeypatch)
    teacher={'id':'teacher-test','role':'teacher','name':'가상 교사','class':'','must_change':'0'}
    other=dict(teacher,id='other-teacher')
    students=[{'id':f'10{i:03}','role':'student','name':f'가상학생{i:02}','class':f'1-{(i-1)//5+1}','must_change':'0'} for i in range(1,36)]
    for u in [teacher,other]+students:backend.append('users',u)
    def actor(u): st.session_state['user']=deepcopy(u); return u
    actor(teacher)
    def paper(cls=('1-1',),subject='공통수학2',idx=2):
        actor(teacher);qid=svc.create_draft(teacher,subject,bank.units(subject)[idx]);svc.publish(teacher,qid,list(cls),reviewed=True);return qid
    def answer(qid,u,indices=None):
        actor(u); p=svc.student_paper(u,qid); rev=p['revision']
        raw=next(q for q in backend.read('quiz_sets') if q['id']==qid)
        keys=json.loads(raw['question_json'])
        for i,q in enumerate(keys):
            choice=q['answer'] if indices is None else indices[i]
            if choice is not None: rev=svc.save_answer(u,qid,q['id'],choice,rev)
        return keys
    return types.SimpleNamespace(st=st,db=db,backend=backend,rt=rt,svc=svc,view=view,t=teacher,other=other,students=students,
                                 actor=actor,paper=paper,answer=answer,monkeypatch=monkeypatch)


@pytest.mark.parametrize('subject',SUBJECTS)
@pytest.mark.parametrize('index',range(8))
def test_every_unit_generates_valid_varied_ten_question_papers(subject,index):
    unit=bank.units(subject)[index];seen=set()
    for seed in range(20):
        questions=bank.generate(subject,unit,seed,exclude=seen)
        assert len(questions)==10 and len({q['id'] for q in questions})==10
        assert len({q['fingerprint'] for q in questions})==10
        assert bank.validate_questions(questions)==questions
        assert len({q['concept'] for q in questions})>=3
        assert not seen.intersection(q['fingerprint'] for q in questions)
        seen.update(q['fingerprint'] for q in questions)


def test_focus_generation_is_new_and_still_ten_questions():
    unit=bank.units('공통수학2')[2]
    first=bank.generate('공통수학2',unit,17)
    second=bank.generate('공통수학2',unit,18,exclude=[q['fingerprint'] for q in first],focus=['반지름'])
    assert len(second)==10 and sum(q['concept']=='반지름' for q in second)>=6


@pytest.mark.parametrize('bad',[True,False,-1,4,None,'1',1.0])
def test_invalid_answer_keys_rejected(bad):
    qs=bank.generate('공통수학1',bank.units('공통수학1')[0],100)
    qs[0]['answer']=bad
    with pytest.raises(ValueError): bank.validate_questions(qs)


def test_duplicate_options_or_prompts_rejected():
    qs=bank.generate('공통수학1',bank.units('공통수학1')[0],11)
    qs[0]['options'][1]=qs[0]['options'][0]
    with pytest.raises(ValueError):bank.validate_questions(qs)
    qs=bank.generate('공통수학1',bank.units('공통수학1')[0],11)
    qs[1]['prompt']=qs[0]['prompt']
    with pytest.raises(ValueError):bank.validate_questions(qs)


def test_default_curriculum_and_custom_unit_mapping(env):
    assert env.svc.units('공통수학2')==bank.units('공통수학2')
    env.db.set_setting('units_공통수학2','수학 탐구\n원의 기초')
    assert env.svc.units('공통수학2')==['수학 탐구','원의 기초']
    with pytest.raises(ValueError):env.svc.create_draft(env.t,'공통수학2','원의 기초')
    qid=env.svc.create_draft(env.t,'공통수학2','원의 기초',bank_unit=bank.units('공통수학2')[2])
    assert env.svc.teacher_paper(env.t,qid)['unit']=='원의 기초'


def test_teacher_preview_edit_publish_freezes_questions(env):
    qid=env.svc.create_draft(env.t,'공통수학2',bank.units('공통수학2')[0])
    old=env.svc.teacher_paper(env.t,qid)
    questions=deepcopy(old['questions']);questions[0]['prompt']='교사가 확인한 새 발문'
    env.svc.edit_draft(env.t,qid,'수정 제목',questions,old['revision'])
    with pytest.raises(env.svc.Conflict):env.svc.edit_draft(env.t,qid,'stale',questions,old['revision'])
    with pytest.raises(env.svc.QuizError):env.svc.publish(env.t,qid,['1-1'])
    env.svc.publish(env.t,qid,['1-1'],reviewed=True)
    newer=env.svc.teacher_paper(env.t,qid)
    with pytest.raises(env.svc.QuizError):env.svc.edit_draft(env.t,qid,'다시',questions,newer['revision'])
    assert newer['title']=='수정 제목'


@pytest.mark.parametrize('scenario',['student','forged_role','no_session','revoked','must_change','other_teacher'])
def test_authorization_on_teacher_actions(env,scenario):
    qid=env.paper()
    user=env.t
    if scenario in ('student','forged_role'):
        env.actor(env.students[0]); user=dict(env.students[0],role='teacher') if scenario=='forged_role' else env.students[0]
    elif scenario=='no_session':env.st.session_state.clear()
    elif scenario=='revoked':env.backend.update('users',env.t['id'],{'role':'student'})
    elif scenario=='must_change':env.backend.update('users',env.t['id'],{'must_change':'1'})
    elif scenario=='other_teacher':user=env.actor(env.other)
    for fn in [lambda:env.svc.teacher_paper(user,qid),lambda:env.svc.grade(user,qid),lambda:env.svc.release(user,qid),lambda:env.svc.dashboard(user,qid)]:
        with pytest.raises(PermissionError): fn()


def test_targeted_distribution_and_seven_classes(env):
    qid=env.svc.create_draft(env.t,'공통수학2',bank.units('공통수학2')[2])
    targets=[env.students[0]['id'],env.students[-1]['id']]
    env.svc.publish(env.t,qid,['1-1','1-7'],targets,reviewed=True)
    for s in [env.students[0],env.students[-1]]:
        env.actor(s);assert len(env.svc.list_quizzes(s))==1
    outsider=env.actor(env.students[1]);assert not env.svc.list_quizzes(outsider)
    with pytest.raises(PermissionError):env.svc.student_paper(outsider,qid)
    env.actor(env.students[0]);env.backend.update('users',env.students[0]['id'],{'class':'1-2'})
    with pytest.raises(PermissionError):env.svc.student_paper(env.students[0],qid)


def test_marks_no_ox_until_teacher_grades_and_no_keys_until_release(env):
    qid=env.paper();u=env.students[0]
    keys=env.answer(qid,u)
    student=env.svc.student_paper(u,qid)
    assert 'score' not in student and 'marks' not in student and 'solutions' not in student
    assert all(set(q)=={'id','prompt','options'} for q in student['questions'])
    assert env.db.read('quiz_sets')==[] and env.db.read('quiz_attempts')==[]
    env.actor(env.t);board=env.svc.dashboard(env.t,qid)
    assert board['students'][0]['count']==10 and not board['students'][0]['marks']
    assert all(x['graded']==0 and x['wrong']==0 for x in board['stats'])
    result=env.svc.grade(env.t,qid,[u['id']]);assert result['graded']==1
    board=env.svc.dashboard(env.t,qid);assert board['students'][0]['score']==100
    env.actor(u);out=env.svc.student_paper(u,qid);assert not out['released'] and 'score' not in out
    assert 'score' not in env.svc.history(u,u['id'])[0]
    with pytest.raises(env.svc.QuizError):env.svc.save_answer(u,qid,'q01',1,10)
    env.actor(env.t);env.svc.release(env.t,qid,[u['id']])
    env.actor(u);out=env.svc.student_paper(u,qid);assert out['score']==100 and out['released']
    assert [x['answer'] for x in out['solutions']]==[x['answer'] for x in keys]


def test_wrong_counts_only_graded_and_blanks_separated(env):
    qid=env.paper();u,v=env.students[:2]
    paper=env.svc.teacher_paper(env.t,qid)
    choices=[(q['answer']+1)%4 for q in paper['questions']]
    env.answer(qid,u,choices)
    env.actor(v);env.svc.save_answer(v,qid,'q01',paper['questions'][0]['answer'],0)
    env.actor(env.t)
    result=env.svc.grade(env.t,qid,[u['id'],v['id']]); assert result['graded']==1 and result['skipped']==1
    board=env.svc.dashboard(env.t,qid);assert all(x['wrong']==1 and x['graded']==1 for x in board['stats'])
    env.svc.grade(env.t,qid,[v['id']],include_incomplete=True)
    board=env.svc.dashboard(env.t,qid)
    assert board['stats'][0]['wrong']==1 and board['stats'][0]['blank']==0
    assert board['stats'][1]['wrong']==2 and board['stats'][1]['wrong_choice']==1 and board['stats'][1]['blank']==1
    again=env.svc.grade(env.t,qid,[v['id']]);assert again['already']==1


def test_submit_does_not_grade_and_locks_revisions(env):
    qid=env.paper();u=env.students[0];env.actor(u)
    with pytest.raises(env.svc.QuizError):env.svc.submit(u,qid)
    env.svc.save_answer(u,qid,'q01',0,0)
    env.svc.submit(u,qid,allow_blank=True)
    env.svc.submit(u,qid,allow_blank=True)
    p=env.svc.student_paper(u,qid);assert p['attempt_state']=='submitted' and 'marks' not in p
    assert len(env.backend.read('quiz_attempts'))==1
    with pytest.raises(env.svc.QuizError):env.svc.save_answer(u,qid,'q02',0,p['revision'])


def test_conflicting_tab_and_classroom_input_lock(env):
    qid=env.paper();u=env.students[0];env.actor(u)
    env.svc.save_answer(u,qid,'q01',1,0)
    with pytest.raises(env.svc.Conflict):env.svc.save_answer(u,qid,'q02',2,0)
    assert env.svc.student_paper(u,qid)['answers']=={'q01':1}
    env.rt.locked=True
    with pytest.raises(env.svc.QuizError):env.svc.save_answer(u,qid,'q02',2,1)
    with pytest.raises(env.svc.QuizError):env.svc.submit(u,qid,allow_blank=True)


@pytest.mark.parametrize('value',[-1,4,True,False,'1',1.0,{},[]])
def test_invalid_choices_never_persist(env,value):
    qid=env.paper();u=env.students[0];env.actor(u)
    with pytest.raises(ValueError):env.svc.save_answer(u,qid,'q01',value,0)
    assert not env.backend.read('quiz_attempts')


def test_individual_files_and_restart_preserve_all_rounds(env):
    qid=env.paper();u,v=env.students[:2];env.answer(qid,u);env.answer(qid,v)
    env.actor(env.t);env.svc.grade(env.t,qid,[u['id']])
    second=env.svc.create_draft(env.t,'공통수학2',bank.units('공통수학2')[2],parent_id=qid)
    env.svc.publish(env.t,second,['1-1'],[u['id']],reviewed=True);env.answer(second,u)
    files=list((Path(env.backend.root)/'quiz_attempts').glob('*.csv'));assert len(files)==2
    for f in files:
        rows=list(csv.DictReader(f.open())); assert len({r['student_id'] for r in rows})==1
        assert not any(s['id'] in f.name for s in (u,v))
    restored=env.db.LocalBackend(env.backend.root)
    assert sorted(restored.read('quiz_attempts'),key=lambda x:x['id'])==sorted(env.backend.read('quiz_attempts'),key=lambda x:x['id'])
    env.actor(env.t);assert len(env.svc.history(env.t,u['id']))==2
    assert env.svc.teacher_paper(env.t,second)['parent_id']==qid
    assert env.svc.teacher_paper(env.t,second)['round']=='2'
    q1=env.svc.teacher_paper(env.t,qid)['questions'];q2=env.svc.teacher_paper(env.t,second)['questions']
    assert not {q['fingerprint'] for q in q1}&{q['fingerprint'] for q in q2}


def test_low_score_recommendation_excludes_ungraded_students(env):
    qid=env.paper();u,v=env.students[:2]
    qs=env.svc.teacher_paper(env.t,qid)['questions']
    env.answer(qid,u,[(q['answer']+1)%4 for q in qs]);env.answer(qid,v)
    env.actor(env.t);env.svc.grade(env.t,qid,[u['id']])
    ids,tags=env.svc.recommend(env.t,qid,60)
    assert ids==[u['id']] and tags


def test_student_cannot_export_other_person_and_teacher_owner_history(env):
    qid=env.paper();u=env.students[0];env.answer(qid,u)
    with pytest.raises(PermissionError):env.svc.history(u,env.students[1]['id'])
    with pytest.raises(PermissionError):env.svc.export_dashboard(u,qid)
    env.actor(env.other);assert env.svc.history(env.other,u['id'])==[]


def test_close_preserves_answers_but_blocks_new_marks(env):
    qid=env.paper();u=env.students[0];env.answer(qid,u)
    env.actor(env.t);env.svc.close(env.t,qid)
    env.actor(u);p=env.svc.student_paper(u,qid);assert len(p['answers'])==10 and not p['editable']
    with pytest.raises(env.svc.QuizError):env.svc.save_answer(u,qid,'q01',0,p['revision'])
    env.actor(env.t);assert env.svc.grade(env.t,qid,[u['id']])['graded']==1


def test_25_students_concurrent_marks_and_grading(env):
    qid=env.paper(tuple(f'1-{n}' for n in range(1,6)))
    people=env.students[:25]
    def work(u):return env.answer(qid,u)
    with ThreadPoolExecutor(max_workers=25) as pool:list(pool.map(work,people))
    env.actor(env.t);board=env.svc.dashboard(env.t,qid)
    assert len(board['students'])==25 and all(s['count']==10 for s in board['students'])
    assert env.svc.grade(env.t,qid)['graded']==25
    assert all(s['score']==100 for s in env.svc.dashboard(env.t,qid)['students'])
    assert len(env.backend.read('quiz_attempts'))==25


def queued_backend(env):
    # Real GitHubBackend methods, with only HTTP/head and credentials replaced.
    b=object.__new__(env.db.GitHubBackend)
    b.repo='example/private-test';b.branch='main';b.lock=threading.RLock();b.flush_lock=threading.Lock()
    b.rows={t:deepcopy(env.backend.read(t)) for t in env.db.SCHEMAS}
    b.ver=0;b.dirty={};b.pending_files=[];b.last_error='';b.last_saved='';b.label='fake GitHub'
    b._head=lambda:'a'*40
    calls=[]
    class Response:
        def __init__(self,data,status=200):self.data=data;self.status_code=status
        def json(self):return self.data
        def raise_for_status(self):
            if self.status_code>=400:raise RuntimeError('mock failure')
    def req(method,path,**kw):
        calls.append((method,path,kw))
        if method=='GET':return Response({'tree':{'sha':'b'*40}})
        return Response({'sha':'c'*40})
    b._req=req
    env.monkeypatch.setattr(env.db,'get_backend',lambda:b)
    return b,calls,Response


def test_real_github_flush_batches_student_files_without_network(env):
    qid=env.paper();b,calls,_=queued_backend(env)
    for s in env.students[:5]:env.answer(qid,s)
    assert len(b.dirty)==5 and not calls
    for path in b.dirty:
        rows=list(csv.DictReader(io.StringIO(b._csv(path))))
        assert len({r['student_id'] for r in rows})==1
    env.actor(env.t);env.svc.flush(env.t,qid)
    posts=[c for c in calls if c[0]=='POST']
    assert len(posts)==2 and len(posts[0][2]['json']['tree'])==5
    assert not b.dirty
    assert env.svc.save_state(env.t,qid)['durable']


def test_failed_remote_save_not_reported_durable_and_release_not_leaked(env):
    qid=env.paper();b,_,_=queued_backend(env)
    s=env.students[0];env.actor(s)
    env.svc.save_answer(s,qid,'q01',0,0)
    b._req=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('upstream secret should not leak'))
    with pytest.raises(env.svc.PendingSave) as err:env.svc.submit(s,qid,allow_blank=True)
    assert 'secret' not in str(err.value)
    assert env.svc.save_state(s,qid)['durable'] is False
    assert not env.svc.student_paper(s,qid)['saved']
    env.actor(env.t)
    with pytest.raises(env.svc.PendingSave):env.svc.grade(env.t,qid,[s['id']])
    with pytest.raises(env.svc.PendingSave):env.svc.release(env.t,qid,[s['id']])
    env.actor(s);assert not env.svc.student_paper(s,qid)['released']
    assert 'score' not in env.svc.history(s,s['id'])[0]


def test_remote_rate_error_does_not_create_four_extra_commits(env):
    qid=env.paper();b,calls,Response=queued_backend(env)
    env.actor(env.students[0]);env.svc.save_answer(env.students[0],qid,'q01',0,0)
    original=b._req
    def rate(method,path,**kw):
        if method=='PATCH':calls.append((method,path,kw));return Response({},429)
        return original(method,path,**kw)
    b._req=rate
    with pytest.raises(RuntimeError):b.flush()
    assert len([x for x in calls if x[0]=='POST'])==2
    assert b.dirty


def test_pending_draft_and_new_publish_are_not_visible_to_students(env):
    b,_,_=queued_backend(env)
    qid=env.svc.create_draft(env.t,'공통수학1',bank.units('공통수학1')[0])
    u=env.actor(env.students[0]);assert env.svc.list_quizzes(u)==[]
    env.actor(env.t);b._req=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('offline'))
    with pytest.raises(env.svc.PendingSave):env.svc.publish(env.t,qid,['1-1'],reviewed=True)
    env.actor(u)
    with pytest.raises(env.svc.QuizError):env.svc.student_paper(u,qid)


def test_safe_html_and_csv_formula_escape(env):
    env.backend.update('users',env.students[0]['id'],{'name':'=HYPERLINK("x")<script>alert(1)</script>'})
    qid=env.paper();env.answer(qid,env.students[0]);env.actor(env.t)
    from quiz_core.presentation import dashboard_html
    html=dashboard_html(env.svc.dashboard(env.t,qid))
    assert '<script>' not in html and '&lt;script&gt;' in html
    csv_data=env.svc.export_dashboard(env.t,qid).decode('utf-8-sig')
    rows=list(csv.reader(io.StringIO(csv_data)));assert rows[1][2].startswith("'=HYPERLINK")


def test_student_widget_callbacks_save_selection_without_submit(env):
    qid=env.paper();u=env.actor(env.students[0])
    env.view._student_body(u)
    radios=[x for x in env.st.outputs if x[0]=='radio'];assert len(radios)==10
    assert not any(x[0]=='success' and '정답' in x[1] for x in env.st.outputs)
    key=f'qm_{u["id"]}_{qid}_q01';env.st.session_state[key]=2
    cb,args=env.st.callbacks[key];cb(*args)
    assert env.svc.student_paper(u,qid)['answers']=={'q01':2}
    env.actor(env.t);assert env.svc.dashboard(env.t,qid)['students'][0]['answers']=={'q01':2}


def test_teacher_controls_and_student_never_receive_key_controls(env):
    qid=env.paper();env.view._monitor_body(env.t,'test')
    buttons=[x[1] for x in env.st.outputs if x[0]=='button']
    assert '개별 채점' in buttons and any(x.startswith('일괄 채점') for x in buttons)
    assert '추가 10문항 생성' in buttons
    env.st.outputs.clear();u=env.actor(env.students[0]);env.view.page(u)
    buttons=[x[1] for x in env.st.outputs if x[0]=='button']
    assert '개별 채점' not in buttons and '학생에게 결과 공개' not in buttons
    assert not any(x[0]=='html' for x in env.st.outputs)


def test_generation_callback_selects_new_draft_and_followup_targets(env):
    env.view._make(env.t,'공통수학2',bank.units('공통수학2')[2],bank.units('공통수학2')[2])
    qid=env.st.session_state['_quiz_draft'];assert env.st.session_state['q_draft_selector']==qid
    env.svc.publish(env.t,qid,['1-1'],reviewed=True)
    env.view._followup(env.t,qid,[env.students[0]['id']],['반지름'])
    new,targets=env.st.session_state['_quiz_next_draft']
    assert new!=qid and targets==[env.students[0]['id']]
    assert env.st.session_state['nav']=='tools'
    env.view.page(env.t)
    assert env.st.session_state['q_draft_selector']==new
    assert env.st.session_state[f'qtargets_{new}']==targets


def test_source_integration_and_no_classroom_resurrection():
    tools=(ROOT/'views/tools.py').read_text()
    assert 'if key == "tool_quiz":' in tools and 'quiz.page(user)' in tools
    assert 'quiz.teacher_dashboard(user)' in (ROOT/'views/dashboard.py').read_text()
    assert 'quiz.student_home(user)' in (ROOT/'views/home.py').read_text()
    assert not (ROOT/'classroom_core').exists()
    assert (ROOT/'views/evaluation_plans.py').exists()


def test_quiz_navigation_clears_old_snorkl_link(env):
    from snorkl_navigation import LINK_SEEN,REQUESTED_COURSE,ACTIVE_TOOL
    env.st.query_params.update(tool='snorkl',course_id='old',embed='true')
    env.st.session_state[LINK_SEEN]=('snorkl','old')
    env.st.session_state[REQUESTED_COURSE]='old'
    env.view._navigate()
    assert env.st.session_state['nav']=='tools'
    assert env.st.session_state[ACTIVE_TOOL]=='tool_quiz'
    assert env.st.query_params=={'embed':'true'}
    assert LINK_SEEN not in env.st.session_state
    assert REQUESTED_COURSE not in env.st.session_state


def test_reset_editor_preserves_unrelated_widgets(env):
    qid=env.svc.create_draft(env.t,'공통수학2',bank.units('공통수학2')[2])
    for key in (f'qedit_revision_{qid}',f'qtitle_{qid}',f'qp_{qid}_1',f'qo_{qid}_1_0'):
        env.st.session_state[key]='stale'
    env.st.session_state['keep-me']='safe'
    env.view._reset_editor(qid)
    assert env.st.session_state.get(f'qtitle_{qid}') is None
    assert env.st.session_state['keep-me']=='safe'


@pytest.mark.parametrize('entry',[lambda e:e.view._monitor_guarded(e.t,'test'),lambda e:e.view._home_body(e.students[0])])
def test_fragment_navigation_requests_a_full_app_rerun(env,entry):
    env.view._navigate()
    with pytest.raises(Rerun): entry(env)
    assert '_quiz_full_rerun' not in env.st.session_state
