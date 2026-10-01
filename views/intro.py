"""1. 간단한 내 소개 / 2. 관심 분야 — 교사가 화면에서 바로 고칠 수 있음."""
import streamlit as st

import storage as db
import ui


def _editable(user, key, title, sub):
    ui.page_title(title, sub)
    text = db.get_setting(key)
    with st.container(border=True):
        st.markdown(text)
    if user["role"] == "teacher":
        with st.expander("✏️ 내용 고치기 (마크다운 사용 가능)"):
            new = st.text_area("내용", value=text, height=260, key=f"edit_{key}")
            if st.button("저장", type="primary", key=f"save_{key}"):
                db.set_setting(key, new)
                st.success("저장했어요.")
                st.rerun()


def intro_page(user):
    _editable(user, "intro", "간단한 내 소개", "수업을 함께하는 선생님을 소개합니다.")


def interests_page(user):
    _editable(user, "interests", "공부하는 분야 · 관심 있는 분야", "요즘 선생님이 파고들고 있는 것들이에요.")
