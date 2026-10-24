# GOOD_RECORDS_1.1_FINAL5
"""구쌤의 수학 교실 — 수업용 대시보드 (Streamlit)

실행:  streamlit run app.py
"""
import time

import streamlit as st

# This preflight runs BEFORE importing views/storage. It never reads Secrets.
from pathlib import Path

DASHBOARD_UPDATE = 'GOOD_RECORDS_1.1_FINAL5'
_UPDATE_FILES = ('ui.py', 'storage.py', 'views/record.py', 'views/teacher.py', 'views/sudanote.py', 'think_app/storage.py', 'think_app/embedded.py', 'record_core/__init__.py', 'record_core/archive.py', 'record_core/assessment.py', 'record_core/checkpoint.py', 'record_core/evidence.py', 'record_core/ai.py', 'record_core/service.py', 'record_core/view.py')

def dashboard_update_issues(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    issues = []
    for relative in _UPDATE_FILES:
        path = root / relative
        if not path.is_file():
            issues.append(relative + "  — 파일 없음")
        else:
            try:
                header = path.read_text(encoding="utf-8")[:256]
            except (OSError, UnicodeError):
                issues.append(relative + "  — 읽기 실패")
                continue
            if DASHBOARD_UPDATE not in header:
                issues.append(relative + "  — 이전 파일이거나 수정본 표시 없음")
    return issues

_update_issues = dashboard_update_issues()
if _update_issues:
    st.set_page_config(page_title="구쌤의 수학 교실 · 업데이트 확인", page_icon="📐", layout="wide")
    st.title("Good쌤을 만나, 수학이 달라졌다")
    st.error("로그인 파일은 수정되었지만, 학생 자료함·생기부 파일 일부가 아직 적용되지 않았습니다.")
    st.code("\n".join(_update_issues), language="text")
    st.info("이번 수정본의 파일·하위 폴더를 앱 코드 저장소의 같은 위치에 모두 덮어쓰세요. 데이터 저장소에는 코드 파일을 올리지 않습니다. Secrets나 기존 학생 자료는 삭제하지 마세요.")
    st.caption(DASHBOARD_UPDATE + " · 부분 업로드 확인됨")
    st.stop()

import auth
import login_bg
import realtime as rt
import storage as db
import ui
from config import APP_TITLE, POLL_SEC
from snorkl_navigation import main_menu_changed, preserve_tool_drafts, sync_shared_link
from views import account, dashboard, emotion, home, intro, math_class, sudanote, teacher, tools
from views.student_announcements import poll_announcements, show_announcement_popup

st.set_page_config(page_title=APP_TITLE, page_icon="📐", layout="wide")
ui.inject_css()

# 저장소 연결 확인: 실패하면 무엇을 고쳐야 하는지 보여 주고 멈춤
try:
    db.get_backend()
except Exception as e:
    ui.page_title("설정을 확인해 주세요", "앱이 데이터 저장소에 연결하지 못했어요.")
    st.caption(DASHBOARD_UPDATE + " · 코드 적용 완료 / 저장소 설정 확인 필요")
    st.error(str(e))
    if "학생별 자료함 암호화키가 없습니다" in str(e):
        st.info("새 학생별 자료함을 처음 연결할 때 한 번만 키를 만드세요. 이미 자료함이 있다면 최초 키를 복구하고, 기존 수행평가 키는 바꾸지 마세요.")
        if st.button("새 학생 자료함용 암호화키 만들기"):
            from cryptography.fernet import Fernet
            st.session_state["new_student_archive_key"] = Fernet.generate_key().decode("ascii")
        if st.session_state.get("new_student_archive_key"):
            st.code('[student_archive]\nencryption_key = "' + st.session_state["new_student_archive_key"] + '"', language="toml")
            st.caption("위 두 줄을 Streamlit Secrets에만 넣고 안전하게 별도 보관하세요. 자동 저장되지 않습니다. 기존 같은 구역이 있으면 값을 수정하세요.")
    st.markdown(
        "**확인할 것**\n\n"
        "1. Streamlit Cloud 앱의 **Settings → Secrets**에 `[app]`과 `[github]`이 들어 있나요?\n"
        "2. 저장 대상은 `jsku-sm/class-dashboard-data`인가요?\n"
        "3. 데이터 저장소가 **비공개(Private)** 인가요?\n"
        "4. 토큰의 **Contents** 권한이 **Read and write**이고, 데이터 저장소가 선택되어 있나요?\n\n"
        "고친 뒤 오른쪽 아래 **Manage app → ⋮ → Reboot app**을 누르세요."
    )
    st.stop()

try:
    auth.ensure_teacher()
except db.SetupError as error:
    st.error(str(error))
    st.stop()


# ------------------------------------------------------------ 로그인 화면 ---
def login_page():
    st.markdown(login_bg.html(), unsafe_allow_html=True)
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(
            '<div class="hero">Good쌤을 만나,<br><span>수학이 달라졌다</span></div>'
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
        st.caption(DASHBOARD_UPDATE + " · 학생별 자료함·생기부 C 연결본")
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
    poll_announcements(user)


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
        return True
    return False


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
        ui.sidebar_header(APP_TITLE, user)
        items = menu_for(user["role"])
        if st.session_state.get("nav") not in items:
            # 이전 세션의 메뉴가 더 이상 없으면 역할별 기본 화면으로 이동합니다.
            st.session_state["nav"] = "dashboard" if is_t else "home"
        page = st.radio("메뉴", list(items), format_func=items.get, key="nav",
                        label_visibility="collapsed", width="stretch", on_change=main_menu_changed,
                        args=(st.session_state, st.query_params))
        st.divider()
        if is_t:
            locked = rt.locked_classes()
            if locked:
                st.warning("🔒 잠금 중: " + ", ".join(locked))
                if st.button("모두 잠금 해제", width="stretch"):
                    rt.set_lock(locked, False)
                    st.rerun()
            st.caption(db.backend_status())
        with st.container(key="sidebar_logout"):
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

# Re-read the account before any role-specific view, including embedded tools.
fresh = auth.get_user(user["id"])
if fresh is None or fresh.get("role") not in ("teacher", "student"):
    st.session_state.clear()
    st.rerun()
user = fresh
st.session_state["user"] = user
if user["must_change"] == "1":
    account.force_change(user)
    st.stop()

if user["role"] == "student":
    st.session_state["_locked"] = rt.is_locked(user["class"])
    rt.touch(user["id"])
    student_poller()
    if st.session_state["_locked"]:
        preserve_tool_drafts(user)
        ui.lock_screen(db.get_setting("lock_message"))
        st.stop()
    if not show_popups():
        show_announcement_popup(user)


if user["role"] == "student" and not emotion.done_today(user):
    emotion.emotion_page(user)
    st.stop()

# A share link chooses a view only; all login/password/emotion/lock checks run first.
sync_shared_link(st.session_state, st.query_params)
home.apply_pending_navigation(user)
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
