"""Student access follows distribution, dates and shared assessment transitions."""
import io
import pytest
from pypdf import PdfWriter
from streamlit.testing.v1 import AppTest
from types import SimpleNamespace
from unittest.mock import patch

from snorkl_navigation import REQUESTED_COURSE
from think_app import classroom, courses, embedded, timer_ui
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.integration import resolve_settings
from think_app.question_files import QuestionFiles
from think_app.storage import MemoryStore, student_pdf_attachments
from think_app.uploads import UploadedFiles


NOTICE = "수행평가 기간이 아닙니다."
ENDED_NOTICE = "선생님이 평가를 종료했습니다."
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


def assert_no_activity_content(app, notice=NOTICE, *, activity_selector=False):
    assert not app.exception and not app.error
    notices = [item.value for item in app.info]
    assert notice in notices
    assert (ENDED_NOTICE if notice == NOTICE else NOTICE) not in notices
    if not activity_selector:
        assert not app.selectbox
    assert not app.text_input and not app.text_area
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
    assert_no_activity_content(app, ENDED_NOTICE if state == "ended" else NOTICE)
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


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
def test_student_assessment_omits_the_old_course_heading(student_app, route):
    _, room, _, course_id, _, make_app = student_app
    add_activity(room, course_id)
    app = make_app(route)
    assert not app.exception and not app.error
    assert "내 소노클 수업" not in [item.value for item in app.subheader]
    assert not any("내 소노클 수업" in item.label for item in app.button)


@pytest.mark.parametrize("published", [True, False])
def test_previous_menu_button_returns_to_course_list_and_preserves_enrollment(student_app, published):
    _, room, manager, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, published=published)
    other = manager.create("다른 반 수업", "#123456", ["1-2"])
    add_activity(room, other)
    app = make_app("requested")
    back = app.button(key="snorkl_student_back")
    assert back.label == "이전메뉴로 돌아가기"
    back.click().run()
    assert not app.exception and not app.error
    assert "_snorkl_student_course" not in app.session_state
    assert not app.selectbox and not app.text_area and not app.get("download_button")
    assert "내 소노클 수업" not in [item.value for item in app.subheader]
    own = app.button(key="snorkl_join_" + course_id)
    assert own.disabled is not published
    assert "snorkl_join_" + other not in [item.key for item in app.button]
    if published:
        own.click().run()
        assert not app.exception and not app.error
        assert app.selectbox(key="snorkl_student_activity_" + course_id).value == aid


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
@pytest.mark.parametrize("status", ["진행 중", "보기만 가능"])
def test_teacher_ending_a_published_activity_replaces_the_student_screen_with_exact_notice(student_app, route, status):
    _, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    room.set_status(aid, status)
    app = make_app(route)
    assert not app.exception and not app.error
    assert ENDED_NOTICE not in [item.value for item in app.info]
    if route != "list":
        assert app.get("download_button")
    room.end_timer(aid)
    app.run()
    assert_no_activity_content(app, ENDED_NOTICE)
    if route == "list":
        assert app.button(key="snorkl_join_" + course_id).disabled


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
@pytest.mark.parametrize("state", ["hidden", "unpublished", "missing_distribution"])
def test_ended_activity_metadata_is_not_disclosed_when_hidden_or_unpublished(student_app, route, state):
    store, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    room.end_timer(aid)
    if state == "hidden":
        room.set_status(aid, "숨김")
    elif state == "unpublished":
        room.set_status(aid, "배포 전")
    else:
        store.transaction(lambda data: data["course_activities"][aid].pop("distributed_at"))
    assert_no_activity_content(make_app(route))


