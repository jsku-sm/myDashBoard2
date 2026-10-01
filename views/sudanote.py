"""4. 수다노트."""
import streamlit as st

import storage as db
import ui
from config import SUDANOTE_GUIDE


def page(user):
    ui.page_title("수다노트", "오늘 수업을 나의 언어로 정리하는 시간")
    with st.container(border=True):
        st.markdown(SUDANOTE_GUIDE)
    url = db.get_setting("sudanote_form")
    st.link_button("✍️ 수다노트 쓰러 가기 (구글 설문)", url, type="primary", width="stretch")
    with st.expander("이 화면에서 바로 쓰기"):
        ui.embed(url, height=900)
    if user["role"] == "teacher":
        with st.expander("⚙️ 설문 링크 바꾸기"):
            new = st.text_input("구글 설문 주소", value=url)
            if st.button("저장", key="save_form"):
                db.set_setting("sudanote_form", new.strip())
                st.rerun()
