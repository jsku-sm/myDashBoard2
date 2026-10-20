"""Internal menu and shared-link navigation, independent of Streamlit widgets.

Links select a view only. They never grant a role or change a student's identity.
"""
ACTIVE_TOOL = "_tools_active"
REQUESTED_COURSE = "_snorkl_requested_course"
LINK_SEEN = "_snorkl_link_seen"


def clear_link(state, query):
    for key in ("tool", "course_id"):
        query.pop(key, None)
    state.pop(LINK_SEEN, None)
    state.pop(REQUESTED_COURSE, None)


def open_snorkl(state, query):
    clear_link(state, query)
    state[ACTIVE_TOOL] = "snorkl"


def close_snorkl(state, query):
    clear_link(state, query)
    state.pop(ACTIVE_TOOL, None)


def main_menu_changed(state, query):
    if state.get("nav") != "tools":
        clear_link(state, query)


def sync_shared_link(state, query):
    """Call after login/first-password/emotion checks, before creating nav widgets."""
    course_id = str(query.get("course_id", "")).strip()
    tool = str(query.get("tool", "")).strip()
    if tool != "snorkl" and not course_id:
        state.pop(LINK_SEEN, None)
        return
    signature = (tool, course_id)
    if state.get(LINK_SEEN) == signature:
        return
    state[LINK_SEEN] = signature
    state["nav"] = "tools"
    state[ACTIVE_TOOL] = "snorkl"
    state[REQUESTED_COURSE] = course_id or None

def preserve_tool_drafts(user):
    """Snapshot committed native editor values before the app-level lock hides them."""
    import streamlit as st
    from think_app.student_drafts import REGISTRY_KEY, capture_active_drafts
    registry = st.session_state.get(REGISTRY_KEY, {})
    if not isinstance(registry, dict):
        return
    scopes = set()
    for entry in registry.values():
        scope = entry.get("scope", {}) if isinstance(entry, dict) else {}
        if scope.get("student_id") == user.get("id") and not scope.get("preview"):
            scopes.add((scope.get("course_id", ""), scope.get("class_id", "")))
    for course_id, class_id in scopes:
        capture_active_drafts(course_id, (user["id"], user.get("name", ""), class_id))