def test_ending_the_selected_activity_keeps_other_active_activity_selectable(student_app):
    _, room, _, course_id, _, make_app = student_app
    ended = add_activity(room, course_id, title="종료할 평가", duration=5, attachment=True)
    ongoing = add_activity(room, course_id, title="계속 진행할 평가", duration=5)
    key = "snorkl_student_activity_" + course_id
    app = make_app("selected", selected_activity=ended)
    assert app.selectbox(key=key).value == ended and app.text_area
    room.end_timer(ended)
    app.run()
    assert_no_activity_content(app, ENDED_NOTICE, activity_selector=True)
    assert app.selectbox(key=key).value == ended
    assert "계속 진행할 평가" in app.selectbox(key=key).options
    app.selectbox(key=key).set_value(ongoing).run()
    assert not app.exception and not app.error
    assert ENDED_NOTICE not in [item.value for item in app.info]
    assert app.selectbox(key=key).value == ongoing and app.text_area
    assert not app.get("download_button")
    assert any("계속 진행할 평가의 비공개 문제" in item.value for item in app.markdown)
    assert not any("종료할 평가의 비공개 문제" in item.value for item in app.markdown)


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
def test_natural_timer_expiry_keeps_the_period_notice_instead_of_teacher_end_notice(student_app, route):
    _, room, _, course_id, clock, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    app = make_app(route)
    clock["now"] = TODAY + "T00:35:00+09:00"
    assert room.activity(aid).get("timer_ended_at") is None
    app.run()
    assert_no_activity_content(app)


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
def test_explicit_teacher_end_notice_remains_after_the_date_period_passes(student_app, route):
    _, room, _, course_id, clock, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    room.end_timer(aid)
    clock["now"] = "2026-10-15T00:00:00+09:00"
    assert_no_activity_content(make_app(route), ENDED_NOTICE)


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
def test_resuming_reopens_the_ended_assessment_on_each_student_entry(student_app, route):
    _, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    room.end_timer(aid)
    app = make_app(route, selected_activity=aid if route != "list" else None)
    assert_no_activity_content(app, ENDED_NOTICE)
    published_at = room.activity(aid)["distributed_at"]
    room.resume_timer(aid, remaining_minutes=3)
    app.run()
    assert not app.exception and not app.error
    assert ENDED_NOTICE not in [item.value for item in app.info]
    assert NOTICE not in [item.value for item in app.info]
    if route == "list":
        assert not app.button(key="snorkl_join_" + course_id).disabled
        app.button(key="snorkl_join_" + course_id).click().run()
    assert app.selectbox(key="snorkl_student_activity_" + course_id).value == aid
    assert app.text_area and app.get("download_button")
    assert any(item.label == "답안 제출" and not item.disabled for item in app.button)
    assert room.activity(aid)["distributed_at"] == published_at
    assert room.activity(aid).get("timer_ended_at") is None
    assert room.timer_state(room.activity(aid))["remaining_seconds"] == 180


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
@pytest.mark.parametrize("period", ["past", "future"])
def test_resuming_includes_today_without_discarding_the_original_date_range(student_app, route, period):
    _, room, _, course_id, clock, make_app = student_app
    aid = add_activity(room, course_id, duration=5)
    room.end_timer(aid)
    if period == "past":
        clock["now"] = "2026-10-15T00:00:00+09:00"
        expected_start, expected_end = TODAY, "2026-10-15"
    else:
        task = room.activity(aid)
        room.save_activity(course_id, task["title"], task["prompt"], task["expected"], task["criteria"],
                           task["max_attempts"], "2026-10-16", "2026-10-17", aid=aid, mode=task["mode"])
        expected_start, expected_end = TODAY, "2026-10-17"
    app = make_app(route)
    assert_no_activity_content(app, ENDED_NOTICE)
    room.resume_timer(aid, remaining_minutes=4)
    app.run()
    assert not app.exception and not app.error
    assert ENDED_NOTICE not in [item.value for item in app.info]
    if route == "list":
        app.button(key="snorkl_join_" + course_id).click().run()
    assert app.text_area
    assert room.activity(aid)["start"] == expected_start
    assert room.activity(aid)["end"] == expected_end


