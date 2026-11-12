"""Teacher preview state and shared validation for published student attempts."""
from copy import deepcopy
import json
import re
import streamlit as st
import storage as db
from game_core import service as games
from record_core.archive import EXPECTED_REPO
from . import api


def _require_student_store(backend, actor):
    if actor['role'] != 'student': return
    if getattr(backend, 'is_local', True):
        raise ValueError('학생 퀴즈는 GitHub 저장 연결이 필요합니다. [app] storage = "github", [github] repo = "jsku-sm/class-dashboard-data" 설정을 확인해 주세요. [QUIZ_STORAGE]')
    if str(getattr(backend, 'repo', '')).strip().casefold() != EXPECTED_REPO.casefold():
        raise ValueError('학생 퀴즈 기록은 jsku-sm/class-dashboard-data에만 저장할 수 있습니다. [github] repo를 확인해 주세요. [QUIZ_STORAGE]')


def storage_info(user):
    backend = db._ready_backend()
    with backend.lock:
        games._actor(user, backend)
        local = getattr(backend, 'is_local', True)
        repo = str(getattr(backend, 'repo', ''))
        return {'ready': not local and repo.casefold() == EXPECTED_REPO.casefold(), 'repo': repo, 'expected': EXPECTED_REPO}


def authorize(user, *, role=None, write=False):
    b = db._ready_backend()
    with b.lock:
        actor = games._actor(user, b, role=role, write=write)
        _require_student_store(b, actor)
        return dict(actor)


def _state(profile):
    return profile.get('quiz_pop', {'revision':0, 'saved':None, 'records':[]})


def snapshot(user):
    b = db._ready_backend()
    with b.lock:
        actor = games._actor(user, b)
        _require_student_store(b, actor)
        if actor['role'] != 'teacher':
            raise PermissionError('학생은 선생님이 알려 준 참여코드로 퀴즈에 입장해 주세요.')
        state = st.session_state.get('_quizpop_preview_'+actor['id'], _state({}))
        return {'userId':actor['id'], 'preview':True, 'role':'teacher', 'revision':state['revision'],
                'saved':deepcopy(state['saved']), 'publication':deepcopy(st.session_state.get('_quizpop_publication_'+actor['id']))}


def validate_saved(value):
    if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False, allow_nan=False)) > 220000:
        raise ValueError('학습 기록의 크기를 확인해 주세요.')
    s = value.get('session')
    if s is None: return {'session':None, 'showingSummary':False}
    if not isinstance(s, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', str(s.get('runId',''))): raise ValueError('학습 회차를 확인해 주세요.')
    s = deepcopy(s)
    s['settings'] = api.settings(s.get('settings'))
    if s.get('mode') not in ('demo','ai') or type(s.get('stage')) is not int or not s['settings']['startStage'] <= s['stage'] <= 4:
        raise ValueError('학습 단계를 확인해 주세요.')
    if not isinstance(s.get('questions'), list): raise ValueError('문항 정보를 확인해 주세요.')
    if not s['questions']: return {'session':None,'showingSummary':False}
    api.validate_schema({'title':s.get('title',''), 'questions':s['questions']}, api.PROMPTS['schemas'][str(s['settings']['count'])])
    n = len(s['questions'])
    if type(s.get('questionIndex')) is not int or not 0 <= s['questionIndex'] < n: raise ValueError('문항 위치를 확인해 주세요.')
    if not isinstance(s.get('progress'),list) or len(s['progress']) != n: raise ValueError('학습 기록을 확인해 주세요.')
    for q, p in zip(s['questions'],s['progress']):
        if not isinstance(p,dict): raise ValueError('학습 기록을 확인해 주세요.')
        attempts=p.get('attempts')
        if not isinstance(attempts,list) or len(attempts)>5 or any(type(i) is not int or not 0<=i<5 for i in attempts) or len(set(attempts))!=len(attempts):
            raise ValueError('답안 기록을 확인해 주세요.')
        if type(p.get('hintsUsed')) is not int or not 0<=p['hintsUsed']<=3: raise ValueError('힌트 기록을 확인해 주세요.')
        p['solved'] = bool(attempts and attempts[-1] == q['correctIndex'])
    if not isinstance(s.get('history'),list) or len(s['history'])>4: raise ValueError('단계 이력을 확인해 주세요.')
    for h in s['history']:
        if not isinstance(h,dict) or any(type(h.get(k)) is not int or not 0<=h[k]<=7 for k in ('solved','firstTry','retried')):
            raise ValueError('단계 결과를 확인해 주세요.')
        if type(h.get('stage')) is not int or not 0<=h['stage']<s['stage']: raise ValueError('완료 단계를 확인해 주세요.')
    if not isinstance(s.get('threads'),list) or len(s['threads'])!=n: raise ValueError('질문 기록을 확인해 주세요.')
    threads=[]
    for thread in s['threads']:
        if not isinstance(thread,list): raise ValueError('질문 기록을 확인해 주세요.')
        messages=[]
        for m in thread[-8:]:
            if not isinstance(m,dict) or m.get('role') not in ('user','assistant'): raise ValueError('대화 기록을 확인해 주세요.')
            messages.append({'role':m['role'],'content':api.text(m.get('content'),5000)})
        threads.append(messages)
    previous=s.get('previous',[])
    if not isinstance(previous,list) or len(previous)>35: raise ValueError('출제 이력을 확인해 주세요.')
    s['previous']=[api.text(p,3000) for p in previous]
    s['threads']=threads
    keep=('runId','settings','mode','stage','questions','progress','questionIndex','history','threads','previous','title')
    return {'session':{k:s[k] for k in keep},'showingSummary':bool(value.get('showingSummary'))}


def _apply(state, saved, revision):
    if type(revision) is not int or revision!=state['revision']:
        raise ValueError('다른 창의 퀴즈 기록이 변경되었어요. 현재 화면을 새로고침해 최신 기록을 열어 주세요.')
    state['saved']=saved
    state['revision']+=1
    s=saved['session']
    if s:
        progress=s['progress']
        result={'runId':s['runId'],'course':s['settings']['course'],'unit':s['settings']['unit'],'mode':s['mode'],
                'stage':s['stage'],'solved':sum(p['solved'] for p in progress)+sum(h['solved'] for h in s['history']),
                'firstTry':sum(p['solved'] and len(p['attempts'])==1 for p in progress)+sum(h['firstTry'] for h in s['history']),
                'hints':sum(p['hintsUsed'] for p in progress),'at':db.now_str()}
        state['records']=([r for r in state.get('records',[]) if r['runId']!=s['runId']]+[result])[-50:]


def save(user, value, revision):
    authorize(user, role='teacher', write=True)
    saved=validate_saved(value)
    b=db._ready_backend()
    with b.lock:
        actor=games._actor(user,b,role='teacher',write=True)
        key='_quizpop_preview_'+actor['id']; state=deepcopy(st.session_state.get(key,_state({})))
        _apply(state,saved,revision);st.session_state[key]=state
        return {'revision':state['revision']}
