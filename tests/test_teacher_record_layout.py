"""Folder migration and writer integration, using only fake accounts/repositories."""
import copy
import csv
import io
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_student_record_vault import gh, review
from test_teacher_progress import env
from record_core.archive import TABLE_CATEGORIES
from record_core.storage_layout import MENU_TABLES, student_path
from record_core.semester import SemesterRecords, term_scope
from record_core.evidence import project

SID='10101'; OTHER='10102'


def row(table, rid='a', sid=SID, **kw):
    r=dict(id=rid,student_id=sid,name='가상학생',author_id='teacher',created_at='2026-10-20 10:00:00',
           updated_at='2026-11-01',subject='공통수학2',content='좌표를 비교하며 대칭 관계를 설명함.',
           category='개념 설명',kind='상점',score='1',reason='수업 참여',period='2026학년도 2학기',
           text='교사가 작성 중인 내용',sources='{}', **{'class':'1-1'})
    r.update(kw);return r


def csv_text(db,table,rows):
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=db.SCHEMAS[table]);w.writeheader()
    w.writerows(db._norm(r,table) for r in rows);return out.getvalue()


def reboot(g):
    b=object.__new__(g.m.GitHubBackend)
    b.repo=g.b.repo;b.branch=g.b.branch;b.rows={t:[] for t in g.m.SCHEMAS}
    b.lock=threading.RLock();b.flush_lock=threading.Lock();b.dirty={};b.pending_files=[];b.ver=0
    b.archive_crypto=g.b.archive_crypto;b.archive_known=set();b.archive_dirty={};b.archive_pending={}
    b.last_error='';b.last_saved='';b._head=g.b._head;b._archive_get=g.b._archive_get
    def req(method,path,**kw):
        if method=='GET' and '/git/trees/' in path:
            return SimpleNamespace(status_code=200,raise_for_status=lambda:None,
                json=lambda:{'tree':[{'path':p,'type':'blob','sha':p} for p in g.remote]})
        return g.b._req(method,path,**kw)
    b._req=req;b._blob=lambda sha:g.remote[sha].encode();b._load_all();return b


@pytest.mark.parametrize('table',sorted(MENU_TABLES))
def test_remote_migration_and_last_row_deletion_do_not_resurrect(gh,table):
    old=f'data/{table}.csv';original=csv_text(gh.m,table,[row(table),row(table,'b',OTHER)])
    gh.remote[old]=original;b=reboot(gh)
    assert len(b.read(table))==2 and len(b.dirty)==2
    assert all(p.startswith('data/'+('school_records' if table=='records' else table)+'/') for p in b.dirty)
    b.flush();assert gh.remote[old]==original
    paths=[student_path(table,row(table)),student_path(table,row(table,'b',OTHER))]
    assert all(p in gh.remote for p in paths)
    bundle=[x for x in b.archive_read_student(SID) if x['payload'].get('table')==table][0]
    assert len(bundle['payload']['rows'])==1
    b.delete(table,'a');b.flush()
    again=reboot(gh)
    assert [r['student_id'] for r in again.read(table)]==[OTHER]
    assert list(csv.DictReader(io.StringIO(gh.remote[paths[0]])))==[]
    assert gh.remote[old]==original and not again.dirty
    assert [x for x in again.archive_read_student(SID) if x['payload'].get('table')==table][0]['payload']['rows']==[]


@pytest.mark.parametrize('table',sorted(MENU_TABLES))
def test_new_partition_is_authoritative_and_partial_migration_keeps_other_students(gh,table):
    gh.remote[f'data/{table}.csv']=csv_text(gh.m,table,[row(table),row(table,'removed'),row(table,'other',OTHER)])
    changed=row(table,content='수정된 관찰',text='수정된 생기부',reason='수정된 사유')
    p=student_path(table,changed);gh.remote[p]=csv_text(gh.m,table,[changed])
    b=reboot(gh);rows=b.read(table)
    assert len(rows)==2 and next(r for r in rows if r['id']=='a')==gh.m._norm(changed,table)
    assert p not in b.dirty and student_path(table,row(table,'other',OTHER)) in b.dirty
    b.flush();assert gh.remote[p]==csv_text(gh.m,table,[changed])


@pytest.mark.parametrize('table',sorted(MENU_TABLES))
def test_local_migration_and_delete_persist_with_original_backup(env,tmp_path,table):
    root=tmp_path/table;root.mkdir();old=root/(table+'.csv')
    original=csv_text(env.db,table,[row(table),row(table,'b',OTHER)]).encode();old.write_bytes(original)
    b=env.db.LocalBackend(str(root));assert len(b.read(table))==2
    target=root/Path(student_path(table,row(table))).relative_to('data')
    assert target.exists();b.delete(table,'a')
    assert [r['id'] for r in env.db.LocalBackend(str(root)).read(table)]==['b']
    assert old.read_bytes()==original and list(csv.DictReader(io.StringIO(target.read_text())))==[]
    with pytest.raises(ValueError):b.update(table,'b',{'student_id':SID})


