"""Teacher-authored announcements persisted in the dashboard's shared store."""
import json

import streamlit as st

import auth
import storage as db
import ui
from config import CLASSES


MAX_TITLE_CHARS = 120
MAX_CONTENT_CHARS = 10_000


def _require_teacher(user):
    if not isinstance(user, dict) or user.get("role") != "teacher" or not user.get("id"):
        raise PermissionError("선생님만 공지를 관리할 수 있어요.")
    db.invalidate("users")
    current = auth.get_user(user["id"])
    if not current or current.get("role") != "teacher":
        raise PermissionError("선생님만 공지를 관리할 수 있어요.")
    return current


def announcement_classes(row):
    """Return the stored class list, excluding malformed or unknown targets."""
    try:
        targets = json.loads(row.get("classes", ""))
    except (TypeError, ValueError):
        return []
    if (not isinstance(targets, list) or any(not isinstance(value, str) or value not in CLASSES for value in targets)
            or len(set(targets)) != len(targets)):
        return []
    return targets


def list_announcements():
    return sorted(db.read("announcements"),
                  key=lambda row: (row.get("updated_at") or row.get("created_at", ""),
                                   row.get("created_at", ""), row.get("id", "")), reverse=True)


def _find(announcement_id):
    if not isinstance(announcement_id, str) or not announcement_id:
        raise ValueError("수정하거나 삭제할 공지를 확인해 주세요.")
    row = next((item for item in db.read("announcements") if item["id"] == announcement_id), None)
    if row is None:
        raise ValueError("공지를 찾을 수 없어요. 목록을 새로 확인해 주세요.")
    return row


def save_announcement(user, title, content, classes, active=True, announcement_id=None):
    """Create or update a class announcement after rechecking its teacher."""
    teacher = _require_teacher(user)
    if (not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_CHARS or
            not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT_CHARS):
        raise ValueError("공지 제목은 1~120자, 내용은 1~10,000자로 입력해 주세요.")
    if (not isinstance(classes, (list, tuple)) or not classes or
            any(not isinstance(value, str) or value not in CLASSES for value in classes) or
            len(set(classes)) != len(classes)):
        raise ValueError("공지 대상 학급을 하나 이상 선택해 주세요.")
    if type(active) is not bool:
        raise ValueError("공지 공개 여부를 확인해 주세요.")
    values = {
        "title": title.strip(), "content": content.strip(),
        "classes": json.dumps([value for value in CLASSES if value in classes], ensure_ascii=False),
        "active": "1" if active else "0", "updated_at": db.now_str(),
    }
    if announcement_id is None:
        values.update(created_at=values["updated_at"], author_id=teacher["id"],
                      author_name=teacher.get("name") or "선생님")
        return db.append("announcements", values)
    _find(announcement_id)
    if not db.update("announcements", announcement_id, values):
        raise ValueError("공지 저장 전에 삭제되었어요. 목록을 새로 확인해 주세요.")
    return announcement_id


def delete_announcement(user, announcement_id):
    _require_teacher(user)
    _find(announcement_id)
    db.delete("announcements", announcement_id)


def tab_announcements(user):
    try:
        _require_teacher(user)
    except PermissionError as error:
        st.error(str(error))
        return
    if st.session_state.pop("_announcement_clear_new", False):
        for suffix in ("title", "content", "classes", "active"):
            st.session_state.pop("announcement_new_" + suffix, None)
    if "_announcement_notice" in st.session_state:
        st.success(st.session_state.pop("_announcement_notice"))
    st.caption("선택한 학급의 학생 홈에 공지를 표시합니다.")
    with st.form("announcement_create_form"):
        title = st.text_input("공지 제목", max_chars=MAX_TITLE_CHARS, key="announcement_new_title")
        content = st.text_area("공지 내용", height=150, max_chars=MAX_CONTENT_CHARS,
                               key="announcement_new_content")
        classes = st.multiselect("공지 대상 학급", CLASSES, default=CLASSES,
                                 key="announcement_new_classes")
        active = st.checkbox("학생에게 공개", value=True, key="announcement_new_active")
        create = st.form_submit_button("공지 저장", type="primary", key="announcement_create_save")
    if create:
        try:
            save_announcement(user, title, content, classes, active)
        except (PermissionError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state["_announcement_notice"] = "공지를 저장했어요. 선택한 학급의 학생 홈에서 확인할 수 있어요." if active else "공지를 비공개로 저장했어요."
            st.session_state["_announcement_clear_new"] = True
            st.rerun()
    st.markdown("#### 공지 목록")
    scope = st.selectbox("대상 학급으로 보기", ["전체"] + CLASSES, key="announcement_filter_class")
    rows = [row for row in list_announcements() if scope == "전체" or scope in announcement_classes(row)]
    if not rows:
        st.info("작성된 공지가 없어요.")
    for row in rows:
        with st.container(border=True):
            st.markdown("**" + ui.esc(row["title"]) + "**")
            st.caption(("공개" if row["active"] == "1" else "비공개") + " · " +
                       ", ".join(announcement_classes(row)) + " · " + row["author_name"] + " · " +
                       (row["updated_at"] or row["created_at"])[:16])
            st.write(row["content"])
            prefix = "announcement_edit_" + row["id"]
            with st.expander("공지 수정"):
                with st.form(prefix + "_form"):
                    changed_title = st.text_input("공지 제목", value=row["title"], max_chars=MAX_TITLE_CHARS,
                                                  key=prefix + "_title")
                    changed_content = st.text_area("공지 내용", value=row["content"], height=150,
                                                    max_chars=MAX_CONTENT_CHARS, key=prefix + "_content")
                    changed_classes = st.multiselect("공지 대상 학급", CLASSES,
                                                     default=announcement_classes(row), key=prefix + "_classes")
                    changed_active = st.checkbox("학생에게 공개", value=row["active"] == "1", key=prefix + "_active")
                    update = st.form_submit_button("수정 저장", type="primary", key=prefix + "_save")
                if update:
                    try:
                        save_announcement(user, changed_title, changed_content, changed_classes, changed_active,
                                          announcement_id=row["id"])
                    except (PermissionError, ValueError) as error:
                        st.error(str(error))
                    else:
                        st.session_state["_announcement_notice"] = "공지를 수정했어요."
                        st.rerun()
            if st.button("공지 삭제", key=prefix + "_delete"):
                try:
                    delete_announcement(user, row["id"])
                except (PermissionError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_announcement_notice"] = "공지를 삭제했어요."
                    st.rerun()
