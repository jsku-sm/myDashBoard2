"""Teacher-owned immutable quiz sets, code entry, and isolated student attempts."""
from copy import deepcopy
import hashlib
import json
import re
import secrets
import uuid

import streamlit as st
import storage as db
from config import CLASSES
from game_core import service as games
from record_core.archive import EXPECTED_REPO
from . import api, service


def _store(b):
    if getattr(b, 'is_local', True) or str(getattr(b, 'repo', '')).casefold() != EXPECTED_REPO.casefold():
        raise ValueError('퀴즈 배포와 학생 기록은 jsku-sm/class-dashboard-data 연결이 필요합니다. [QUIZ_STORAGE]')


def _actor(user, b, role=None, write=False):
    actor = games._actor(user, b, role=role, write=write)
    _store(b)
    return actor


def normalize_code(code):
    code = str(code).strip()
    if not re.fullmatch(r'[0-9]{6}', code): raise ValueError('숫자 6자리 참여코드를 입력해 주세요.')
    return code


def _room(b, code):
    code = normalize_code(code)
    row = next((r for r in b.read('quizpop_rooms') if r['code'] == code), None)
    if row is None: raise ValueError('퀴즈를 찾을 수 없어요. 선생님 화면의 참여코드를 확인해 주세요.')
    return deepcopy(row)


def _owner(actor, room):
    if actor['role'] != 'teacher' or room['owner_id'] != actor['id']:
        raise PermissionError('이 퀴즈를 만든 교사만 관리할 수 있습니다.')


def _target(actor, room):
    if not any(t['id'] == actor['id'] and t['class'] == actor.get('class') for t in json.loads(room['targets_json'])):
        raise PermissionError('선생님이 참여 대상으로 지정한 학급의 학생만 입장할 수 있어요.')


def _active(room):
    if room['status'] != 'open': raise ValueError('선생님이 참여를 종료한 퀴즈입니다. 다른 참여코드를 입력해 주세요.')


def _attempt(b, room, actor):
    row = next((r for r in b.read('quizpop_attempts') if r['room_id'] == room['id'] and r['student_id'] == actor['id']), None)
    if row is None: raise PermissionError('먼저 참여코드를 입력해 퀴즈에 입장해 주세요.')
    return deepcopy(row)


def code_kind(user, code):
    """Resolve the shared six-digit entry without exposing another student's data."""
    code = normalize_code(code)
    b = db._ready_backend()
    with b.lock:
        _actor(user, b, 'student', write=True)
        if any(r['code'] == code for r in b.read('quizpop_rooms')): return 'quiz'
        if any(r['code'] == code for r in b.read('review_rooms')): return 'review'
        if any(r['code'] == code for r in b.read('reward_rooms')): return 'reward'
    raise ValueError('참여코드를 찾을 수 없어요. 숫자 6자리를 확인해 주세요.')


def publish(user, title, classes):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'teacher', write=True)
        if not isinstance(classes, list) or not classes or any(c not in CLASSES for c in classes):
            raise ValueError('참여할 학급을 선택해 주세요.')
        title = api.text(title, 160)
        state = st.session_state.get('_quizpop_preview_'+actor['id'], {})
        saved = service.validate_saved(state.get('saved'))
        session = saved['session']
        if not session or not session.get('questions'): raise ValueError('먼저 퀴즈를 생성해 문항을 확인해 주세요.')
        targets = [{k:u.get(k,'') for k in ('id','name','class')} for u in b.read('users')
                   if u['role'] == 'student' and u.get('class') in classes]
        if not targets: raise ValueError('선택한 학급에 등록된 학생이 없습니다.')
        settings = dict(session['settings'], startStage=session['stage'])
        fingerprint = hashlib.sha256(games._json([actor['id'],title,targets,session['runId'],settings,session['questions']]).encode()).hexdigest()
        existing = next((r for r in b.read('quizpop_rooms') if r['publish_key'] == fingerprint and r['status'] == 'open'), None)
        if existing:
            code = existing['code']
        else:
            occupied = {r['code'] for t in ('quizpop_rooms','review_rooms','reward_rooms') for r in b.read(t)}
            for _ in range(100):
                code = str(secrets.randbelow(900000)+100000)
                if code not in occupied: break
            else: raise ValueError('참여코드를 만들지 못했어요. 다시 시도해 주세요.')
            row = dict(id=uuid.uuid4().hex,owner_id=actor['id'],code=code,title=title,stage=str(session['stage']),
                       settings_json=games._json(settings),questions_json=games._json(session['questions']),
                       targets_json=games._json(targets),status='open',publish_key=fingerprint,
                       created_at=db.now_str(),updated_at=db.now_str())
            games._put(b,'quizpop_rooms',row)
    # A repeated publish retries the same room after a storage failure; it does
    # not mint another code or silently replace a quiz students already joined.
    flush(user, code)
    return code


