"""Separate workspaces and lossless diary path migration; no live repository."""
import csv
import io
import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_teacher_planner import planner, diary, rule
from test_teacher_progress import env


def csv_text(db, table, rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=db.SCHEMAS[table])
    writer.writeheader()
    writer.writerows(db._norm(r, table) for r in rows)
    return out.getvalue()


def remote_backend(e, remote):
    db = e.db
    b = db.GitHubBackend.__new__(db.GitHubBackend)
    b.repo = 'jsku-sm/class-dashboard-data'; b.branch = 'main'
    b.rows = {t: [] for t in db.SCHEMAS}
    b.lock = threading.RLock(); b.flush_lock = threading.Lock()
    b.dirty = {}; b.pending_files = []; b.ver = 0
    b.archive_crypto = None; b.archive_dirty = {}; b.archive_pending = {}; b.archive_known = set()
    b.last_error = ''; b.last_saved = ''
    state = {'fail_write': False, 'fail_read': False, 'entries': [], 'truncated': False}
    def response(code, payload):
        def check():
            if code >= 400: raise RuntimeError('simulated failure')
        return SimpleNamespace(status_code=code, json=lambda: payload, raise_for_status=check)
    def req(method, path, **kw):
        if method == 'GET' and '/git/trees/' in path:
            return response(200, {'truncated': state['truncated'], 'tree': [dict(type='blob', path=p, sha=p) for p in remote]})
        if method == 'GET' and '/git/commits/' in path:
            return response(200, {'tree': {'sha': 'base-tree'}})
        if method == 'POST' and path.endswith('/git/trees'):
            state['entries'] = kw['json']['tree']; return response(201, {'sha': 'tree'})
        if method == 'POST' and path.endswith('/git/commits'):
            return response(201, {'sha': 'commit'})
        if method == 'PATCH':
            assert kw['json']['force'] is False
            if state['fail_write']: return response(403, {})
            remote.update({entry['path']: entry['content'] for entry in state['entries']})
            return response(200, {})
        raise AssertionError((method, path))
    def blob(sha):
        if state['fail_read']: raise RuntimeError('simulated read failure')
        return remote[sha].encode('utf-8')
    b._req = req; b._head = lambda: 'head'; b._blob = blob
    return b, state


def test_server_snapshots_exclude_other_workspace_and_owner(planner):
    e = planner; diary(e); rule(e); e.create()
    progress = e.planner.snapshot(e.t, 'progress')
    work = e.planner.snapshot(e.t, 'diary')
    assert progress['lessons'] and progress['rules'] and not progress['diary']
    assert work['diary'] and not any(work[k] for k in ('lessons', 'rules', 'classes', 'subjects', 'periods'))
    e.st.session_state['user'] = e.other
    assert not e.planner.snapshot(e.other, 'diary')['diary']
    assert not e.planner.snapshot(e.other, 'progress')['lessons']


@pytest.mark.parametrize('mode,action,kind', [
    ('progress','save_diary',None), ('progress','carry',None),
    ('progress','move','diary'), ('progress','trash','diary'), ('progress','restore','diary'),
    ('diary','save_lesson',None), ('diary','save_rule',None), ('diary','generate',None),
    ('diary','preview_generate',None), ('diary','move','lesson'), ('diary','move','assessment'),
    ('diary','trash','lesson'), ('diary','restore','assessment'), ('diary','restore','rule')])
def test_cross_workspace_requests_rejected_even_with_forged_mode(planner,mode,action,kind):
    e = planner; r = diary(e); e.create()
    before = {t: e.backend.read(t) for t in (*e.planner.TABLES, e.svc.TABLE)}
    command = dict(token='cross-scope-request', action=action, mode='diary' if mode=='progress' else 'progress',
                   payload=dict(r, kind=kind, date='2026-10-23'))
    with pytest.raises(PermissionError): e.planner.dispatch(e.t, command, mode)
    assert before == {t: e.backend.read(t) for t in before}


def test_pending_is_scoped_to_active_workspace(planner):
    e = planner; r = diary(e); e.backend.is_local = False
    e.backend.dirty = {e.db.GitHubBackend._path('teacher_diary', r): 1}
    assert e.planner.pending(e.t, 'diary') and not e.planner.pending(e.t, 'progress')
    e.backend.dirty = {'data/teaching_progress.csv': 1}
    assert e.planner.pending(e.t, 'progress') and not e.planner.pending(e.t, 'diary')


