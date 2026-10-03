"""구쌤의 수학 교실 — 수업용 대시보드 (Streamlit)

실행:  streamlit run app.py
"""
import time

import streamlit as st

import auth
import login_bg
import realtime as rt
import storage as db
import ui
from config import APP_TITLE, POLL_SEC
from views import account, dashboard, emotion, home, intro, math_class, sudanote, teacher, tools

st.set_page_config(page_title=APP_TITLE, page_icon="📐", layout="wide")
ui.inject_css()

# 저장소 연결 확인: 실패하면 무엇을 고쳐야 하는지 보여 주고 멈춤
try:
    db.get_backend()
except Exception as e:
    ui.page_title("설정을 확인해 주세요", "앱이 데이터 저장소에 연결하지 못했어요.")
    st.error(str(e))
    st.markdown(
        "**확인할 것**\n\n"
        "1. Streamlit Cloud 앱의 **Settings → Secrets**에 `[app]`과 `[github]`이 들어 있나요?\n"
        "2. `repo`는 `내아이디/저장소이름` 형식인가요?\n"
        "3. 데이터 저장소가 **비공개(Private)** 인가요?\n"
        "4. 토큰의 **Contents** 권한이 **Read and write**이고, 데이터 저장소가 선택되어 있나요?\n\n"
        "고친 뒤 오른쪽 아래 **Manage app → ⋮ → Reboot app**을 누르세요."
    )
    st.stop()

auth.ensure_teacher()


# ------------------------------------------------------------ 로그인 화면 ---
def login_page():
    st.markdown(login_bg.html(), unsafe_allow_html=True)
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(
            '<div class="hero">오늘도<br><span>생각하는 수학 시간</span></div>'
            '<p class="formula">f(x) = 나의 질문 + 나의 언어</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "학번과 비밀번호로 들어오세요. 처음 들어오는 학생은 **비밀번호가 학번과 같아요.** "
            "들어오면 바로 새 비밀번호로 바꾸게 됩니다."
        )
    with right, st.container(key="login_card"):
        with st.form("login", border=False):
            st.markdown("### 로그인")
            uid = st.text_input("학번", placeholder="예: 10101")
            pw = st.text_input("비밀번호", type="password")
            ok = st.form_submit_button("들어가기", type="primary", width="stretch")
        wait = st.session_state.get("_login_block", 0) - time.time()
        if ok:
            if wait > 0:
                st.error(f"로그인을 여러 번 실패했어요. {int(wait)+1}초 뒤에 다시 시도하세요.")
                return
            user = auth.login(uid, pw)
            if user:
                st.session_state.clear()
                st.session_state["user"] = user
                if user["role"] == "student":
                    db.append("logins", {
                        "created_at": db.now_str(), "date": db.today_str(),
                        "student_id": user["id"], "name": user["name"], "class": user["class"],
                    })
                    rt.touch(user["id"])
                st.rerun()
            else:
                n = st.session_state.get("_login_fail", 0) + 1
                st.session_state["_login_fail"] = n
                if n >= 5:
                    st.session_state["_login_block"] = time.time() + 30
                    st.session_state["_login_fail"] = 0
                st.error("학번 또는 비밀번호가 맞지 않아요. 잊어버렸다면 선생님께 초기화를 부탁하세요.")
        st.caption("선생님은 교사 아이디로 같은 곳에서 로그인합니다.")
        st.caption("🌗 화면 밝기는 오른쪽 위 ⋮ 메뉴에서 고를 수 있어요. "
                   "(System = 기기 설정 따라가기 · Light = 밝게 · Dark = 어둡게)")
        if db.get_backend().is_local:
            st.warning("지금은 시험 모드예요. 서버가 다시 시작되면 데이터가 사라집니다. "
                       "(secrets 에 깃허브 저장소를 설정하면 계속 보관돼요)")


# ------------------------------------------------- 학생 화면 실시간 확인 ---
@st.fragment(run_every=POLL_SEC)
def student_poller():
    user = st.session_state.get("user")
    if not user:
        return
    rt.touch(user["id"])
    if rt.is_locked(user["class"]) != st.session_state.get("_locked", False):
        st.rerun(scope="app")
    if rt.has_pending(user["id"]):
        st.session_state.setdefault("_popups", []).extend(rt.pop_all(user["id"]))
        st.rerun(scope="app")


