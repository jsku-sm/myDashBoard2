# GOOD_RECORDS_1.1_FINAL5
"""Authenticated, in-process Snorkl renderer for myDashBoard2.

No second login, app-wide page config, separate server, iframe app, or sidebar.
The original classroom editors, uploads, assessment and feedback are reused.
"""
import hashlib
import json

import streamlit as st

from . import storage as assessment_storage
from .ai import AI
from .classroom import Classroom
from .classroom_ui import course_detail, student_preview
from .courses import CourseManager
from .ownership import OwnedCourseManager
from .course_admin import active_courses, archived_courses
from .integration import load_embedded_settings, student_identity, visible_courses
from .storage import AppError, GitHubStore, LocalStore, MemoryStore
from .persistence import local_encryption_key, migrate_memory_store
from .timer_ui import student_availability_watch
from .student_drafts import capture_active_drafts
from .student_scores import render_student_scores
from snorkl_navigation import REQUESTED_COURSE


@st.cache_resource(show_spinner=False)
def memory_store():
    # Shared within this dashboard process, never a fake persistent store.
    return MemoryStore()


@st.cache_resource(show_spinner=False)
def persistent_store(mode, data_dir, repo, branch, token, key):
    if mode == "github":
        if not repo or not token:
            raise AppError("수행평가를 보관할 GitHub 저장소와 토큰이 필요합니다. 아래 연결 안내를 확인하세요.")
        return GitHubStore(repo, branch, token, key)
    if mode == "local":
        return LocalStore(data_dir, local_encryption_key(data_dir, key))
    raise AppError("저장 모드 설정을 확인하세요.")


def get_store(settings):
    mode = "local" if settings.mode == "demo" else settings.mode
    import storage as dashboard_storage
    vault_backend = dashboard_storage._ready_backend()
    if not vault_backend.is_local:
        # Verify BEFORE initializing/migrating any assessment store or its key.
        if (mode != "github" or settings.repo.casefold() != vault_backend.repo.casefold()
                or settings.branch != vault_backend.branch):
            raise AppError("수행평가도 jsku-sm/class-dashboard-data의 같은 브랜치에 연결하세요. [snorkl] mode/repo 설정과 최상위 GITHUB_REPO를 확인하세요. 원본을 다른 곳으로 자동 이동하지 않습니다.")
    elif mode == "github":
        raise AppError("대시보드와 수행평가 모두 같은 GitHub 저장소에 연결한 뒤 사용하세요.")
    arguments = (mode, settings.data_dir, settings.repo,
                 settings.branch, settings.github_token, settings.encryption_key)
    store = persistent_store(*arguments)
    expected_type = assessment_storage.LocalStore if mode == "local" else assessment_storage.GitHubStore
    if not isinstance(store, expected_type):
        # Streamlit can retain an instance of the previous module's class after
        # hot reload. Keep its object and locks for in-flight student writers.
        old_type = type(store)
        if old_type.__module__ != expected_type.__module__ or old_type.__name__ != expected_type.__name__:
            raise AppError("수행평가 저장소 연결을 확인하세요. 기존 보관 자료는 유지됩니다.")
        lock = store.lock if mode == "local" else store._read_lock
        with lock:
            try:
                store.__class__ = expected_type
            except TypeError:
                raise AppError("수행평가 저장소를 다시 연결하지 못했습니다. 앱을 다시 실행하면 기존 보관 자료를 불러옵니다.") from None
    store.read()
    # The unchanged cached factory lets a running app recover its previous
    # memory-only records when this update is loaded.
    migrate_memory_store(memory_store(), store)
    if mode == "github":
        from record_core.assessment import bind
        bind(store, vault_backend)
    return store


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
ai_enabled = false
# 기존 대시보드의 [github] repo, branch, token을 자동 사용합니다.
# 기존 암호화 자료가 있을 때만 원래 encryption_key를 추가하세요.
# 저장소·브랜치는 대시보드와 동일하게 연결합니다.''', language="toml")
    st.caption("기존 소노클 기록을 불러오려면 원래 저장소·브랜치·암호화 키를 그대로 사용하세요. 키를 바꾸면 이전 기록을 읽을 수 없습니다.")
    st.caption("원본 앱의 THINK_MODE, GITHUB_REPO, GITHUB_TOKEN, ENCRYPTION_KEY, OPENAI_API_KEY 등 최상위 Secrets도 지원합니다.")
    st.caption("데이터 형식은 유지합니다. 대시보드 CSV와 소노클 think-learning-v1/ 암호화 파일은 별도로 저장됩니다.")
    st.caption("새 보관 공간의 암호화 키는 비공개 저장소에 함께 보관해 재시작 후에도 같은 자료를 불러옵니다.")


