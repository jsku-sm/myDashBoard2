"""로그인 직후 감정 체크 화면."""
import streamlit as st

import storage as db
from config import EMOTIONS, EMOTION_MAP


def today_emotion(user):
    rows = [r for r in db.read("emotions")
            if r["student_id"] == user["id"] and r["date"] == db.today_str()]
    return rows[-1]["emotion"] if rows else None


def done_today(user) -> bool:
    if st.session_state.get("_emo_done"):
        return True
    if today_emotion(user):
        st.session_state["_emo_done"] = True
        return True
    return False


def save(user, key):
    db.append("emotions", {
        "created_at": db.now_str(), "date": db.today_str(), "student_id": user["id"],
        "name": user["name"], "class": user["class"], "emotion": key,
    })
    st.session_state["_emo_done"] = True
    st.session_state["_emo_msg"] = key


def picker(user, key_prefix="emo"):
    with st.container(key="emo_grid"):
        cols = st.columns(4)
        for i, (k, emoji, label, _c, _m) in enumerate(EMOTIONS):
            with cols[i % 4]:
                if st.button(f"{emoji}  \n**{label}**", key=f"{key_prefix}_{k}", width="stretch"):
                    save(user, k)
                    st.rerun()


def emotion_page(user):
    st.markdown(
        f'<div class="hero" style="text-align:center">{user["name"]}님,<br>'
        f'<span>지금 기분이 어때요?</span></div>'
        '<p class="pg-sub" style="text-align:center">가장 가까운 얼굴을 하나 골라 주세요. '
        '선생님만 볼 수 있어요.</p>',
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 6, 1])
    with mid:
        picker(user)


def toast_after_pick():
    key = st.session_state.pop("_emo_msg", None)
    if key and key in EMOTION_MAP:
        e = EMOTION_MAP[key]
        st.toast(f"{e[1]} {e[4]}")
