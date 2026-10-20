"""Deferred classroom-to-tool navigation, applied before sidebar widgets exist."""

PENDING = "_classroom_pending_navigation"


def apply_pending_navigation(state, user):
    request = state.pop(PENDING, None)
    if not isinstance(request, dict) or request.get("user_id") != user.get("id"):
        return
    if request.get("menu") in ("sudanote", "math1", "math2", "teacher"):
        if request["menu"] == "teacher" and user.get("role") != "teacher":
            return
        state["nav"] = request["menu"]
