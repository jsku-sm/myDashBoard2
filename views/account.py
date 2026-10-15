"""내 정보: 비밀번호 바꾸기."""
import streamlit as st

import auth
import ui


_CSS = """
<style>
.st-key-account_page {
  --account-ink:var(--ink,light-dark(#263553,#E6ECF7));
  --account-muted:light-dark(#65758A,#B8C5D5);
  --account-surface:light-dark(#FFFFFF,#1C263C);
}
.st-key-account_page [data-testid="stMarkdownContainer"] {
  color:var(--account-ink);
  font-family:'Pretendard',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
.st-key-account_page :is(.st-key-account_profile,.st-key-account_password,.st-key-account_force_password) {
  border:1.5px solid light-dark(#B5D7CA,#587B6C);border-radius:22px;
  padding:24px;box-shadow:0 5px 0 light-dark(#DDEAE6,#152A24);overflow:hidden;
}
.st-key-account_page .st-key-account_profile {
  background:linear-gradient(145deg,light-dark(#E9F7F0,#223B32),light-dark(#ECF4FD,#24364A));
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) {
  border-color:light-dark(#CAB7E4,#775E91);
  background:linear-gradient(135deg,light-dark(#F4EEFC,#312940),light-dark(#FCFAFF,#272337));
  box-shadow:0 5px 0 light-dark(#E7DFF1,#1D1928);
}
.st-key-account_page .account-kicker {
  display:flex;align-items:center;gap:8px;margin:0 0 14px;
  color:light-dark(#4E7667,#BCE1CE);font-size:.75rem;font-weight:800;letter-spacing:.08em;
}
.st-key-account_page .account-kicker::before {
  content:"";width:7px;height:7px;border-radius:50%;background:currentColor;
}
.st-key-account_page .account-person {
  display:flex;align-items:center;gap:14px;margin-bottom:21px;
}
.st-key-account_page .account-avatar {
  display:grid;place-items:center;flex:0 0 65px;width:65px;height:65px;border-radius:20px;
  border:1.5px solid light-dark(#A7CCB9,#70967F);background:light-dark(#FFFFFFBD,#FFFFFF10);
  color:light-dark(#487960,#BCE5CB);
}
.st-key-account_page .account-avatar svg {width:42px;height:42px;}
.st-key-account_page .account-name {margin:0;font-size:1.4rem;font-weight:800;line-height:1.4;overflow-wrap:anywhere;}
.st-key-account_page .account-role {
  display:inline-block;margin-top:5px;padding:3px 10px;border:1px solid light-dark(#AACDBB,#678774);
  border-radius:99px;background:light-dark(#FFFFFFB8,#FFFFFF0E);color:light-dark(#486D58,#C6E8D4);
  font-size:.75rem;font-weight:750;
}
.st-key-account_page .account-details {display:grid;gap:9px;margin:0;}
.st-key-account_page .account-detail {
  display:flex;align-items:baseline;justify-content:space-between;gap:15px;
  padding:13px 14px;border:1px solid light-dark(#C9DED8,#4C655C);border-radius:12px;
  background:light-dark(#FFFFFFBB,#FFFFFF08);
}
.st-key-account_page .account-detail dt {color:var(--account-muted);font-size:.8rem;white-space:nowrap;}
.st-key-account_page .account-detail dd {margin:0;text-align:right;font-size:.9rem;font-weight:750;overflow-wrap:anywhere;min-width:0;}
.st-key-account_page .account-security-heading {display:flex;align-items:center;gap:11px;margin-bottom:7px;}
.st-key-account_page .account-lock {
  display:grid;place-items:center;flex:0 0 40px;width:40px;height:40px;border:1px solid light-dark(#C8B3E2,#7D6592);
  border-radius:13px;background:light-dark(#E7DAF5,#443354);color:light-dark(#71518F,#E0C7F4);
}
.st-key-account_page .account-lock svg {width:23px;height:23px;}
.st-key-account_page .account-security-heading h4 {margin:0!important;font-size:1.18rem!important;}
.st-key-account_page .account-password-sub {margin:0 0 6px;color:var(--account-muted);font-size:.82rem;line-height:1.6;}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) [data-testid="stForm"] {
  padding:0;border:0;background:transparent;
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) [data-testid="stTextInput"] label {
  font-size:.83rem;font-weight:750;color:light-dark(#64517B,#E0D0EE);
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password)
  :is([data-baseweb="input"],[data-testid="stTextInputRootElement"]) {
  min-height:45px;border:1.5px solid light-dark(#C8B4E0,#856D9A);border-radius:12px;
  background:var(--account-surface);box-shadow:0 2px 0 light-dark(#E8DEF1,#211B2C);
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) input {color:var(--account-ink);}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password)
  :is([data-baseweb="input"],[data-testid="stTextInputRootElement"]):focus-within {
  border-color:light-dark(#8865AB,#CDA9EE);outline:3px solid light-dark(#DBC9ED,#59416F);outline-offset:1px;
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) [data-testid="stFormSubmitButton"] button {
  width:100%;min-height:46px;margin-top:5px;border:1.5px solid light-dark(#76A88B,#7CB794);
  border-radius:12px;background:light-dark(#D7EFDF,#2C503D);color:light-dark(#2D6244,#D8F4E2);
  font-weight:800;box-shadow:0 3px 0 light-dark(#B6D8C2,#1A3225);
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) [data-testid="stFormSubmitButton"] button:hover {
  background:light-dark(#C4E6D0,#375F49);border-color:light-dark(#467756,#B1DDBF);
}
.st-key-account_page :is(.st-key-account_password,.st-key-account_force_password) [data-testid="stFormSubmitButton"] button:focus-visible {
  outline:3px solid light-dark(#7EAF91,#A5D6B5);outline-offset:3px;
}
.st-key-account_page .account-help {
  display:flex;align-items:flex-start;gap:9px;margin-top:7px;padding:13px 16px;
  border:1px solid light-dark(#E3D099,#8D7A48);border-radius:13px;
  background:light-dark(#FFF9E7,#373122);color:light-dark(#826E40,#E5D5AB);font-size:.79rem;line-height:1.7;
}
.st-key-account_page .account-help b {flex:0 0 auto;font-weight:800;}
.st-key-account_page .st-key-account_force_password {max-width:530px;margin:0 auto;}
@media(max-width:640px) {
  .st-key-account_page [data-testid="stHorizontalBlock"] {gap:1.1rem;}
  .st-key-account_page :is(.st-key-account_profile,.st-key-account_password,.st-key-account_force_password) {padding:18px 16px;border-radius:18px;}
  .st-key-account_page .account-person {gap:11px;margin-bottom:16px;}
  .st-key-account_page .account-avatar {width:56px;height:56px;flex-basis:56px;border-radius:17px;}
  .st-key-account_page .account-name {font-size:1.25rem;}
  .st-key-account_page .account-detail {padding:11px 12px;}
  .st-key-account_page .account-help {display:block;padding:12px 14px;}
  .st-key-account_page .account-help b {margin-right:5px;}
}
</style>
"""

