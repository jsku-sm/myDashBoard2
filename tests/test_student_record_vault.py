"""Student vault/record workflow tests; no real GitHub/OpenAI calls or real students."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
import sys
import threading
import types
from pathlib import Path
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter, PdfReader
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, TextStringObject
from record_core.archive import ArchiveCrypto, ArchiveError, EXPECTED_REPO, SENTINEL, TABLE_CATEGORIES, table_bundle, encryption_key
from record_core.ai import AIConfig, RecordAI, prepare_file, parse_pages, anonymize, public_manifest, draft_input
from record_core.service import RecordService, byte_count, check_final, scope_id
from record_core.evidence import project, validate_reviews
from record_core.assessment import bind, sync_state

ROOT=Path(__file__).resolve().parents[1]
SID='1101'; OTHER='1102'; EID='E'+'a'*16; FID='F'+'b'*16


def pdf(pages=3, ink=False, encrypted=False):
    w=PdfWriter()
    for _ in range(pages): w.add_blank_page(width=240,height=320)
    if ink:
        a=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Ink'),NameObject('/Contents'):TextStringObject('handwritten evidence')})
        w.pages[0][NameObject('/Annots')]=ArrayObject([w._add_object(a)])
    if encrypted: w.encrypt('not-shared')
    o=io.BytesIO();w.write(o);return o.getvalue()


def png():
    o=io.BytesIO();Image.new('RGB',(120,80)).save(o,format='PNG');return o.getvalue()


class MemoryVault:
    """A test double with real encryption, explicit commit and original sources."""
    is_local=False;repo=EXPECTED_REPO;branch='main'
    def __init__(self,key=None):
        self.archive_crypto=ArchiveCrypto(key or Fernet.generate_key().decode())
        self.rows={t:[] for t in TABLE_CATEGORIES};self.rows.update(users=[],quiz_sets=[])
        self.files={};self.pending={};self.dirty=set();self.original_files={};self.fail=False
    def read(self,t):return copy.deepcopy(self.rows.get(t,[]))
    def append(self,t,r):
        self.rows.setdefault(t,[]).append(copy.deepcopy(r));self.dirty.add(t)
    def update(self,t,rid,values):
        next(r for r in self.rows[t] if r['id']==rid).update(values);self.dirty.add(t)
    def queue_archive(self,sid,cat,lid,payload,attachments=()):
        entries,envelope=self.archive_crypto.bundle(sid,cat,lid,payload,attachments)
        for p,v in entries.items():
            if p not in self.files or p.endswith('/current.json.enc'):self.pending[p]=v
        return envelope
    def archive_student_tables(self,sid):
        for table in TABLE_CATEGORIES:
            if any(str(r.get('student_id'))==str(sid) for r in self.rows[table]):
                entries,_=table_bundle(self.archive_crypto,table,sid,self.rows[table],self.rows,self.original_files.get)
                self.pending.update(entries)
    def flush(self):
        if self.fail:raise RuntimeError('simulated commit failure')
        for t in self.dirty:
            if t in TABLE_CATEGORIES:
                for sid in {r.get('student_id') for r in self.rows[t] if r.get('student_id')}:
                    entries,_=table_bundle(self.archive_crypto,t,sid,self.rows[t],self.rows,self.original_files.get)
                    self.pending.update(entries)
        self.files.update(self.pending);self.pending={};self.dirty=set()
    def archive_read_student(self,sid):
        root=self.archive_crypto.student_dir(sid)+'/'
        out=[]
        for p,v in self.files.items():
            if p.startswith(root) and p.endswith('/current.json.enc'):
                b=self.archive_crypto.open_bundle(v,sid,p);b['_path']=p;out.append(b)
        return out
    def archive_load_attachment(self,sid,desc):
        return self.archive_crypto.open_attachment(self.files[desc['path']].encode(),desc,sid)


class AssessmentStore:
    repo=EXPECTED_REPO;branch='main'
    def __init__(self):
        self.blobs={'pdf-file':pdf(), 'img-file':png()}
        self.state={'courses':{'course':{'id':'course','owner_id':'teacher','subject':'공통수학2'}},
            'course_activities':{'task':{'id':'task','course_id':'course','title':'대칭이동 풀이','subject':'공통수학2','prompt':'x축 대칭점을 구하시오.'}},
            'course_attempts':{'attempt':{'id':'attempt','student_id':SID,'name':'가상학생가','class_id':'1-1','course_id':'course','activity_id':'task','text':'y 부호를 고침','images':['img-file'], 'documents':[{'original_ref':'pdf-file','filename':'가상학생가_과제.pdf','original_mime':'application/pdf'}], 'created':'2026-10-24T01:00:00Z'}},
            'course_uploads':{}, 'attempts':{}}
    def read(self):return copy.deepcopy(self.state)
    def get_blob(self,ref):return self.blobs[ref]


@pytest.fixture
def env():
    b=MemoryVault();actor=['teacher'];a=AssessmentStore()
    b.rows['users']=[{'id':'teacher','name':'가상교사','role':'teacher','must_change':'0'},
                     {'id':'teacher2','name':'다른교사','role':'teacher','must_change':'0'},
                     {'id':SID,'name':'가상학생가','role':'student','class':'1-1'},
                     {'id':OTHER,'name':'가상학생나','role':'student','class':'1-1'}]
    b.rows['sudanotes']=[{'id':'note1','student_id':SID,'name':'가상학생가','class':'1-1','date':'2026-10-23','subject':'공통수학2','q1':'대칭의 부호를 확인함','q2':'틀린 y좌표를 수정함'},
                        {'id':'note2','student_id':OTHER,'date':'2026-10-23','subject':'공통수학2','q1':'다른 학생 비공개'}]
    b.rows['points']=[{'id':'p1','student_id':SID,'created_at':'2026-10-24','kind':'벌점','score':'1','reason':'AI에 보내지 말아야 할 사유'}]
    b.rows['quiz_sets']=[{'id':'quiz','teacher_id':'teacher','subject':'공통수학2','title':'대칭 퀴즈','question_json':'[{"prompt":"반사 좌표"}]'}]
    b.rows['quiz_attempts']=[{'id':'qa','quiz_id':'quiz','student_id':SID,'created_at':'2026-10-24','state':'graded','answers_json':'{"q1":2}','marks_json':'{}','score':'1','graded_by':'teacher'}]
    b.rows['game_profiles']=[{'id':'g','student_id':SID,'state_json':json.dumps({'sessions':[{'id':'s1','topic_id':'move.reflection','status':'completed','created_at':'2026-10-24','questions':[],'answers':[{'kind':'supported'}]}]})}]
    s=RecordService(b,lambda:actor[0]);s.sync(SID,a)
    def load():return s.load(SID,'공통수학2','2026-03-01','2027-02-28')
    return types.SimpleNamespace(b=b,s=s,a=a,actor=actor,load=load)


def review(item,**changes):
    value=dict(evidence_id=item['id'],evidence_hash=item['evidence_hash'],context='정규 교과수업',teacher_confirmed=True,subject='공통수학2',fact='대칭이동에서 y좌표의 부호 오류를 점검하고 수정함.')
    value.update(changes);return value


def api_response(value,status='completed'):
    return types.SimpleNamespace(status_code=200,json=lambda:{'status':status,'model':'test-model','id':'resp-test','usage':{},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value,ensure_ascii=False)}]}]})


def api(fake):
    return RecordAI(AIConfig(api_key='not-real',model='test-model',enabled=True),session=types.SimpleNamespace(post=fake))


def test_key_resolution_and_wrong_key():
    key=Fernet.generate_key().decode();c=ArchiveCrypto(key)
    assert encryption_key({'student_archive':{'encryption_key':key}})==key
    assert encryption_key({'ENCRYPTION_KEY':key})==key
    assert encryption_key({'snorkl':{'encryption_key':key}})==key
    with pytest.raises(ArchiveError):encryption_key({})
    with pytest.raises(ArchiveError):ArchiveCrypto('password')
    with pytest.raises(ArchiveError):ArchiveCrypto(Fernet.generate_key().decode()).verify_sentinel(c.sentinel())
    c.verify_sentinel(c.sentinel())


@pytest.mark.parametrize('cat',sorted(TABLE_CATEGORIES.values())+['assessments','uploads','analyses','drafts'])
def test_each_category_encrypted_versioned_and_private(cat):
    c=ArchiveCrypto(Fernet.generate_key().decode())
    x,e=c.bundle(SID,cat,'source1',{'private':'가상학생가 작성 기록'},[{'data':b'private-file','name':'학생자료.txt'}])
    assert len(x)==3 and sum('/history/' in p for p in x)==1
    assert all(SID not in p and '가상학생가' not in v for p,v in x.items())
    current=next(p for p in x if p.endswith('current.json.enc'))
    opened=c.open_bundle(x[current],SID,current)
    assert opened['payload']['private']=='가상학생가 작성 기록'
    desc=opened['attachments'][0]
    assert c.open_attachment(x[desc['path']].encode(),desc,SID)==b'private-file'
    with pytest.raises(ArchiveError):c.open_bundle(x[current],OTHER,current)
    with pytest.raises(ArchiveError):c.open_attachment(x[desc['path']].encode(),desc,OTHER)
    y,e2=c.bundle(SID,cat,'source1',{'private':'수정함'},[])
    assert e2['version']!=e['version'] and current in y


def test_migration_preserves_originals_and_enumerates_sources(env):
    before=copy.deepcopy(env.b.rows);w=env.load()
    assert env.b.rows==before
    assert {e['category'] for e in w['data']['evidence']}=={'sudanotes','assessments','games','quizzes','points'}
    assert all(e['student_id']==SID for e in w['data']['evidence'])
    assert '다른 학생 비공개' not in json.dumps(w,ensure_ascii=False)
    assert all(not p.startswith('students/1101') for p in env.b.files)


def test_snapshots_include_quiz_questions_and_full_game_state(env):
    values=env.b.archive_read_student(SID)
    q=next(v for v in values if v['category']=='quizzes')
    assert q['payload']['quiz_sets'][0]['question_json']
    g=next(v for v in values if v['category']=='games')
    assert 'state_json' in g['payload']['rows'][0]


@pytest.mark.parametrize('actor',[SID,OTHER,None,'missing'])
def test_student_and_forged_actor_denied(env,actor):
    env.actor[0]=actor
    with pytest.raises(PermissionError):env.load()


def test_teacher_revocation_rechecked_on_every_action(env):
    w=env.load();item=w['data']['evidence'][0]
    env.b.rows['users'][0]['role']='student'
    with pytest.raises(PermissionError):env.s.save(w,[review(item)],'초안')
    with pytest.raises(PermissionError):env.s.prepare(w,[])


def test_cross_teacher_workspace_and_tampering(env):
    w=env.load();env.actor[0]='teacher2'
    with pytest.raises(PermissionError):env.s.validate(w)
    own=env.s.load(SID,'공통수학2','2026-03-01','2027-02-28')
    assert not any(e['category'] in ('assessments','quizzes') for e in own['data']['evidence'])
    env.actor[0]='teacher';bad=copy.deepcopy(w);bad['data']['student_id']=OTHER
    with pytest.raises(ArchiveError):env.s.validate(bad)


def test_wrong_repo_or_branch_blocks_assessment(env):
    env.a.repo='jsku-sm/other-data'
    with pytest.raises(ArchiveError):bind(env.a,env.b)
    env.a.repo=EXPECTED_REPO;env.a.branch='other'
    with pytest.raises(ArchiveError):bind(env.a,env.b)


def test_upload_before_submission_is_archived(env):
    env.a.state['course_uploads']['upload']={'id':'upload','student_id':SID,'name':'가상학생가','filename':'worksheet.pdf','course_id':'course','activity_id':'task','created':'2026-10-24','original_ref':'pdf-file','original_mime':'application/pdf'}
    env.s.sync(SID,env.a)
    item=next(e for e in env.load()['data']['evidence'] if e['category']=='uploads')
    assert item['attachments'][0]['name']=='worksheet.pdf' and '최종 제출' in item['text']


def test_deletion_archives_tombstone_and_preserves_history(env):
    prev=env.a.read();env.a.state['course_attempts']={}
    sync_state(env.a,env.b,env.a.state,prev);env.b.flush()
    assert not any(e['category']=='assessments' for e in env.load()['data']['evidence'])
    assert any('/assessments/' in p and '/history/' in p for p in env.b.files)


@pytest.mark.parametrize('spec,expected',[('',[0,1,2]),('1',[0]),('1,3',[0,2]),('2-3',[1,2]),('1,1',[0])])
def test_pdf_page_selection(spec,expected):assert parse_pages(spec,3)==expected


@pytest.mark.parametrize('spec',['0','4','3-1','1;2','a','1,','1-99'])
def test_invalid_pdf_pages(spec):
    with pytest.raises(ArchiveError):parse_pages(spec,3)


def test_pdf_selection_preserves_handwritten_annotations():
    f=prepare_file(pdf(3,ink=True),'student.pdf',EID,FID,'1,3')
    r=PdfReader(io.BytesIO(f['data']))
    assert len(r.pages)==2 and f['pages']==[1,3]
    assert r.pages[0]['/Annots'][0].get_object()['/Subtype']=='/Ink'
    assert 'student' not in f['name']


@pytest.mark.parametrize('raw,name',[(b'bad','x.pdf'),(b'html','x.html'),(b'','x.png'),(pdf(encrypted=True),'x.pdf'),(b'fake','x.jpg')])
def test_invalid_files_fail_closed(raw,name):
    with pytest.raises(ArchiveError):prepare_file(raw,name,EID,FID)


def test_image_preparation_and_replacement_flag():
    f=prepare_file(png(),'student.png',EID,FID,replacement=True)
    assert f['mime']=='image/png' and f['replacement'] and Image.open(io.BytesIO(f['data'])).size==(120,80)


def test_file_read_only_selected_student(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    assert env.s.file(w,e['id'],0)==png()
    with pytest.raises(ArchiveError):env.s.file(w,e['id'],12)
    bad=dict(e['attachments'][0]);bad['path']=env.b.archive_crypto.student_dir(OTHER)+'/attachments/'+'a'*64+'.bin.enc'
    with pytest.raises((ArchiveError,KeyError)):env.b.archive_load_attachment(SID,bad)


def test_prepare_and_load_never_call_external_api(env,monkeypatch):
    import requests
    post=Mock(side_effect=AssertionError('No API call allowed'));monkeypatch.setattr(requests,'post',post)
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    p=env.s.prepare(w,[{'evidence_id':e['id'],'index':1,'pages':'2'}])
    assert p['files'][0]['pages']==[2] and not post.called


def test_ai_consent_and_enabled_required_no_network():
    post=Mock()
    f=prepare_file(png(),'x.png',EID,FID)
    with pytest.raises(ArchiveError):api(post).analyze([f],consent=False)
    with pytest.raises(ArchiveError):RecordAI(AIConfig(api_key='x',model='x',enabled=False),session=types.SimpleNamespace(post=post)).analyze([f],consent=True)
    assert not post.called


def test_analysis_exact_selection_and_store_false(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    p=env.s.prepare(w,[{'evidence_id':e['id'],'index':1,'pages':'1'}]);f=p['files'][0]
    result={'observations':[dict(evidence_id=e['id'],file_id=f['file_id'],page_or_region='선택 1쪽',observed_text='y 좌표',math_concepts=['대칭'],process_seen='부호를 고침',uncertain_parts=['중간 숫자 불명확'],teacher_check='원본 부호 확인')],'warnings':[]}
    post=Mock(return_value=api_response(result));r=env.s.analyze(w,p,api(post),consent=True)
    payload=post.call_args.kwargs['json'];assert payload['store'] is False and 'tools' not in payload
    content=payload['input'][0]['content'];files=[c for c in content if c['type']=='input_file']
    assert len(files)==1 and base64.b64decode(files[0]['file_data'].split(',',1)[1])==f['data']
    assert not any(c['type']=='input_image' for c in content)
    assert '가상학생가' not in json.dumps(payload,ensure_ascii=False)
    assert r['status']=='교사 확인 전' and any('/analyses/' in k for k in env.b.files)


def test_analysis_failed_commit_retains_result_no_second_call(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    p=env.s.prepare(w,[{'evidence_id':e['id'],'index':0}]);post=Mock(return_value=api_response({'observations':[],'warnings':[]}))
    env.b.fail=True
    with pytest.raises(ArchiveError) as info:env.s.analyze(w,p,api(post),consent=True)
    assert info.value.completed_report and post.call_count==1
    env.b.fail=False;env.b.flush();assert post.call_count==1


@pytest.mark.parametrize('change',['bytes','manifest','scope'])
def test_prepared_tampering_before_network(env,change):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    p=env.s.prepare(w,[{'evidence_id':e['id'],'index':0}]);post=Mock()
    if change=='bytes':p['files'][0]['data']=b'changed'
    if change=='manifest':p['data']['manifest']=[]
    if change=='scope':p['data']['scope_id']='other'
    with pytest.raises(ArchiveError):env.s.analyze(w,p,api(post),consent=True)
    assert not post.called


def test_model_unselected_source_rejected():
    f=prepare_file(png(),'x.png',EID,FID)
    bad={'observations':[{'evidence_id':'other','file_id':'other'}],'warnings':[]}
    with pytest.raises(ArchiveError):api(Mock(return_value=api_response(bad))).analyze([f],consent=True)


@pytest.mark.parametrize('status',[400,401,403,404,429,500])
def test_api_failure_no_retry_or_sensitive_error(status):
    post=Mock(return_value=types.SimpleNamespace(status_code=status,text='secret-token'))
    with pytest.raises(ArchiveError) as e:api(post).analyze([prepare_file(png(),'x.png',EID,FID)],consent=True)
    assert post.call_count==1 and 'secret-token' not in str(e.value)


@pytest.mark.parametrize('changes',[{'context':'방과후'},{'teacher_confirmed':False},{'subject':'공통수학1'},{'evidence_hash':'changed'},{'fact':'좋음'}])
def test_teacher_review_gate(env,changes):
    w=env.load();item=next(e for e in w['data']['evidence'] if e['category']=='sudanotes')
    with pytest.raises(ArchiveError):validate_reviews(w['data']['evidence'],[review(item,**changes)],'공통수학2')


def test_points_never_pass_to_ai(env):
    w=env.load();item=next(e for e in w['data']['evidence'] if e['category']=='points')
    post=Mock()
    with pytest.raises(ArchiveError):env.s.draft(w,[review(item)],api(post),consent=True)
    assert not post.called


def test_draft_actual_preview_matches_sanitized_input(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='sudanotes')
    reviews=[review(e,fact='가상학생가(1101)가 대칭이동의 부호 오류를 고침. 연락 010-1234-5678 test@example.com')]
    output={'sentences':[{'text':'대칭이동의 부호를 확인하고 수정함.','evidence_ids':[e['id']]}],'cautions':[]}
    post=Mock(return_value=api_response(output));draft=env.s.draft(w,reviews,api(post),consent=True)
    text=post.call_args.kwargs['json']['input'][0]['content'][0]['text']
    assert text==env.s.input_preview(w,reviews)
    assert all(x not in text for x in ['가상학생가','010-1234-5678','test@example.com'])
    assert e['id'] in text and draft['evidence_hashes'][e['id']]==e['evidence_hash']


def test_draft_unrecognized_evidence_rejected():
    post=Mock(return_value=api_response({'sentences':[{'text':'근거 없음.','evidence_ids':['unknown']}],'cautions':[]}))
    with pytest.raises(ArchiveError):api(post).draft('공통수학2',[{'evidence_id':EID,'source':'교사 관찰','confirmed_fact':'사실'}],consent=True)


def test_save_unconfirmed_work_then_restore_and_finalize(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='sudanotes')
    env.s.save(w,[review(e,teacher_confirmed=False,context='확인 필요')],'작성 중 메모')
    restored=env.load();assert any(p.get('text')=='작성 중 메모' for p in restored['data']['saved'])
    text='대칭이동 학습에서 좌표의 부호를 대조해 풀이를 수정하는 모습을 보임.'
    env.s.save(restored,[review(e)],text,final=True,confirmed=True,review_note='학습지 원본과 수정 과정을 대조함.')
    assert env.b.rows['records'][0]['text']==text and 'teacher_confirmed' in env.b.rows['records'][0]['sources']
    after=env.load();assert any(p.get('kind')=='final' for p in after['data']['saved'])
    assert any('/school_records/' in p and '/history/' in p for p in env.b.files)


def test_final_requires_edit_and_does_not_accept_stale_source(env):
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='sudanotes');r=review(e)
    d={'text':'AI 초안 문장임.','evidence_hashes':{e['id']:e['evidence_hash']}}
    with pytest.raises(ArchiveError):env.s.save(w,[r],d['text']+' ',d,final=True,confirmed=True,review_note='자료를 다시 대조함.')
    env.b.update('sudanotes','note1',{'q1':'교사가 아직 보지 않은 새 내용'});env.b.flush()
    with pytest.raises(ArchiveError):env.s.save(w,[r],'교사의 수정 문장임.',d,final=True,confirmed=True,review_note='자료를 다시 대조함.')


def test_byte_count_and_length_guard():
    assert byte_count('가\n나')==8
    with pytest.raises(ArchiveError):check_final('가'*501,None,confirmed=True,review_note='교사 확인함.')
    with pytest.raises(ArchiveError):check_final('직접 기록함.',None,confirmed=False,review_note='교사 확인함.')
    check_final('직접 기록함.',None,confirmed=True,review_note='교사 확인함.')


def test_legacy_record_not_lost(env):
    env.b.append('records',{'id':'old','student_id':SID,'author_id':'teacher','subject':'공통수학2','period':'2026-03-01~2027-02-28','updated_at':'2026-10-24','text':'과거 교사 작성 문장'})
    env.b.flush();w=env.load()
    assert any(p.get('legacy_review_required') and p['text']=='과거 교사 작성 문장' for p in w['data']['saved'])


def test_student_period_separation(env):
    w=env.load();assert scope_id('teacher',SID,'공통수학2','2026-03-01','2027-02-28')==w['data']['scope_id']
    assert env.s.load(SID,'공통수학2','2026-03-01','2026-04-01')['data']['evidence']==[]
    assert env.s.load(OTHER,'공통수학2','2026-03-01','2027-02-28')['data']['scope_id']!=w['data']['scope_id']


def load_storage(monkeypatch):
    st=types.ModuleType('streamlit');st.session_state={};st.secrets={}
    st.cache_resource=lambda *a,**k: (a[0] if a and callable(a[0]) else lambda f:f)
    st.cache_data=st.cache_resource
    monkeypatch.setitem(sys.modules,'streamlit',st)
    name='vault_test_storage';spec=importlib.util.spec_from_file_location(name,ROOT/'storage.py');m=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,m);spec.loader.exec_module(m)
    return m


@pytest.fixture
def gh(monkeypatch):
    m=load_storage(monkeypatch);b=m.GitHubBackend.__new__(m.GitHubBackend)
    b.repo=EXPECTED_REPO;b.branch='main';b.rows={t:[] for t in m.SCHEMAS};b.lock=threading.RLock();b.flush_lock=threading.Lock();b.dirty={};b.pending_files=[];b.ver=0
    b.archive_crypto=ArchiveCrypto(Fernet.generate_key().decode());b.archive_dirty={};b.archive_pending={};b.archive_known=set();b.last_error='';b.last_saved=''
    remote={};pending_tree={};heads=['h0'];calls=[];control={'deny':False,'conflict':0,'private':True}
    def resp(code,payload):
        r=types.SimpleNamespace(status_code=code,json=lambda:payload,text='simulated')
        def check():
            if code>=400:raise RuntimeError('request failed')
        r.raise_for_status=check;return r
    def request(method,path,**kw):
        calls.append((method,path,kw))
        if path==f'/repos/{b.repo}':return resp(200,{'private':control['private']})
        if path.endswith('/git/commits/'+heads[-1]):return resp(200,{'tree':{'sha':'tree0'}})
        if path.endswith('/git/trees') and method=='POST':
            pending_tree.clear();pending_tree.update({e['path']:e.get('content') for e in kw['json']['tree']});return resp(201,{'sha':'tree-next'})
        if path.endswith('/git/commits') and method=='POST':return resp(201,{'sha':'head-next'})
        if '/git/refs/heads/' in path:
            if control['deny']:return resp(403,{})
            if control['conflict']:
                control['conflict']-=1;return resp(409,{})
            assert kw['json']['force'] is False
            remote.update(pending_tree);heads.append('head-next');return resp(200,{})
        raise AssertionError((method,path))
    b._req=request;b._head=lambda:heads[-1];b._archive_get=lambda p:remote.get(p,'').encode() or None
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    return types.SimpleNamespace(m=m,b=b,remote=remote,calls=calls,control=control)


def test_github_source_and_archive_same_commit_with_retry(gh):
    b=gh.b;b.append('sudanotes',{'id':'n','student_id':SID,'subject':'공통수학2','q1':'저장 사실'})
    gh.control['conflict']=1;b.flush()
    assert b.pending_count()==0
    assert any(p.startswith('data/sudanotes') for p in gh.remote)
    path=next(p for p in gh.remote if p.endswith('current.json.enc'))
    assert b.archive_crypto.open_bundle(gh.remote[path],SID,path)['payload']['rows'][0]['q1']=='저장 사실'
    assert len([c for c in gh.calls if c[0]=='PATCH'])==2


def test_commit_failure_does_not_clear_pending_and_public_blocks(gh):
    b=gh.b;b.append('points',{'id':'p','student_id':SID,'score':'1'});gh.control['deny']=True
    with pytest.raises(RuntimeError):b.flush()
    assert b.pending_count()>0 and not gh.remote
    gh.control['deny']=False;gh.control['private']=False
    with pytest.raises(gh.m.SetupError):b.flush()
    assert b.pending_count()>0 and not gh.remote
    gh.control['private']=True;b.flush();assert b.pending_count()==0


def test_wrong_remote_key_stops_write(gh):
    gh.remote[SENTINEL]=ArchiveCrypto(Fernet.generate_key().decode()).sentinel()
    gh.b.append('points',{'id':'p','student_id':SID,'score':'1'})
    with pytest.raises(ArchiveError):gh.b.flush()
    assert not any(c[0]=='POST' for c in gh.calls)


def test_updated_quiz_marks_archive_dirty(gh):
    b=gh.b;b.rows['quiz_attempts']=[{'id':'a','quiz_id':'q','student_id':SID}]
    b.rows['quiz_sets']=[{'id':'q','teacher_id':'teacher'}]
    b.update('quiz_sets','q',{'title':'문항 변경'})
    assert ('quiz_attempts',SID) in b.archive_dirty


def test_deleted_source_archives_empty_current_but_keeps_history(gh):
    b=gh.b;b.append('points',{'id':'p','student_id':SID,'score':'1'});b.flush()
    old=set(gh.remote);b.delete('points','p');b.flush()
    path=next(p for p in gh.remote if p.endswith('current.json.enc'))
    assert b.archive_crypto.open_bundle(gh.remote[path],SID,path)['payload']['rows']==[]
    assert old.issubset(gh.remote) and len([p for p in gh.remote if '/history/' in p])==2


def test_archive_path_checked_before_any_network(gh):
    with pytest.raises(ArchiveError):gh.b.archive_load_attachment(SID,{'path':'../auth/users'})
    assert gh.calls==[]


def test_branding_and_entrypoint_only_teacher():
    app=(ROOT/'app.py').read_text();ui=(ROOT/'ui.py').read_text()
    assert 'Good쌤을 만나,' in app and '수학이 달라졌다' in app
    assert '스스로 발견한 가능성과 자신감' in ui
    assert 'from record_core.view import render' in (ROOT/'views/record.py').read_text()


def test_save_checkpoint_retry_does_not_duplicate_notes_or_points():
    from record_core.checkpoint import append_confirmed
    for table in ('sudanotes','points'):
        state={};db=types.SimpleNamespace(append_many=Mock(),flush_now=Mock(side_effect=RuntimeError('offline')))
        rows=[{'id':'fixed-id','student_id':SID,'content':'saved work'}]
        with pytest.raises(RuntimeError):append_confirmed(db,state,'key',table,rows)
        assert state['key']['rows']==rows and db.append_many.call_count==1
        db.flush_now.side_effect=None
        assert append_confirmed(db,state,'key',table)==rows
        assert db.append_many.call_count==1 and 'key' not in state


def test_actual_assessment_transaction_calls_vault_hook(env,monkeypatch):
    import think_app.storage as source
    raw=[None]
    store=source.GitHubStore.__new__(source.GitHubStore)
    store.repo=EXPECTED_REPO;store.branch='main';store.fernet=Fernet(Fernet.generate_key())
    store._check_private=lambda:None
    store._get=lambda path:(raw[0], 'sha' if raw[0] else None)
    def put(path,data,sha):
        raw[0]=data
        return types.SimpleNamespace(status_code=201)
    store._put=put;store.invalidate=lambda:None;store.get_blob=env.a.get_blob
    monkeypatch.setattr(source,'_prepare_submissions',lambda *args:None)
    bind(store,env.b)
    initial=env.a.read()
    store.transaction(lambda state:state.update(initial))
    assert any('/assessments/' in p for p in env.b.files)
    env.b.fail=True
    def change(state):state['course_attempts']['attempt']['teacher_comment']='교사가 새 피드백을 작성함'
    with pytest.raises(source.AppError,match='원본은 저장되었으나'):
        store.transaction(change)
    saved=json.loads(store.fernet.decrypt(raw[0]))
    assert saved['course_attempts']['attempt']['teacher_comment']=='교사가 새 피드백을 작성함'
    assert store._archive_retry is True
    env.b.fail=False;store.transaction(lambda state:None)
    assert store._archive_retry is False
    bundle=next(v for v in env.b.archive_read_student(SID) if v['category']=='assessments')
    assert bundle['payload']['item']['teacher_comment']=='교사가 새 피드백을 작성함'


class RecordingUI(types.ModuleType):
    """Render-only Streamlit widget stub; deliberately not a real UI runtime."""
    def __init__(self):
        super().__init__('streamlit');self.session_state={};self.secrets={};self.labels=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def columns(self,values,**kw):return [self]*(values if isinstance(values,int) else len(values))
    def tabs(self,values,**kw):self.labels.extend(values);return [self]*len(values)
    def container(self,*args,**kw):return self
    def expander(self,label,*args,**kw):self.labels.append(label);return self
    def selectbox(self,label,options,key=None,index=0,**kw):
        self.labels.append(label)
        return self.session_state.setdefault(key,options[index])
    def date_input(self,label,value=None,**kw):self.labels.append(label);return value
    def button(self,label,**kw):self.labels.append(label);return False
    def multiselect(self,label,options,key=None,**kw):self.labels.append(label);return self.session_state.setdefault(key,[])
    def text_area(self,label,key=None,**kw):self.labels.append(label);return self.session_state.setdefault(key,'')
    def text_input(self,label,key=None,**kw):return self.text_area(label,key=key,**kw)
    def checkbox(self,label,key=None,**kw):self.labels.append(label);return self.session_state.setdefault(key,False)
    def number_input(self,label,value=0,**kw):self.labels.append(label);return value
    def file_uploader(self,label,**kw):self.labels.append(label);return None
    def __getattr__(self,name):
        if name.startswith('__'):raise AttributeError(name)
        if name in ('cache_resource','cache_data'):return lambda *a,**k: a[0] if a and callable(a[0]) else lambda f:f
        return lambda *a,**k:self.labels.append((name,str(a)[:100]))


def test_render_workspace_options_and_analysis_no_network(env,monkeypatch):
    st=RecordingUI();st.session_state['user']={'id':'teacher','role':'teacher'}
    db=types.ModuleType('storage');db._ready_backend=lambda:env.b;db.now=lambda:__import__('datetime').datetime(2026,10,24)
    db.SetupError=type('SetupError',(Exception,),{});db.invalidate=lambda *args:None
    monkeypatch.setitem(sys.modules,'streamlit',st);monkeypatch.setitem(sys.modules,'storage',db)
    spec=importlib.util.spec_from_file_location('record_core._test_view',ROOT/'record_core/view.py');view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
    view.render()
    assert '학생별 작성하기' in st.labels and '학생 선택' in st.labels
    assert any(isinstance(s,str) and '학생 자료파일 불러오기' in s for s in st.labels)
    w=env.load();e=next(e for e in w['data']['evidence'] if e['category']=='assessments')
    prefix='test_';st.session_state[prefix+'selected']=[e['id']]
    view._workspace(env.s,w,prefix,AIConfig(api_key='',enabled=False))
    assert '분석할 첨부파일만 선택' in st.labels and '교사 작성·수정란' in st.labels
    assert '교사 최종 확인본 저장' in st.labels
    st.session_state['user']={'id':SID,'role':'teacher'};st.labels=[]
    view.render();assert '학생 선택' not in st.labels


def test_ui_reload_discards_removed_evidence_and_prepared_files(env,monkeypatch):
    st=RecordingUI();db=types.ModuleType('storage');db.SetupError=type('SetupError',(Exception,),{})
    monkeypatch.setitem(sys.modules,'streamlit',st);monkeypatch.setitem(sys.modules,'storage',db)
    spec=importlib.util.spec_from_file_location('record_core._test_view',ROOT/'record_core/view.py');view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
    st.session_state={'x_selected':['Eremoved'],'x_prepared':{},'x_file_choices':['removed']}
    view._restore('x_',env.load())
    assert st.session_state['x_selected']==[] and 'x_prepared' not in st.session_state and 'x_file_choices' not in st.session_state


def test_assessment_preflight_rejects_wrong_repo_before_initialization(env,monkeypatch):
    # Execute just the factory function so SDK/real Streamlit aren't required.
    import ast
    tree=ast.parse((ROOT/'think_app/embedded.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='get_store')
    db=types.ModuleType('storage');db._ready_backend=lambda:env.b
    monkeypatch.setitem(sys.modules,'storage',db)
    initialized=Mock(side_effect=AssertionError('Must not initialize wrong storage'))
    namespace={'AppError':ArchiveError,'persistent_store':initialized}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'factory','exec'),namespace)
    for mode,repo in [('local',EXPECTED_REPO),('github','jsku-sm/wrong')]:
        settings=types.SimpleNamespace(mode=mode,repo=repo,branch='main')
        with pytest.raises(ArchiveError):namespace['get_store'](settings)
    assert not initialized.called