@st.dialog("⚠️ 벌점 안내")
def penalty_dialog(items):
    for it in items:
        st.markdown(
            f'<div class="note coral"><h4>벌점 {it["score"]}점이 부과되었어요</h4>'
            f'<div>사유: {ui.esc(it["reason"])}</div></div>',
            unsafe_allow_html=True,
        )
    st.write("행동을 돌아보고 다음 시간에 더 멋진 모습을 보여 주세요. 궁금한 점은 선생님께 이야기하세요.")
    if st.button("확인했어요", type="primary", width="stretch"):
        st.rerun()


def show_popups():
    pops = st.session_state.pop("_popups", [])
    if not pops:
        return
    good = [p for p in pops if p["kind"] == "상점"]
    bad = [p for p in pops if p["kind"] == "벌점"]
    if good:
        total = sum(int(p["score"]) for p in good)
        reasons = ", ".join(dict.fromkeys(p["reason"] for p in good))
        ui.fireworks(f"🎉 상점 +{total}점!", reasons)
    if bad:
        penalty_dialog(bad)


# ------------------------------------------------------------ 사이드바 ---
# 메뉴 (id, 이름, 번호 붙임 여부, 보이는 사람). 번호는 보이는 메뉴 순서대로 자동으로 붙어요.
MENU = [
    ("home", "🏠 홈", False, "student"),
    ("dashboard", "📊 대시보드", False, "teacher"),
    ("intro", "👋 선생님 소개", True, "all"),
    ("math1", "📐 공통수학1", True, "all"),
    ("math2", "📏 공통수학2", True, "all"),
    ("sudanote", "📝 수다노트", True, "all"),
    ("tools", "🧰 수업도구", True, "all"),
    ("teacher", "🛡️ 교사전용", True, "teacher"),
    ("account", "🔑 내 정보", False, "all"),
]


def menu_for(role):
    items, n = {}, 0
    for mid, label, numbered, who in MENU:
        if who not in ("all", role):
            continue
        if numbered:
            n += 1
            label = f"{n}. {label}"
        items[mid] = label
    return items


def sidebar(user):
    is_t = user["role"] == "teacher"
    with st.sidebar:
        st.markdown(f"## {APP_TITLE}")
        if is_t:
            st.markdown(f"**{user['name']}** · 교사")
        else:
            st.markdown(f"**{user['name']}** ({user['class']} · {user['id']})")
        items = menu_for(user["role"])
        if st.session_state.get("nav") not in items:
            st.session_state.pop("nav", None)
        page = st.radio("메뉴", list(items), format_func=items.get, key="nav",
                        label_visibility="collapsed")
        st.divider()
        if is_t:
            locked = rt.locked_classes()
            if locked:
                st.warning("🔒 잠금 중: " + ", ".join(locked))
                if st.button("모두 잠금 해제", width="stretch"):
                    rt.set_lock(locked, False)
                    st.rerun()
            st.caption(db.backend_status())
        if st.button("로그아웃", width="stretch"):
            if not is_t:
                rt.leave(user["id"])
            st.session_state.clear()
            st.rerun()
    return page


# -------------------------------------------------------------- 메인 ---
user = st.session_state.get("user")
if not user:
    login_page()
    st.stop()

if user["role"] == "student":
    st.session_state["_locked"] = rt.is_locked(user["class"])
    rt.touch(user["id"])
    student_poller()
    if st.session_state["_locked"]:
        ui.lock_screen(db.get_setting("lock_message"))
        st.stop()
    show_popups()

fresh = auth.get_user(user["id"])
if fresh is None:
    st.session_state.clear()
    st.rerun()
if fresh["must_change"] == "1":
    account.force_change(fresh)
    st.stop()

if user["role"] == "student" and not emotion.done_today(user):
    emotion.emotion_page(user)
    st.stop()

page = sidebar(user)

ROUTES = {
    "home": lambda: home.page(user),
    "dashboard": lambda: dashboard.page(user),
    "intro": lambda: intro.intro_page(user),
    "math1": lambda: math_class.page(user, "공통수학1"),
    "math2": lambda: math_class.page(user, "공통수학2"),
    "sudanote": lambda: sudanote.page(user),
    "tools": lambda: tools.page(user),
    "teacher": lambda: teacher.page(user),
    "account": lambda: account.page(user),
}
ROUTES[page]()
