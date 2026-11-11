"""Room ownership, server-graded questions, timed tickets and replayed scores.

Uses the existing single Streamlit server and batched GitHub backend. Browsers
never access GitHub, answer keys, another student's identity, or raw tables.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
import secrets
import time
import uuid
import streamlit as st
import storage as db
from config import CLASSES
from game_core import service as profiles, engine as avatar
from game_core.concept_quiz_catalog import unit_info
from . import questions, simulation as sim
from .catalog import GAMES, MODES, DIFFICULTIES

GRACE = 12


def dump(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def actor(user, b, role=None, write=False): return profiles._actor(user, b, role, write=write)
def put(b, table, row): profiles._put(b, table, row)


def room(b, code):
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ValueError('6자리 참여코드를 입력해 주세요.')
    r = next((deepcopy(r) for r in b.read('reward_rooms') if r['code'] == code), None)
    if not r: raise ValueError('참여코드를 찾을 수 없어요.')
    return r


def access(u, r, owner=False):
    if u['role'] == 'teacher':
        if u['id'] != r['owner_id']: raise PermissionError('이 게임을 만든 교사만 관리할 수 있습니다.')
    elif owner or not any(t['id'] == u['id'] and t['class'] == u.get('class') for t in json.loads(r['targets_json'])):
        raise PermissionError('선생님이 지정한 반의 학생만 참여할 수 있습니다.')


def attempts(b, r):
    rows = [deepcopy(a) for a in b.read('reward_attempts') if a['room_id'] == r['id']]
    for a in rows: a['state'] = json.loads(a['state_json'])
    return rows


def save(b, a):
    a.update(state_json=dump(a['state']), revision=str(int(a['revision'])+1), updated_at=db.now_str())
    put(b, 'reward_attempts', a)


def prepare(user, unit, topics, difficulty):
    b = db._ready_backend()
    with b.lock: actor(user, b, 'teacher')
    return questions.build(unit, topics, difficulty, secrets.randbits(32))


def create(user, *, unit, topics, difficulty, paper, game, mode, classes, duration):
    info = unit_info(unit)
    checked = questions.validate(paper, unit, topics)
    if game not in GAMES or mode not in MODES or difficulty not in DIFFICULTIES or type(duration) is not int or duration not in (300, 600):
        raise ValueError('게임·참여 방식·활동 시간을 확인해 주세요.')
    if not isinstance(classes, list) or not classes or any(c not in CLASSES for c in classes): raise ValueError('참여할 반을 선택해 주세요.')
    b = db._ready_backend()
    with b.lock:
        u = actor(user, b, 'teacher')
        targets = [{k: a.get(k, '') for k in ('id','name','class')} for a in b.read('users') if a['role'] == 'student' and a.get('class') in classes]
        if not targets: raise ValueError('선택한 반에 등록된 학생이 없습니다.')
        codes = {r['code'] for table in ('quizpop_rooms','review_rooms','reward_rooms') for r in b.read(table)}
        for _ in range(100):
            code = str(secrets.randbelow(900000)+100000)
            if code not in codes: break
        else: raise ValueError('참여코드를 만들지 못했어요. 다시 시도해 주세요.')
        r = dict(id=uuid.uuid4().hex, owner_id=u['id'], code=code, title=info['subject']+' · '+info['title'], unit=unit,
                 topics_json=dump(topics), difficulty=difficulty, game=game, mode=mode, targets_json=dump(targets),
                 questions_json=dump(checked), status='lobby', duration=str(duration), seed=str(secrets.randbits(32)), goal='0',
                 created_at=db.now_str(), started_at='', ended_at='')
        put(b, 'reward_rooms', r)
    return code


def history(user):
    b = db._ready_backend()
    with b.lock:
        u = actor(user, b, 'teacher')
        return sorted([{k:r[k] for k in ('code','title','status','game','mode','created_at')} for r in b.read('reward_rooms') if r['owner_id'] == u['id']], key=lambda r:r['created_at'], reverse=True)


def paper(user, code):
    b = db._ready_backend()
    with b.lock:
        r = room(b, code); access(actor(user, b, 'teacher'), r)
        return json.loads(r['questions_json'])


def join(user, code):
    b = db._ready_backend()
    with b.lock:
        u = actor(user, b, 'student', write=True); r = room(b, code); access(u, r)
        settle(b, r)
        existing = next((a for a in attempts(b, r) if a['student_id'] == u['id']), None)
        if existing: return existing['id']
        if r['status'] not in ('lobby', 'running'): raise ValueError('종료된 게임입니다. 새 참여코드를 입력해 주세요.')
        a = dict(id=hashlib.sha256((r['id']+':'+u['id']).encode()).hexdigest(), room_id=r['id'], student_id=u['id'],
                 name=u['name'], **{'class':u.get('class','')}, alias=f"플레이어 {len(attempts(b,r))+1:02}", revision='0',
                 joined_at=db.now_str(), updated_at=db.now_str(), state_json=dump(dict(index=0, turn=0, correct=0, wrong=0,
                 hinted=False, hints=0, ticket=False, feedback=None, answers=[], runs=[], run=None, events=[])))
        put(b, 'reward_attempts', a)
        return a['id']


def credit(b, a, key, amount, badge=''):
    """A profile ledger makes interrupted two-row saves recoverable and idempotent."""
    u = dict(id=a['student_id'], name=a['name'], **{'class':a['class']})
    row = profiles._row(b, u); p = json.loads(row['state_json'])
    rewards = p.setdefault('reward_arcade', dict(awards={}, badges=[]))
    if key in rewards['awards']: return
    rewards['awards'][key] = amount; p['earned'] += amount
    if badge and badge not in rewards['badges']: rewards['badges'].append(badge)
    row.update(state_json=dump(p), revision=str(int(row['revision'])+1), updated_at=db.now_str())
    put(b, 'game_profiles', row)


def finish_run(b, r, a):
    s = a['state']; run = s['run']
    if not run: return
    state = run['sim']; coins = 2+min(20, state['score']//50)
    badge = run['game'] if state['score'] >= GAMES[run['game']]['medal'] else ''
    credit(b, a, run['id'], coins, badge)
    record = dict(id=run['id'], game=run['game'], score=state['score'], hits=state['hits'], combo=state['best_combo'],
                  coins=coins, badge=badge, seconds=round(run['until']-run['start'],2),
                  ranked=run['until']-run['start'] >= 89.99, ticks=state['t'], at=db.now_str())
    s['runs'].append(record); s['run'] = None; save(b, a)


def settle(b, r):
    now = time.time()
    if r['status'] == 'running' and now >= float(r['started_at'])+int(r['duration']):
        r.update(status='ended', ended_at=str(float(r['started_at'])+int(r['duration'])))
        put(b, 'reward_rooms', r)
    rows = attempts(b, r)
    for a in rows:
        run = a['state']['run']
        if run:
            if r['status'] == 'ended' and run['until'] > float(r['ended_at']):
                run['until'] = float(r['ended_at']); save(b,a)
            if now >= run['until']+GRACE: finish_run(b,r,a)
    if r['mode'] == 'coop' and int(r['goal']) and r['status'] == 'ended':
        rows = attempts(b, r)
        total = sum(sum(x['score'] for x in a['state']['runs']) for a in rows)
        if not any(a['state']['run'] for a in rows) and total >= int(r['goal']):
            for a in rows: credit(b,a,'coop:'+r['id'],5,'coop')


def control(user, code, action):
    b = db._ready_backend()
    with b.lock:
        r = room(b,code); access(actor(user,b,'teacher'),r); settle(b,r)
        if action == 'start' and r['status'] == 'lobby':
            n = len(attempts(b,r))
            if not n: raise ValueError('학생이 한 명 이상 입장하면 시작할 수 있어요.')
            r.update(status='running', started_at=str(time.time()), goal=str(n*GAMES[r['game']]['medal']))
            put(b,'reward_rooms',r)
        elif action == 'end' and r['status'] != 'ended':
            r.update(status='ended',ended_at=str(time.time())); put(b,'reward_rooms',r); settle(b,r)
        elif action not in ('start','end'): raise ValueError('지원하지 않는 동작입니다.')


def act(user, code, event):
    if not isinstance(event,dict) or not isinstance(event.get('id'),str) or not 8 <= len(event['id']) <= 100:
        raise ValueError('요청을 확인해 주세요.')
    b = db._ready_backend()
    with b.lock:
        u = actor(user,b,'student',write=True); r = room(b,code); access(u,r); settle(b,r)
        a = next((a for a in attempts(b,r) if a['student_id']==u['id']), None)
        if not a: raise ValueError('먼저 참여코드를 입력해 주세요.')
        s = a['state']; kind = event.get('action'); now = time.time()
        if event['id'] in s['events']: return
        if kind == 'progress':
            run = s['run']
            if not run or run['id'] != event.get('run'): return # acknowledged late duplicate
            start = event.get('start'); data = event.get('inputs')
            if type(start) is not int or start < 0 or not isinstance(data,list) or len(data)>1800:
                raise ValueError('게임 입력을 다시 확인해 주세요.')
            if any(type(k) is not int or not 0 <= k <= 15 for k in data): raise ValueError('지원하지 않는 게임 입력입니다.')
            if start > run['sim']['t']: raise ValueError('아직 저장하지 못한 조작이 있어요. 다시 연결해 주세요.')
            ceiling = min(1800, math.floor(max(0,min(now,run['until'])-run['start'])*sim.HZ))
            if start+len(data) > ceiling: raise ValueError('서버의 게임 시간보다 빠른 기록은 반영할 수 없어요.')
            skip = max(0,run['sim']['t']-start)
            sim.replay(run['sim'],data[skip:])
            if event.get('final') is True and now >= run['until']:
                finish_run(b,r,a)
        else:
            if r['status'] != 'running': raise ValueError('아직 시작하지 않았거나 종료된 활동입니다.')
            if kind == 'play':
                if s['run']: return
                if not s['ticket']: raise ValueError('서로 다른 문제 3개를 맞히면 게임을 할 수 있어요.')
                gid = event.get('game') if r['mode']=='solo' else r['game']
                if gid not in GAMES: raise ValueError('게임을 선택해 주세요.')
                until = min(now+90,float(r['started_at'])+int(r['duration']))
                if until-now < 1: raise ValueError('활동이 끝나고 있어요. 다음 활동에서 도전해 주세요.')
                s['run'] = dict(id=uuid.uuid4().hex, game=gid, start=now, until=until, sim=sim.initial(gid,int(r['seed'])))
                s['ticket']=False; s['feedback']=None
            elif kind in ('answer','hint','next'):
                qs=json.loads(r['questions_json'])
                if s['run'] or s['ticket'] or s['index'] >= len(qs): raise ValueError('현재 화면에서 이어 가세요.')
                if type(event.get('index')) is not int or event['index']!=s['index'] or event.get('turn')!=s['turn']:
                    raise ValueError('문제가 바뀌었어요. 현재 문제에서 다시 선택해 주세요.')
                q=qs[s['index']]
                if kind == 'hint':
                    if not s['hinted']: s['hints']+=1
                    s['hinted']=True
                elif kind == 'next':
                    if not s['feedback'] or not s['feedback']['correct']: raise ValueError('문제를 맞힌 뒤 다음으로 이동해요.')
                    s['index']+=1; s['turn']=0; s['hinted']=False; s['feedback']=None
                    if s['correct']%3==0: s['ticket']=True
                elif s['feedback'] and s['feedback']['correct']:
                    return
                else:
                    choice=event.get('choice')
                    if type(choice) is not int or not 0<=choice<len(q['options']): raise ValueError('보기 하나를 골라 주세요.')
                    correct=choice==q['answer']; s['correct']+=int(correct); s['wrong']+=int(not correct)
                    s['answers'].append(dict(index=s['index'],qid=q['id'],topic=q['topic_id'],choice=choice,correct=correct,hint=s['hinted'],at=db.now_str()))
                    s['feedback']=dict(correct=correct,choice=choice,message=q['explanation'] if correct else '한 번 더 생각해 볼까요? 힌트를 보고 다시 도전해요.')
                    s['turn']+=1
            else: raise ValueError('지원하지 않는 동작입니다.')
        s['events']=(s['events']+[event['id']])[-256:]
        save(b,a)


def ranking(rows):
    ranked=[]
    for a in rows:
        values=[r['score'] for r in a['state']['runs'] if r['ranked']]
        if values: ranked.append(dict(alias=a['alias'],score=max(values)))
    ranked.sort(key=lambda r:-r['score'])
    for i,row in enumerate(ranked): row['rank']=next(j+1 for j,r in enumerate(ranked) if r['score']==row['score'])
    return ranked


def snapshot(user, code):
    b=db._ready_backend()
    with b.lock:
        r=room(b,code); u=actor(user,b); access(u,r); settle(b,r)
        rows=attempts(b,r); now=time.time(); qs=json.loads(r['questions_json'])
        total=sum(sum(x['score'] for x in a['state']['runs'])+(a['state']['run']['sim']['score'] if a['state']['run'] else 0) for a in rows)
        v={k:r[k] for k in ('code','title','status','game','mode')}
        v.update(role=u['role'],server_time=now,ends_at=float(r['started_at'])+int(r['duration']) if r['started_at'] else None,
                 duration=int(r['duration']),participants=len(rows),goal=int(r['goal']),contribution=total,
                 settling=any(a['state']['run'] for a in rows), games=GAMES, modes=MODES,
                 leaderboard=ranking(rows) if r['mode']=='rank' else [], question_count=len(qs))
        if u['role']=='teacher':
            cooperative={p['student_id']:json.loads(p['state_json']).get('reward_arcade',{}).get('awards',{}).get('coop:'+r['id'],0) for p in b.read('game_profiles')}
            v['students']=[dict(name=a['name'],student_id=a['student_id'],class_name=a['class'],alias=a['alias'],
                correct=a['state']['correct'],wrong=a['state']['wrong'],hints=a['state']['hints'],
                games=len(a['state']['runs']),best=max([x['score'] for x in a['state']['runs']] or [0]),
                phase='게임 중' if a['state']['run'] else '게임 입장 대기' if a['state']['ticket'] else '문제 풀이',
                coins=sum(x['coins'] for x in a['state']['runs'])+cooperative.get(a['student_id'],0)) for a in rows]
        else:
            a=next((a for a in rows if a['student_id']==u['id']),None)
            if not a: raise ValueError('먼저 참여코드를 입력해 주세요.')
            s=a['state']; v.update(alias=a['alias'],index=s['index'],turn=s['turn'],correct=s['correct'],wrong=s['wrong'],hints=s['hints'],
                ticket=s['ticket'],run=deepcopy(s['run']),runs=deepcopy(s['runs']),feedback=deepcopy(s['feedback']))
            if s['index']<len(qs) and not s['ticket'] and not s['run'] and r['status']=='running':
                q=qs[s['index']]; v['question']={k:q[k] for k in ('prompt','options','topic_title','standard')}
                v['question']['hint']=q['hint'] if s['hinted'] else None
            p=json.loads(profiles._row(b,u)['state_json'])
            v['coins']=avatar.wallet(p); v['badges']=p.get('reward_arcade',{}).get('badges',[])
            v['personal_best']={g:max([x['score'] for old in b.read('reward_attempts') if old['student_id']==u['id']
                                    for x in json.loads(old['state_json'])['runs'] if x['game']==g and x['ranked']] or [0]) for g in GAMES}
        return v


def save_status(user, code):
    b=db._ready_backend()
    with b.lock:
        r=room(b,code); u=actor(user,b); access(u,r)
        rows=[('reward_rooms',r)]+[('reward_attempts',a) for a in attempts(b,r) if u['role']=='teacher' or a['student_id']==u['id']]
        ids={a['student_id'] for a in attempts(b,r) if u['role']=='teacher' or a['student_id']==u['id']}
        rows += [('game_profiles',p) for p in b.read('game_profiles') if p['student_id'] in ids]
        return dict(local=getattr(b,'is_local',True), pending=any(db.GitHubBackend._path(t,a) in getattr(b,'dirty',{}) for t,a in rows), error=bool(getattr(b,'last_error','')))


def flush(user,code):
    save_status(user,code)
    db.flush_now()
    return save_status(user,code)


def csv_export(user,code):
    b=db._ready_backend()
    with b.lock:
        r=room(b,code); access(actor(user,b,'teacher'),r); settle(b,r)
        out=io.StringIO(); writer=csv.writer(out)
        writer.writerow(['학번','이름','반','주제','문제 번호','선택','정오','힌트','게임','게임 점수','별 조각'])
        def safe(x):
            value=str(x)
            return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
        for a in attempts(b,r):
            base=[safe(a[k]) for k in ('student_id','name','class')]
            for x in a['state']['answers']: writer.writerow(base+[x['topic'],x['index']+1,x['choice']+1,'O' if x['correct'] else 'X','사용' if x['hint'] else '', '', '', ''])
            for x in a['state']['runs']: writer.writerow(base+['','','','','',GAMES[x['game']]['title'],x['score'],x['coins']])
            p=json.loads(profiles._row(b,dict(id=a['student_id'],name=a['name'],**{'class':a['class']}))['state_json'])
            bonus=p.get('reward_arcade',{}).get('awards',{}).get('coop:'+r['id'],0)
            if bonus:writer.writerow(base+['','','','','','학급 협동 목표 달성','',bonus])
        return ('\ufeff'+out.getvalue()).encode('utf-8')
