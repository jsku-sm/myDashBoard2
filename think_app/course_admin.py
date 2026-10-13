"""Teacher-only course administration reused from the uploaded Snorkl app.
Called only by the authenticated embedded teacher route.
"""
from datetime import datetime
from io import BytesIO
import html
import qrcode
import streamlit as st
from .courses import COLORS, DASHBOARD_CLASSES as CLASSES, CourseManager
from .storage import AppError
from .integration import course_url


def render_share(course):
    st.subheader("수업 공유")
    st.caption("이 주소로 들어온 학생도 대시보드 로그인 후, 등록된 반의 수업에만 참여합니다.")
    try:
        url = course_url(st.context.url, course["id"])
    except AppError as error:
        st.warning(str(error))
        return
    st.code(url, language=None)
    image = BytesIO()
    qrcode.make(url).save(image, format="PNG")
    st.image(image.getvalue(), caption="대시보드 로그인 → 소노클 수업", width=220)


def formatted_date(value: str) -> str:
    try:
        date = datetime.fromisoformat(value)
        return f"{date.year}년 {date.month}월 {date.day}일"
    except (TypeError, ValueError):
        return value


def create_form(manager: CourseManager):
    with st.form("create_course"):
        title = st.text_input("수행평가 이름", max_chars=120)
        st.caption("‘데스모스’ 또는 ‘Desmos’가 포함된 이름은 그래프 작업 화면으로 바로 연결됩니다.")
        color = st.color_picker("수행평가 이름 앞에 표시할 색상", value=COLORS[0])
        selected_classes = st.multiselect("참여할 수 있는 대상", CLASSES, default=[CLASSES[0]])
        submitted = st.form_submit_button("수행평가 만들기", type="primary")
    if submitted:
        try:
            manager.create(title, color, selected_classes)
            st.session_state.pop("show_create_form", None)
            st.success("수행평가를 만들었습니다.")
            st.rerun()
        except AppError as error:
            st.error(str(error))


def edit_form(manager: CourseManager, course: dict):
    with st.form("edit_course_" + course["id"]):
        title = st.text_input("수업 이름", value=course["title"], max_chars=120)
        color = st.color_picker(
            "수업 이름 앞에 표시할 색상",
            value=course["color"],
            key="course_color_" + course["id"],
        )
        selected_classes = st.multiselect(
            "참여할 수 있는 대상",
            list(dict.fromkeys(CLASSES + course["classes"])),
            default=course["classes"],
            key="course_classes_" + course["id"],
        )
        left, right = st.columns(2)
        save = left.form_submit_button("수정 저장", type="primary")
        cancel = right.form_submit_button("취소")
    if save:
        try:
            manager.update(course["id"], title, color, selected_classes)
            st.session_state.pop("editing_course", None)
            st.success("수업 정보를 수정했습니다.")
            st.rerun()
        except AppError as error:
            st.error(str(error))
    if cancel:
        st.session_state.pop("editing_course", None)
        st.rerun()


def delete_confirmation(manager: CourseManager):
    pending = st.session_state.get("delete_course")
    course = manager.get(pending) if pending else None
    if not course:
        return
    st.warning(f"‘{course['title']}’ 수업을 삭제할까요? 삭제한 수업은 복구할 수 없습니다.")
    confirm, cancel = st.columns(2)
    if confirm.button("수업 삭제", type="primary", key="confirm_delete_course"):
        try:
            manager.delete(course["id"])
            st.session_state.pop("delete_course", None)
            st.success("수업을 삭제했습니다.")
            st.rerun()
        except AppError as error:
            st.error(str(error))
    if cancel.button("취소", key="cancel_delete_course"):
        st.session_state.pop("delete_course", None)
        st.rerun()


def archive_confirmation(manager: CourseManager):
    pending = st.session_state.get("archive_course")
    course = manager.get(pending) if pending else None
    if not course:
        return
    st.info(f"‘{course['title']}’ 수업을 GitHub 보관 공간에 저장합니다.")
    confirm, cancel = st.columns(2)
    if confirm.button("GitHub에 보관", type="primary", key="confirm_archive_course"):
        try:
            manager.archive(course["id"])
            st.session_state.pop("archive_course", None)
            st.success("수업 파일을 GitHub에 보관했습니다.")
            st.rerun()
        except AppError as error:
            st.error(str(error))
    if cancel.button("취소", key="cancel_archive_course"):
        st.session_state.pop("archive_course", None)
        st.rerun()


def active_courses(manager: CourseManager):
    courses = manager.list_courses()
    if st.button("＋ 수행평가 만들기", type="primary", key="create_assessment"):
        st.session_state.show_create_form = not st.session_state.get("show_create_form", False)
    if st.session_state.get("show_create_form"):
        create_form(manager)

    if courses:
        name_header, updated_header, _ = st.columns([4.6, 2.1, 2.1])
        name_header.caption("수업 이름 · 참여 학급")
        updated_header.caption("마지막 업데이트")
    for course in courses:
        name, updated, share, edit, menu = st.columns([4.6, 2.1, 0.7, 0.7, 0.7])
        if name.button(course["title"], key="open_course_" + course["id"], use_container_width=True):
            st.session_state.selected_course = course["id"]
            st.session_state.pop("selected_activity", None)
            st.session_state.pop("show_guide", None)
            st.rerun()
        name.markdown(f'<span style="color:{course["color"]}">●</span> ' + html.escape(", ".join(course["classes"])), unsafe_allow_html=True)
        updated.markdown(formatted_date(course["updated"]))
        if share.button("공유", key="share_" + course["id"], help="수업 링크와 QR 코드"):
            st.session_state.sharing_course = course["id"]
        if edit.button("수정", key="edit_" + course["id"]):
            st.session_state.editing_course = course["id"]
        with menu.popover("⋯", help="수업 메뉴"):
            if st.button("수업 보관", key="archive_" + course["id"], use_container_width=True):
                st.session_state.archive_course = course["id"]
            if st.button("삭제", key="delete_" + course["id"], use_container_width=True):
                st.session_state.delete_course = course["id"]
        if st.session_state.get("sharing_course") == course["id"]:
            with st.expander("공유 주소 및 QR 코드", expanded=True):
                render_share(course)
        if st.session_state.get("editing_course") == course["id"]:
            edit_form(manager, course)
    delete_confirmation(manager)
    archive_confirmation(manager)


def archived_courses(manager: CourseManager):
    try:
        archives = manager.list_archives()
    except AppError as error:
        st.error(str(error))
        return
    if not archives:
        st.info("보관된 수업이 없습니다.")
        return
    for archive in archives:
        col, restore = st.columns([5, 1])
        course = archive["course"]
        col.markdown(
            f'<div class="course-title"><span style="color:{course["color"]}">●</span> '
            f'{html.escape(course["title"])}</div><div class="course-meta">'
            f'보관일 {formatted_date(archive["archived_at"])} · '
            f'{html.escape(", ".join(course["classes"]))}</div>',
            unsafe_allow_html=True,
        )
        if restore.button("불러오기", key="restore_" + archive["id"]):
            try:
                manager.restore(archive["id"])
                st.success("보관된 수업을 불러왔습니다.")
                st.rerun()
            except AppError as error:
                st.error(str(error))