def publish_current(user, *, retry=False):
    """Publish each saved teacher paper once; practice answers never mint codes.

    Saving a draft and publishing are separate outcomes: a failed GitHub write
    must not make the browser resend an already accepted draft revision.
    """
    service.authorize(user, role='teacher', write=True)
    saved = service.snapshot(user).get('saved')
    session = saved.get('session') if saved else None
    key = '_quizpop_publication_'+user['id']
    if not session or not session.get('questions'):
        st.session_state.pop(key, None)
        return None
    signature = hashlib.sha256(games._json([session['runId'],session['stage'],session['settings'],session['questions']]).encode()).hexdigest()
    previous = st.session_state.get(key, {})
    if previous.get('signature') == signature:
        if previous.get('status') == 'ready':
            b=db._ready_backend()
            with b.lock:
                if _room(b,previous['code'])['status'] != 'open':
                    previous=dict(previous,status='closed')
                    st.session_state[key]=previous
        if previous.get('status') in ('ready','closed') or not retry:
            return deepcopy(previous)
    classes = list(st.session_state.get('_quizpop_publish_classes', CLASSES))
    result = dict(signature=signature,runId=session['runId'],stage=session['stage'],title=session['title'],
                  count=len(session['questions']),classes=classes,status='pending',code='',error='')
    st.session_state[key] = result
    try:
        code = publish(user,session['title'],classes)
        result.update(status='ready',code=code)
    except (ValueError,PermissionError) as error:
        result.update(status='error',error=str(error))
    except Exception:
        result.update(status='error',error='문항은 준비됐지만 참여코드를 저장하지 못했어요. 저장소 연결을 확인하고 다시 시도해 주세요. [QUIZ_PUBLISH]')
    st.session_state[key] = result
    return deepcopy(result)


def join(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'student', write=True)
        room = _room(b, code); _active(room); _target(actor, room)
        existing = next((r for r in b.read('quizpop_attempts') if r['room_id'] == room['id'] and r['student_id'] == actor['id']), None)
        if existing: return room['code']
        aid = hashlib.sha256((room['id']+':'+actor['id']).encode()).hexdigest()
        questions = json.loads(room['questions_json'])
        session = dict(runId=aid,settings=json.loads(room['settings_json']),mode='ai',stage=int(room['stage']),
                       title=room['title'],questions=questions,questionIndex=0,
                       progress=[dict(attempts=[],solved=False,hintsUsed=0) for _ in questions],
                       history=[],threads=[[] for _ in questions],previous=[q['prompt'] for q in questions])
        saved = service.validate_saved(dict(session=session,showingSummary=False))
        games._put(b,'quizpop_attempts',dict(id=aid,room_id=room['id'],student_id=actor['id'],name=actor['name'],
                   **{'class':actor['class']},state_json=games._json(saved),revision='0',joined_at=db.now_str(),updated_at=db.now_str()))
        return room['code']


def snapshot(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'student', write=True)
        room = _room(b, code); _target(actor, room); row = _attempt(b, room, actor)
        return dict(userId=actor['id'],preview=False,role='student',revision=int(row['revision']),
                    saved=json.loads(row['state_json']),assignment=dict(code=room['code'],title=room['title'],closed=room['status']!='open'))


def save(user, code, value, revision):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'student', write=True)
        room = _room(b, code); _active(room); _target(actor, room); row = _attempt(b, room, actor)
        if type(revision) is not int or revision != int(row['revision']):
            raise ValueError('다른 창에서 풀이가 변경되었어요. 새로고침해 최신 기록을 열어 주세요.')
        saved = service.validate_saved(value); previous = json.loads(row['state_json'])
        s, old = saved['session'], previous['session']
        if not s or any(s[k] != old[k] for k in ('runId','settings','mode','stage','title','questions','history','previous')):
            raise PermissionError('교사가 배포한 문항과 학습 설정은 학생이 바꿀 수 없습니다.')
        for question, current, before in zip(s['questions'], s['progress'], old['progress']):
            correct=question['correctIndex']
            if correct in current['attempts'] and current['attempts'][-1] != correct:
                raise ValueError('정답을 맞힌 뒤의 추가 답안은 저장할 수 없습니다.')
            if current['hintsUsed'] < min(3,sum(a != correct for a in current['attempts'])):
                raise ValueError('오답 힌트 기록을 확인해 주세요.')
            if current['attempts'][:len(before['attempts'])] != before['attempts'] or current['hintsUsed'] < before['hintsUsed']:
                raise ValueError('이미 저장한 답안과 힌트 기록은 되돌릴 수 없어요. 새로고침해 주세요.')
            if before['solved'] and current['attempts'] != before['attempts']:
                raise ValueError('완료한 문항의 답안을 다시 변경할 수 없습니다.')
        if saved['showingSummary'] and not all(p['solved'] for p in s['progress']):
            raise ValueError('모든 문항을 푼 뒤 결과를 확인해 주세요.')
        row.update(state_json=games._json(saved),revision=str(revision+1),updated_at=db.now_str())
        games._put(b,'quizpop_attempts',row)
        return {'revision':revision+1}


