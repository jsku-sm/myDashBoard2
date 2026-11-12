"""Planner integration: private storage, canonical links, dates, conflict/retry."""
import importlib.util
import sys
import pytest
from test_teacher_progress import env, ROOT, load

@pytest.fixture
def planner(env, monkeypatch):
    service=load('teacher_planner.service',ROOT/'teacher_planner/service.py',monkeypatch)
    env.planner=service
    return env


def diary(e,token='diary-request-01',**kw):
    payload=dict(kind='task',date='2026-10-20',time='09:00',deadline='2026-10-22',title='학습지 준비',body='내용',done='0',important='1')
    payload.update(kw)
    ids=e.planner.save_private(e.t,'teacher_diary',payload,token)
    return next(r for r in e.planner.snapshot(e.t)['diary'] if r['id']==ids[0])


def rule(e,token='rule-request-01',**kw):
    p={'weekday':'1','period':'2교시','class':'1-1','subject':'공통수학2','content':'함수 탐구'}
    p.update(kw)
    ids=e.planner.save_private(e.t,'teacher_timetable',p,token)
    return next(r for r in e.planner.snapshot(e.t)['rules'] if r['id']==ids[0])


def test_private_owner_roles_and_generic_guards(planner):
    e=planner;r=diary(e);rule(e)
    assert e.db.read('teacher_diary')==[] and e.db.read('teacher_timetable')==[]
    for table in ('teacher_diary','teacher_timetable'):
        with pytest.raises(PermissionError):e.db.append(table,{})
        with pytest.raises(PermissionError):e.db.append_many(table,[{}])
        with pytest.raises(PermissionError):e.db.update(table,r['id'],{'title':'escape'})
        with pytest.raises(PermissionError):e.db.delete(table,r['id'])
    for actor in (e.other,e.student):
        e.st.session_state['user']=actor
        if actor==e.other:
            snap=e.planner.snapshot(actor);assert not snap['diary'] and not snap['rules']
        else:
            with pytest.raises(PermissionError):e.planner.snapshot(actor)
        with pytest.raises(PermissionError):e.planner.move(actor,'diary',r['id'],r['revision'],'2026-10-21')
    e.st.session_state['user']=e.t;e.backend.update('users',e.t['id'],{'role':'student'})
    with pytest.raises(PermissionError):e.planner.snapshot(e.t)


def test_same_canonical_lesson_and_independent_assessment(planner):
    e=planner;rid=e.create()[0];r=e.svc.get_record(e.t,rid)
    e.planner.move(e.t,'lesson',rid,r['revision'],'2026-10-23','4교시')
    r=e.svc.get_record(e.t,rid)
    assert r['date']=='2026-10-23' and r['period']=='4교시'
    assert r['assessment_date']=='2026-11-03' and r['assessment_period']=='3교시'
    e.planner.move(e.t,'assessment',rid,r['revision'],'2026-11-05','5교시')
    r=e.planner.snapshot(e.t)['lessons'][0]
    assert r['date']=='2026-10-23' and r['assessment_date']=='2026-11-05'
    assert len(e.backend.read(e.svc.TABLE))==1
    with pytest.raises(e.svc.ConflictError):e.planner.move(e.t,'lesson',rid,'1','2026-10-24')


def test_diary_reopen_duplicate_save_move_due_and_trash(planner):
    e=planner;r=diary(e);assert diary(e)['id']==r['id']
    e.planner.move(e.t,'diary',r['id'],r['revision'],'2026-10-21')
    r=e.planner.snapshot(e.t)['diary'][0]
    assert r['date']=='2026-10-21' and r['deadline']=='2026-10-22'
    reopened=e.db.LocalBackend(e.backend.root)
    assert reopened.read('teacher_diary')[0]==r
    assert e.db.GitHubBackend._path('teacher_diary',r).startswith('data/teacher_diary/')
    assert e.t['id'] not in e.db.GitHubBackend._path('teacher_diary',r)
    e.planner.trash(e.t,'teacher_diary',r['id'],r['revision'])
    r=e.planner.snapshot(e.t)['diary'][0];assert r['deleted_at']
    e.planner.trash(e.t,'teacher_diary',r['id'],r['revision'],True)
    assert not e.planner.snapshot(e.t)['diary'][0]['deleted_at']