def test_resuming_the_closed_selection_reopens_that_activity_among_other_active_ones(student_app):
    _, room, _, course_id, _, make_app = student_app
    resumed = add_activity(room, course_id, title="재개할 평가", duration=5, attachment=True)
    other = add_activity(room, course_id, title="다른 진행 평가", duration=5)
    key = "snorkl_student_activity_" + course_id
    app = make_app("selected", selected_activity=resumed)
    for minutes in (2, 3):
        room.end_timer(resumed)
        app.run()
        assert_no_activity_content(app, ENDED_NOTICE, activity_selector=True)
        assert app.selectbox(key=key).value == resumed
        room.resume_timer(resumed, remaining_minutes=minutes)
        app.run()
        assert not app.exception and not app.error
        assert app.selectbox(key=key).value == resumed
        assert set(app.selectbox(key=key).options) == {"재개할 평가", "다른 진행 평가"}
        assert app.text_area and app.get("download_button")
        assert ENDED_NOTICE not in [item.value for item in app.info]
        assert room.student_activity_available(room.activity(other))


def test_resuming_preserves_the_student_pdf_submission_and_its_feedback(student_app):
    store, room, _, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, duration=5)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    raw = output.getvalue()
    record = UploadedFiles(store).save(aid, "10101", "시험학생", "1-1", "풀이.pdf", raw)
    request = room.submit(aid, "10101", "시험학생", "1-1", "PDF 풀이를 첨부합니다.", [], True,
                          "a" * 32, quiz_answer="4", upload_ids=[record["id"]])
    feedback = {"correctness": "correct", "explanation_score": 4, "criteria": [],
                "praise": "풀이를 설명했습니다.", "observation": "PDF 풀이를 확인했습니다.",
                "needs_teacher_review": False}
    room.evaluate(request, SimpleNamespace(available=True, feedback=lambda *args, **kwargs: feedback))
    room.comment(request, "제출한 풀이를 확인했습니다.")
    original = store.read()["course_attempts"][request]
    room.end_timer(aid)
    app = make_app("selected", selected_activity=aid)
    assert_no_activity_content(app, ENDED_NOTICE)
    room.resume_timer(aid, remaining_minutes=3)
    app.run()
    assert not app.exception and not app.error
    assert ENDED_NOTICE not in [item.value for item in app.info]
    assert app.text_area and app.get("download_button")
    assert store.read()["course_attempts"][request] == original
    assert student_pdf_attachments(store, original) == [(record, raw)]
    assert UploadedFiles(store).read(record, aid, "10101", "1-1", original=True) == raw


@pytest.mark.parametrize("route", ["list", "requested", "selected"])
def test_resuming_does_not_restore_access_after_the_course_is_reassigned_to_another_class(student_app, route):
    _, room, manager, course_id, _, make_app = student_app
    aid = add_activity(room, course_id, duration=5, attachment=True)
    room.end_timer(aid)
    app = make_app(route)
    assert_no_activity_content(app, ENDED_NOTICE)
    course = manager.get(course_id)
    manager.update(course_id, course["title"], course["color"], ["1-2"])
    room.resume_timer(aid, remaining_minutes=3)
    app.run()
    assert not app.exception
    assert not app.selectbox and not app.text_area and not app.get("download_button")
    assert ENDED_NOTICE not in [item.value for item in app.info]
    if route == "list":
        assert "snorkl_join_" + course_id not in [item.key for item in app.button]
    else:
        assert any("참여할 권한이 없습니다" in item.value for item in app.error)


def closed_screen_watcher(monkeypatch):
    reruns = []
    monkeypatch.setattr(timer_ui, "st", SimpleNamespace(
        session_state={}, empty=lambda: None, rerun=lambda **kwargs: reruns.append(kwargs)))
    return timer_ui.student_availability_watch.__wrapped__, reruns


@pytest.mark.parametrize("scope", ["all", "course", "activity"])
def test_closed_screen_observer_restarts_the_whole_app_once_when_an_assessment_reopens(student_app, monkeypatch, scope):
    _, room, _, course_id, clock, _ = student_app
    aid = add_activity(room, course_id, duration=5)
    room.end_timer(aid)
    watch, reruns = closed_screen_watcher(monkeypatch)
    kwargs = ({"course_id": course_id} if scope == "course" else
              {"course_id": course_id, "aid": aid} if scope == "activity" else {})
    watch(room, **kwargs)
    watch(room, **kwargs)
    assert reruns == []
    room.resume_timer(aid, remaining_minutes=3)
    watch(room, **kwargs)
    assert reruns == [{"scope": "app"}]
    clock["now"] = TODAY + "T00:30:01+09:00"
    watch(room, **kwargs)
    assert reruns == [{"scope": "app"}]


