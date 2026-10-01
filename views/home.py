"""학생 홈."""
import streamlit as st

import storage as db
import ui
from config import EMOTION_MAP
from views import emotion


def page(user):
    emotion.toast_after_pick()
    ui.page_title(f"{user['name']}님, 반가워요", f"{user['class']}반 · 오늘 {db.today_str()}")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### 오늘의 기분")
        key = emotion.today_emotion(user)
        if key in EMOTION_MAP:
            e = EMOTION_MAP[key]
            ui.note(f'<div style="font-size:3rem">{e[1]}</div><b>{e[2]}</b><br>'
                    f'<span class="meta">{ui.esc(e[4])}</span>', "yellow")

    with c2:
        st.markdown("#### 최근에 받은 피드백")
        subs = [s for s in db.read("submissions") if s["student_id"] == user["id"]]
        if not subs:
            st.info("아직 올린 결과물이 없어요. 공통수학 메뉴의 '학급 게시판'에서 올려 보세요.")
        for s in subs[::-1][:3]:
            body = f'<span class="chip">{ui.esc(s["subject"])}</span><b>{ui.esc(s["title"])}</b>' \
                   f'<div style="margin-top:.4rem">💬 {ui.esc(s["feedback"])}</div>'
            if s["teacher_comment"]:
                body += f'<div style="margin-top:.3rem">🧑‍🏫 {ui.esc(s["teacher_comment"])}</div>'
            ui.note(body, "mint")

    with st.expander("기분이 바뀌었나요? 다시 고르기"):
        emotion.picker(user, key_prefix="emo_again")

    if db.get_setting("show_points_to_students") == "1":
        pts = [p for p in db.read("points") if p["student_id"] == user["id"]]
        plus = sum(int(p["score"] or 0) for p in pts if p["kind"] == "상점")
        minus = sum(int(p["score"] or 0) for p in pts if p["kind"] == "벌점")
        st.markdown("#### 나의 상점·벌점")
        a, b, c = st.columns(3)
        a.metric("상점", f"{plus}점")
        b.metric("벌점", f"{minus}점")
        c.metric("합계", f"{plus - minus}점")
