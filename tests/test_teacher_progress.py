"""Local CSV + UI-control doubles. No production account, network, or browser."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace, ModuleType
import ast
import csv
import importlib.util
import io
import sys
import threading
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Rerun(Exception): pass


class FakeStreamlit(ModuleType):
    def __init__(self):
        super().__init__('streamlit')
        self.session_state = {}
        self.events = set()
        self.outputs = []
        self.current_form = ''

    def cache_resource(self, *a, **kw): return lambda fn: fn
    cache_data = cache_resource
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def columns(self, n, **kw): return [self] * (n if isinstance(n,int) else len(n))
    def container(self, *a, **kw): return self
    def expander(self, *a, **kw): return self
    def spinner(self, *a, **kw): return self
    @contextmanager
    def form(self, key, **kw):
        old = self.current_form
        self.current_form = key
        yield self
        self.current_form = old
    def _display(self, kind, body, **kw): self.outputs.append((kind,body,kw))
    def markdown(self, body, **kw): self._display('markdown', body, **kw)
    def caption(self, body, **kw): self._display('caption', body, **kw)
    def info(self, body, **kw): self._display('info', body, **kw)
    def error(self, body, **kw): self._display('error', body, **kw)
    def warning(self, body, **kw): self._display('warning', body, **kw)
    def success(self, body, **kw): self._display('success', body, **kw)
    def download_button(self, label, data, **kw): self.outputs.append(('download', label, data))
    def button(self,label, *, key=None, disabled=False, **kw):
        self.outputs.append(('button',label,key))
        hit = key in self.events
        self.events.discard(key)
        return hit and not disabled
    def form_submit_button(self,label, **kw): return self.button(label,key=self.current_form+':'+label,**kw)
    def _widget(self,kind,label,default,key,**kw):
        self.outputs.append((kind,label,key))
        return self.session_state.setdefault(key, default)
    def text_input(self,label,value='',key=None,**kw): return self._widget('text',label,value,key,**kw)
    text_area=text_input
    def selectbox(self,label,options,index=0,key=None,**kw):
        val=self._widget('selectbox',label, None if index is None or not options else options[index],key,**kw)
        if val not in options and val is not None: return None
        return val
    def multiselect(self,label,options,default=None,key=None,**kw): return self._widget('multi',label,default or [],key,**kw)
    def date_input(self,label,value=None,key=None,**kw): return self._widget('date',label,value,key,**kw)
    def radio(self,label,options,index=0,key=None,**kw): return self._widget('radio',label,options[index],key,**kw)
    def checkbox(self,label,value=False,key=None,**kw): return self._widget('checkbox',label,value,key,**kw)
    def rerun(self,*a,**kw): raise Rerun()


def load(name,path,monkeypatch):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def env(monkeypatch,tmp_path):
    st=FakeStreamlit(); monkeypatch.setitem(sys.modules,'streamlit',st)
    db=load('storage',ROOT/'storage.py',monkeypatch)
    back=db.LocalBackend(str(tmp_path/'data'))
    monkeypatch.setattr(db,'get_backend',lambda:back)
    monkeypatch.setattr(db,'_cache',lambda:cache)
    monkeypatch.setattr(db,'today_str',lambda:'2026-10-20')
    from datetime import datetime
    monkeypatch.setattr(db,'now',lambda:datetime(2026,10,20,9,0,0))
    cache={'data':{},'lock':threading.Lock()}
    svc=load('teaching_progress_service',ROOT/'teaching_progress_service.py',monkeypatch)
    vis=load('teaching_progress_visuals',ROOT/'teaching_progress_visuals.py',monkeypatch)
    view=load('views.teaching_progress',ROOT/'views/teaching_progress.py',monkeypatch)
    t={'id':'test-teacher-A','role':'teacher','must_change':'0','name':'시험교사 A'}
    other={'id':'test-teacher-B','role':'teacher','must_change':'0','name':'시험교사 B'}
    stu={'id':'test-student','role':'student','must_change':'0','name':'가상학생'}
    for user in (t,other,stu): back.append('users',user)
    st.session_state['user']=dict(t)
    payload={'date':'2026-10-20','subject':'공통수학2','period':'2교시','content':'원의 방정식: 중심과 반지름',
             'status':'예정','assessment_title':'픽토그램 수행평가','assessment_date':'2026-11-03',
             'assessment_period':'3교시','assessment_status':'예정','memo':'아이패드 충전'}
    obj=SimpleNamespace(st=st,db=db,backend=back,svc=svc,vis=vis,view=view,t=t,other=other,student=stu,payload=payload)
    def create(classes=None,request='request-0001',**changes):
        return svc.create_records(t,classes or ['1-1'],dict(payload,**changes),request)
    obj.create=create
    return obj


def test_schema_and_source_integration(env):
    assert env.svc.TABLE in env.db.SCHEMAS
    assert env.db.CACHE_TTL[env.svc.TABLE]==0
    dashboard=(ROOT/'views/dashboard.py').read_text()
    assert 'quiz' not in dashboard.lower() and '퀴즈' not in dashboard
    teacher=(ROOT/'views/teacher.py').read_text()
    assert '📅 진도관리' in teacher and 'tab_teaching_progress(user)' in teacher
    assert 'from views.teaching_progress import' in teacher
    tools=(ROOT/'views/tools.py').read_text()
    assert 'quiz' in tools and '4. 퀴즈' in tools
    assert 'quiz' in (ROOT/'views/home.py').read_text()


def test_seven_independent_rows_persist_and_reopen(env):
    ids=env.create(classes=[f'1-{i}' for i in range(1,8)])
    assert len(set(ids))==7
    rows=env.svc.list_records(env.t)
    assert len(rows)==7 and all(r['status']=='예정' for r in rows)
    env.svc.set_completed(env.t,ids[0],rows[0]['revision'])
    assert sum(r['status']=='완료' for r in env.svc.list_records(env.t))==1
    fresh=env.db.LocalBackend(env.backend.root)
    assert len(fresh.read(env.svc.TABLE))==7
    assert Path(env.backend.root,'teaching_progress.csv').is_file()
    assert all(r['revision'] in ('1','2') for r in fresh.read(env.svc.TABLE))


def test_retry_same_creation_is_idempotent_and_duplicate_classes_removed(env):
    first=env.create(classes=['1-1','1-1','1-2'])
    second=env.create(classes=['1-1','1-2'])
    assert first==second and len(env.svc.list_records(env.t))==2
    with pytest.raises(env.svc.ConflictError): env.create(content='내용을 바꿈')


def test_different_batch_classes_dont_add_partial_duplicate(env):
    env.create(classes=['1-1'])
    with pytest.raises(env.svc.ConflictError): env.create(classes=['1-1','1-2'])
    assert len(env.svc.list_records(env.t))==1


def test_concurrent_different_batches_and_same_batch(env):
    with ThreadPoolExecutor(max_workers=8) as pool:
        result=list(pool.map(lambda i:env.create(request=f'concurrent-{i:04d}'),range(25)))
    assert len(env.svc.list_records(env.t))==25
    with ThreadPoolExecutor(max_workers=8) as pool:
        result=list(pool.map(lambda i:env.create(request='same-request-01'),range(25)))
    assert len({r[0] for r in result})==1
    assert len(env.svc.list_records(env.t))==26


@pytest.mark.parametrize('actor',['student','other','missing','forged','revoked','must_change'])
def test_owner_and_current_teacher_validation(env,actor):
    rid=env.create()[0]
    who=env.t
    if actor=='student': who=env.student
    elif actor=='other': who=env.other
    elif actor=='missing': env.st.session_state.pop('user')
    elif actor=='forged': who=dict(env.student,role='teacher')
    elif actor=='revoked': env.backend.update('users',env.t['id'],{'role':'student'})
    elif actor=='must_change': env.backend.update('users',env.t['id'],{'must_change':'1'})
    if actor not in ('missing','revoked','must_change'): env.st.session_state['user']=who
    with pytest.raises(PermissionError): env.svc.get_record(who,rid)
    with pytest.raises(PermissionError): env.svc.update_record(who,rid,env.payload,'1-1','1')
    with pytest.raises(PermissionError): env.svc.delete_record(who,rid,'1')
    with pytest.raises(PermissionError): env.svc.restore_record(who,rid,'1')
    if actor != 'other':
        with pytest.raises(PermissionError): env.svc.create_records(who,['1-1'],env.payload,'new-request')
        with pytest.raises(PermissionError): env.svc.export_csv(who,'2026-10-01','2026-10-31')
    else:
        assert env.svc.list_records(who)==[]
        assert '원의 방정식' not in env.svc.export_csv(who,'2026-10-01','2026-10-31').decode('utf-8-sig')


def test_generic_read_write_paths_protect_teacher_record(env):
    rid=env.create()[0]
    assert len(env.db.read(env.svc.TABLE))==1
    for who in (env.student,env.other):
        env.st.session_state['user']=who
        assert env.db.read(env.svc.TABLE)==[]
        with pytest.raises(PermissionError): env.db.update(env.svc.TABLE,rid,{'content':'hack'})
        with pytest.raises(PermissionError): env.db.delete(env.svc.TABLE,rid)
    env.st.session_state['user']=env.t
    with pytest.raises(PermissionError): env.db.update(env.svc.TABLE,rid,{'author_id':env.other['id']})
    env.backend.update('users',env.t['id'],{'role':'student'})
    assert env.db.read(env.svc.TABLE)==[]
    with pytest.raises(PermissionError): env.db.append(env.svc.TABLE,dict(env.payload,author_id=env.t['id']))


@pytest.mark.parametrize('field,value',[
    ('date','2026-02-30'),('date',''),('date','2026/10/20'),('date','2101-01-01'),
    ('subject','알수없는과목'),('period','100교시'),('status','자동채점'),
    ('content','x'*4001),('content',['invalid']),('memo','x'*4001),('assessment_title','x'*301),
    ('assessment_date','어제'),('assessment_period','invalid'),('assessment_status','invalid'),
])
def test_invalid_fields_write_nothing(env,field,value):
    with pytest.raises(ValueError): env.create(**{field:value})
    assert env.svc.list_records(env.t)==[]


@pytest.mark.parametrize('classes',[[],['2-1'],['1-8'],['../../'],[{}],None,'1-1'])
def test_invalid_classes(env,classes):
    with pytest.raises(ValueError): env.svc.create_records(env.t,classes,env.payload,'invalid-classes')
    assert not env.svc.list_records(env.t)


def test_empty_content_and_assessment_rejected(env):
    with pytest.raises(ValueError): env.create(content='',assessment_title='',assessment_date='')
    with pytest.raises(ValueError): env.create(assessment_title='',assessment_date='2026-11-01')


def test_future_completed_lesson_or_assessment_rejected(env):
    with pytest.raises(ValueError): env.create(date='2026-10-21',status='완료')
    with pytest.raises(ValueError): env.create(assessment_status='완료')
    with pytest.raises(ValueError): env.create(assessment_status='완료',assessment_date='')


def test_no_assessment_clears_default_fields(env):
    rid=env.create(assessment_title='',assessment_date='')[0]
    r=env.svc.get_record(env.t,rid)
    assert r['assessment_status']==r['assessment_period']==r['assessment_date']==''


def test_assessment_only_is_not_a_completed_lesson(env):
    rid=env.create(content='',status='완료')[0]
    r=env.svc.get_record(env.t,rid)
    assert r['status']=='예정'
    with pytest.raises(ValueError): env.svc.set_completed(env.t,rid,'1')
    card=env.svc.summaries([r],'2026-10-20')[0]
    assert card['completed']==0 and card['total']==0 and card['assessment']==r


def test_edit_changes_one_record_preserves_id_created_owner_assessment_independent(env):
    ids=env.create(classes=['1-1','1-2'])
    old=env.svc.get_record(env.t,ids[0])
    env.svc.update_record(env.t,ids[0],dict(old,date='2026-10-19',status='완료',memo='수정'),'1-3','1')
    r=env.svc.get_record(env.t,ids[0])
    assert r['assessment_date']==old['assessment_date']
    assert r['id']==old['id'] and r['created_at']==old['created_at'] and r['author_id']==env.t['id']
    assert r['revision']=='2' and r['class']=='1-3'
    assert env.svc.get_record(env.t,ids[1])['status']=='예정'
    with pytest.raises(env.svc.ConflictError): env.svc.update_record(env.t,ids[0],old,'1-1','1')
    assert env.svc.get_record(env.t,ids[0])['memo']=='수정'


def test_soft_delete_restore_and_version_check(env):
    rid=env.create()[0]
    env.svc.delete_record(env.t,rid,'1')
    assert env.svc.list_records(env.t)==[]
    with pytest.raises(PermissionError): env.svc.get_record(env.t,rid)
    deleted=env.svc.get_record(env.t,rid,include_deleted=True)
    assert deleted['deleted_at'] and deleted['revision']=='2'
    assert len(env.backend.read(env.svc.TABLE))==1
    with pytest.raises(env.svc.ConflictError): env.svc.restore_record(env.t,rid,'1')
    env.svc.restore_record(env.t,rid,'2')
    assert len(env.svc.list_records(env.t))==1
    assert env.svc.get_record(env.t,rid)['revision']=='3'


def test_failed_flush_has_queued_data_idempotent_retry_no_secret_in_error(env,monkeypatch):
    def fail(): raise RuntimeError('secret-EXAMPLE-token')
    monkeypatch.setattr(env.db,'flush_now',fail)
    with pytest.raises(env.svc.SavePendingError) as error: env.create()
    assert 'secret' not in str(error.value)
    assert len(error.value.ids)==1 and len(env.svc.list_records(env.t))==1
    monkeypatch.setattr(env.db,'flush_now',lambda:None)
    assert env.create()==error.value.ids
    assert len(env.svc.list_records(env.t))==1


def test_locked_store_does_not_hold_lock_on_remote_flush(env,monkeypatch):
    called=[]
    def flush():
        assert not env.backend.lock._is_owned()
        called.append(True)
    monkeypatch.setattr(env.db,'flush_now',flush)
    rid=env.create()[0]
    env.svc.update_record(env.t,rid,dict(env.payload,memo='saved'),'1-1','1')
    env.svc.delete_record(env.t,rid,'2'); env.svc.restore_record(env.t,rid,'3')
    assert len(called)==4


def test_assessment_filter_uses_its_date_not_lesson_date_and_unknown_dates(env):
    env.create(request='old-lesson1',date='2026-09-10',assessment_date='2026-11-03')
    env.create(request='undated-001',assessment_date='')
    all_rows=env.svc.list_records(env.t)
    assert len(env.svc.filter_records(all_rows,'2026-11-01','2026-11-30',mode='lesson'))==0
    assert len(env.svc.filter_records(all_rows,'2026-11-01','2026-11-30',mode='assessment'))==2
    assert len(env.svc.filter_records(all_rows,'2026-11-01','2026-11-30',mode='assessment',include_undated=False))==1
    with pytest.raises(ValueError): env.svc.filter_records(all_rows,'2026-11-30','2026-11-01')


def test_summary_subjects_future_and_latest_completed(env):
    env.create(request='summary-001',date='2026-10-10',status='완료',content='먼저 완료')
    env.create(request='summary-002',date='2026-10-19',status='완료',content='최근 완료')
    env.create(request='summary-003',date='2026-10-25',content='다음 수업')
    env.create(request='summary-004',date='2026-10-12',status='휴강')
    env.create(request='summary-005',date='2026-10-14',content='상태 확인')
    cards=env.svc.summaries(env.svc.list_records(env.t),'2026-10-20')
    assert len(cards)==7 and cards[0]['last']['content']=='최근 완료'
    assert cards[0]['next']['content']=='다음 수업' and cards[0]['overdue']==1
    assert cards[0]['completed']==2 and cards[1]['last'] is None
    other=env.svc.summaries(env.svc.list_records(env.t),'2026-10-20','공통수학1')
    assert other[0]['last'] is None


def test_export_scoped_bom_formula_safe(env):
    env.create(classes=['1-1','1-2'],content='=HYPERLINK("unsafe")',memo='+SUM(1,2)')
    blob=env.svc.export_csv(env.t,'2026-10-01','2026-10-31','1-1')
    assert blob.startswith(b'\xef\xbb\xbf')
    out=list(csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))))
    assert len(out)==1 and out[0]['학급']=='1-1'
    assert out[0]['수업내용'].startswith("'=") and out[0]['메모'].startswith("'+")
    assert 'author_id' not in out[0] and 'revision' not in out[0]


def test_visuals_escape_markup_and_preserve_newline(env):
    env.create(content='<script>alert(1)</script>\n둘째 줄')
    rows=env.svc.list_records(env.t)
    rendered=env.vis.cards_html(env.svc.summaries(rows,'2026-10-20'),'2026-10-20')+env.vis.table_html(env.svc.display_rows(rows))
    assert '<script>' not in rendered and '&lt;script&gt;' in rendered
    assert '둘째 줄' in rendered and 'overflow:auto' in env.vis.CSS


def test_quizzes_materials_unaffected(env):
    env.backend.append('quiz_sets',{'id':'legacy-quiz','teacher_id':env.t['id']})
    env.backend.append('quiz_attempts',{'id':'legacy-answer','quiz_id':'legacy-quiz','student_id':env.student['id'],'score':'83.3'})
    before=deepcopy(env.backend.read('quiz_attempts'))
    rid=env.create()[0]; env.svc.set_completed(env.t,rid,'1'); env.svc.delete_record(env.t,rid,'2')
    assert env.backend.read('quiz_attempts')==before
    assert len(env.backend.read('quiz_sets'))==1


def test_ui_student_has_no_form_data_or_download(env):
    env.create()
    env.st.session_state['user']=env.student
    env.view.page(env.student)
    assert [o for o in env.st.outputs if o[0]=='error']
    assert not [o for o in env.st.outputs if o[0] in ('text','selectbox','download')]


def test_ui_create_edit_complete_and_filters(env):
    prefix=env.view._prefix(env.t)
    env.view.page(env.t)
    nonce=env.st.session_state[prefix+'_nonce']
    fkey=prefix+'_new_'+nonce
    env.st.session_state[fkey+'_content']='UI 기록 시험'
    env.st.session_state[fkey+'_classes']=['1-1','1-7']
    env.st.events.add(fkey+'_form:선택 학급에 기록 저장')
    with pytest.raises(Rerun): env.view.page(env.t)
    rows=env.svc.list_records(env.t); assert len(rows)==2
    env.view.page(env.t)
    rid=rows[0]['id'];env.st.session_state[prefix+'_selected']=rid
    env.st.events.add(prefix+'_open_edit');env.view.page(env.t)
    snapshot=env.st.session_state[prefix+'_editor'];epoch=env.st.session_state[prefix+'_edit_epoch']
    editkey=prefix+'_edit_'+rid+'_r'+snapshot['revision']+'_'+epoch
    env.st.session_state[editkey+'_memo']='편집 완료'
    env.st.events.add(editkey+'_form:수정 저장')
    with pytest.raises(Rerun): env.view.page(env.t)
    assert env.svc.get_record(env.t,rid)['memo']=='편집 완료'
    env.st.events.add(prefix+'_complete')
    with pytest.raises(Rerun): env.view.page(env.t)
    assert env.svc.get_record(env.t,rid)['status']=='완료'


def test_ui_invalid_keeps_inputs(env):
    prefix=env.view._prefix(env.t);env.view.page(env.t)
    fkey=prefix+'_new_'+env.st.session_state[prefix+'_nonce']
    env.st.session_state[fkey+'_memo']='내용 없음에도 입력 유지'
    env.st.events.add(fkey+'_form:선택 학급에 기록 저장')
    env.view.page(env.t)
    assert not env.svc.list_records(env.t)
    assert env.st.session_state[fkey+'_memo']=='내용 없음에도 입력 유지'
    assert any(o[0]=='error' for o in env.st.outputs)


def test_ui_failed_flush_retry_same_record_and_resets_form(env,monkeypatch):
    prefix=env.view._prefix(env.t);env.view.page(env.t)
    nonce=env.st.session_state[prefix+'_nonce'];fkey=prefix+'_new_'+nonce
    env.st.session_state[fkey+'_content']='네트워크 재시도'
    env.st.events.add(fkey+'_form:선택 학급에 기록 저장')
    def fail():raise RuntimeError('fake failure')
    monkeypatch.setattr(env.db,'flush_now',fail)
    with pytest.raises(Rerun):env.view.page(env.t)
    assert env.st.session_state[prefix+'_pending_action']=='create'
    assert len(env.svc.list_records(env.t))==1
    monkeypatch.setattr(env.db,'flush_now',lambda:None)
    env.st.events.add(prefix+'_retry')
    with pytest.raises(Rerun):env.view.page(env.t)
    assert len(env.svc.list_records(env.t))==1
    assert env.st.session_state[prefix+'_nonce']!=nonce
    assert prefix+'_pending_action' not in env.st.session_state


def test_ui_assessment_outside_lesson_month_still_shown(env):
    env.create(date='2026-09-15',assessment_date='2026-10-27')
    p=env.view._prefix(env.t)
    env.st.session_state[p+'_mode']='수행평가일 기준'
    env.view.page(env.t)
    tables=[o[1] for o in env.st.outputs if o[0]=='markdown' and '<table>' in str(o[1])]
    assert len(tables)==1 and '2026-10-27' in tables[0] and '픽토그램' in tables[0]
    assert len([o for o in env.st.outputs if o[0]=='download'])==1


def test_github_csv_serialization_and_load_are_schema_compatible(env,monkeypatch):
    rid=env.create()[0]
    original=env.svc.get_record(env.t,rid)
    remote=object.__new__(env.db.GitHubBackend)
    remote.lock=threading.RLock();remote.rows={env.svc.TABLE:[original]};remote.repo='example/private-test'
    path=remote._path(env.svc.TABLE,original)
    assert path=='data/teaching_progress.csv'
    text=remote._csv(path)
    saved=list(csv.DictReader(io.StringIO(text)))[0]
    assert saved==original
    remote.rows={}
    monkeypatch.setattr(remote,'_head',lambda:'head-test')
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'tree':[{'type':'blob','path':path,'sha':'blob-test'}]}
    monkeypatch.setattr(remote,'_req',lambda *a,**kw:Response())
    monkeypatch.setattr(remote,'_blob',lambda sha:text.encode())
    remote._load_all(tables={env.svc.TABLE})
    assert remote.rows[env.svc.TABLE]==[original]


def test_generic_append_assigns_actual_owner_not_supplied_owner(env):
    rid=env.db.append(env.svc.TABLE,dict(env.payload,author_id=env.other['id']))
    r=next(r for r in env.backend.read(env.svc.TABLE) if r['id']==rid)
    assert r['author_id']==env.t['id']
    env.st.session_state['user']=env.student
    with pytest.raises(PermissionError): env.db.append_many(env.svc.TABLE,[dict(env.payload,id='forced')])


def test_pending_and_retry_authorization(env,monkeypatch):
    monkeypatch.setattr(env.backend,'is_local',False)
    env.backend.dirty={'data/teaching_progress.csv':1}
    assert env.svc.pending_save(env.t)
    env.backend.dirty.clear()
    assert not env.svc.pending_save(env.t)
    env.st.session_state['user']=env.student
    with pytest.raises(PermissionError):env.svc.retry_save(env.student)


def test_ui_conflict_keeps_unsubmitted_values_and_reload_nonce(env):
    rid=env.create()[0];p=env.view._prefix(env.t)
    env.view.page(env.t);env.st.session_state[p+'_selected']=rid
    env.st.events.add(p+'_open_edit');env.view.page(env.t)
    old=env.st.session_state[p+'_editor'];old_epoch=env.st.session_state[p+'_edit_epoch']
    editkey=p+'_edit_'+rid+'_r1_'+old_epoch
    env.st.session_state[editkey+'_memo']='보관할 초안'
    env.svc.update_record(env.t,rid,dict(old,memo='다른 창에서 수정'),'1-1','1')
    env.st.events.add(editkey+'_form:수정 저장');env.view.page(env.t)
    assert env.svc.get_record(env.t,rid)['memo']=='다른 창에서 수정'
    assert env.st.session_state[editkey+'_memo']=='보관할 초안'
    assert any(o[0]=='error' and '먼저 수정' in o[1] for o in env.st.outputs)
    env.st.events.add(p+'_reload_edit')
    with pytest.raises(Rerun):env.view.page(env.t)
    assert env.st.session_state[p+'_edit_epoch']!=old_epoch
    assert env.st.session_state[p+'_editor']['memo']=='다른 창에서 수정'


def test_ui_delete_confirmation_and_restore(env):
    rid=env.create()[0];p=env.view._prefix(env.t)
    env.view.page(env.t);env.st.session_state[p+'_selected']=rid
    env.st.events.add(p+'_delete_'+rid);env.view.page(env.t)
    assert len(env.svc.list_records(env.t))==1
    env.st.session_state[p+'_confirm_'+rid]=True;env.st.events.add(p+'_delete_'+rid)
    with pytest.raises(Rerun):env.view.page(env.t)
    assert len(env.svc.list_records(env.t))==0
    env.st.session_state[p+'_restore_selected']=rid;env.st.events.add(p+'_restore')
    with pytest.raises(Rerun):env.view.page(env.t)
    assert len(env.svc.list_records(env.t))==1