def storage_notice(settings, teacher):
    if settings.mode in ("local", "demo") and teacher:
        st.caption("수행평가 자료 자동 저장 · 앱을 다시 실행하면 저장된 자료를 불러옵니다.")
        with st.expander("자료 보관 위치"):
            st.caption("현재 서버에 암호화해 보관합니다. Streamlit Cloud에서 운영할 때는 GitHub 저장소를 연결하세요.")
            settings_help()
    elif settings.mode == "github" and teacher:
        st.caption("저장 위치 · 비공개 GitHub의 소노클 전용 암호화 파일")


def _student_course(store, manager, course, settings, user):
    # Re-check current enrollment every run, including links and stale state.
    identity = student_identity(user, course)
    capture_active_drafts(course["id"], identity)
    if st.button("이전메뉴로 돌아가기", key="snorkl_student_back"):
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
    activities = room.activities(course["id"])
    key = "snorkl_student_activity_" + course["id"]
    actor = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:16]
    selected_key = "snorkl_student_selected_" + course["id"] + "_" + actor
    selected_id = st.session_state.get(key, st.session_state.get(selected_key))
    if selected_id:
        st.session_state[selected_key] = selected_id
    previously_selected = next((task for task in activities if task["id"] == selected_id), None)
    ended_notice = "선생님이 평가를 종료했습니다."
    selected_ended = bool(previously_selected and
                          room.student_unavailable_notice(previously_selected) == ended_notice)
    tasks = [task for task in activities
             if room.student_activity_available(task)]
    if not tasks:
        ended = selected_ended or any(room.student_unavailable_notice(task) == ended_notice for task in activities)
        st.info(ended_notice if ended else "수행평가 기간이 아닙니다.")
        student_availability_watch(room, course["id"], closed=True)
        return
    mapping = {task["id"]: task for task in tasks}
    if selected_ended:
        # Keep the student's ended selection until they choose another activity;
        # student_preview displays the notice without exposing its editor.
        mapping = {previously_selected["id"]: previously_selected, **mapping}
    if st.session_state.get(key) not in mapping:
        st.session_state.pop(key, None)
        if st.session_state.get(selected_key) in mapping:
            st.session_state[key] = st.session_state[selected_key]
    aid = st.selectbox("활동 선택", list(mapping), format_func=lambda value: mapping[value]["title"], key=key)
    st.session_state[selected_key] = aid
    # Never call shared_student()/student_workbench(): those allow editable identity.
    student_preview(room, course, mapping[aid], AI(settings), identity=identity)


def student_view(store, manager, settings, user, requested):
    if requested:
        # A home/share shortcut opens the requested activity even if the student
        # was last viewing their score report.
        st.session_state.pop("_snorkl_student_scores", None)
    selected_course = manager.get(st.session_state.get("_snorkl_student_course"))
    if selected_course is not None:
        # Capture edits before navigation hides the student editor's widgets.
        from .integration import matching_class
        if matching_class(user, selected_course) is not None:
            capture_active_drafts(selected_course["id"], student_identity(user, selected_course))
    if st.session_state.get("_snorkl_student_scores"):
        if st.button("수행평가로 돌아가기", key="snorkl_student_scores_back"):
            st.session_state.pop("_snorkl_student_scores", None)
            st.rerun()
        render_student_scores(store, user)
        return
    if st.button("내 점수 확인하기", key="snorkl_student_scores_open", use_container_width=True):
        st.session_state["_snorkl_student_scores"] = True
        st.rerun()
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
    st.caption("로그인한 반에 배정된 수업만 표시됩니다.")
    courses = visible_courses(user, manager.list_courses())
    if not courses:
        st.info("아직 배정된 소노클 수업이 없습니다. 선생님이 수업을 만들고 반을 지정하면 여기에 표시됩니다.")
        st.info("수행평가 기간이 아닙니다.")
    room = Classroom(store)
    student_availability_watch(room)
    for course in courses:
        activities = room.activities(course["id"])
        available = any(room.student_activity_available(task)
                        for task in activities)
        with st.container(border=True):
            st.caption("참여 학급 · " + ", ".join(course["classes"]))
            if not available:
                notice = next((room.student_unavailable_notice(task) for task in activities
                               if room.student_unavailable_notice(task) == "선생님이 평가를 종료했습니다."),
                              "수행평가 기간이 아닙니다.")
                st.info(notice)
            if st.button(course["title"], key="snorkl_join_" + course["id"],
                         use_container_width=True, disabled=not available) and available:
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
    with st.container(key="snorkl_workspace"):
        embedded_style()
        try:
            settings = load_embedded_settings()
            storage_notice(settings, teacher)
            store = get_store(settings)
            manager = OwnedCourseManager(store, user) if teacher else CourseManager(store)
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
