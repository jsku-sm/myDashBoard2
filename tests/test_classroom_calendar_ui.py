"""Calendar gestures persist only allowed plans; student displays stay read-only."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from classroom_core import ClassroomService
from views import classroom as view
from test_classroom_calendar_notes import actor, environment, note, place


def test_student_calendar_resolves_shared_cards_without_private_resource_titles():
    store, users, teacher, cid, work = environment()
    public = work.save_material(cid, "공개 학습지", body="읽기", published=True)
    private = work.save_material(cid, "숨겨진 제목", body="초안")
    for resource in (public, private):
        place(teacher, cid, "material", resource["id"])
    teacher.set_lesson(cid, "lesson", {"planned_date": "2026-10-20", "resources": [
        {"kind": "material", "id": public["id"]}, {"kind": "material", "id": private["id"]}]},
        teacher.get_course(cid)["version"], "자료 연결")
    teacher.add_session(cid, "lesson", "2026-10-21", note="개인 지원 사유")
    note(teacher, cid, text="학생에게 알릴 준비물")
    student = actor(store, users, "s")
    items, tray, resources = view._calendar_data(student, [student.get_course(cid)], users["s"], "전체")
    assert "숨겨진 제목" not in str((items, tray, resources))
    assert "개인 지원 사유" not in str((items, tray, resources))
    assert {row["title"] for row in resources} == {"공개 학습지"}
    assert any(row.get("item_kind") == "resource" and row["id"] == public["id"] for row in items)
    assert any(row.get("item_kind") == "note" and row["detail"] == "학생에게 알릴 준비물" for row in items)
    assert any(row["date"] == "2026-10-21" and "보충 수업" in row["subtitle"] for row in items)
    assert all(not row["movable"] for row in items + tray + resources)


APP_SOURCE = '''
from datetime import date
import streamlit as st
from classroom_core import ClassroomService, MemoryStore, StorageError
from classroom_core.work import WorkService
from views import classroom as view
from views import classroom_calendar

class FailingStore(MemoryStore):
    fail = False
    def put(self, *args, **kwargs):
        if self.fail:
            raise StorageError("모의 저장 실패")
        return super().put(*args, **kwargs)

if "fixture" not in st.session_state:
    users = {"t": {"id":"t", "role":"teacher"}, "s": {"id":"s", "role":"student", "class":"1-1"}}
    store = FailingStore()
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _:False)
    plan = teacher.create_curriculum("수업안", "수학", [{"id":"one", "title":"함수"}])
    course = teacher.create_course("1-1", "2026-2", "수학", class_name="1-1", curriculum_id=plan["id"], student_ids=["s"])
    task = WorkService(teacher).save_assignment(course["id"], "탐구 과제", "설명", published=True, due_at="2026-10-30T12:00:00+09:00")
    st.session_state.fixture = (store, users, course["id"], task["id"])
store, users, cid, aid = st.session_state.fixture
user = users[st.session_state.get("actor", "t")]
service = ClassroomService(store, user, users.get, lock_checker=lambda _:False)
def calendar(**kwargs):
    st.session_state.payload = kwargs
    return st.session_state.pop("event", None)
classroom_calendar.render_week = calendar
view._calendar(service, [service.get_course(cid)], user, date(2026,10,20), key="test")
'''


def app():
    result = AppTest.from_string(APP_SOURCE).run()
    assert not result.exception
    return result


@pytest.mark.parametrize("kind", ["lesson", "resource"])
def test_drop_saves_immediately_and_same_position_does_not_duplicate_audit(kind):
    screen = app()
    store, _, cid, aid = screen.session_state["fixture"]
    task = store.get("assignments", aid)
    event = dict(kind=kind, course_id=cid, id="one" if kind == "lesson" else aid, date="2026-10-21",
                 expected_version=store.get("courses", cid)["version"])
    if kind == "resource":
        event["resource_kind"] = "assignment"
    screen.session_state["event"] = event
    screen.run()
    assert not screen.exception and not screen.error
    course = store.get("courses", cid)
    if kind == "lesson":
        assert course["lesson_records"]["one"]["planned_date"] == "2026-10-21"
    else:
        assert course["calendar_resources"]["assignment:" + aid]["date"] == "2026-10-21"
        assert course["lesson_records"] == {}
    assert store.get("assignments", aid) == task
    assert any(row["date"] == "2026-10-21" for row in screen.session_state["payload"]["items"])
    screen.session_state["event"] = event
    screen.run()
    assert store.get("courses", cid) == course


def test_failed_drop_stays_unsaved_and_retry_can_persist():
    screen = app()
    store, _, cid, _ = screen.session_state["fixture"]
    original = store.get("courses", cid)
    store.fail = True
    screen.session_state["event"] = dict(kind="lesson", course_id=cid, id="one", date="2026-10-21", expected_version=original["version"])
    screen.run()
    assert not screen.exception and screen.error
    assert store.get("courses", cid) == original
    assert any("저장하지 못했습니다" in row.value for row in screen.warning)
    store.fail = False
    next(button for button in screen.button if button.label == "달력 배치 다시 저장").click().run()
    assert not screen.exception
    assert store.get("courses", cid)["lesson_records"]["one"]["planned_date"] == "2026-10-21"


def test_student_forged_drop_has_no_editor_and_no_write():
    screen = app()
    store, _, cid, aid = screen.session_state["fixture"]
    original = store.get("courses", cid)
    screen.session_state["actor"] = "s"
    screen.session_state["event"] = dict(kind="resource", resource_kind="assignment", course_id=cid, id=aid, date="2026-10-21", expected_version=original["version"])
    screen.run()
    assert not screen.exception and not screen.error
    assert not screen.session_state["payload"]["editable"]
    assert store.get("courses", cid) == original
    assert not any(row.label in {"메모 저장", "날짜에 배치", "자료·과제 날짜 저장"} for row in screen.button)
    assert not any(row.label == "날짜 메모" for row in screen.text_area)


def test_teacher_date_note_saved_and_shared_read_only():
    screen = app()
    store, _, cid, _ = screen.session_state["fixture"]
    next(field for field in screen.text_area if field.label == "날짜 메모").set_value("도형 학습지 지참")
    next(button for button in screen.button if button.label == "메모 저장").click().run()
    assert not screen.exception and not screen.error
    assert store.get("courses", cid)["calendar_notes"]["2026-10-20"] == "도형 학습지 지참"
    screen.session_state["actor"] = "s"
    screen.run()
    assert any(row.get("detail") == "도형 학습지 지참" for row in screen.session_state["payload"]["items"])
    assert not any(field.label == "날짜 메모" for field in screen.text_area)


@pytest.mark.parametrize("event", [
    dict(kind="lesson", id="missing", date="2026-10-21"),
    dict(kind="lesson", id="one", date="2026-11-01"),
    dict(kind="resource", id="missing", resource_kind="material", date="2026-10-21"),
])
def test_invalid_browser_reference_cannot_schedule(event):
    screen = app()
    store, _, cid, _ = screen.session_state["fixture"]
    original = store.get("courses", cid)
    screen.session_state["event"] = dict(event, course_id=cid, expected_version=original["version"])
    screen.run()
    assert not screen.exception and not screen.error
    assert store.get("courses", cid) == original


def test_drop_with_stale_display_version_cannot_overwrite_another_teacher():
    screen = app()
    store, users, cid, _ = screen.session_state["fixture"]
    original = store.get("courses", cid)
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    changed = teacher.set_lesson(cid, "one", {"planned_date": "2026-10-22"}, original["version"], "다른 창 변경")
    screen.session_state["event"] = dict(kind="lesson", course_id=cid, id="one", date="2026-10-21", expected_version=original["version"])
    screen.run()
    assert not screen.exception and screen.error
    assert store.get("courses", cid) == changed
    next(button for button in screen.button if button.label == "달력 배치 다시 저장").click().run()
    assert store.get("courses", cid)["lesson_records"]["one"]["planned_date"] == "2026-10-21"
