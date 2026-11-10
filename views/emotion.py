"""로그인 직후 감정 체크 화면."""
import streamlit as st

import storage as db
from config import EMOTIONS, EMOTION_MAP


def _student(user, backend):
    """Resolve only the signed-in student; never accept a caller's peer ID."""
    session = st.session_state.get("user") or {}
    if not user or user.get("id") != session.get("id"):
        return None
    actor = next((r for r in backend.read("users") if r["id"] == session.get("id")), None)
    if not actor or actor.get("role") != "student" or actor.get("must_change") == "1":
        return None
    return actor


def today_emotion(user):
    # Generic db.read("emotions") deliberately hides classroom records from
    # students. This server-side projection returns only one's own mood today.
    backend = db._ready_backend()
    with backend.lock:
        actor = _student(user, backend)
        if not actor:
            return None
        today = db.today_str()
        rows = [r for r in backend.read("emotions")
                if r["student_id"] == actor["id"] and r["date"] == today
                and r.get("emotion") in EMOTION_MAP]
        # Timestamp first; insertion order breaks ties for changes in a second.
        latest = max(enumerate(rows), key=lambda item: (item[1].get("created_at", ""), item[0]),
                     default=None)
        return latest[1]["emotion"] if latest else None


def done_today(user) -> bool:
    # Check persisted identity/date, not a flag surviving overnight in a tab.
    return today_emotion(user) is not None


def save(user, key):
    if key not in EMOTION_MAP:
        raise ValueError("표시된 기분 중 하나를 선택해 주세요.")
    backend = db._ready_backend()
    with backend.lock:
        actor = _student(user, backend)
        if not actor:
            raise PermissionError("로그인한 학생 본인의 기분만 선택할 수 있어요.")
        created_at = db.now_str()
        db.append("emotions", {
            "created_at": created_at, "date": created_at[:10], "student_id": actor["id"],
            "name": actor["name"], "class": actor["class"], "emotion": key,
        })
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