def test_failed_remote_commit_preserves_pending_until_source_and_archive_commit_together(gh):
    for table in MENU_TABLES:gh.remote[f'data/{table}.csv']=csv_text(gh.m,table,[row(table)])
    original=dict(gh.remote);b=reboot(gh);gh.control['deny']=True
    with pytest.raises(RuntimeError):b.flush()
    assert b.dirty and b.archive_dirty and gh.remote==original
    gh.control['deny']=False;b.flush()
    assert not b.dirty and not b.archive_dirty
    assert {x['payload'].get('table') for x in b.archive_read_student(SID)} >= MENU_TABLES
    assert all(gh.remote[p]==content for p,content in original.items())


def test_partition_owner_mismatch_aborts_before_loading(gh):
    gh.remote[student_path('observations',row('observations'))]=csv_text(gh.m,'observations',[row('observations',sid=OTHER)])
    before=dict(gh.remote)
    with pytest.raises(ValueError,match='학번'):reboot(gh)
    assert gh.remote==before and not gh.calls


def test_students_cannot_mutate_points_or_view_other_students(env):
    e=env;e.backend.append('points',row('points',sid=e.student['id']))
    e.backend.append('points',row('points','foreign',OTHER))
    e.st.session_state['user']=e.student
    assert len(e.db.read('points'))==1
    for op in [lambda:e.db.append('points',row('points')),lambda:e.db.append_many('points',[row('points')]),
               lambda:e.db.update('points','a',{'score':'9'}),lambda:e.db.delete('points','a')]:
        with pytest.raises(PermissionError):op()
    e.st.session_state['user']=e.t;e.backend.update('users',e.t['id'],{'role':'student'})
    with pytest.raises(PermissionError):e.db.append('points',row('points'))


def install_writer(gh):
    users=[{'id':'teacher','name':'가상교사','role':'teacher','must_change':'0'},
           {'id':'teacher2','name':'다른교사','role':'teacher','must_change':'0'},
           {'id':SID,'name':'가상학생','role':'student','class':'1-1'},
           {'id':OTHER,'name':'가상학생2','role':'student','class':'1-1'}]
    gh.remote['data/users.csv']=csv_text(gh.m,'users',users)
    scope=term_scope('teacher',SID,'공통수학2',2026,2)
    saved=dict(format='semester-record-v1',kind='working_draft',scope_id=scope,teacher_id='teacher',student_id=SID,
               subject='공통수학2',academic_year=2026,semester=2,start='2026-09-01',end='2027-02-28',revision=2,
               text='기존 교사의 수정 초안',reviews=[],saved_at='2026-11-01',settings={})
    entries,_=gh.b.archive_crypto.bundle(SID,'drafts',scope,saved);gh.remote.update(entries)
    gh.remote['data/records.csv']=csv_text(gh.m,'records',[row('records',scope[:32],text=saved['text'])])
    gh.remote['data/observations.csv']=csv_text(gh.m,'observations',[row('observations'),row('observations','wrong-subject',subject='공통수학1'),row('observations','other-teacher',author_id='teacher2'),row('observations','other-student',sid=OTHER)])
    gh.remote['data/points.csv']=csv_text(gh.m,'points',[row('points')])
    b=reboot(gh);b.flush();return b,saved,entries


def test_migrated_writer_loads_subject_owner_and_term_then_edits_exports_reopens(gh):
    b,saved,entries=install_writer(gh);s=SemesterRecords(b,'teacher')
    w=s.load_term(SID,'공통수학2',2026,2);d=w['data']
    assert d['current']==saved
    assert len([e for e in d['evidence'] if e['category']=='observations'])==1
    assert len([e for e in d['evidence'] if e['category']=='points'])==1
    assert all(not e['eligible'] for e in d['evidence'] if e['category']=='points')
    assert all(gh.remote[p]==content for p,content in entries.items())
    p=s.save_term(w,[],'폴더 정리 후 교사가 수정한 문장')
    assert p['revision']==3
    b=reboot(gh);s=SemesterRecords(b,'teacher');w=s.load_term(SID,'공통수학2',2026,2)
    assert w['data']['current']['text']==p['text']
    csv_rows=list(csv.DictReader(io.StringIO(s.export_csv([w]).decode('utf-8-sig'))))
    assert csv_rows[0]['교과세특']==p['text'] and csv_rows[0]['학기']=='2'
    assert SemesterRecords(b,'teacher2').load_term(SID,'공통수학2',2026,2)['data']['current'] is None
    assert s.load_term(SID,'공통수학2',2026,1)['data']['current'] is None
    assert s.load_term(OTHER,'공통수학2',2026,2)['data']['current'] is None


