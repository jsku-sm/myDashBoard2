"""Arcade additions preserve the existing avatar game and account boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import pytest
from test_game_learning import game_env
from test_concept_quiz import load
from game_core import play_lab_engine as lab

ROOT = Path(__file__).resolve().parents[1]


def event(kind="start", seq=1, run="run-12345678", game="bubble", **values):
    return dict(game=game, type=kind, runId=run, seq=seq, elapsed=seq*2, stage=1, stageCount=3,
                score=10, mode="relaxed", **values)


def test_all_twelve_games_exist_and_duplicate_batches_do_not_duplicate_records():
    assert len(lab.TITLES) == 12
    for gid in lab.TITLES:
        s = lab.initial()
        batch = [event(game=gid), event("success", 2, game=gid), event("clear", 3, game=gid), event("win", 4, game=gid)]
        lab.apply(s, batch, "now")
        saved = deepcopy(s)
        lab.apply(s, batch, "now")
        assert s == saved
        g = s["games"][gid]
        assert (g["starts"],g["wins"],g["successes"],g["clears"],g["points"],g["seconds"]) == (1,1,1,1,100,8)


def test_pause_resume_uses_elapsed_deltas_and_distinguishes_errors_and_hints():
    s = lab.initial()
    batch = [event(), event("error",2), event("hint",3), event("pause",4), event("resume",5), event("clear",6), event("clear",7)]
    lab.apply(s,batch,"now")
    g=s["games"]["bubble"]
    assert g["errors"]==1 and g["hints"]==1 and g["seconds"]==14
    assert g["clears"]==1 and g["points"]==100


@pytest.mark.parametrize("bad",[{"game":"unknown"},{"seq":True},{"elapsed":float("nan")},{"score":-1},{"stage":31},{"stageCount":0},{"mode":"invalid"},{"runId":"a"}])
def test_malformed_events_rejected_before_mutation(bad):
    s=lab.initial()
    with pytest.raises(ValueError):lab.apply(s,[{**event(),**bad}],"now")
    assert s==lab.initial()


@pytest.fixture
def env(game_env):
    e=game_env
    e.lab=load('game_core.play_lab_service',ROOT/'game_core/play_lab_service.py',e.monkeypatch)
    e.quiz=load('game_core.function_quiz_service',ROOT/'game_core/function_quiz_service.py',e.monkeypatch)
    return e


def test_avatar_quiz_and_arcade_coexist_and_survive_disk_reload(env):
    e=env;u=e.ss[0];sid=e.start(u);original=deepcopy(e.raw(u));e.actor(u)
    e.quiz.act(u,e.quiz.snapshot(u)['revision'],dict(id=uuid.uuid4().hex,action='open',level=1,topic=0))
    quiz_before=deepcopy(e.raw(u)['function_quiz'])
    e.lab.act(u,e.lab.snapshot(u)['revision'],[event(),event('win',2)])
    p=e.raw(u)
    for field in original:assert p[field]==original[field],field
    assert p['active_id']==sid and p['function_quiz']==quiz_before
    assert p['play_lab']['games']['bubble']['wins']==1
    disk=e.db.LocalBackend(e.b.root)
    assert json.loads(disk.read('game_profiles')[0]['state_json'])==p


def test_permissions_class_lock_and_stale_revision(env):
    e=env;u=e.actor(e.ss[0]);rev=e.lab.snapshot(u)['revision']
    e.lab.act(u,rev,[event()])
    with pytest.raises(ValueError):e.lab.act(u,rev,[event('success',2)])
    with pytest.raises(PermissionError):e.lab.snapshot(u,e.ss[1]['id'])
    with pytest.raises(PermissionError):e.lab.act(u,0,[event()],preview=True)
    e.rt.locked=True
    with pytest.raises(PermissionError):e.lab.act(u,e.lab.snapshot(u)['revision'],[event('success',2)])
    e.rt.locked=False;e.actor(e.t)
    assert e.lab.snapshot(e.t,u['id'])['games']['bubble']['starts']==1
    with pytest.raises(PermissionError):e.lab.act(e.t,0,[event()])


def test_teacher_preview_never_writes_students_and_retry_after_conflict_is_idempotent(env):
    e=env;e.actor(e.t);before=deepcopy(e.b.read('game_profiles'))
    e.lab.act(e.t,0,[event(),event('win',2)],preview=True)
    assert e.lab.snapshot(e.t,preview=True)['games']['bubble']['wins']==1
    assert e.b.read('game_profiles')==before
    u=e.actor(e.ss[0]);batch=[event(),event('win',2)]
    e.lab.act(u,e.lab.snapshot(u)['revision'],batch)
    e.lab.act(u,e.lab.snapshot(u)['revision'],batch)
    assert e.lab.snapshot(u)['games']['bubble']['wins']==1


def test_deployment_assets_are_local_and_preserve_old_avatar_entry():
    import re
    path=ROOT/'game_core/play_lab_frontend'
    html=(path/'index.html').read_text()
    for asset in re.findall(r'(?:src|href)="([^"]+)"',html):
        assert (path/asset).is_file(),asset
    view=(ROOT/'game_core/view.py').read_text()
    assert 'play_lab_page(user,lambda:_avatar_page(user))' in view
    assert 'if s:_lesson(user,p,s)' in view and 'else:_landing(user,p)' in view
    assert 'function_quiz_page(user)' in view
