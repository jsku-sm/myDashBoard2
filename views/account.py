"""내 정보: 비밀번호 바꾸기."""
import streamlit as st

import auth
import ui


def _pw_form(user, require_current: bool, key: str):
    with st.form(key):
        cur = st.text_input("지금 비밀번호", type="password") if require_current else None
        new = st.text_input("새 비밀번호 (4자 이상)", type="password")
        new2 = st.text_input("새 비밀번호 확인", type="password")
        ok = st.form_submit_button("비밀번호 바꾸기", type="primary")
    if not ok:
        return False
    if require_current and not auth.check_pw(cur, auth.get_user(user["id"])["pw_hash"]):
        st.error("지금 비밀번호가 맞지 않아요.")
    elif len(new) < 4:
        st.error("새 비밀번호는 4자 이상으로 정해 주세요.")
    elif new != new2:
        st.error("새 비밀번호 두 칸이 서로 달라요.")
    elif new == user["id"]:
        st.error("학번과 같은 비밀번호는 쓸 수 없어요.")
    else:
        auth.change_password(user["id"], new)
        return True
    return False


def force_change(user):
    ui.page_title("새 비밀번호를 정해 주세요", "처음 로그인했거나 비밀번호가 초기화되었어요. 나만 아는 비밀번호로 바꿔야 들어갈 수 있어요.")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if _pw_form(user, require_current=False, key="force_pw"):
            st.success("바꿨어요!")
            st.rerun()


def page(user):
    ui.page_title("내 정보", "비밀번호를 바꿀 수 있어요.")
    st.markdown(f"**이름** {user['name']}  \n**아이디(학번)** {user['id']}" +
                (f"  \n**학급** {user['class']}" if user["class"] else ""))
    st.markdown("#### 비밀번호 바꾸기")
    if _pw_form(user, require_current=True, key="change_pw"):
        st.success("비밀번호를 바꿨어요. 다음 로그인부터 새 비밀번호를 쓰세요.")
    st.caption("비밀번호를 잊어버리면 선생님께 초기화를 부탁하세요. 초기화하면 학번과 같은 비밀번호가 됩니다.")
