"""Class announcement popups with durable, per-student acknowledgements."""
import hashlib
import json

import streamlit as st

import auth
import storage as db
from announcement_ui import CSS as ANNOUNCEMENT_CSS, header_html
from student_updates import build_student_updates


def _current_student(user):
    if not isinstance(user, dict) or user.get("role") != "student" or not user.get("id"):
        return None
    db.invalidate("users")
    current = auth.get_user(user["id"])
    if (not current or current.get("role") != "student" or current.get("must_change") == "1"):
        return None
    return current


def _visible_announcements(user):
    return build_student_updates(user, [], [], [], db.read("announcements"), {})["announcements"]


def _revision(item):
    # Include content so edits made within the same timestamp still notify.
    values = [item.get(field, "") for field in
              ("id", "title", "content", "author_name", "updated_at")]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def _displayed_key(user):
    return "_student_announcement_displayed_" + user["id"]


def pending_announcements(user):
    current = _current_student(user)
    if current is None or not current.get("class"):
        return []
    read = {(row["announcement_id"], row["revision"]) for row in db.read("announcement_reads")
            if row["student_id"] == current["id"]}
    return [item for item in _visible_announcements(current)
            if item["id"] and (item["id"], _revision(item)) not in read]


def acknowledge_announcements(user, items):
    """Acknowledge only the revisions still visible to this current account."""
    current = _current_student(user)
    if current is None or not current.get("class"):
        return
    visible = {item["id"]: item for item in _visible_announcements(current)}
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        latest = visible.get(item["id"])
        if latest is None or _revision(latest) != _revision(item):
            continue
        identifier = hashlib.sha256(json.dumps([current["id"], item["id"]]).encode()).hexdigest()
        values = dict(student_id=current["id"], announcement_id=item["id"],
                      revision=_revision(latest), read_at=db.now_str())
        if not db.update("announcement_reads", identifier, values):
            db.append("announcement_reads", dict(id=identifier, **values))


@st.dialog("💌 선생님의 알림 편지", width="large", dismissible=False)
def _announcement_dialog(user, displayed):
    # Dialog interactions rerun independently: recheck visibility before render.
    pending = pending_announcements(user)
    if (not pending or
            [(item["id"], _revision(item)) for item in pending] !=
            [(item["id"], _revision(item)) for item in displayed]):
        # A click on an older dialog must not acknowledge a newly edited post.
        st.session_state[_displayed_key(user)] = pending
        st.rerun(scope="app")
        return
    st.markdown(ANNOUNCEMENT_CSS, unsafe_allow_html=True)
    st.markdown('<span class="good-notice-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
    import streamlit.components.v1 as components
    components.html(header_html(), height=120, scrolling=False)
    st.markdown(f'<div class="good-notice-intro"><span class="good-notice-count">새 편지 {len(pending)}개</span><br>'
                '우리 반에 도착한 선생님의 이야기예요.<br>차근차근 읽고, 확인 버튼을 눌러 주세요.</div>', unsafe_allow_html=True)
    for index, item in enumerate(pending):
        # User-entered text stays in Streamlit's safe text/Markdown path.
        card_key = "good_notice_card_" + hashlib.sha256(item["id"].encode()).hexdigest()[:16]
        with st.container(key=card_key):
            st.caption(f"LETTER {index + 1:02d} · " + " · ".join(value for value in
                       (item["author_name"], item["updated_at"]) if value))
            st.subheader(item["title"])
            st.write(item["content"])
    st.markdown('<p class="good-notice-footer">확인한 공지는 홈의 공지 목록에서 다시 볼 수 있어요.</p>', unsafe_allow_html=True)
    if st.button("확인했어요", key="acknowledge_announcements", type="primary", width="stretch"):
        acknowledge_announcements(user, displayed)
        st.session_state.pop(_displayed_key(user), None)
        st.rerun(scope="app")


def show_announcement_popup(user):
    pending = pending_announcements(user)
    if pending:
        key = _displayed_key(user)
        # Retain what was shown even if a click triggers a full app rerun.
        displayed = st.session_state.setdefault(key, pending)
        _announcement_dialog(user, displayed)
    elif isinstance(user, dict) and user.get("id"):
        st.session_state.pop(_displayed_key(user), None)


def poll_announcements(user):
    """Used by the global student poller, including outside the home page."""
    current = _current_student(user)
    if current is None or any(current.get(field) != user.get(field) for field in ("role", "class")):
        # Reapply account/password and class lock checks even with no notices.
        st.rerun(scope="app")
        return
    pending = pending_announcements(user)
    signature = tuple((item["id"], _revision(item)) for item in pending)
    key = "_student_announcement_signature_" + user["id"]
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    if previous is not None and previous != signature:
        st.rerun(scope="app")
