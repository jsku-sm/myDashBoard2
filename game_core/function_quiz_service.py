"""Store the imported quiz in existing, encrypted game_profiles records."""
from copy import deepcopy
import streamlit as st
import storage as db
from . import service as games, engine as game_engine, function_quiz_engine as quiz


def snapshot(user,student_id=None,*,preview=False):
    b=db._ready_backend()
    with b.lock:
        if preview:
            actor=games._actor(user,b,"teacher")
            state=st.session_state.get("_function_demo_"+actor["id"],quiz.initial())
            view=quiz.public(state,preview=True)
            return dict(view,revision=0,name="교사 미리보기")
        target=games._target(user,b,student_id)
        row=games._row(b,target)
        profile=games._load(row["state_json"],game_engine.new_profile())
        view=quiz.public(profile.get("function_quiz",quiz.initial()))
        return dict(view,revision=int(row["revision"]),name=target["name"])


def act(user,revision,event,*,preview=False):
    if preview:
        b=db._ready_backend()
        with b.lock:
            actor=games._actor(user,b,"teacher")
            key="_function_demo_"+actor["id"]
            draft=deepcopy(st.session_state.get(key,quiz.initial()))
            quiz.apply(draft,event,db.now_str(),preview=True)
            st.session_state[key]=draft
        return
    def mutate(profile,b,actor):
        state=profile.setdefault("function_quiz",quiz.initial())
        quiz.apply(state,event,db.now_str())
    games._mutate(user,revision,mutate)