def guide_payload(user, code, payload):
    """Student guidance is limited to an assigned question, never new generation."""
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'student', write=True)
        room = _room(b, code); _active(room); _target(actor, room); _attempt(b, room, actor)
        if not isinstance(payload, dict) or not isinstance(payload.get('context'), dict): raise ValueError('질문 내용을 확인해 주세요.')
        question = next((q for q in json.loads(room['questions_json']) if q['prompt'] == payload['context'].get('question')), None)
        if question is None: raise PermissionError('참여한 퀴즈의 문항만 질문할 수 있어요.')
        settings = json.loads(room['settings_json'])
        context = {k:settings[k] for k in ('unit','range','standards')}
        context.update(question=question['prompt'],concept=question['concept'],visual=question['visual'])
        return dict(context=context,history=payload.get('history',[]),text=payload.get('text'))


def history(user):
    b = db._ready_backend()
    with b.lock:
        actor = games._actor(user, b, role='teacher')
        return sorted([{k:r[k] for k in ('code','title','status','created_at','stage')} for r in b.read('quizpop_rooms')
                       if r['owner_id'] == actor['id']],key=lambda r:r['created_at'],reverse=True)


def report(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user,b,'teacher'); room = _room(b,code); _owner(actor,room)
        rows = {a['student_id']:a for a in b.read('quizpop_attempts') if a['room_id'] == room['id']}
        count = len(json.loads(room['questions_json'])); results=[]
        for target in json.loads(room['targets_json']):
            attempt = rows.get(target['id']); progress = json.loads(attempt['state_json'])['session']['progress'] if attempt else []
            solved = sum(p['solved'] for p in progress)
            results.append({'학번':target['id'],'이름':target['name'],'학급':target['class'],
                            '상태':'완료' if solved==count else '풀이 중' if attempt else '미참여',
                            '완료 문항':solved,'첫 시도 정답':sum(p['solved'] and len(p['attempts'])==1 for p in progress),
                            '힌트 사용':sum(p['hintsUsed'] for p in progress)})
        return dict(code=room['code'],title=room['title'],status=room['status'],stage=int(room['stage']),count=count,
                    joined=len(rows),completed=sum(r['상태']=='완료' for r in results),results=results)


def teacher_paper(user, code):
    """Read the exact published paper, including closed quizzes, for its owner."""
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, 'teacher')
        room = _room(b, code)
        _owner(actor, room)
        return dict(code=room['code'], title=room['title'], stage=int(room['stage']),
                    settings=json.loads(room['settings_json']),
                    questions=json.loads(room['questions_json']))


def close(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user,b,'teacher',write=True); room = _room(b,code); _owner(actor,room)
        room.update(status='closed',updated_at=db.now_str()); games._put(b,'quizpop_rooms',room)
    key='_quizpop_publication_'+user['id']
    current=st.session_state.get(key,{})
    if current.get('code') == code:
        st.session_state[key]=dict(current,status='closed')
    flush(user,code)


def save_status(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user,b); room = _room(b,code)
        if actor['role']=='teacher':
            _owner(actor,room)
            attempts=[r for r in b.read('quizpop_attempts') if r['room_id']==room['id']]
        else:
            _target(actor,room);attempts=[_attempt(b,room,actor)]
        paths=[db.GitHubBackend._path('quizpop_rooms',room)]+[db.GitHubBackend._path('quizpop_attempts',r) for r in attempts]
        pending=any(p in getattr(b,'dirty',{}) for p in paths)
        pending=pending or any(('quizpop_attempts',r['student_id']) in getattr(b,'archive_dirty',{}) for r in attempts)
        return dict(pending=pending,error=bool(getattr(b,'last_error','')))


def flush(user, code):
    save_status(user,code)
    try: db.flush_now()
    except Exception: raise ValueError('GitHub 저장 확인이 필요합니다. 화면을 유지하고 저장 확인을 다시 눌러 주세요.') from None
    if save_status(user,code)['pending']: raise ValueError('GitHub 저장 대기 중입니다. 잠시 뒤 다시 확인해 주세요.')