def test_local_old_diary_migrates_and_tombstone_does_not_resurrect(planner, tmp_path):
    e = planner; old = diary(e); root = tmp_path/'legacy-local'
    legacy = root/'teacher_diary'/'old.csv'; legacy.parent.mkdir(parents=True)
    original = csv_text(e.db, 'teacher_diary', [old]); legacy.write_text(original)
    b = e.db.LocalBackend(str(root)); assert b.read('teacher_diary') == [old]
    target = root/e.db.GitHubBackend._path('teacher_diary',old)
    assert target.is_file() and legacy.read_bytes() == original.encode()
    b.update('teacher_diary',old['id'],dict(deleted_at='2026-10-21',revision='2',done='1'))
    rows = e.db.LocalBackend(str(root)).read('teacher_diary')
    assert len(rows)==1 and rows[0]['deleted_at'] and rows[0]['done']=='1'
    assert legacy.read_bytes() == original.encode()


def test_remote_migration_merge_retry_restart_and_separate_teacher_files(planner):
    e = planner; db = e.db; old = diary(e)
    # One current tombstone, a legacy-only record and another teacher's work.
    deleted = dict(old, revision='3', deleted_at='2026-10-21', done='1')
    extra = dict(old,id='legacy-only',title='아직 남은 업무',revision='2')
    other = dict(old,id='other-work',author_id=e.other['id'])
    oldpath = 'data/teacher_diary/old.csv'
    target = db.GitHubBackend._path('teacher_diary',old)
    remote = {oldpath: csv_text(db,'teacher_diary',[old,extra,other]),
              target: csv_text(db,'teacher_diary',[deleted]),
              'data/teaching_progress.csv': csv_text(db,e.svc.TABLE,[]),
              'students/untouched.txt': 'preserve me'}
    original = dict(remote)
    b,state = remote_backend(e,remote); b._load_all()
    rows = b.read('teacher_diary'); assert len(rows)==3
    assert next(r for r in rows if r['id']==old['id'])==deleted
    assert len(b.dirty)==2 and all(p.startswith('goodteacher/teacher_diary/') for p in b.dirty)
    state['fail_write']=True
    with pytest.raises(RuntimeError): b.flush()
    assert b.dirty and remote==original
    state['fail_write']=False; b.flush()
    assert not b.dirty and len(state['entries'])==2
    assert all(p.startswith('goodteacher/') for p in (x['path'] for x in state['entries']))
    assert remote[oldpath]==original[oldpath] and remote['data/teaching_progress.csv']==original['data/teaching_progress.csv']
    assert remote['students/untouched.txt']=='preserve me'
    reboot,_=remote_backend(e,remote);reboot._load_all()
    assert sorted(reboot.read('teacher_diary'),key=lambda r:r['id'])==sorted(rows,key=lambda r:r['id'])
    assert not reboot.dirty
    # Newer legacy edits can be recovered; current paths win equal revisions.
    remote[oldpath]=csv_text(db,'teacher_diary',[dict(extra,revision='4',title='이전 앱의 최신 수정')])
    reboot,_=remote_backend(e,remote);reboot._load_all()
    assert next(r for r in reboot.read('teacher_diary') if r['id']==extra['id'])['title']=='이전 앱의 최신 수정'
    assert target in reboot.dirty


def test_migration_read_failure_never_publishes_partial_rows(planner):
    e=planner;r=diary(e);remote={'data/teacher_diary/old.csv':csv_text(e.db,'teacher_diary',[r])}
    b,state=remote_backend(e,remote);state['fail_read']=True
    with pytest.raises(RuntimeError):b._load_all()
    assert not b.rows['teacher_diary'] and not b.dirty
    state['fail_read']=False;state['truncated']=True
    with pytest.raises(e.db.SetupError):b._load_all()
    assert not b.rows['teacher_diary'] and not b.dirty


def test_cached_upgrade_moves_pending_edits_without_writing_legacy_path(planner):
    e=planner;r=diary(e);b,_=remote_backend(e,{})
    b.rows['teacher_diary']=[dict(r,title='저장 대기 중인 수정',revision='2')]
    b.dirty={'data/teacher_diary/old.csv':1,'data/teaching_progress.csv':1}
    b._upgrade_diary_storage();b._upgrade_diary_storage()
    target=e.db.GitHubBackend._path('teacher_diary',r)
    assert set(b.dirty)=={target,'data/teaching_progress.csv'}
    assert '저장 대기 중인 수정' in b._csv(target)
