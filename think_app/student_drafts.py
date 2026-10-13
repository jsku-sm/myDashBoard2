"""Keep unsubmitted student work in private, non-widget session state."""
import copy
import hashlib
import json

import streamlit as st

from .media import activity_mode


REGISTRY_KEY = "_assessment_student_draft_registry"
CONTENT_FIELDS = ("prompt", "expected", "criteria", "quiz_options", "question_files", "expected_images", "curriculum")
MAX_IMAGE_CHARS = 16_000_000
MAX_AUDIO_BYTES = 10_000_000
MAX_GRAPH_BYTES = 500_000


def _scope(task, identity, preview, attempt_count, editor_key):
    student_id, _, class_id = identity
    content = {field: task.get(field) for field in CONTENT_FIELDS}
    content["mode"] = activity_mode(task)
    fingerprint = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                            allow_nan=False).encode()).hexdigest()
    return {"course_id": task["course_id"], "activity_id": task["id"],
            "student_id": student_id.strip(), "class_id": class_id.strip(), "preview": bool(preview),
            "attempt_count": attempt_count, "editor_key": editor_key, "content_fingerprint": fingerprint}


def draft_key(task, identity, preview, attempt_count, editor_key=None):
    scope = _scope(task, identity, preview, attempt_count, editor_key)
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return "_assessment_student_draft_" + digest


def load_draft(task, identity, preview, attempt_count, editor_key=None):
    key = draft_key(task, identity, preview, attempt_count, editor_key)
    draft = st.session_state.get(key)
    if not isinstance(draft, dict) or draft.get("scope") != _scope(task, identity, preview, attempt_count, editor_key):
        return {}
    return copy.deepcopy(draft)


def _board(value):
    if not isinstance(value, dict):
        return None
    image = value.get("image")
    if not isinstance(image, str) or not image.startswith("data:image/png;base64,") or len(image) > MAX_IMAGE_CHARS:
        return None
    result = {"image": image, "hasInk": bool(value.get("hasInk"))}
    if type(value.get("revision")) is int:
        result["revision"] = value["revision"]
    return result


def _graph(value):
    if not isinstance(value, dict):
        return None
    result = {field: value[field] for field in ("mode", "state", "expressions", "ready", "revision",
                                               "connected", "can_capture", "frame_loaded") if field in value}
    try:
        if len(json.dumps(result, allow_nan=False).encode()) > MAX_GRAPH_BYTES:
            return None
        result = copy.deepcopy(result)
    except (ValueError, TypeError, RecursionError):
        return None
    image = value.get("image")
    if isinstance(image, str) and image.startswith("data:image/png;base64,") and len(image) <= MAX_IMAGE_CHARS:
        result["image"] = image
    return result


def _audio(value):
    if isinstance(value, (bytes, bytearray)) and 0 < len(value) <= MAX_AUDIO_BYTES:
        return bytes(value)
    return None


def _upload_ids(value):
    if not isinstance(value, (list, tuple)) or len(value) > 3 or any(not isinstance(item, str) for item in value):
        return []
    return list(dict.fromkeys(value))


def remember_draft(task, identity, preview, attempt_count, editor_key=None, *, widget_key,
                   text="", transcript="", quiz_answer=None, board=None, graph=None, upload_ids=(),
                   raw_audio=None, consent=False):
    key = draft_key(task, identity, preview, attempt_count, editor_key)
    scope = _scope(task, identity, preview, attempt_count, editor_key)
    previous = st.session_state.get(key, {})
    old_board, old_graph = previous.get("board"), previous.get("graph")
    saved_graph = _graph(graph)
    if saved_graph is not None and old_graph and "state" not in saved_graph and "state" in old_graph:
        saved_graph = dict(copy.deepcopy(old_graph), **saved_graph)
    draft = {"scope": scope, "widget_key": widget_key,
             "text": text if isinstance(text, str) and len(text) <= 12000 else previous.get("text", ""),
             "transcript": transcript if isinstance(transcript, str) and len(transcript) <= 12000 else previous.get("transcript", ""),
             "quiz_answer": quiz_answer if quiz_answer is None or isinstance(quiz_answer, str) and len(quiz_answer) <= 2000 else previous.get("quiz_answer"),
             "board": _board(board) if board is not None else copy.deepcopy(old_board),
             "graph": saved_graph if graph is not None else copy.deepcopy(old_graph),
             "upload_ids": _upload_ids(upload_ids), "raw_audio": _audio(raw_audio), "consent": bool(consent)}
    st.session_state[key] = draft
    registry = dict(st.session_state.get(REGISTRY_KEY, {}))
    registry[key] = {"scope": scope, "widget_key": widget_key}
    st.session_state[REGISTRY_KEY] = registry


