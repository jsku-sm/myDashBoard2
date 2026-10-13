"""Authenticated, in-process Snorkl renderer for myDashBoard2.

No second login, app-wide page config, separate server, iframe app, or sidebar.
The original classroom editors, uploads, assessment and feedback are reused.
"""
import streamlit as st

from .ai import AI
from .classroom import Classroom
from .classroom_ui import course_detail, student_preview
from .courses import CourseManager
from .course_admin import active_courses, archived_courses
from .integration import load_embedded_settings, student_identity, visible_courses
from .storage import AppError, GitHubStore, LocalStore, MemoryStore
from snorkl_navigation import REQUESTED_COURSE


@st.cache_resource(show_spinner=False)
def memory_store():
    # Shared within this dashboard process, never a fake persistent store.
    return MemoryStore()


@st.cache_resource(show_spinner=False)
def persistent_store(mode, data_dir, repo, branch, token, key):
    if mode == "github":
        if not repo or not token or not key:
            raise AppError("소노클의 GitHub 저장에는 저장소·토큰·암호화 키가 필요합니다. 아래 연결 안내를 확인하세요.")
        return GitHubStore(repo, branch, token, key)
    if mode == "local":
        if not key:
            raise AppError("소노클 로컬 저장에는 encryption_key가 필요합니다. 아래 연결 안내를 확인하세요.")
        return LocalStore(data_dir, key)
    raise AppError("저장 모드 설정을 확인하세요.")


def get_store(settings):
    if settings.mode == "demo":
        return memory_store()
    return persistent_store(settings.mode, settings.data_dir, settings.repo,
                            settings.branch, settings.github_token, settings.encryption_key)


def embedded_style():
    # Scope styling to the tool; keep the dashboard's own navigation/theme.
    st.markdown('''<style>
    .st-key-snorkl_workspace .lab-section{display:flex;align-items:center;gap:12px;margin:20px 0}
    .st-key-snorkl_workspace .lab-section strong{font-size:1.5rem}
    .st-key-snorkl_workspace .lab-number{display:inline-flex;align-items:center;justify-content:center;
        width:40px;height:40px;border-radius:12px;font-weight:800;color:#172124}
    .st-key-snorkl_workspace .course-title{font-size:1.05rem;font-weight:750}
    .st-key-snorkl_workspace .course-meta{opacity:.7;font-size:.9rem}
    </style>''', unsafe_allow_html=True)


def settings_help():
    st.caption("기존 [app]·[github] 설정을 지우지 말고 [snorkl]을 한 번만 추가하세요.")
    st.code('''[snorkl]
mode = "github"
encryption_key = "소노클에서 사용하던 Fernet 키 또는 새로 생성한 키"
ai_enabled = false
# 기존 대시보드의 [github] repo, branch, token을 자동 사용합니다.
# 다른 저장소를 쓰면 github_repo, github_branch, github_token을 여기에 설정하세요.''', language="toml")
    st.caption("기존 소노클 기록을 불러오려면 원래 저장소·브랜치·암호화 키를 그대로 사용하세요. 키를 바꾸면 이전 기록을 읽을 수 없습니다.")
    st.caption("원본 앱의 THINK_MODE, GITHUB_REPO, GITHUB_TOKEN, ENCRYPTION_KEY, OPENAI_API_KEY 등 최상위 Secrets도 지원합니다.")
    st.caption("데이터 형식은 유지합니다. 대시보드 CSV와 소노클 think-learning-v1/ 암호화 파일은 별도로 저장됩니다.")


def storage_notice(settings, teacher):
    if settings.mode == "local":
        st.warning("소노클은 서버의 로컬 파일에 저장됩니다. Streamlit Cloud의 영구 보관용으로 사용하지 마세요.")
    elif settings.mode == "github" and teacher:
        st.caption("저장 위치 · 비공개 GitHub의 소노클 전용 암호화 파일")


