"""Guarded adapter: run the uploaded Snorkl inside the logged-in dashboard."""
import streamlit as st
import auth
import realtime as rt


def page(user):
    session_user = st.session_state.get("user") or {}
    if not session_user.get("id") or session_user.get("id") != user.get("id"):
        st.error("대시보드에 먼저 로그인해 주세요.")
        return
    current = auth.get_user(session_user["id"])
    if not current or current.get("role") not in ("teacher", "student"):
        st.error("계정을 확인할 수 없습니다. 로그아웃 후 다시 로그인해 주세요.")
        return
    if current.get("must_change") == "1":
        st.warning("대시보드에서 초기 비밀번호를 먼저 변경해 주세요.")
        return
    if current["role"] == "student" and rt.is_locked(current["class"]):
        st.warning("지금은 선생님 설명 시간입니다. 잠금이 해제되면 계속할 수 있어요.")
        return
    try:
        from think_app.embedded import render
    except ImportError as error:
        st.error("소노클 실행에 필요한 라이브러리가 아직 준비되지 않았습니다.")
        st.caption(f"확인할 모듈: {getattr(error, 'name', '') or 'think_app'}")
        st.info("통합본의 requirements.txt와 think_app 폴더를 함께 업로드한 뒤 Streamlit 앱을 재시작하세요.")
        return
    # Password hashes and unrelated dashboard data are not handed to the tool.
    identity = {key: current.get(key, "") for key in ("id", "name", "class", "role")}
    render(identity)
