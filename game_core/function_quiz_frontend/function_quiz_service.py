"""Store the imported quiz in existing, encrypted game_profiles records."""
from copy import deepcopy
import streamlit as st
import storage as db
from . import service as games, engine as game_engine, function_quiz_engine as quiz
from .concept_quiz_catalog import UNITS, unit_info


def _state(profile, unit):
    return profile.get("function_quiz",quiz.initial()) if unit=="functions" else profile.get("concept_quizzes",{}).get(unit,quiz.initial())


def _demo_key(actor, unit):
    return "_function_demo_"+actor["id"] if unit=="functions" else "_concept_demo_"+actor["id"]+"_"+unit


def overview(profile):
    result=[]
    for unit in UNITS:
        info=unit_info(unit);state=_state(profile,unit)
        result.append(dict(unit=unit,subject=info['subject'],title=info['title'],
            solved=sum(len(s['passed']) for s in state['stages'].values()),total=len(info['topics'])*5,
            points=sum(state['awards'].values()),totals=deepcopy(state['totals']),mastered_at=state['mastered_at']))
    return result


def snapshot(user,student_id=None,*,preview=False,unit="functions",history=True,include_overview=True):
    unit_info(unit)
    b=db._ready_backend()
    with b.lock:
        if preview:
            actor=games._actor(user,b,"teacher")
            state=st.session_state.get(_demo_key(actor,unit),quiz.initial())
            view=quiz.public(state,preview=True,unit=unit,history=history)
            return dict(view,revision=0,name="교사 미리보기")
        target=games._target(user,b,student_id)
        row=games._row(b,target)
    profile=games._load(row["state_json"],game_engine.new_profile())
    view=quiz.public(_state(profile,unit),unit=unit,history=history)
    return dict(view,revision=int(row["revision"]),name=target["name"],overview=overview(profile) if include_overview else [])


def act(user,revision,event,*,preview=False,unit="functions"):
    unit_info(unit)
    if preview:
        b=db._ready_backend()
        with b.lock:
            actor=games._actor(user,b,"teacher")
            key=_demo_key(actor,unit)
            draft=deepcopy(st.session_state.get(key,quiz.initial()))
            quiz.apply(draft,event,db.now_str(),preview=True,unit=unit)
            st.session_state[key]=draft
        return
    def mutate(profile,b,actor):
        state=profile.setdefault("function_quiz",quiz.initial()) if unit=="functions" else profile.setdefault("concept_quizzes",{}).setdefault(unit,quiz.initial())
        quiz.apply(state,event,db.now_str(),unit=unit)
    games._mutate(user,revision,mutate)