def _student_course(store, manager, course, settings, user):
    # Re-check current enrollment every run, including links and stale state.
    identity = student_identity(user, course)
    if st.button("← 내 소노클 수업 목록", key="snorkl_student_back"):
        st.session_state.pop("_snorkl_student_course", None)
        st.rerun()
    st.title(course["title"])
    st.caption(f"{user['class']} · {user['name']} · {user['id']} — 로그인한 계정으로 제출됩니다.")
    if st.button("활동 목록 새로고침", key="snorkl_student_refresh"):
        invalidate = getattr(store, "invalidate", None)
        if invalidate:
            invalidate()
        st.rerun()
    room = Classroom(store)
    tasks = [task for task in room.activities(course["id"]) if task.get("status") != "숨김"]
    if not tasks:
        st.info("선생님이 공개한 활동이 아직 없습니다.")
        return
    mapping = {task["id"]: task for task in tasks}
    key = "snorkl_student_activity_" + course["id"]
    if st.session_state.get(key) not in mapping:
        st.session_state.pop(key, None)
    aid = st.selectbox("활동 선택", list(mapping), format_func=lambda value: mapping[value]["title"], key=key)
    # Never call shared_student()/student_workbench(): those allow editable identity.
    student_preview(room, course, mapping[aid], AI(settings), identity=identity)


def student_view(store, manager, settings, user, requested):
    if requested:
        course = manager.get(requested)
        if course is None:
            st.error("공유한 수업을 찾을 수 없습니다. 삭제되었거나 보관된 수업일 수 있습니다.")
            return
        student_identity(user, course)  # fail closed for other classes
        st.session_state["_snorkl_student_course"] = course["id"]
    selected = st.session_state.get("_snorkl_student_course")
    if selected:
        course = manager.get(selected)
        if course is not None:
            _student_course(store, manager, course, settings, user)
            return
        st.session_state.pop("_snorkl_student_course", None)
        st.info("수업이 삭제되었거나 보관되었습니다.")
    st.subheader("내 소노클 수업")
    st.caption("로그인한 반에 배정된 수업만 표시됩니다.")
    courses = visible_courses(user, manager.list_courses())
    if not courses:
        st.info("아직 배정된 소노클 수업이 없습니다. 선생님이 수업을 만들고 반을 지정하면 여기에 표시됩니다.")
    for course in courses:
        with st.container(border=True):
            st.caption("참여 학급 · " + ", ".join(course["classes"]))
            if st.button(course["title"], key="snorkl_join_" + course["id"], use_container_width=True):
                st.session_state["_snorkl_student_course"] = course["id"]
                st.rerun()


def teacher_view(store, manager, settings, requested):
    if requested:
        if manager.get(requested) is None:
            st.error("공유한 수업을 찾을 수 없습니다. 삭제되었거나 보관된 수업일 수 있습니다.")
            return
        st.session_state["selected_course"] = requested
        st.session_state.pop("selected_activity", None)
    selected = st.session_state.get("selected_course")
    if selected:
        course = manager.get(selected)
        if course:
            if st.button("수업 자료·제출함 새로고침", key="snorkl_teacher_refresh"):
                invalidate = getattr(store, "invalidate", None)
                if invalidate:
                    invalidate()
                st.rerun()
            course_detail(store, course, settings)
            return
        st.session_state.pop("selected_course", None)
        st.session_state.pop("selected_activity", None)
    st.caption("수행평가 만들기 → 활동·모범답안 등록 → 학생 답안 확인·피드백")
    if settings.mode == "github":
        current, archived = st.tabs(["현재 진행 중", "보관됨"])
        with current:
            active_courses(manager)
        with archived:
            archived_courses(manager)
    else:
        active_courses(manager)


def render(user):
    if user.get("role") not in ("teacher", "student"):
        st.error("대시보드 로그인이 필요합니다.")
        return
    teacher = user["role"] == "teacher"
    st.caption("수업도구 / 3. 수행평가 · 교사 공간" if teacher else "수업도구 / 3. 수행평가 · 학생 공간")
    with st.container(key="snorkl_workspace"):
        embedded_style()
        try:
            settings = load_embedded_settings()
            storage_notice(settings, teacher)
            store = get_store(settings)
            manager = CourseManager(store)
            requested = st.session_state.pop(REQUESTED_COURSE, None)
            if teacher:
                teacher_view(store, manager, settings, requested)
            else:
                student_view(store, manager, settings, user, requested)
        except AppError as error:
            st.error(str(error))
            if teacher:
                with st.expander("소노클 저장·연결 설정 확인"):
                    settings_help()
            elif st.button("내 수업 목록으로 돌아가기", key="snorkl_denied_back"):
                st.session_state.pop("_snorkl_student_course", None)
                st.rerun()