def capture_active_drafts(course_id, identity, preview=False):
    """Capture committed widget values before a closing guard omits the editor."""
    student_id, _, class_id = identity
    registry = st.session_state.get(REGISTRY_KEY, {})
    if not isinstance(registry, dict):
        return
    for key, entry in list(registry.items()):
        scope = entry.get("scope", {}) if isinstance(entry, dict) else {}
        if (scope.get("course_id") != course_id or scope.get("student_id") != student_id.strip() or
                scope.get("class_id") != class_id.strip() or scope.get("preview") != bool(preview)):
            continue
        draft = st.session_state.get(key)
        widget_key = entry.get("widget_key")
        if not isinstance(draft, dict) or draft.get("scope") != scope or not isinstance(widget_key, str):
            continue
        draft = copy.deepcopy(draft)
        for field, suffix, limit in (("text", "_text", 12000), ("transcript", "_transcript", 12000),
                                     ("quiz_answer", "_quiz", 2000)):
            widget = widget_key + suffix
            if widget in st.session_state:
                value = st.session_state[widget]
                if value is None and field == "quiz_answer" or isinstance(value, str) and len(value) <= limit:
                    draft[field] = value
        for field, suffix, copy_media in (("board", "_board", _board), ("graph", "_graph", _graph)):
            widget = widget_key + suffix
            if widget in st.session_state:
                value = copy_media(st.session_state[widget])
                if value is not None:
                    if field == "graph" and draft.get("graph") and "state" not in value:
                        value = dict(draft["graph"], **value)
                    draft[field] = value
        if widget_key + "_consent" in st.session_state:
            draft["consent"] = bool(st.session_state[widget_key + "_consent"])
        audio = st.session_state.get(widget_key + "_audio")
        if audio is not None and callable(getattr(audio, "getvalue", None)):
            raw_audio = _audio(audio.getvalue())
            if raw_audio is not None:
                draft["raw_audio"] = raw_audio
        identity_digest = hashlib.sha256(json.dumps([scope["activity_id"], class_id.strip(), student_id.strip(), bool(preview)],
                                                    ensure_ascii=False).encode()).hexdigest()[:16]
        upload_key = widget_key + "_saved_uploads_" + identity_digest
        if upload_key in st.session_state:
            draft["upload_ids"] = _upload_ids(st.session_state[upload_key])
        st.session_state[key] = draft


def restore_draft_widgets(draft, widget_key):
    """Restore editable values only; files and audio use separate saved media."""
    if not isinstance(draft, dict) or not draft:
        return
    for field, suffix in (("text", "_text"), ("transcript", "_transcript"), ("quiz_answer", "_quiz"),
                          ("consent", "_consent")):
        if field in draft:
            st.session_state.setdefault(widget_key + suffix, copy.deepcopy(draft[field]))
    raw_audio = _audio(draft.get("raw_audio"))
    st.session_state.setdefault(widget_key + "_audio_hash", hashlib.sha256(raw_audio).hexdigest() if raw_audio else "")


def forget_draft(task, identity, preview, attempt_count, editor_key=None):
    key = draft_key(task, identity, preview, attempt_count, editor_key)
    st.session_state.pop(key, None)
    registry = dict(st.session_state.get(REGISTRY_KEY, {}))
    registry.pop(key, None)
    st.session_state[REGISTRY_KEY] = registry
