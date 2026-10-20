"""학생 홈."""
import streamlit as st

import storage as db
import ui
from config import EMOTION_MAP
from views import emotion
from views.home_style import HOME_CSS
from views.student_home_updates import apply_pending_navigation, render_student_updates, select_home_item


def _summary(user):
    show_points = db.get_setting("show_points_to_students") == "1"
    with st.container(key="home_summary", border=True, gap="small"):
        columns = st.columns([2, 3, 1.2] if show_points else [5, 1.2], gap="small", vertical_alignment="center")
        with columns[0]:
            selected = EMOTION_MAP.get(emotion.today_emotion(user))
            icon, label = (selected[1], selected[2]) if selected else ("🙂", "아직 선택하지 않았어요")
            st.markdown('<p class="home-label">오늘의 기분</p>'
                        f'<div class="home-emotion"><span class="home-emotion-icon">{icon}</span>'
                        f'<strong>{ui.esc(label)}</strong></div>', unsafe_allow_html=True)
        if show_points:
            with columns[1]:
                pts = [p for p in db.read("points") if p["student_id"] == user["id"]]
                plus = sum(int(p["score"] or 0) for p in pts if p["kind"] == "상점")
                minus = sum(int(p["score"] or 0) for p in pts if p["kind"] == "벌점")
                st.markdown('<p class="home-label">나의 상점·벌점</p><div class="home-points">' +
                            "".join(f'<span><small class="home-point-label">{name}</small><strong>{value}점</strong></span>'
                                    for name, value in (("상점", plus), ("벌점", minus), ("합계", plus - minus))) +
                            '</div>', unsafe_allow_html=True)
        with columns[-1]:
            picker = st.popover("기분 변경", key="home_emotion_picker", on_change="rerun", width="stretch")
            if picker.open:
                with picker:
                    emotion.picker(user, key_prefix="emo_again")


def _recent_feedback(user):
    subs = sorted((s for s in db.read("submissions") if s["student_id"] == user["id"]),
                  key=lambda s: (s["created_at"], s["id"]), reverse=True)
    with st.popover(f"최근에 받은 피드백 · {len(subs)}건", key="home_recent_feedback", width="stretch"):
        if not subs:
            st.caption("아직 올린 결과물이 없어요. 학급 게시판에서 결과물을 올려 보세요.")
            return
        selected = select_home_item(subs, "recent", user, "게시판 피드백 선택",
                                    lambda item: item["title"] or item["subject"])
        st.caption(selected["subject"])
        st.write(selected["feedback"] or "아직 피드백이 없어요.")
        if selected["teacher_comment"]:
            st.markdown("**선생님 한마디**")
            st.write(selected["teacher_comment"])


def page(user):
    emotion.toast_after_pick()
    st.markdown(HOME_CSS, unsafe_allow_html=True)
    with st.container(key="student_home", gap="small"):
        st.markdown('<div class="home-welcome">'
                    f'<h1 class="home-name">{ui.esc(user["name"])}님, 반가워요</h1>'
                    f'<span class="home-date">{ui.esc(user["class"])} · {db.today_str()}</span></div>',
                    unsafe_allow_html=True)
        _summary(user)
        from views import quiz
        quiz.student_home(user)
        render_student_updates(user)
        _recent_feedback(user)
