"""Class announcement popups with durable, per-student acknowledgements."""
import hashlib
import json

import streamlit as st

import auth
import storage as db
from student_updates import build_student_updates


def _current_student(user):
    if not isinstance(user, dict) or user.get("role") != "student" or not user.get("id"):
        return None
    db.invalidate("users")
    current = auth.get_user(user["id"])
    if (not current or current.get("role") != "student" or not current.get("class") or
            current.get("must_change") == "1"):
        return None
    return current


def _visible_announcements(user):
    return build_student_updates(user, [], [], [], db.read("announcements"), {})["announcements"]


def _revision(item):
    # Include content so edits made within the same timestamp still notify.
    values = [item.get(field, "") for field in
              ("id", "title", "content", "author_name", "updated_at")]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def pending_announcements(user):
    current = _current_student(user)
    if current is None:
        return []
    read = {(row["announcement_id"], row["revision"]) for row in db.read("announcement_reads")
            if row["student_id"] == current["id"]}
    return [item for item in _visible_announcements(current)
            if item["id"] and (item["id"], _revision(item)) not in read]


def acknowledge_announcements(user, items):
    """Acknowledge only the revisions still visible to this current account."""
    current = _current_student(user)
    if current is None:
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


@st.dialog("📢 선생님 공지", width="large", dismissible=False)
def _announcement_dialog(user, displayed):
    # Dialog interactions rerun independently: recheck visibility before render.
    pending = pending_announcements(user)
    if (not pending or
            [(item["id"], _revision(item)) for item in pending] !=
            [(item["id"], _revision(item)) for item in displayed]):
        # A click on an older dialog must not acknowledge a newly edited post.
        st.rerun(scope="app")
        return
    st.caption("우리 반에 새로 올라온 공지예요. 내용을 읽고 확인해 주세요.")
    for index, item in enumerate(pending):
        if index:
            st.divider()
        st.subheader(item["title"])
        st.caption(" · ".join(value for value in (item["author_name"], item["updated_at"]) if value))
        st.write(item["content"])
    if st.button("확인했어요", key="acknowledge_announcements", type="primary", width="stretch"):
        acknowledge_announcements(user, displayed)
        st.rerun(scope="app")


def show_announcement_popup(user):
    pending = pending_announcements(user)
    if pending:
        _announcement_dialog(user, pending)


def poll_announcements(user):
    """Used by the global student poller, including outside the home page."""
    pending = pending_announcements(user)
    signature = tuple((item["id"], _revision(item)) for item in pending)
    key = "_student_announcement_signature_" + user["id"]
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    if previous is not None and previous != signature:
        st.rerun(scope="app")