def test_carry_selective_atomic_preserves_deadline(planner):
    e=planner;a=diary(e);b=diary(e,'diary-request-02',done='1');c=diary(e,'diary-request-03',kind='meeting')
    with pytest.raises(e.svc.ConflictError):e.planner.carry(e.t,[a,b],'2026-10-20')
    assert all(r['date']=='2026-10-20' for r in e.planner.snapshot(e.t)['diary'])
    e.planner.carry(e.t,[a],'2026-10-20')
    rows={r['id']:r for r in e.planner.snapshot(e.t)['diary']}
    assert rows[a['id']]['date']=='2026-10-21' and rows[a['id']]['deadline']=='2026-10-22'
    assert rows[b['id']]['date']==rows[c['id']]['date']=='2026-10-20'


def test_timetable_generation_preview_exclusions_and_repeated_moves(planner):
    e=planner;rule(e)
    p=e.planner.generate(e.t,'2026-10-20','2026-11-10',['2026-10-27'])
    assert p['count']==3 and not e.planner.snapshot(e.t)['lessons']
    assert e.planner.generate(e.t,'2026-10-20','2026-11-10',['2026-10-27'],p['fingerprint'])['count']==3
    rows=e.svc.list_records(e.t);assert [r['date'] for r in rows]==['2026-10-20','2026-11-03','2026-11-10']
    first=rows[0];e.planner.move(e.t,'lesson',first['id'],first['revision'],'2026-10-21')
    second=rows[1];e.svc.delete_record(e.t,second['id'],second['revision'])
    p=e.planner.generate(e.t,'2026-10-20','2026-11-10',['2026-10-27'])
    assert p['count']==0 and p['skipped']==3
    assert len(e.svc.list_records(e.t,include_deleted=True))==3


def test_rule_edit_preserves_manual_content_and_generation_conflict(planner):
    e=planner;r=rule(e);p=e.planner.generate(e.t,'2026-10-20','2026-10-20',[])
    e.planner.save_private(e.t,'teacher_timetable',dict(r,content='새 개념'),'edit-rule-01',r['id'],r['revision'])
    with pytest.raises(e.svc.ConflictError):e.planner.generate(e.t,'2026-10-20','2026-10-20',[],p['fingerprint'])
    p=e.planner.generate(e.t,'2026-10-20','2026-10-20',[])
    e.planner.generate(e.t,'2026-10-20','2026-10-20',[],p['fingerprint'])
    lesson=e.svc.list_records(e.t)[0]
    e.svc.update_record(e.t,lesson['id'],dict(lesson,content='내가 수정한 진도'),lesson['class'],lesson['revision'])
    assert e.planner.generate(e.t,'2026-10-20','2026-10-20',[])['count']==0
    assert e.svc.list_records(e.t)[0]['content']=='내가 수정한 진도'


def test_existing_lesson_slot_prevents_auto_double_booking(planner):
    e=planner;e.create();rule(e)
    p=e.planner.generate(e.t,'2026-10-20','2026-10-20',[])
    assert p['count']==0 and p['skipped']==1
    with pytest.raises(ValueError):rule(e,'rule-request-02',**{'class':'1-2'})


@pytest.mark.parametrize('change',[{'date':'2026-02-30'},{'title':''},{'time':'25:00'},{'done':'yes'},{'kind':'admin'},{'deadline':'1999-01-01'}])
def test_diary_validation(planner,change):
    with pytest.raises(ValueError):diary(planner,**change)


def test_future_completed_lesson_and_invalid_generation(planner):
    e=planner;rid=e.create(status='완료')[0];r=e.svc.get_record(e.t,rid)
    with pytest.raises(ValueError):e.planner.move(e.t,'lesson',rid,r['revision'],'2026-10-21')
    rule(e)
    for start,end in [('2026-10-21','2026-10-20'),('2026-01-01','2027-01-02')]:
        with pytest.raises(ValueError):e.planner.generate(e.t,start,end,[])


def test_leap_year_year_boundary(planner):
    e=planner;rule(e,weekday='3')
    p=e.planner.generate(e.t,'2024-02-28','2024-03-01',[]);assert p['sample'][0]['date']=='2024-02-29'
    p=e.planner.generate(e.t,'2026-12-31','2027-01-01',[]);assert p['sample'][0]['date']=='2026-12-31'


