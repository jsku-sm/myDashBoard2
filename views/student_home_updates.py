"""Recent teacher updates shown above the student home's existing feedback."""
from datetime import datetime
import hashlib
import json
import re

import streamlit as st

import auth
import storage as db
import ui
from config import TZ
from snorkl_navigation import REQUESTED_COURSE, open_snorkl
from student_updates import build_student_updates


PENDING_NAVIGATION = "_student_home_navigation"


def apply_pending_navigation(user):
    """Apply a home shortcut before the sidebar's nav widget is instantiated."""
    request = st.session_state.pop(PENDING_NAVIGATION, None)
    if (not isinstance(request, dict) or user.get("role") != "student" or
            request.get("student_id") != user.get("id") or request.get("class") != user.get("class")):
        return
    cid, aid = request.get("course_id"), request.get("activity_id")
    if not all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) for value in (cid, aid)):
        return
    open_snorkl(st.session_state, st.query_params)
    st.session_state["nav"] = "tools"
    st.session_state[REQUESTED_COURSE] = cid
    st.session_state["snorkl_student_activity_" + cid] = aid


def _assessment_state():
    from think_app.embedded import get_store
    from think_app.integration import load_embedded_settings
    return get_store(load_embedded_settings()).read()


def _date_label(value):
    if not value:
        return ""
    try:
        instant = datetime.fromisoformat(value)
        instant = instant.replace(tzinfo=TZ) if instant.tzinfo is None else instant.astimezone(TZ)
        return instant.strftime("%m.%d %H:%M")
    except (TypeError, ValueError):
        return ""


def _content(text):
    if len(text) <= 180:
        st.write(text)
    else:
        st.write(text[:180] + "…")
        with st.popover("글 전체 읽기"):
            st.write(text)


def _document(item):
    if not item["file_id"]:
        return
    name = item["file_name"] or "파일"
    data = db.load_file_cached(item["file_id"])
    st.download_button(name, data=data if data is not None else b"", file_name=name,
                       mime=item["mime"] or None, key="home_document_" + item["id"],
                       type="tertiary", width="stretch", on_click="ignore", disabled=data is None,
                       help="파일을 찾을 수 없어요. 선생님께 문의해 주세요." if data is None else None)


def _feedback(item):
    with st.container(border=True):
        ui.note(f"<b>{ui.esc(item['title'])}</b>", "mint")
        kind = "질문 답변" if item["source"] == "question" else "수행평가 피드백" if item["source"] == "assessment" else "게시판 피드백"
        st.caption(" · ".join(value for value in
                             (item["subject"] or item["course_title"], kind, _date_label(item["updated_at"])) if value))
        _content(item["content"])
        if item["student_feedback"] and item["student_feedback"] != item["content"]:
            st.caption("풀이 피드백")
            _content(item["student_feedback"])


def _assessment(item, user):
    with st.container(border=True):
        ui.note(f"<b>{ui.esc(item['title'])}</b>", "yellow")
        st.caption(item["course_title"])
        if item["phase"] == "ended":
            label = "평가 종료"
        elif item.get("period") == "scheduled":
            label = "시작 예정"
        elif item.get("period") == "closed":
            label = "기간 종료"
        elif item.get("period") == "invalid":
            label = "평가 기간 확인 필요"
        elif item["available"]:
            label = ("보기만 가능" if item["status"] == "보기만 가능" else
                     "제출 완료" if item["attempt_count"] >= item["max_attempts"] else "참여 가능")
        elif item["phase"] == "waiting":
            label = "평가 시작 대기"
        elif item["phase"] == "expired":
            label = "풀이 시간 종료"
        else:
            label = "기간 대기·종료"
        st.write(label)
        st.caption(item["start"] + " ~ " + (item["end"] or "마감일 없음"))
        st.caption(f"나의 제출 {item['attempt_count']}회 / 최대 {item['max_attempts']}회")
        if item["notice"] and not item["available"]:
            st.caption(item["notice"])
        if st.button("수행평가 열기", key="home_assessment_" + item["id"], disabled=not item["available"],
                     use_container_width=True):
            st.session_state[PENDING_NAVIGATION] = {
                "student_id": user["id"], "class": user["class"],
                "course_id": item["course_id"], "activity_id": item["id"],
            }
            st.rerun(scope="app")


def _announcement(item):
    with st.container(border=True):
        ui.note(f"<b>{ui.esc(item['title'])}</b>", "yellow")
        st.caption(" · ".join(value for value in (item["author_name"], _date_label(item["updated_at"])) if value))
        _content(item["content"])


def _items(items, render, empty):
    if not items:
        st.caption(empty)
        return
    for item in items[:2]:
        render(item)
    if len(items) > 2:
        with st.expander(f"더 보기 · {len(items) - 2}건"):
            for item in items[2:]:
                render(item)


@st.fragment(run_every="10s")
def render_student_updates(user):
    if user.get("role") != "student":
        return
    current = auth.get_user(user.get("id"))
    if (not current or current.get("role") != "student" or
            current.get("class") != user.get("class") or current.get("must_change") == "1"):
        st.rerun(scope="app")
        return
    from think_app.storage import AppError
    unavailable = False
    try:
        state = _assessment_state()
    except AppError:
        state, unavailable = {}, True
    updates = build_student_updates(user, db.read("materials"), db.read("submissions"),
                                    db.read("questions"), db.read("announcements"), state)
    signature = hashlib.sha256(json.dumps((updates, unavailable), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    signature_key = "_student_home_updates_signature_" + user["id"] + "_" + user["class"]
    previous = st.session_state.get(signature_key)
    st.session_state[signature_key] = signature
    if previous is not None and previous != signature:
        # Refresh the original recent-feedback section as well, so an edited
        # teacher comment cannot appear differently in the two home sections.
        st.rerun(scope="app")
        return
    st.markdown("#### 선생님 소식")
    st.caption("선생님이 올린 자료와 나에게 남긴 피드백, 수행평가와 공지를 확인하세요.")
    documents, feedback = st.columns(2, gap="large")
    with documents:
        st.markdown("##### 📄 배포 문서")
        if not updates["documents"]:
            st.caption("아직 배포된 문서가 없어요.")
        for item in updates["documents"][:5]:
            _document(item)
    with feedback:
        st.markdown("##### 💬 선생님 피드백")
        _items(updates["feedback"], _feedback, "아직 선생님이 남긴 피드백이 없어요.")
    assessments, announcements = st.columns(2, gap="large")
    with assessments:
        st.markdown("##### 📝 수행평가 배포 현황")
        if unavailable:
            st.info("수행평가 소식을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.")
        else:
            _items(updates["assessments"], lambda item: _assessment(item, user), "아직 우리 반에 배포된 수행평가가 없어요.")
    with announcements:
        st.markdown("##### 📢 공지글")
        _items(updates["announcements"], _announcement, "아직 우리 반에 올라온 공지가 없어요.")
