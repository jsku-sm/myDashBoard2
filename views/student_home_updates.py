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


def _preview(text):
    text = " ".join(text.split())
    preview = text if len(text) <= 88 else text[:87] + "…"
    st.markdown(f'<p class="home-preview">{ui.esc(preview)}</p>', unsafe_allow_html=True)


def select_home_item(items, category, user, label, title):
    """Render one item, retaining history without constructing every old card."""
    key = "home_select_" + category + "_" + user["id"] + "_" + user["class"]
    by_id = {}
    for item in items:
        identity = (item["source"] + ":" + item["id"]) if category == "feedback" else item["id"]
        by_id.setdefault(identity, item)
    options = list(by_id)
    if not options:
        st.session_state.pop(key, None)
        st.session_state.pop(key + "_latest", None)
        st.selectbox(label, [], key=key, disabled=True, placeholder="아직 등록된 글이 없어요.",
                     label_visibility="collapsed")
        return None
    previous_latest = st.session_state.get(key + "_latest")
    selected = st.session_state.get(key)
    if selected not in by_id:
        st.session_state.pop(key, None)
    elif selected == previous_latest and previous_latest != options[0]:
        # Follow new posts while the latest is selected; keep an older post
        # the student has deliberately chosen until it is hidden or deleted.
        st.session_state[key] = options[0]
    st.session_state[key + "_latest"] = options[0]
    titles = [title(by_id[value]) for value in options]
    # Streamlit serializes choices by their displayed labels. Distinguish
    # repeated filenames/titles so choosing an older record selects that one.
    labels = dict(zip(options, titles if len(set(titles)) == len(titles) else
                      [f"{index + 1:02d} · {text}" for index, text in enumerate(titles)]))
    chosen = st.selectbox(label, options, format_func=labels.get,
                          key=key, label_visibility="collapsed")
    return by_id[chosen]


def _heading(title, count):
    name, number = st.columns([5, 1], vertical_alignment="center", gap="small")
    name.markdown(title)
    number.markdown(f'<span class="home-count">{count}건</span>', unsafe_allow_html=True)


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
    kind = "질문 답변" if item["source"] == "question" else "수행평가 피드백" if item["source"] == "assessment" else "게시판 피드백"
    st.caption(" · ".join(value for value in (kind, _date_label(item["updated_at"])) if value))
    _preview(item["content"])
    with st.popover("피드백 전체 읽기", width="stretch"):
        st.markdown(f"**{ui.esc(item['title'])}**")
        st.write(item["content"])
        if item["student_feedback"] and item["student_feedback"] != item["content"]:
            st.caption("풀이 피드백")
            st.write(item["student_feedback"])


def _assessment(item, user):
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
    st.caption(f"{label} · 제출 {item['attempt_count']} / {item['max_attempts']}회")
    if item["notice"] and not item["available"]:
        _preview(item["notice"])
    else:
        _preview(item["start"] + " ~ " + (item["end"] or "마감일 없음"))
    if st.button("수행평가 열기", key="home_assessment_" + item["id"], disabled=not item["available"],
                 width="stretch"):
        st.session_state[PENDING_NAVIGATION] = {
            "student_id": user["id"], "class": user["class"],
            "course_id": item["course_id"], "activity_id": item["id"],
        }
        st.rerun(scope="app")


def _announcement(item):
    st.caption(" · ".join(value for value in (item["author_name"], _date_label(item["updated_at"])) if value))
    _preview(item["content"])
    with st.popover("공지 전체 읽기", width="stretch"):
        st.markdown(f"**{ui.esc(item['title'])}**")
        st.write(item["content"])


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
    with st.container(key="home_updates", gap="small"):
        st.markdown('<p class="home-section-label">선생님 소식 <span>목록에서 이전 글도 확인할 수 있어요</span></p>',
                    unsafe_allow_html=True)
        documents, feedback = st.columns(2, gap="small")
        with documents, st.container(border=True, key="home_documents", gap="small"):
            _heading("##### 📄 배포 문서", len(updates["documents"]))
            selected = select_home_item(updates["documents"], "documents", user, "배포 문서 선택",
                                        lambda item: item["file_name"] or item["title"] or "첨부 문서")
            if selected:
                st.caption(" · ".join(value for value in
                                     (selected["subject"], selected["category"], _date_label(selected["uploaded_at"])) if value))
                _document(selected)
            else:
                st.caption("아직 배포된 문서가 없어요.")
        with feedback, st.container(border=True, key="home_feedback", gap="small"):
            _heading("##### 💬 선생님 피드백", len(updates["feedback"]))
            selected = select_home_item(updates["feedback"], "feedback", user, "선생님 피드백 선택",
                                        lambda item: item["title"] or "선생님 피드백")
            if selected:
                _feedback(selected)
            else:
                st.caption("아직 선생님이 남긴 피드백이 없어요.")
        assessments, announcements = st.columns(2, gap="small")
        with assessments, st.container(border=True, key="home_assessments", gap="small"):
            _heading("##### 📝 수행평가 배포 현황", len(updates["assessments"]))
            if unavailable:
                select_home_item([], "assessments", user, "수행평가 선택", lambda item: item["title"])
                st.caption("수행평가 소식을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.")
            else:
                selected = select_home_item(updates["assessments"], "assessments", user, "수행평가 선택",
                                            lambda item: item["title"] or item["course_title"])
                if selected:
                    _assessment(selected, user)
                else:
                    st.caption("아직 우리 반에 배포된 수행평가가 없어요.")
        with announcements, st.container(border=True, key="home_announcements", gap="small"):
            _heading("##### 📢 공지글", len(updates["announcements"]))
            selected = select_home_item(updates["announcements"], "announcements", user, "공지글 선택",
                                        lambda item: item["title"] or "우리 반 공지")
            if selected:
                _announcement(selected)
            else:
                st.caption("아직 우리 반에 올라온 공지가 없어요.")
