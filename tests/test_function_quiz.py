"""New quiz progression, server authority, additive persistence and archives."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import pytest
from test_game_learning import game_env
from test_concept_quiz import load
from game_core import function_quiz_engine as quiz
from record_core.archive import ArchiveCrypto,table_bundle
from cryptography.fernet import Fernet

ROOT=Path(__file__).resolve().parents[1]

def event(action,**values):return dict(id=uuid.uuid4().hex,action=action,**values)
def answer_event(state,correct=True):
    a=state['active'];q=a['question']
    return event('answer',question_id=a['id'],turn=a['turn'],choice=q['answer'] if correct else (q['answer']+1)%3,seconds=0)


def test_bank_has_all_six_topics_five_levels_unique_valid_questions():
    bank=quiz.bank();assert len(bank['topics'])==6 and len(bank['levels'])==5
    assert len(bank['questions'])==2407
    for level in range(1,6):
        for topic in range(6):
            qs=[q for q in bank['questions'] if (q['level'],q['topic'])==(level,topic)]
            assert len(qs)>1 and len({q['prompt'] for q in qs})==len(qs)
            assert all(len(set(q['options']))==3 and type(q['answer']) is int and 0<=q['answer']<3 and q['explanation'] for q in qs)


def test_stages_unlock_sequentially_and_master_bonus_never_duplicates():
    state=quiz.initial()
    with pytest.raises(ValueError):quiz.open_question(state,2,0)
    for level in range(1,6):
        assert quiz.unlocked(state)==level
        for topic in range(6):
            quiz.apply(state,event('open',level=level,topic=topic),'now')
            e=answer_event(state);quiz.apply(state,e,'now');quiz.apply(state,e,'now')
            # A fresh event ID still cannot resubmit a resolved turn.
            quiz.apply(state,answer_event(state),'now')
        assert state['stages'][str(level)]['completed_at']=='now'
    assert state['totals']==dict(answered=30,correct=30,wrong=0,seconds=0)
    assert sum(state['awards'].values())==1800 and state['mastered_at']
    quiz.open_question(state,5,5);quiz.apply(state,answer_event(state),'now')
    assert sum(state['awards'].values())==1800


def test_retry_tracks_errors_and_never_leaks_unsubmitted_answer():
    s=quiz.initial();quiz.open_question(s,1,0)
    public=quiz.public(s)['question']
    assert 'answer' not in public and 'explanation' not in public and public['result'] is None
    old=answer_event(s,False);quiz.apply(s,old,'now')
    assert s['totals']['wrong']==1 and not s['stages']['1']['passed']
    q=quiz.public(s)['question'];assert q['result']['answer'] is not None
    quiz.apply(s,event('retry',question_id=q['id'],turn=q['turn']),'now')
    with pytest.raises(ValueError):quiz.apply(s,{**old,'id':uuid.uuid4().hex},'now')
    quiz.apply(s,answer_event(s),'now')
    assert s['totals']['answered']==2 and s['totals']['correct']==1
    assert s['stages']['1']['passed']['0']['tries']==2


def test_random_open_never_immediately_repeats_and_bad_values_rejected():
    s=quiz.initial();seen=None
    for _ in range(12):
        quiz.open_question(s,5,5,preview=True)
        assert s['active']['question']['id']!=seen;seen=s['active']['question']['id']
    for choice in [None,-1,3,True,'0']:
        with pytest.raises(ValueError):quiz.apply(s,{**answer_event(s),'choice':choice},'now')
    with pytest.raises(ValueError):quiz.apply(s,{**answer_event(s),'seconds':float('nan')},'now')
    assert s['totals']['answered']==0


@pytest.fixture
def env(game_env):
    e=game_env
    svc=load('game_core.function_quiz_service',ROOT/'game_core/function_quiz_service.py',e.monkeypatch)
    import game_core
    e.monkeypatch.setattr(game_core,'function_quiz_service',svc,raising=False)
    e.quiz=svc
    return e


def test_existing_game_and_new_quiz_both_survive_restart_and_archive(env,tmp_path):
    e=env;u=e.ss[0];sid=e.start(u);original=deepcopy(e.raw(u));e.actor(u)
    e.quiz.act(u,e.quiz.snapshot(u)['revision'],event('open',level=1,topic=0))
    s=e.raw(u)['function_quiz'];e.quiz.act(u,e.quiz.snapshot(u)['revision'],answer_event(s))
    combined=e.raw(u);assert combined['sessions']==original['sessions'] and combined['active_id']==sid
    assert combined['earned']==original['earned']  # New points never mint old-game wallet coins.
    row=e.b.read('game_profiles')[0]
    crypto=ArchiveCrypto(Fernet.generate_key().decode())
    entries,envelope=table_bundle(crypto,'game_profiles',u['id'],[row],{'game_profiles':[row]},lambda _:None)
    assert entries and envelope
    # Disk reload follows the same LocalBackend path, without copying in-memory rows.
    reloaded=e.db.LocalBackend(e.b.root)
    assert json.loads(reloaded.read('game_profiles')[0]['state_json'])==combined


def test_role_isolation_lock_and_stale_revisions(env):
    e=env;u=e.actor(e.ss[0]);start=event('open',level=1,topic=0)
    rev=e.quiz.snapshot(u)['revision'];e.quiz.act(u,rev,start)
    with pytest.raises(ValueError):e.quiz.act(u,rev,start)
    with pytest.raises(PermissionError):e.quiz.snapshot(u,e.ss[1]['id'])
    with pytest.raises(PermissionError):e.quiz.act(u,0,start,preview=True)
    e.rt.locked=True
    with pytest.raises(PermissionError):e.quiz.act(u,e.quiz.snapshot(u)['revision'],answer_event(e.raw(u)['function_quiz']))
    e.rt.locked=False;e.actor(e.t)
    assert e.quiz.snapshot(e.t,u['id'])['question']
    with pytest.raises(PermissionError):e.quiz.act(e.t,0,start)


def test_teacher_preview_all_levels_does_not_touch_student_store(env):
    e=env;e.actor(e.t)
    before=deepcopy(e.b.read('game_profiles'))
    e.quiz.act(e.t,0,event('open',level=5,topic=5),preview=True)
    assert e.quiz.snapshot(e.t,preview=True)['question']['level']==5
    assert e.b.read('game_profiles')==before
