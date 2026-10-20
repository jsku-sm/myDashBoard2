"""Deferred classroom-to-tool navigation, applied before sidebar widgets exist."""

PENDING = "_classroom_pending_navigation"


def apply_pending_navigation(state, user):
    request = state.pop(PENDING, None)
    if not isinstance(request, dict) or request.get("user_id") != user.get("id"):
        return
    if request.get("menu") == "snorkl":
        from snorkl_navigation import ACTIVE_TOOL, REQUESTED_COURSE
        state["nav"] = "tools"
        state[ACTIVE_TOOL] = "snorkl"
        state[REQUESTED_COURSE] = request["course_id"]
        state["_classroom_requested_activity"] = request["activity_id"]
        if user.get("role") == "teacher":
            state["selected_course"] = request["course_id"]
            state["selected_activity"] = request["activity_id"]
        else:
            state.pop("_snorkl_student_scores", None)
            state["_snorkl_student_course"] = request["course_id"]
            state["snorkl_student_activity_" + request["course_id"]] = request["activity_id"]
    elif request.get("menu") in ("sudanote", "math1", "math2", "teacher"):
        if request["menu"] == "teacher" and user.get("role") != "teacher":
            return
        state["nav"] = request["menu"]


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