def test_save_failure_no_duplicate_and_retry_outside_lock(planner,monkeypatch):
    e=planner
    def fail():
        assert not e.backend.lock._is_owned()
        raise RuntimeError('network')
    monkeypatch.setattr(e.db,'flush_now',fail)
    with pytest.raises(e.svc.SavePendingError):diary(e)
    assert len(e.backend.read('teacher_diary'))==1
    monkeypatch.setattr(e.db,'flush_now',lambda:None)
    e.planner.retry(e.t)
    assert diary(e)['id']==e.backend.read('teacher_diary')[0]['id']


def test_dispatch_no_role_trust_or_foreign_ownership(planner):
    e=planner
    command={'token':'dispatch-001','action':'save_diary','payload':dict(kind='task',date='2026-10-20',title='준비',author_id=e.other['id'])}
    e.planner.dispatch(e.t,command)
    assert e.planner.snapshot(e.t)['diary'][0]['author_id']==e.t['id']
    e.st.session_state['user']=e.student
    with pytest.raises(PermissionError):e.planner.dispatch(dict(e.student,role='teacher'),command)


def test_remote_dirty_blocks_changes_until_confirmed(planner,monkeypatch):
    e=planner;r=diary(e)
    e.backend.is_local=False
    path=e.db.GitHubBackend._path('teacher_diary',r)
    e.backend.dirty={path:1}
    assert e.planner.pending(e.t)
    with pytest.raises(e.svc.SavePendingError):
        e.planner.dispatch(e.t,{'action':'save_diary','token':'blocked-write','payload':dict(r,title='새 내용')})
    assert e.backend.read('teacher_diary')[0]['title']=='학습지 준비'
    monkeypatch.setattr(e.db,'flush_now',lambda:e.backend.dirty.clear())
    e.planner.dispatch(e.t,{'action':'retry','token':'retry-request','payload':{}})
    assert not e.planner.pending(e.t)


def test_teacher_partition_paths_and_reload(planner):
    e=planner;a=diary(e)
    e.st.session_state['user']=e.other
    e.planner.save_private(e.other,'teacher_diary',dict(a,title='다른 교사 업무'),'other-request')
    rows=e.backend.read('teacher_diary')
    assert len({e.db.GitHubBackend._path('teacher_diary',r) for r in rows})==2
    assert len(e.planner.snapshot(e.other)['diary'])==1


@pytest.mark.parametrize('kind',['task','meeting','event','note'])
def test_all_work_types_complete_and_uncomplete_persist(planner,kind):
    e=planner;r=diary(e,kind=kind)
    e.planner.dispatch(e.t,dict(token='complete-work-01',action='save_diary',payload=dict(r,done='1')))
    done=e.planner.snapshot(e.t)['diary'][0]
    assert done['done']=='1' and done['deadline']==r['deadline'] and done['body']==r['body']
    assert e.db.LocalBackend(e.backend.root).read('teacher_diary')[0]['done']=='1'
    with pytest.raises(e.svc.ConflictError):
        e.planner.dispatch(e.t,dict(token='stale-work-check',action='save_diary',payload=dict(r,done='0')))
    e.planner.dispatch(e.t,dict(token='uncomplete-work-01',action='save_diary',payload=dict(done,done='0')))
    assert e.db.LocalBackend(e.backend.root).read('teacher_diary')[0]['done']=='0'


def test_seven_period_timetable_rejects_eighth_and_skips_old_template(planner):
    e=planner
    assert '7교시' in e.planner.snapshot(e.t)['periods'] and '8교시' not in e.planner.snapshot(e.t)['periods']
    with pytest.raises(ValueError):rule(e,period='8교시')
    with pytest.raises(ValueError):e.create(period='8교시')
    r=rule(e,period='7교시')
    legacy=dict(r,id='historical-eighth',period='8교시')
    e.backend.append('teacher_timetable',legacy)
    preview=e.planner.generate(e.t,'2026-10-20','2026-10-20',[])
    assert preview['count']==1 and preview['sample'][0]['period']=='7교시'
    assert any(r['period']=='8교시' for r in e.backend.read('teacher_timetable'))