@pytest.mark.parametrize("scope", ["course", "activity"])
def test_scoped_closed_screen_observer_ignores_another_class_assessment_reopening(student_app, monkeypatch, scope):
    _, room, manager, own_course, _, _ = student_app
    own = add_activity(room, own_course, duration=5)
    other_course = manager.create("다른 반 평가", "#123456", ["1-2"])
    other = add_activity(room, other_course, duration=5)
    room.end_timer(own)
    room.end_timer(other)
    watch, reruns = closed_screen_watcher(monkeypatch)
    kwargs = {"course_id": own_course}
    if scope == "activity":
        kwargs["aid"] = own
    watch(room, **kwargs)
    room.resume_timer(other, remaining_minutes=3)
    watch(room, **kwargs)
    assert reruns == []
    room.resume_timer(own, remaining_minutes=3)
    watch(room, **kwargs)
    assert reruns == [{"scope": "app"}]


def test_closed_screen_observer_requests_access_revalidation_after_class_assignment_changes(student_app, monkeypatch):
    _, room, manager, course_id, _, _ = student_app
    aid = add_activity(room, course_id, duration=5)
    room.end_timer(aid)
    watch, reruns = closed_screen_watcher(monkeypatch)
    watch(room, course_id=course_id, aid=aid)
    course = manager.get(course_id)
    manager.update(course_id, course["title"], course["color"], ["1-2"])
    watch(room, course_id=course_id, aid=aid)
    assert reruns == [{"scope": "app"}]
    watch(room, course_id=course_id, aid=aid)
    assert reruns == [{"scope": "app"}]


@pytest.mark.parametrize("scope", ["course", "activity"])
def test_resume_before_the_first_closed_observer_read_still_restarts_the_app(student_app, monkeypatch, scope):
    _, room, _, course_id, _, _ = student_app
    aid = add_activity(room, course_id, duration=5)
    room.end_timer(aid)
    rendered_closed = not room.student_activity_available(room.activity(aid))
    assert rendered_closed
    room.resume_timer(aid, remaining_minutes=3)
    watch, reruns = closed_screen_watcher(monkeypatch)
    kwargs = {"course_id": course_id}
    if scope == "activity":
        kwargs["aid"] = aid
    watch(room, closed=rendered_closed, **kwargs)
    assert reruns == [{"scope": "app"}]
    watch(room, **kwargs)
    assert reruns == [{"scope": "app"}]


@pytest.mark.parametrize("scope", ["course", "activity"])
def test_a_still_closed_initial_snapshot_does_not_create_a_rerun_loop(student_app, monkeypatch, scope):
    _, room, _, course_id, clock, _ = student_app
    aid = add_activity(room, course_id, duration=5)
    room.end_timer(aid)
    watch, reruns = closed_screen_watcher(monkeypatch)
    kwargs = {"course_id": course_id}
    if scope == "activity":
        kwargs["aid"] = aid
    watch(room, closed=True, **kwargs)
    watch(room, closed=True, **kwargs)
    clock["now"] = TODAY + "T00:30:01+09:00"
    watch(room, closed=True, **kwargs)
    assert reruns == []


def test_closed_activity_observer_ignores_an_unrelated_activity_already_reopened_before_its_first_read(student_app, monkeypatch):
    _, room, _, course_id, _, _ = student_app
    focused = add_activity(room, course_id, title="계속 종료된 평가", duration=5)
    other = add_activity(room, course_id, title="다른 평가", duration=5)
    room.end_timer(focused)
    room.end_timer(other)
    room.resume_timer(other, remaining_minutes=3)
    watch, reruns = closed_screen_watcher(monkeypatch)
    watch(room, course_id=course_id, aid=focused, closed=True)
    watch(room, course_id=course_id, aid=focused, closed=True)
    assert reruns == []
