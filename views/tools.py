"""5. 수업도구 + 교사 화면 잠금."""
import streamlit as st

import realtime as rt
import storage as db
import ui
from config import CLASSES

TOOLS = [
    ("tool_snorkl", "가. 스노클", "AI가 내 풀이 설명을 듣고 피드백해 줘요."),
    ("tool_desmos", "나. 데스모스", "그래프를 직접 그려 보며 생각해요."),
    ("tool_activity", "다. 데스모스 액티비티", "선생님이 알려 준 코드로 입장해요."),
    ("tool_quiz", "라. 퀴즈", "배운 내용을 퀴즈로 확인해요."),
    ("tool_apps", "마. 앱 (by 구쌤)", "구쌤이 직접 만든 수학 앱이에요."),
]


def lock_panel():
    with st.container(border=True):
        st.markdown("### 🔒 화면 잠금")
        st.caption("잠그면 해당 학급 학생들의 이 앱 화면이 몇 초 안에 잠기고, 해제하면 원래대로 돌아와요. "
                   "(학생이 따로 열어 둔 다른 사이트 탭까지 잠글 수는 없어요.)")
        status = " ".join(f"{'🔒' if rt.is_locked(c) else '🔓'} {c}" for c in CLASSES)
        st.markdown(status)
        targets = st.multiselect("대상 학급", CLASSES, default=CLASSES, key="lock_targets")
        msg = st.text_input("잠금 화면 문구", value=db.get_setting("lock_message"), key="lock_msg")
        c1, c2 = st.columns(2)
        if c1.button("🔒 잠금", type="primary", width="stretch", disabled=not targets):
            if msg != db.get_setting("lock_message"):
                db.set_setting("lock_message", msg)
            rt.set_lock(targets, True)
            st.rerun()
        if c2.button("🔓 잠금 해제", width="stretch", disabled=not targets):
            rt.set_lock(targets, False)
            st.rerun()


def page(user):
    is_t = user["role"] == "teacher"
    ui.page_title("수업도구", "수업에서 함께 쓰는 도구 모음")
    if is_t:
        lock_panel()

    for key, title, desc in TOOLS:
        links = ui.parse_links(db.get_setting(key))
        st.markdown(f"#### {title}")
        st.caption(desc)
        if not links:
            st.caption("선생님이 링크를 준비 중이에요.")
        else:
            cols = st.columns(min(len(links), 3))
            for i, (name, url) in enumerate(links):
                cols[i % len(cols)].link_button(name, url, width="stretch")
        if key == "tool_desmos" and links:
            with st.expander("이 화면에서 바로 계산기 열기"):
                ui.embed(links[0][1], height=560)
        if is_t:
            with st.expander(f"⚙️ {title} 링크 고치기"):
                st.caption("한 줄에 하나씩 `이름|주소` 형식으로 적어 주세요.")
                new = st.text_area("링크", value=db.get_setting(key), key=f"edit_{key}", height=100)
                if st.button("저장", key=f"save_{key}"):
                    db.set_setting(key, new)
                    st.rerun()
        st.write("")
