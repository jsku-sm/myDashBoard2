"""Reuse login checks, encrypted game_profiles and GitHub save queue."""
from copy import deepcopy
import streamlit as st
import storage as db
from . import service as games, engine as avatar, play_lab_engine as lab


def snapshot(user, student_id=None, *, preview=False, history=True):
    b = db._ready_backend()
    with b.lock:
        if preview:
            actor = games._actor(user, b, "teacher")
            state = st.session_state.get("_lab_demo_" + actor["id"], lab.initial())
            return dict(lab.public(state, history=history), revision=0, userId=actor["id"], name="교사 미리보기", preview=True)
        target = games._target(user, b, student_id)
        row = games._row(b, target)
    # Authorized row is already a detached copy; JSON/render work need not block classmates.
    profile = games._load(row["state_json"], avatar.new_profile())
    return dict(lab.public(profile.get("play_lab", lab.initial()), history=history), revision=int(row["revision"]), userId=target["id"], name=target["name"], preview=False)


def act(user, revision, events, *, preview=False):
    if preview:
        b = db._ready_backend()
        with b.lock:
            actor = games._actor(user, b, "teacher")
            key = "_lab_demo_" + actor["id"]
            state = deepcopy(st.session_state.get(key, lab.initial()))
            lab.apply(state, events, db.now_str())
            st.session_state[key] = state
        return
    def mutate(profile, backend, actor):
        lab.apply(profile.setdefault("play_lab", lab.initial()), events, db.now_str())
    games._mutate(user, revision, mutate)