def test_deletion_during_writing_invalidates_ai_and_final_before_generation(gh):
    b,_,_=install_writer(gh);s=SemesterRecords(b,'teacher');w=s.load_term(SID,'공통수학2',2026,2)
    r=review(next(e for e in w['data']['evidence'] if e['category']=='observations'))
    b.delete('observations','a') # deliberately leave it pending before generate
    ai=SimpleNamespace(draft=Mock())
    with pytest.raises(ValueError):s.generate(w,[r],ai,'stale-source-request',consent=True)
    assert not ai.draft.called
    with pytest.raises(ValueError):s.save_term(w,[r],'삭제된 근거로 완성하려던 문장',final=True,confirmed=True,review_note='근거를 대조하여 확인함')
    assert s.load_term(SID,'공통수학2',2026,2)['data']['current']['text']=='기존 교사의 수정 초안'


def test_quizpop_and_reward_sources_are_selected_by_teacher_subject_and_actual_answers(gh):
    b,_,_=install_writer(gh)
    qroom=dict(id='qr',owner_id='teacher',title='행렬 퀴즈',settings_json=json.dumps({'course':'공통수학1'}),questions_json='[]')
    rroom=dict(id='rr',owner_id='teacher',title='대칭 학습',unit='geometry',questions_json='[]')
    qa=dict(id='qa',room_id='qr',student_id=SID,updated_at='2026-10-20',state_json=json.dumps({'session':{'progress':[{'attempts':[0,1],'hintsUsed':1}]}}))
    ra=dict(id='ra',room_id='rr',student_id=SID,updated_at='2026-10-20',state_json=json.dumps({'answers':[{'choice':1,'correct':True,'hint':False}], 'runs':[{'score':999,'coins':55}]}))
    for table, rows in [('quizpop_rooms',[qroom]),('reward_rooms',[rroom]),('quizpop_attempts',[qa]),('reward_attempts',[ra])]:
        for r in rows:b.append(table,r)
    b.flush();s=SemesterRecords(b,'teacher')
    common1=s.load_term(SID,'공통수학1',2026,2)['data']['evidence']
    common2=s.load_term(SID,'공통수학2',2026,2)['data']['evidence']
    assert any(e['title']=='행렬 퀴즈' and e['category']=='quizzes' for e in common1)
    assert not any(e['title']=='행렬 퀴즈' for e in common2)
    game=next(e for e in common2 if e['title']=='대칭 학습')
    assert '999' not in game['text'] and '55' not in game['text'] and 'choice' in game['text']
    assert not any(e['title'] in ('행렬 퀴즈','대칭 학습') for e in SemesterRecords(b,'teacher2').load_term(SID,'공통수학2',2026,2)['data']['evidence'])
    b.update('reward_attempts','ra',{'state_json':json.dumps({'answers':[]})});b.flush()
    assert not any(e['title']=='대칭 학습' for e in s.load_term(SID,'공통수학2',2026,2)['data']['evidence'])


def legacy_instance(g):
    def old_csv(self,path):
        return csv_text(g.m,'observations',self.rows['observations'])
    cls=type('GitHubBackend',(),{'__module__':g.m.__name__,'is_local':False,'_csv':old_csv})
    b=object.__new__(cls);b.__dict__.update(g.b.__dict__)
    b.rows=copy.deepcopy(g.b.rows);b.dirty={};return b


def test_dirty_legacy_hot_upgrade_stops_before_swapping_serializer(gh,monkeypatch):
    b=legacy_instance(gh);b.rows['observations']=[gh.m._norm(row('observations'), 'observations')]
    b.dirty={'data/observations.csv':2};old_class=type(b)
    monkeypatch.setattr(gh.m,'get_backend',lambda:b)
    with pytest.raises(gh.m.SetupError,match='Reboot'):
        gh.m._ready_backend()
    assert type(b) is old_class and b.dirty=={'data/observations.csv':2}
    assert '좌표를 비교' in b._csv('data/observations.csv')


def test_clean_legacy_hot_upgrade_queues_new_paths_without_changing_other_work(gh,monkeypatch):
    b=legacy_instance(gh);b.rows['observations']=[gh.m._norm(row('observations'),'observations')]
    b.dirty={'data/submissions.csv':5};original_dirty=b.dirty
    monkeypatch.setattr(gh.m,'get_backend',lambda:b)
    assert gh.m._ready_backend() is b and type(b) is gh.m.GitHubBackend
    assert b.dirty is original_dirty and b.dirty['data/submissions.csv']==5
    assert student_path('observations',row('observations')) in b.dirty
    assert 'data/observations.csv' not in b.dirty
