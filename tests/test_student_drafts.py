"""Private session drafts survive omitted widgets without crossing ownership."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from think_app import student_drafts


TASK = {"id": "activity", "course_id": "course", "title": "수행평가", "mode": "writing",
        "prompt": "풀이를 설명하세요.", "expected": "모범답안", "criteria": ["근거 설명"],
        "quiz_options": [], "question_files": []}
IDENTITY = ("1001", "학생", "1반")
BOARD = {"image": "data:image/png;base64,aW1hZ2U=", "hasInk": True, "revision": 3}
GRAPH = {"mode": "sdk", "ready": True, "state": {"expressions": {"list": [{"id": "1", "latex": "x+1"}]}},
         "expressions": [{"id": "1", "latex": "x+1"}], "image": BOARD["image"]}


@pytest.fixture
def state(monkeypatch):
    result = {}
    monkeypatch.setattr(student_drafts.st, "session_state", result)
    return result


def remember(task=TASK, identity=IDENTITY, preview=False, attempt_count=0, editor_key=None, **changes):
    values = {"widget_key": "student_editor", "text": "작성한 답안", "transcript": "확인한 음성 전사",
              "quiz_answer": "4", "board": BOARD, "graph": GRAPH, "upload_ids": ["a" * 32],
              "raw_audio": b"recorded audio", "consent": True}
    values.update(changes)
    student_drafts.remember_draft(task, identity, preview, attempt_count, editor_key, **values)


@pytest.mark.parametrize("different", ["student", "class", "course", "activity", "preview", "attempt", "editor"])
def test_drafts_are_isolated_by_owner_task_attempt_and_editor(state, different):
    remember()
    task, identity, preview, attempt, editor = copy.deepcopy(TASK), IDENTITY, False, 0, None
    if different == "student": identity = ("1002", "다른 학생", "1반")
    if different == "class": identity = ("1001", "학생", "2반")
    if different in ("course", "activity"): task["course_id" if different == "course" else "id"] = "other"
    if different == "preview": preview = True
    if different == "attempt": attempt = 1
    if different == "editor": editor = "workbench"
    assert student_drafts.load_draft(task, identity, preview, attempt, editor) == {}
    assert student_drafts.load_draft(TASK, IDENTITY, False, 0)["text"] == "작성한 답안"


@pytest.mark.parametrize("field,value", [("prompt", "다른 문제"), ("expected", "다른 모범답안"),
                                       ("criteria", ["다른 평가 기준"]), ("mode", "quiz"),
                                       ("quiz_options", ["1", "2"]),
                                       ("question_files", [{"id": "new-file", "sha256": "changed"}])])
def test_changed_activity_content_does_not_restore_a_previous_question_draft(state, field, value):
    remember()
    changed = dict(TASK, **{field: value})
    assert student_drafts.load_draft(changed, IDENTITY, False, 0) == {}


def test_timer_period_and_display_name_changes_keep_same_student_work(state):
    remember()
    changed = dict(TASK, start="2026-10-15", end="2026-10-15", timer_ended_at=None,
                   timer_deadline="2026-10-15T02:00:00+09:00", duration_minutes=20)
    assert student_drafts.load_draft(changed, ("1001", "바뀐 표시 이름", "1반"), False, 0)["text"] == "작성한 답안"


def test_media_and_loaded_drafts_are_copied_without_mutating_saved_work(state):
    board, graph, audio = copy.deepcopy(BOARD), copy.deepcopy(GRAPH), bytearray(b"recording")
    remember(board=board, graph=graph, raw_audio=audio)
    board["image"] = "changed"
    graph["state"]["expressions"]["list"][0]["latex"] = "changed"
    audio[0] = 0
    loaded = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    assert loaded["board"] == BOARD and loaded["graph"] == GRAPH and loaded["raw_audio"] == b"recording"
    loaded["graph"]["state"]["expressions"]["list"].clear()
    assert student_drafts.load_draft(TASK, IDENTITY, False, 0)["graph"] == GRAPH


def test_closing_capture_saves_latest_owned_widgets_and_audio_before_cleanup(state):
    remember()
    other = ("1002", "다른 학생", "1반")
    remember(identity=other, widget_key="other_editor", text="다른 학생의 원래 답안")
    digest = hashlib.sha256(json.dumps([TASK["id"], "1반", "1001", False], ensure_ascii=False).encode()).hexdigest()[:16]
    state.update({"student_editor_text": "종료 직전 마지막 답안", "student_editor_transcript": "마지막 전사",
                  "student_editor_quiz": "5", "student_editor_board": dict(BOARD, revision=4),
                  "student_editor_graph": dict(GRAPH, revision=7), "student_editor_consent": False,
                  "student_editor_audio": SimpleNamespace(getvalue=lambda: b"latest audio"),
                  "student_editor_saved_uploads_" + digest: ["b" * 32],
                  "other_editor_text": "다른 학생의 변경값"})
    student_drafts.capture_active_drafts("course", IDENTITY)
    for key in list(state):
        if key.startswith("student_editor"):
            del state[key]
    draft = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    assert draft["text"] == "종료 직전 마지막 답안" and draft["transcript"] == "마지막 전사"
    assert draft["quiz_answer"] == "5" and draft["board"]["revision"] == 4
    assert draft["graph"]["revision"] == 7 and draft["upload_ids"] == ["b" * 32]
    assert draft["raw_audio"] == b"latest audio" and draft["consent"] is False
    student_drafts.restore_draft_widgets(draft, "student_editor")
    assert state["student_editor_text"] == draft["text"]
    assert state["student_editor_transcript"] == "마지막 전사"
    assert state["student_editor_audio_hash"] == hashlib.sha256(b"latest audio").hexdigest()
    assert student_drafts.load_draft(TASK, other, False, 0)["text"] == "다른 학생의 원래 답안"


def test_restore_preserves_live_values_and_never_reinjects_file_audio_or_component_widgets(state):
    remember()
    state["student_editor_text"] = "학생이 새로 수정한 답안"
    draft = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    before = set(state)
    student_drafts.restore_draft_widgets(draft, "student_editor")
    assert state["student_editor_text"] == "학생이 새로 수정한 답안"
    assert set(state) - before == {"student_editor_transcript", "student_editor_quiz",
                                  "student_editor_consent", "student_editor_audio_hash"}
    assert "student_editor_uploads" not in state and "student_editor_audio" not in state
    assert "student_editor_board" not in state and "student_editor_graph" not in state


def test_capturing_new_audio_keeps_existing_hash_so_the_editor_detects_recording_changes(state):
    remember(raw_audio=b"first audio", transcript="이전 녹음의 전사")
    old_hash = hashlib.sha256(b"first audio").hexdigest()
    state["student_editor_audio_hash"] = old_hash
    state["student_editor_audio"] = SimpleNamespace(getvalue=lambda: b"replacement audio")
    student_drafts.capture_active_drafts("course", IDENTITY)
    draft = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    student_drafts.restore_draft_widgets(draft, "student_editor")
    assert draft["raw_audio"] == b"replacement audio"
    assert state["student_editor_audio_hash"] == old_hash
    assert hashlib.sha256(draft["raw_audio"]).hexdigest() != state["student_editor_audio_hash"]


def test_partial_sdk_events_keep_the_previous_graph_state_until_new_capture_arrives(state):
    remember()
    remember(graph={"mode": "sdk", "ready": False, "connected": True})
    draft = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    assert draft["graph"]["state"] == GRAPH["state"]
    assert draft["graph"]["ready"] is False


def test_oversized_media_is_not_copied_but_text_is_kept(state, monkeypatch):
    monkeypatch.setattr(student_drafts, "MAX_IMAGE_CHARS", 30)
    monkeypatch.setattr(student_drafts, "MAX_AUDIO_BYTES", 8)
    monkeypatch.setattr(student_drafts, "MAX_GRAPH_BYTES", 40)
    remember(board={"image": "data:image/png;base64," + "x" * 20, "hasInk": True},
             graph=GRAPH, raw_audio=b"x" * 9)
    draft = student_drafts.load_draft(TASK, IDENTITY, False, 0)
    assert draft["text"] == "작성한 답안"
    assert draft["board"] is None and draft["graph"] is None and draft["raw_audio"] is None


def test_forgetting_submitted_work_does_not_remove_another_attempt_or_recreate_old_draft(state):
    remember()
    remember(attempt_count=1, text="다음 시도의 작성 내용")
    student_drafts.forget_draft(TASK, IDENTITY, False, 0)
    state["student_editor_text"] = "남아 있는 이전 widget 값"
    student_drafts.capture_active_drafts("course", IDENTITY)
    assert student_drafts.load_draft(TASK, IDENTITY, False, 0) == {}
    assert student_drafts.load_draft(TASK, IDENTITY, False, 1)["text"] == "남아 있는 이전 widget 값"


def test_text_survives_real_streamlit_widget_cleanup_and_resume():
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from think_app.student_drafts import load_draft, remember_draft, capture_active_drafts, restore_draft_widgets\n"
        "task={'id':'activity','course_id':'course','prompt':'문제','criteria':['설명'],'mode':'writing'}\n"
        "identity=('1001','학생','1반')\n"
        "capture_active_drafts('course',identity)\n"
        "if st.session_state.get('open',True):\n"
        "  draft=load_draft(task,identity,False,0)\n"
        "  restore_draft_widgets(draft,'student_editor')\n"
        "  text=st.text_area('나의 답안',key='student_editor_text')\n"
        "  remember_draft(task,identity,False,0,widget_key='student_editor',text=text)\n"
        "else:\n"
        "  st.info('선생님이 평가를 종료했습니다.')\n")
    app.run()
    app.text_area(key="student_editor_text").set_value("이어 작성할 답안").run()
    app.session_state["open"] = False
    app.run()
    assert not app.exception and not app.text_area
    assert "student_editor_text" not in app.session_state
    app.session_state["open"] = True
    app.run()
    assert not app.exception
    assert app.text_area(key="student_editor_text").value == "이어 작성할 답안"
