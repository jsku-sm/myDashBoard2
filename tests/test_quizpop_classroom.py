"""Code-based QuizPop classes; real persistence rules, fake transport/accounts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from cryptography.fernet import Fernet
from test_game_learning import game_env
from test_concept_quiz import load
from test_quiz_pop import ROOT, saved
from test_student_record_vault import gh
from test_game_learning import Rerun


@pytest.fixture
def classroom_env(game_env):
    e=game_env;e.b.is_local=False;e.b.repo='jsku-sm/class-dashboard-data'
    import quiz_pop
    e.qs=load('quiz_pop.service',ROOT/'quiz_pop/service.py',e.monkeypatch)
    e.monkeypatch.setattr(quiz_pop,'service',e.qs,raising=False)
    e.qc=load('quiz_pop.classroom',ROOT/'quiz_pop/classroom.py',e.monkeypatch)
    e.monkeypatch.setattr(quiz_pop,'classroom',e.qc,raising=False)
    e.qv=load('quiz_pop.view',ROOT/'quiz_pop/view.py',e.monkeypatch)
    e.monkeypatch.setattr(quiz_pop,'view',e.qv,raising=False)
    e.entry=load('quiz_pop.entry',ROOT/'quiz_pop/entry.py',e.monkeypatch)
    e.monkeypatch.setattr(quiz_pop,'entry',e.entry,raising=False)
    def publish(classes=None):
        e.actor(e.t)
        e.qs.save(e.t,saved(),e.qs.snapshot(e.t)['revision'])
        return e.qc.publish(e.t,'함께 푸는 다항식',classes or ['1-1'])
    e.publish=publish
    return e


def finish_value(snapshot):
    value=deepcopy(snapshot['saved'])
    for q,p in zip(value['session']['questions'],value['session']['progress']):
        p.update(attempts=[q['correctIndex']],solved=True,hintsUsed=0)
    value['showingSummary']=True
    return value


def test_teacher_publish_student_join_solve_resume_report_and_original_data(classroom_env):
    e=classroom_env;student=e.ss[0]
    e.start(student);original=deepcopy(e.raw(student))
    code=e.publish();assert len(code)==6 and code.isdigit()
    e.actor(student);assert e.qc.code_kind(student,code)=='quiz'
    assert e.qc.join(student,code)==code
    snap=e.qc.snapshot(student,code);assert snap['role']=='student' and not snap['preview']
    assert snap['saved']['session']['questions']==saved()['session']['questions']
    assert all(not p['attempts'] for p in snap['saved']['session']['progress'])
    e.qc.save(student,code,finish_value(snap),0)
    assert e.qc.join(student,code)==code and len(e.b.read('quizpop_attempts'))==1
    assert e.qc.snapshot(student,code)['saved']['showingSummary']
    assert e.raw(student)==original
    # Discard shared read cache, then use a new backend instance on the same files.
    e.db._cache()['data'].clear()
    restored=e.db.LocalBackend(e.b.root);restored.is_local=False;restored.repo=e.b.repo
    e.monkeypatch.setattr(e.db,'get_backend',lambda:restored)
    assert e.qc.snapshot(student,code)['saved']['showingSummary']
    e.actor(e.t);report=e.qc.report(e.t,code)
    assert report['joined']==1 and report['completed']==1
    assert report['results'][0]['첫 시도 정답']==3


def test_student_cannot_generate_publish_or_save_personal_draft(classroom_env):
    e=classroom_env;code=e.publish();e.actor(e.ss[0]);e.qc.join(e.ss[0],code)
    calls=[];e.monkeypatch.setattr(e.qv.api,'call',lambda *args:calls.append(args))
    for claimed_user in [e.ss[0],dict(e.ss[0],role='teacher')]:
        with pytest.raises(PermissionError):
            e.qv.dispatch(claimed_user,{'action':'generate','payload':{}},{},code)
        with pytest.raises(PermissionError):e.qs.save(claimed_user,saved(),0)
        with pytest.raises(PermissionError):e.qc.publish(claimed_user,'forged',['1-1'])
    assert not calls and len(e.b.read('quizpop_rooms'))==1


def test_teacher_paper_uses_published_questions_after_draft_changes_and_close(classroom_env):
    e=classroom_env;code=e.publish()
    expected=saved()['session']['questions']
    changed=saved();changed['session']['questions'][0]['prompt']='다른 퀴즈 문항'
    e.qs.save(e.t,changed,e.qs.snapshot(e.t)['revision'])
    paper=e.qc.teacher_paper(e.t,code)
    assert paper['questions']==expected and paper['code']==code
    assert 'targets_json' not in paper
    paper['questions'][0]['prompt']='읽기 결과 변경'
    assert e.qc.teacher_paper(e.t,code)['questions']==expected
    e.qc.close(e.t,code)
    before=deepcopy({t:e.b.read(t) for t in ('quizpop_rooms','quizpop_attempts')})
    assert e.qc.teacher_paper(e.t,code)['questions']==expected
    assert before=={t:e.b.read(t) for t in before}
    for actor in (e.other,e.ss[0]):
        e.actor(actor)
        with pytest.raises(PermissionError):e.qc.teacher_paper(actor,code)
        with pytest.raises(PermissionError):e.qc.teacher_paper(dict(actor,role='teacher'),code)
    e.actor(e.ss[0])
    with pytest.raises(PermissionError):e.qv.teacher_paper(e.ss[0])


def test_no_questions_before_join_wrong_code_class_and_impersonation(classroom_env):
    e=classroom_env;code=e.publish();e.actor(e.ss[0])
    with pytest.raises(PermissionError):e.qc.snapshot(e.ss[0],code)
    for bad in ['abc123','12345','１２３４５６','000000']:
        with pytest.raises(ValueError):e.qc.join(e.ss[0],bad)
    with pytest.raises(PermissionError):e.qc.join(e.ss[1],code)
    e.actor(e.ss[2])
    with pytest.raises(PermissionError):e.qc.join(e.ss[2],code)
    e.actor(e.ss[0]);e.rt.locked=True
    with pytest.raises(PermissionError):e.qc.join(e.ss[0],code)
    assert not e.b.read('quizpop_attempts')


def test_assignment_frozen_revision_protected_and_teacher_owner_only(classroom_env):
    e=classroom_env;code=e.publish();e.actor(e.ss[0]);e.qc.join(e.ss[0],code)
    snap=e.qc.snapshot(e.ss[0],code)
    for field,value in [('title','forged'),('runId','another-run'),('stage',1)]:
        altered=deepcopy(snap['saved']);altered['session'][field]=value
        with pytest.raises((PermissionError,ValueError)):e.qc.save(e.ss[0],code,altered,0)
    altered=deepcopy(snap['saved']);altered['session']['questions'][0]['correctIndex']=4
    with pytest.raises(PermissionError):e.qc.save(e.ss[0],code,altered,0)
    e.qc.save(e.ss[0],code,finish_value(snap),0)
    with pytest.raises(ValueError,match='다른 창'):e.qc.save(e.ss[0],code,snap['saved'],0)
    with pytest.raises(ValueError):e.qc.save(e.ss[0],code,snap['saved'],1)
    e.actor(e.other)
    assert not e.qc.history(e.other)
    with pytest.raises(PermissionError):e.qc.report(e.other,code)
    with pytest.raises(PermissionError):e.qc.close(e.other,code)
    e.actor(e.t);e.qc.close(e.t,code)
    e.actor(e.ss[0]);assert e.qc.snapshot(e.ss[0],code)['assignment']['closed']
    with pytest.raises(ValueError,match='종료'):e.qc.join(e.ss[0],code)
    with pytest.raises(ValueError,match='종료'):e.qc.save(e.ss[0],code,finish_value(snap),1)


def test_codes_share_namespace_with_old_review_games_and_publication_retry(classroom_env):
    e=classroom_env
    e.b.append('review_rooms',{'id':'legacy','code':'123456'})
    numbers=iter([23456,23457]);e.monkeypatch.setattr(e.qc.secrets,'randbelow',lambda n:next(numbers))
    code=e.publish();assert code=='123457'
    assert e.qc.publish(e.t,'함께 푸는 다항식',['1-1'])==code
    assert len(e.b.read('quizpop_rooms'))==1
    e.actor(e.ss[0]);assert e.qc.code_kind(e.ss[0],'123456')=='review'


def test_failed_publish_keeps_one_room_for_storage_retry(classroom_env):
    e=classroom_env
    e.monkeypatch.setattr(e.db,'flush_now',lambda:(_ for _ in ()).throw(RuntimeError('private provider detail')))
    with pytest.raises(ValueError,match='GitHub 저장'):e.publish()
    code=e.b.read('quizpop_rooms')[0]['code']
    e.monkeypatch.setattr(e.db,'flush_now',lambda:None)
    assert e.qc.publish(e.t,'함께 푸는 다항식',['1-1'])==code
    assert len(e.b.read('quizpop_rooms'))==1


def test_guidance_requires_join_and_uses_only_the_published_question(classroom_env):
    e=classroom_env;code=e.publish();e.actor(e.ss[0]);e.qc.join(e.ss[0],code)
    q=saved()['session']['questions'][0]
    payload={'context':{'question':q['prompt'],'concept':'forged','explanation':'secret'},'history':[],'text':'도와주세요'}
    result=e.qc.guide_payload(e.ss[0],code,payload)
    assert result['context']['concept']==q['concept'] and 'explanation' not in result['context']
    payload['context']['question']='다른 문항 출제'
    with pytest.raises(PermissionError):e.qc.guide_payload(e.ss[0],code,payload)


def test_twenty_five_students_keep_the_same_paper_and_separate_records(classroom_env):
    e=classroom_env
    students=[dict(e.ss[0],id=f'fake-{i:02}',name=f'가상{i}') for i in range(25)]
    for s in students:e.b.append('users',s)
    code=e.publish()
    def solve(s):
        e.actor(s);e.qc.join(s,code);snap=e.qc.snapshot(s,code)
        e.qc.save(s,code,finish_value(snap),0)
        return snap['saved']['session']['questions']
    with ThreadPoolExecutor(max_workers=10) as pool:papers=list(pool.map(solve,students))
    assert all(p==papers[0] for p in papers) and len(e.b.read('quizpop_attempts'))==25
    assert len({e.db.GitHubBackend._path('quizpop_attempts',a) for a in e.b.read('quizpop_attempts')})==25
    e.actor(e.t);assert e.qc.report(e.t,code)['completed']==25


def test_new_attempt_is_in_student_quiz_archive_without_class_roster(classroom_env):
    from record_core.archive import ArchiveCrypto,table_bundle
    e=classroom_env;code=e.publish();e.actor(e.ss[0]);e.qc.join(e.ss[0],code)
    crypto=ArchiveCrypto(Fernet.generate_key().decode())
    tables={t:e.b.read(t) for t in ('users','quizpop_rooms','quizpop_attempts')}
    entries,_=table_bundle(crypto,'quizpop_attempts',e.ss[0]['id'],tables['quizpop_attempts'],tables,lambda fid:None)
    assert entries
    decoded=[crypto.decrypt(value) for path,value in entries.items() if path.endswith('.enc')]
    assert any('quizpop_rooms' in json.dumps(x) for x in decoded)
    assert all('targets_json' not in json.dumps(x) for x in decoded)


def test_student_page_shows_entry_and_never_mounts_builder(classroom_env):
    e=classroom_env;e.actor(e.ss[0]);e.monkeypatch.setattr(e.qv,'_component',lambda **kwargs:pytest.fail('unjoined student got component'))
    e.qv.page(e.ss[0])
    assert any(kind=='button' and text=='퀴즈 참여' for kind,text,_ in e.st.outputs)
    assert not any('퀴즈 생성 →' in str(text) for _,text,_ in e.st.outputs)


def test_other_storage_is_rejected_for_teachers_and_students(classroom_env):
    e=classroom_env;code=e.publish()
    for local,repo in [(True,''),(False,'jsku-sm/myDashBoard2')]:
        e.b.is_local=local;e.b.repo=repo
        e.actor(e.t)
        with pytest.raises(ValueError,match='QUIZ_STORAGE'):e.qc.publish(e.t,'title',['1-1'])
        e.actor(e.ss[0])
        with pytest.raises(ValueError,match='QUIZ_STORAGE'):e.qc.join(e.ss[0],code)


def test_github_commit_keeps_questions_attempt_and_encrypted_archive_together(gh):
    b=gh.b
    b.append('quizpop_rooms',dict(id='room1',owner_id='teacher',code='123456',title='함수',status='open',
        questions_json=json.dumps(saved()['session']['questions']),targets_json='[{"id":"other-student"}]'))
    b.append('quizpop_attempts',dict(id='attempt1',room_id='room1',student_id='10101',state_json=json.dumps(saved())))
    gh.control['deny']=True
    with pytest.raises(RuntimeError):b.flush()
    assert b.dirty and b.archive_dirty and not gh.remote
    gh.control['deny']=False;b.flush()
    assert not b.dirty and not b.archive_dirty
    assert any(p.startswith('data/quizpop_rooms/') for p in gh.remote)
    assert any(p.startswith('data/quizpop_attempts/') for p in gh.remote)
    path=next(p for p in gh.remote if '/quizzes/' in p and p.endswith('current.json.enc'))
    payload=b.archive_crypto.open_bundle(gh.remote[path],'10101',path)['payload']
    assert payload['table']=='quizpop_attempts' and payload['quizpop_rooms'][0]['code']=='123456'
    assert 'targets_json' not in payload['quizpop_rooms'][0]
    b.update('quizpop_rooms','room1',{'status':'closed'})
    assert ('quizpop_attempts','10101') in b.archive_dirty
    b.flush()
    assert b.archive_crypto.open_bundle(gh.remote[path],'10101',path)['payload']['quizpop_rooms'][0]['status']=='closed'


def test_teacher_automatically_shows_code_and_student_entry_opens_assigned_paper(classroom_env):
    e=classroom_env;e.actor(e.t);e.qs.save(e.t,saved(),0)
    e.monkeypatch.setattr(e.qv,'config',lambda:{'enabled':False,'model':'test','reason':'no key'})
    e.monkeypatch.setattr(e.qv,'_settings',lambda cfg:None)
    e.monkeypatch.setattr(e.qv,'_component',lambda **kwargs:None)
    e.qv.teacher_page(e.t)
    code=e.qs.snapshot(e.t)['publication']['code']
    assert any(kind=='markdown' and code in str(value) for kind,value,_ in e.st.outputs)
    e.actor(e.ss[0]);e.st.session_state['quizpop_join_input']=code
    e.st.events.add('submit:퀴즈 참여')
    with pytest.raises(Rerun):e.entry.student_entry(e.ss[0],standalone=False)
    assert e.st.session_state['_quizpop_student_code']==code
    mounted=[];e.monkeypatch.setattr(e.qv,'_component',lambda **kwargs:mounted.append(kwargs))
    e.qv.page(e.ss[0])
    assert len(mounted)==1 and mounted[0]['data']['assignment']['code']==code
    assert mounted[0]['data']['saved']['session']['questions']==saved()['session']['questions']


def test_autopublish_on_save_is_idempotent_and_next_paper_gets_new_code(classroom_env):
    e=classroom_env;e.actor(e.t);e.st.session_state['_quizpop_publish_classes']=['1-1']
    result=e.qv.dispatch(e.t,{'action':'save','payload':saved(),'revision':0},{})
    code=result['publication']['code'];assert len(code)==6 and result['publication']['status']=='ready'
    e.qv.dispatch(e.t,{'action':'save','payload':saved(),'revision':1},{})
    assert len(e.b.read('quizpop_rooms'))==1
    e.qc.close(e.t,code)
    assert e.qc.publish_current(e.t,retry=True)['status']=='closed'
    assert len(e.b.read('quizpop_rooms'))==1
    new=saved();new['session']['runId']='new-quiz-123'
    result=e.qv.dispatch(e.t,{'action':'save','payload':new,'revision':2},{})
    assert result['publication']['code']!=code and len(e.b.read('quizpop_rooms'))==2


def test_failed_code_publish_keeps_accepted_draft_and_retries_same_room(classroom_env):
    e=classroom_env;e.actor(e.t)
    e.monkeypatch.setattr(e.db,'flush_now',lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE')))
    result=e.qv.dispatch(e.t,{'action':'save','payload':saved(),'revision':0},{})
    assert result['revision']==1 and result['publication']['status']=='error'
    assert result['publication']['code']=='' and 'PRIVATE' not in result['publication']['error']
    assert e.qs.snapshot(e.t)['saved']==saved() and len(e.b.read('quizpop_rooms'))==1
    reserved=e.b.read('quizpop_rooms')[0]['code']
    e.monkeypatch.setattr(e.db,'flush_now',lambda:None)
    result=e.qv.dispatch(e.t,{'action':'publish','payload':{}},{})
    assert result['publication']['code']==reserved and result['publication']['status']=='ready'
    assert e.qs.snapshot(e.t)['revision']==1 and len(e.b.read('quizpop_rooms'))==1
    e.actor(e.ss[0])
    with pytest.raises(PermissionError):e.qv.dispatch(e.ss[0],{'action':'publish','payload':{}},{},reserved)