_PERSON = ('<svg viewBox="0 0 48 48" fill="none" aria-hidden="true">'
           '<circle cx="24" cy="16" r="7" stroke="currentColor" stroke-width="2.2"/>'
           '<path d="M10 39c0-7.7 6.3-14 14-14s14 6.3 14 14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
           '<path d="M35 8h6M38 5v6M6 22h5M8.5 19.5v5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity=".6"/>'
           '</svg>')
_LOCK = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
         '<rect x="5" y="10" width="14" height="11" rx="3" stroke="currentColor" stroke-width="1.7"/>'
         '<path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="1.7"/>'
         '<circle cx="12" cy="15" r="1.2" fill="currentColor"/><path d="M12 16v2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>'
         '</svg>')


def _password_heading():
    st.markdown(
        '<div class="account-security-heading"><span class="account-lock">'
        + _LOCK + '</span><h4>비밀번호 바꾸기</h4></div>'
        '<p class="account-password-sub">나만 아는 비밀번호로 내 학습 기록을 지켜요.</p>',
        unsafe_allow_html=True,
    )


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
    st.markdown(_CSS, unsafe_allow_html=True)
    ui.page_title("새 비밀번호를 정해 주세요", "처음 로그인했거나 비밀번호가 초기화되었어요. 나만 아는 비밀번호로 바꿔야 들어갈 수 있어요.")
    with st.container(key="account_page"):
        with st.container(key="account_force_password"):
            _password_heading()
            if _pw_form(user, require_current=False, key="force_pw"):
                st.success("바꿨어요!")
                st.rerun()


def page(user):
    st.markdown(_CSS, unsafe_allow_html=True)
    ui.page_title("내 정보", "비밀번호를 바꿀 수 있어요.")
    with st.container(key="account_page"):
        profile, password = st.columns([.95, 1.2], gap="medium")
        with profile:
            with st.container(key="account_profile"):
                role = "선생님" if user["role"] == "teacher" else "학생"
                details = [("이름", user["name"]), ("아이디(학번)", user["id"])]
                if user["class"]:
                    details.append(("학급", user["class"]))
                detail_html = "".join(
                    '<div class="account-detail"><dt>' + ui.esc(label)
                    + '</dt><dd>' + ui.esc(value) + '</dd></div>'
                    for label, value in details
                )
                st.markdown(
                    '<p class="account-kicker">나의 프로필</p>'
                    '<div class="account-person"><span class="account-avatar">' + _PERSON
                    + '</span><div><p class="account-name">' + ui.esc(user["name"])
                    + '</p><span class="account-role">' + role + '</span></div></div>'
                    '<dl class="account-details">' + detail_html + '</dl>',
                    unsafe_allow_html=True,
                )
        with password:
            with st.container(key="account_password"):
                _password_heading()
                if _pw_form(user, require_current=True, key="change_pw"):
                    st.success("비밀번호를 바꿨어요. 다음 로그인부터 새 비밀번호를 쓰세요.")
        st.markdown(
            '<div class="account-help"><b>도움말</b><span>비밀번호를 잊어버리면 선생님께 초기화를 부탁하세요. 초기화하면 학번과 같은 비밀번호가 됩니다.</span></div>',
            unsafe_allow_html=True,
        )
