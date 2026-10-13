"""Student links and stale selections expose only distributed, current activities."""
import pytest
from streamlit.testing.v1 import AppTest
from unittest.mock import patch

from snorkl_navigation import REQUESTED_COURSE
from think_app import classroom, courses, embedded
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.integration import resolve_settings
from think_app.question_files import QuestionFiles
from think_app.storage import MemoryStore


NOTICE = "수행평가 기간이 아닙니다."
TODAY = "2026-10-14"


@pytest.fixture
def student_app(monkeypatch):
    clock = {"now": TODAY + "T00:30:00+09:00"}
    monkeypatch.setattr(classroom, "now", lambda: clock["now"])
    monkeypatch.setattr(courses, "now", lambda: clock["now"])
    store = MemoryStore()
    room = Classroom(store)
    manager = CourseManager(store)
    course_id = manager.create("학생 수행평가", "#123456", ["1-1"])
    user = {"role": "student", "id": "10101", "name": "시험학생", "class": "1-1"}
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: resolve_settings({}, {}))
    monkeypatch.setattr(embedded, "get_store", lambda settings: store)
    monkeypatch.setattr(embedded, "_period_test_user", user, raising=False)

    def app(route="list", selected=None, selected_activity=None):
        result = AppTest.from_string(
            "from think_app import embedded as view\n"
            "view.render(view._period_test_user)\n"
        )
        if route == "requested":
            result.session_state[REQUESTED_COURSE] = selected or course_id
        elif route == "selected":
            result.session_state["_snorkl_student_course"] = selected or course_id
        if selected_activity:
            result.session_state["snorkl_student_activity_" + (selected or course_id)] = selected_activity
        return result.run()

    return store, room, manager, course_id, clock, app


def add_activity(room, course_id, title="공개 활동", start=TODAY, end=TODAY,
                 published=True, duration=0, attachment=False):
    files = []
    if attachment:
        files = [QuestionFiles(room.store).save(
            course_id, "비공개 문제 파일 내용".encode(), "비공개문제.txt")]
    aid = room.save_activity(course_id, title, title + "의 비공개 문제", "모범답안",
                             ["풀이 과정 설명"], 2, start, end, mode="quiz",
                             duration_minutes=duration, question_files=files)
    if published:
        if end and end < TODAY:
            with patch.object(classroom, "now", return_value=end + "T12:00:00+09:00"):
                room.distribute_activity(aid)
        else:
            room.distribute_activity(aid)
    return aid


def assert_no_activity_content(app):
    assert not app.exception and not app.error
    assert NOTICE in [item.value for item in app.info]
    assert not app.selectbox and not app.text_input and not app.text_area
    assert not app.get("file_uploader") and not app.get("audio_input")
    assert not app.get("download_button") and not app.get("component_instance")
    assert not any("비공개 문제" in item.value for item in app.markdown)


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
@pytest.mark.parametrize("state", ["future", "past", "unpublished", "waiting", "expired", "ended", "hidden"])
def test_unavailable_activities_are_hidden_from_every_student_entry(student_app, route, state):
    store, room, _, course_id, clock, make_app = student_app
    start, end = TODAY, TODAY
    if state == "future":
        start = end = "2026-10-15"
    elif state == "past":
        start = end = "2026-10-13"
    if state == "waiting":
        clock["now"] = "2026-10-13T23:30:00+09:00"
    aid = add_activity(room, course_id, start=start, end=end, published=state != "unpublished",
                       duration=2 if state in ("waiting", "expired", "ended") else 0,
                       attachment=True)
    clock["now"] = TODAY + "T00:30:00+09:00"
    if state in ("expired", "ended"):
        if state == "ended":
            room.end_timer(aid)
        else:
            clock["now"] = TODAY + "T00:32:00+09:00"
    elif state == "hidden":
        room.set_status(aid, "숨김")
    app = make_app(route)
    assert_no_activity_content(app)
    if route == "list":
        assert app.button(key="snorkl_join_" + course_id).disabled


