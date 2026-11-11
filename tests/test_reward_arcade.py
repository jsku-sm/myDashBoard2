"""Offline classroom, permissions, persistence, scoring and replay regressions."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import subprocess
import types
import uuid
import pytest
from test_game_learning import game_env
from test_concept_quiz import load
from test_student_record_vault import gh
from game_core.concept_quiz_catalog import UNITS, unit_info
from reward_core import questions, simulation as sim
from reward_core.catalog import GAMES, DIFFICULTIES

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def env(game_env):
    e=game_env
    e.reward=load('reward_core.service',ROOT/'reward_core/service.py',e.monkeypatch)
    import reward_core
    e.monkeypatch.setattr(reward_core,'service',e.reward,raising=False)
    e.clock=[1000.0];e.monkeypatch.setattr(e.reward,'time',types.SimpleNamespace(time=lambda:e.clock[0]))
    e.paper=questions.build('geometry',['move.translation','move.reflection'],'easy',12)
    def create(mode='rank',game='jump',duration=600):
        return e.reward.create(e.actor(e.t),unit='geometry',topics=['move.translation','move.reflection'],difficulty='easy',
                              paper=e.paper,game=game,mode=mode,classes=['1-1'],duration=duration)
    e.create_reward=create
    def begin(mode='rank',game='jump',n=1,duration=600):
        code=create(mode,game,duration)
        for u in e.ss[:n]:e.reward.join(e.actor(u),code)
        e.reward.control(e.actor(e.t),code,'start');return code
    e.begin_reward=begin
    def action(code,kind,u=None,**kw):
        u=e.actor(u or e.ss[0]);v=e.reward.snapshot(u,code)
        event=dict(id=uuid.uuid4().hex,action=kind,index=v['index'],turn=v['turn'],**kw)
        e.reward.act(u,code,event);return event
    e.ra=action
    def solve(code,n=3,u=None,hint=False):
        u=u or e.ss[0]
        for _ in range(n):
            e.actor(u);v=e.reward.snapshot(u,code)
            if hint:action(code,'hint',u)
            action(code,'answer',u,choice=e.paper[v['index']]['answer'])
            action(code,'next',u)
    e.solve=solve
    def run(code,game='jump',u=None,seconds=90,keys=None):
        u=u or e.ss[0];action(code,'play',u,game=game)
        v=e.reward.snapshot(u,code);run=v['run'];e.clock[0]=run['start']+seconds
        action(code,'progress',u,run=run['id'],start=0,inputs=keys or [0]*int(seconds*20),final=True)
    e.run_reward=run
    return e


@pytest.mark.parametrize('unit',UNITS)
@pytest.mark.parametrize('difficulty',DIFFICULTIES)
def test_scoped_unique_questions_for_each_topic(unit,difficulty):
    for t in unit_info(unit)['topics']:
        p=questions.build(unit,[t['id']],difficulty,333)
        assert len(p)>=3 and {q['topic_id'] for q in p}=={t['id']}
        assert len({q['prompt'] for q in p})==len(p)
        assert questions.validate(p,unit,[t['id']])==p
        assert p==questions.build(unit,[t['id']],difficulty,333)


def test_hint_wrong_retry_three_distinct_and_no_duplicate_award(env):
    e=env;code=e.begin_reward();u=e.actor(e.ss[0])
    e.ra(code,'hint');wrong=(e.paper[0]['answer']+1)%len(e.paper[0]['options'])
    event=e.ra(code,'answer',choice=wrong);e.reward.act(u,code,event)
    assert e.reward.snapshot(u,code)['wrong']==1
    e.solve(code,hint=True)
    v=e.reward.snapshot(u,code);assert v['ticket'] and v['correct']==3 and v['hints']==3 and v['index']==3
    e.run_reward(code)
    v=e.reward.snapshot(u,code);assert not v['run'] and not v['ticket'] and v['question'] and len(v['runs'])==1
    earned=v['runs'][0]['coins'];assert v['coins']==earned
    e.reward.snapshot(u,code);assert e.reward.snapshot(u,code)['coins']==earned


@pytest.mark.parametrize('game',GAMES)
def test_full_game_uses_server_replay_and_persists(env,game):
    e=env;code=e.begin_reward(game=game);e.solve(code)
    e.ra(code,'play',game=game);u=e.ss[0];v=e.reward.snapshot(u,code);run=v['run'];inputs=[(i//20)%5 for i in range(1800)]
    # A forged score field is ignored; replay alone determines points.
    e.clock[0]+=30
    ev=e.ra(code,'progress',run=run['id'],start=0,inputs=inputs[:600],score=9999999)
    e.reward.act(u,code,ev)
    expected=sim.replay(deepcopy(run['sim']),inputs[:600]);assert e.reward.snapshot(u,code)['run']['sim']==expected
    # Overlapping retransmission skips only the already committed prefix.
    e.clock[0]+=60
    e.ra(code,'progress',run=run['id'],start=300,inputs=inputs[300:],final=True)
    v=e.reward.snapshot(u,code);r=v['runs'][0];expected=sim.replay(expected,inputs[600:])
    assert r['score']==expected['score'] and r['ranked'] and r['ticks']==1800
    disk=e.db.LocalBackend(e.b.root)
    assert json.loads(disk.read('reward_attempts')[0]['state_json'])['runs'][0]==r
    assert json.loads(disk.read('game_profiles')[0]['state_json'])['earned']==r['coins']


def test_server_time_locks_budget_and_no_game_time_banking(env):
    e=env;code=e.begin_reward();u=e.actor(e.ss[0])
    with pytest.raises(ValueError):e.ra(code,'play',game='jump')
    e.solve(code);e.ra(code,'play',game='jump');r=e.reward.snapshot(u,code)['run']
    with pytest.raises(ValueError):e.ra(code,'progress',run=r['id'],start=0,inputs=[0]*1800,final=True)
    with pytest.raises(ValueError):e.ra(code,'answer',choice=0)
    e.ra(code,'play',game='maze');assert e.reward.snapshot(u,code)['run']['until']==r['until']
    e.clock[0]+=90
    e.ra(code,'progress',run=r['id'],start=0,inputs=[0]*1800,final=True)
    with pytest.raises(ValueError):e.ra(code,'play',game='jump')


def test_short_final_round_rewards_but_not_ranked(env):
    e=env;code=e.begin_reward(duration=300);e.solve(code);e.clock[0]=1280
    e.ra(code,'play',game='jump');v=e.reward.snapshot(e.ss[0],code);r=v['run'];assert r['until']==1300
    e.clock[0]=1300;e.ra(code,'progress',run=r['id'],start=0,inputs=[0]*400,final=True)
    v=e.reward.snapshot(e.ss[0],code)
    assert v['status']=='ended' and v['runs'][0]['coins']>=2 and not v['runs'][0]['ranked'] and not v['leaderboard']


def test_teacher_early_stop_and_disconnect_settle_once(env):
    e=env;code=e.begin_reward();e.solve(code);e.ra(code,'play',game='jump')
    r=e.reward.snapshot(e.ss[0],code)['run'];e.clock[0]+=10
    e.ra(code,'progress',run=r['id'],start=0,inputs=[4 if i%20==0 else 0 for i in range(200)])
    e.reward.control(e.actor(e.t),code,'end');e.clock[0]+=13
    v=e.reward.snapshot(e.actor(e.ss[0]),code);assert not v['run'] and len(v['runs'])==1 and not v['runs'][0]['ranked']
    coins=v['coins'];e.reward.snapshot(e.ss[0],code);assert e.reward.snapshot(e.ss[0],code)['coins']==coins


def test_permissions_keys_scope_and_code_routing(env):
    e=env;code=e.create_reward()
    with pytest.raises(PermissionError):e.reward.join(e.actor(e.ss[2]),code)
    with pytest.raises(PermissionError):e.reward.control(e.actor(e.other),code,'start')
    with pytest.raises(PermissionError):e.reward.prepare(e.actor(e.ss[0]),'geometry',['move.translation'],'easy')
    with pytest.raises(PermissionError):e.reward.paper(e.ss[0],code)
    e.reward.join(e.ss[0],code);e.reward.control(e.actor(e.t),code,'start')
    v=e.reward.snapshot(e.actor(e.ss[0]),code)
    text=json.dumps(v,ensure_ascii=False)
    assert 'answer' not in v['question'] and 'explanation' not in v['question']
    assert 'students' not in v and 'targets_json' not in text and e.ss[1]['name'] not in text
    assert e.db.read('reward_rooms')==[] and e.db.read('reward_attempts')==[]
    with pytest.raises(PermissionError):e.db.append('reward_attempts',{})
    with pytest.raises(PermissionError):e.reward.csv_export(e.ss[0],code)
    e.rt.locked=True
    with pytest.raises(PermissionError):e.ra(code,'hint')
    e.rt.locked=False


def test_solo_can_select_five_rank_cannot_change_game(env):
    e=env;code=e.begin_reward(mode='solo');e.solve(code);e.ra(code,'play',game='maze')
    assert e.reward.snapshot(e.ss[0],code)['run']['game']=='maze'
    code=e.begin_reward(mode='rank');e.solve(code);e.ra(code,'play',game='maze')
    assert e.reward.snapshot(e.ss[0],code)['run']['game']=='jump'


def test_same_seed_tied_ranks_and_coop_reward(env):
    e=env;code=e.begin_reward(mode='rank',game='kart',n=2)
    for u in e.ss[:2]:e.solve(code,u=u);e.run_reward(code,game='kart',u=u)
    v=e.reward.snapshot(e.actor(e.t),code)
    assert [r['rank'] for r in v['leaderboard']]==[1,1]
    # Cooperative target freezes at start, aggregates earned points, and awards once.
    code=e.begin_reward(mode='coop',game='kart',n=2,duration=600)
    for u in e.ss[:2]:e.solve(code,u=u);e.run_reward(code,game='kart',u=u)
    with e.b.lock:
        r=e.reward.room(e.b,code);r['goal']='1';e.reward.put(e.b,'reward_rooms',r)
    before={u['id']:e.reward.snapshot(e.actor(u),code)['coins'] for u in e.ss[:2]}
    e.reward.control(e.actor(e.t),code,'end');e.clock[0]+=13
    for u in e.ss[:2]:
        v=e.reward.snapshot(e.actor(u),code);assert v['coins']==before[u['id']]+5 and 'coop' in v['badges']
        assert e.reward.snapshot(u,code)['coins']==v['coins']


def test_25_students_concurrent_no_cross_identity_or_duplicate_join(env):
    e=env
    users=[dict(e.ss[0],id=f'student-{i}',name=f'검증학생{i}') for i in range(25)]
    for u in users:e.b.append('users',u)
    code=e.create_reward()
    def join(u):
        e.actor(u);e.reward.join(u,code);e.reward.join(u,code)
    with ThreadPoolExecutor(max_workers=25) as pool:list(pool.map(join,users))
    rows=e.b.read('reward_attempts');assert len(rows)==25 and len({a['alias'] for a in rows})==25
    e.reward.control(e.actor(e.t),code,'start')
    def solve(u):e.solve(code,u=u,hint=True)
    with ThreadPoolExecutor(max_workers=25) as pool:list(pool.map(solve,users))
    v=e.reward.snapshot(e.actor(e.t),code);assert sum(s['correct'] for s in v['students'])==75
    assert all(json.loads(r['state_json'])['ticket'] for r in e.b.read('reward_attempts'))


def test_existing_avatar_progress_survives_and_rewards_once_after_retry(env):
    e=env;sid=e.start();before=deepcopy(e.raw());code=e.begin_reward();e.solve(code);e.run_reward(code)
    p=e.raw();assert p['active_id']==sid and p['sessions']==before['sessions'] and p['owned']==before['owned']
    assert p['earned']>before['earned'];assert len(p['reward_arcade']['awards'])==1


def test_python_and_browser_simulation_agree_for_all_games():
    cases=[];expected=[]
    for gid in GAMES:
        for seed in (0,1,42,4294967295):
            rng=random.Random(seed);inputs=[rng.randrange(16) for _ in range(1800)];s=sim.initial(gid,seed)
            snapshots=[]
            for i,k in enumerate(inputs):
                sim.step(s,k)
                if (i+1)%100==0:snapshots.append(deepcopy(s))
            cases.append(dict(gid=gid,seed=seed,inputs=inputs));expected.append(snapshots)
    js="import{initial,step}from './reward_core/source/src/simulation.js';let raw='';for await(const b of process.stdin)raw+=b;const out=JSON.parse(raw).map(({gid,seed,inputs})=>{const s=initial(gid,seed),out=[];inputs.forEach((k,i)=>{step(s,k);if((i+1)%100===0)out.push(structuredClone(s));});return out;});process.stdout.write(JSON.stringify(out));"
    p=subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(cases),text=True,capture_output=True,cwd=ROOT,check=True)
    assert json.loads(p.stdout)==expected


def test_deployment_assets_and_storage_partition_contract(env):
    import re
    for asset in re.findall(r'(?:src|href)="([^"]+)"',(ROOT/'reward_core/frontend/index.html').read_text()):assert (ROOT/'reward_core/frontend'/asset).is_file()
    e=env;r1={'id':'one'};r2={'id':'two'}
    assert e.db.GitHubBackend._path('reward_rooms',r1)!=e.db.GitHubBackend._path('reward_rooms',r2)
    assert e.db.GitHubBackend._path('reward_attempts',{'student_id':'s1'})!=e.db.GitHubBackend._path('reward_attempts',{'student_id':'s2'})
    from record_core.archive import TABLE_CATEGORIES,EXPECTED_REPO
    assert TABLE_CATEGORIES['reward_attempts']=='games' and EXPECTED_REPO=='jsku-sm/class-dashboard-data'


def test_github_atomic_commit_retry_and_private_student_archive(gh):
    b=gh.b
    b.append('reward_rooms',dict(id='room',owner_id='teacher',code='123456',title='단원 마무리',status='running',
        questions_json='[]',targets_json='[{"id":"private-peer"}]'))
    b.append('reward_attempts',dict(id='attempt',room_id='room',student_id='10101',state_json='{"runs":[]}'))
    gh.control['deny']=True
    with pytest.raises(RuntimeError):b.flush()
    assert b.dirty and b.archive_dirty
    gh.control['deny']=False;b.flush()
    assert not b.dirty and not b.archive_dirty
    assert any(p.startswith('data/reward_rooms/') for p in gh.remote)
    assert any(p.startswith('data/reward_attempts/') for p in gh.remote)
    path=next(p for p in gh.remote if '/games/' in p and p.endswith('/current.json.enc'))
    payload=b.archive_crypto.open_bundle(gh.remote[path],'10101',path)['payload']
    assert payload['table']=='reward_attempts' and payload['reward_rooms'][0]['code']=='123456'
    assert 'private-peer' not in json.dumps(payload)
    b.update('reward_rooms','room',{'status':'ended'})
    assert ('reward_attempts','10101') in b.archive_dirty
    b.flush()
    assert b.archive_crypto.open_bundle(gh.remote[path],'10101',path)['payload']['reward_rooms'][0]['status']=='ended'
