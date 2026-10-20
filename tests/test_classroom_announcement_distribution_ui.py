"""Teachers choose classes; students see only notices sent to their boards."""
from streamlit.testing.v1 import AppTest


APP_SOURCE = '''
import streamlit as st
from classroom_core import ClassroomService, MemoryStore, StorageError
from classroom_core.work import WorkService
from views import classroom as view
from views import classroom_work

class FailingStore(MemoryStore):
    fail_distribution = False
    def put(self, namespace, *args, **kwargs):
        if namespace == "stream_distributions" and self.fail_distribution:
            raise StorageError("일괄 공지 저장 실패")
        return super().put(namespace, *args, **kwargs)

if "fixture" not in st.session_state:
    users = {"t": dict(id="t", role="teacher", name="교사"),
             "other": dict(id="other", role="teacher", name="다른 교사"),
             "s1": dict(id="s1", role="student", name="학생1", **{"class":"1-1"}),
             "s2": dict(id="s2", role="student", name="학생2", **{"class":"1-2"})}
    store = FailingStore()
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _:False)
    first = teacher.create_course("1-1", "2026-2", "수학", class_name="1-1", student_ids=["s1"])
    after = teacher.create_course("방과후", "2026-2", "수학", kind="after_school", class_name="1-1", student_ids=["s1"])
    second = teacher.create_course("1-2", "2026-2", "수학", class_name="1-2", student_ids=["s2"])
    archived = teacher.create_course("1-4", "2025-2", "수학", class_name="1-4")
    teacher.archive_course(archived["id"], archived["version"])
    teacher.create_course("학급 미지정", "2026-2", "수학")
    foreign_teacher = ClassroomService(store, users["other"], users.get, lock_checker=lambda _:False)
    foreign_teacher.create_course("다른 교사 수업", "2026-2", "수학", class_name="1-3")
    st.session_state.fixture = (store, users, first["id"], after["id"], second["id"], archived["id"])

store, users, first, after, second, archived = st.session_state.fixture
actor = users[st.session_state.get("actor", "t")]
service = ClassroomService(store, actor, users.get, lock_checker=lambda _:False)
courses = service.list_courses()
if st.session_state.get("mode") == "integrated":
    original_create, original_detail = view._create_course, view._course_detail
    view._create_course = lambda *a, **k:None
    view._course_detail = lambda *a, **k:None
    try:
        view._my_courses(service, courses, actor)
    finally:
        view._create_course, view._course_detail = original_create, original_detail
else:
    classroom_work.render_announcement_distribution(service, courses, actor)
    if actor["role"] == "student":
        original_questions, original_records = classroom_work._render_questions, classroom_work.render_records
        classroom_work._render_questions = lambda *a, **k:None
        classroom_work.render_records = lambda *a, **k:None
        try:
            for course in courses:
                classroom_work.render_stream(service, course, actor)
        finally:
            classroom_work._render_questions, classroom_work.render_records = original_questions, original_records
'''


def app(mode=None):
    screen = AppTest.from_string(APP_SOURCE)
    if mode:
        screen.session_state["mode"] = mode
    screen.run()
    assert not screen.exception and not screen.error
    return screen


def element(items, label):
    return next(item for item in items if item.label == label)


def compose(screen):
    element(screen.text_input, "일괄 공지 제목").set_value("다음 수업 준비물")
    element(screen.text_area, "일괄 공지 내용").set_value("학습지를 지참하세요.")


def test_all_classes_distribution_posts_to_active_owned_boards_only():
    screen = app()
    assert any("2개 학급 · 3개 수업 게시판" in row.value for row in screen.caption)
    assert any("정규·방과후" in row.value for row in screen.caption)
    compose(screen)
    element(screen.button, "선택한 학급에 공지 게시").click().run()
    assert not screen.exception and not screen.error
    store, _, first, after, second, archived = screen.session_state["fixture"]
    notice, = store.list("stream_distributions")
    assert set(notice["target_course_ids"]) == {first, after, second}
    assert archived not in notice["target_course_ids"]
    assert store.list("stream") == []  # A single atomic publication, no partial copies.
    assert any("2개 학급의 3개 수업 게시판" in row.value for row in screen.success)
    assert element(screen.text_input, "일괄 공지 제목").value == ""
    assert element(screen.text_area, "일괄 공지 내용").value == ""


def test_selected_class_notice_is_visible_only_to_its_student():
    screen = app()
    element(screen.radio, "공지 배포 범위").set_value("선택 학급").run()
    assert element(screen.multiselect, "공지를 게시할 학급").options == ["1-1", "1-2"]
    element(screen.multiselect, "공지를 게시할 학급").set_value(["1-2"]).run()
    compose(screen)
    element(screen.button, "선택한 학급에 공지 게시").click().run()
    assert not screen.exception and not screen.error
    store, _, _, _, second, _ = screen.session_state["fixture"]
    notice, = store.list("stream_distributions")
    assert notice["target_course_ids"] == [second]
    screen.session_state["actor"] = "s1"
    screen.run()
    assert not screen.exception and not screen.error
    assert not any("다음 수업 준비물" in row.value for row in screen.markdown)
    assert not any(row.label == "선택한 학급에 공지 게시" for row in screen.button)
    screen.session_state["actor"] = "s2"
    screen.run()
    assert not screen.exception and not screen.error
    assert any("다음 수업 준비물" in row.value for row in screen.markdown)
    assert any("학습지를 지참하세요." in row.value for row in screen.markdown)


def test_empty_selection_never_means_every_class():
    screen = app()
    element(screen.radio, "공지 배포 범위").set_value("선택 학급").run()
    compose(screen)
    element(screen.button, "선택한 학급에 공지 게시").click().run()
    assert not screen.exception
    assert any("한 곳 이상 선택" in row.value for row in screen.warning)
    assert screen.session_state["fixture"][0].list("stream_distributions") == []


def test_failure_retains_draft_and_same_request_retries_once():
    from views.classroom_work import _key
    screen = app()
    store = screen.session_state["fixture"][0]
    store.fail_distribution = True
    compose(screen)
    element(screen.button, "선택한 학급에 공지 게시").click().run()
    assert not screen.exception and screen.error and not screen.success
    assert store.list("stream_distributions") == []
    assert store.list("stream") == []
    assert element(screen.text_input, "일괄 공지 제목").value == "다음 수업 준비물"
    token_key = _key("announcement_distribution", "t") + "_draft_request"
    request_id = screen.session_state[token_key]
    store.fail_distribution = False
    element(screen.button, "선택한 학급에 공지 게시").click().run()
    assert not screen.exception and not screen.error
    notice, = store.list("stream_distributions")
    assert notice["request_id"] == request_id


def test_bulk_form_only_appears_on_teacher_all_filter():
    screen = app("integrated")
    assert element(screen.text_input, "일괄 공지 제목")
    screen.session_state["classroom_t_my_kind"] = "regular"
    screen.run()
    assert not screen.exception and not screen.error
    assert not any(row.label == "일괄 공지 제목" for row in screen.text_input)
    screen.session_state["classroom_t_my_kind"] = "after_school"
    screen.run()
    assert not any(row.label == "일괄 공지 제목" for row in screen.text_input)
    screen.session_state["classroom_t_my_kind"] = "전체"
    screen.run()
    assert element(screen.text_input, "일괄 공지 제목")