def test_distributing_current_activity_unlocks_existing_student_selection(student_app):
    _, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, published=False)
    app = make_app("requested")
    assert_no_activity_content(app)
    room.distribute_activity(aid)
    app.run()
    assert not app.exception and not app.error
    assert NOTICE not in [item.value for item in app.info]
    assert app.selectbox(key="snorkl_student_activity_" + course_id).value == aid
    assert any(item.label == "나의 답안" for item in app.text_area)
    assert any(item.label == "답안 제출" and not item.disabled for item in app.button)


def test_mixed_periods_only_show_current_distributed_activity_and_clear_stale_choice(student_app):
    _, room, _, course_id, _, make_app = student_app
    current = add_activity(room, course_id, title="오늘 평가")
    future = add_activity(room, course_id, title="미래 평가", start="2026-10-15", end="2026-10-15",
                          attachment=True)
    add_activity(room, course_id, title="종료 평가", start="2026-10-13", end="2026-10-13")
    add_activity(room, course_id, title="배포 전 평가", published=False)
    app = make_app()
    assert not app.button(key="snorkl_join_" + course_id).disabled
    app.button(key="snorkl_join_" + course_id).click().run()
    key = "snorkl_student_activity_" + course_id
    assert app.selectbox(key=key).value == current
    app = make_app("selected", selected_activity=future)
    assert not app.exception and not app.error
    assert app.selectbox(key=key).value == current
    assert app.selectbox(key=key).options == ["오늘 평가"]
    assert not app.get("download_button")
    assert not any("미래 평가의 비공개 문제" in item.value for item in app.markdown)


@pytest.mark.parametrize("route", ["requested", "selected"])
def test_another_class_link_is_denied_before_period_or_activity_details(student_app, route):
    _, room, manager, _, _, make_app = student_app
    other = manager.create("다른 반 수업", "#123456", ["1-2"])
    add_activity(room, other, attachment=True)
    app = make_app(route, other)
    assert not app.exception
    assert any("참여할 권한이 없습니다" in item.value for item in app.error)
    assert not app.selectbox and not app.text_area and not app.get("download_button")
    assert not any("다른 반 수업" in item.value for item in app.title)


@pytest.mark.parametrize("status", ["진행 중", "보기만 가능"])
def test_legacy_published_activities_without_distribution_metadata_remain_visible(student_app, status):
    store, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id)

    def legacy(state):
        task = state["course_activities"][aid]
        task.pop("distribution_required", None)
        task.pop("distributed_at", None)
        task["status"] = status

    store.transaction(legacy)
    app = make_app("requested")
    assert not app.exception and not app.error
    assert NOTICE not in [item.value for item in app.info]
    assert app.selectbox(key="snorkl_student_activity_" + course_id).value == aid
    assert any("공개 활동의 비공개 문제" in item.value for item in app.markdown)
    assert any(item.label == "나의 답안" for item in app.text_area) == (status == "진행 중")


def test_course_list_keeps_unavailable_cards_disabled_and_omits_other_classes(student_app):
    _, room, manager, available, _, make_app = student_app
    add_activity(room, available)
    future = manager.create("다음 평가 수업", "#123456", ["1-1"])
    add_activity(room, future, start="2026-10-15", end="2026-10-15")
    other = manager.create("다른 반 수업", "#123456", ["1-2"])
    add_activity(room, other)
    app = make_app()
    assert not app.exception and not app.error
    assert not app.button(key="snorkl_join_" + available).disabled
    assert app.button(key="snorkl_join_" + future).disabled
    assert "snorkl_join_" + other not in [item.key for item in app.button]
    assert NOTICE in [item.value for item in app.info]


def test_period_ending_after_render_hides_previous_question_and_controls(student_app):
    _, room, _, course_id, clock, make_app = student_app
    add_activity(room, course_id, attachment=True)
    app = make_app("selected")
    assert not app.exception and app.text_area and app.get("download_button")
    clock["now"] = "2026-10-15T00:00:00+09:00"
    app.run()
    assert_no_activity_content(app)


def test_empty_assigned_course_has_the_period_notice_on_all_entry_paths(student_app):
    *_, make_app = student_app
    for route in ("list", "requested", "selected"):
        assert_no_activity_content(make_app(route))
