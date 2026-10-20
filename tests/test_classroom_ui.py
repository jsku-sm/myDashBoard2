"""Streamlit interaction checks for durable progress and role-aware screens."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from views import classroom as view


SCRIPT = '''
import streamlit as st
from classroom_core import ClassroomService, MemoryStore, StorageError
from views import classroom as view

class TestStore(MemoryStore):
    fail = False
    def put(self, *args, **kwargs):
        if self.fail:
            raise StorageError("GitHub 저장 실패 · 다시 시도하세요.")
        return super().put(*args, **kwargs)

users = {"t": {"id":"t", "role":"teacher", "name":"교사"},
         "s": {"id":"s", "role":"student", "name":"학생", "class":"1-1"}}
if "test_store" not in st.session_state:
    store = TestStore()
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _:False)
    plan = teacher.create_curriculum("기하 수업안", "수학", [
        {"id":"one", "unit":"기하", "title":"직선", "objective":"직선을 이해한다"},
        {"id":"two", "unit":"기하", "title":"원"}])
    course = teacher.create_course("수학 수업", "2026-2", "수학", class_name="1-1", curriculum_id=plan["id"], student_ids=["s"])
    after = teacher.create_course("방과후", "2026-2", "수학", kind="after_school", class_name="1-1")
    student = ClassroomService(store, users["s"], users.get, lock_checker=lambda _:False)
    student.request_join(after["id"])
    st.session_state.test_store = store
    st.session_state.test_course = course["id"]
store = st.session_state.test_store
mode = st.session_state.get("test_mode", "editor")
user = users["s"] if mode == "student" else users["t"]
service = ClassroomService(store, user, users.get, lock_checker=lambda _:False)
course = service.get_course(st.session_state.test_course)
if mode == "editor":
    view._lesson_editor(service, course, course["lessons"][0], user, key="test")
elif mode == "dashboard":
    view._dashboard(service, service.list_courses(), user)
elif mode == "matrix":
    view._matrix(service, service.list_courses(), user, "전체")
elif mode == "student":
    view._my_courses(service, service.list_courses(), user)
'''


@pytest.fixture(autouse=True)
def isolated_helpers(monkeypatch):
    monkeypatch.setattr(view, "_resources", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "_work_tab", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "_calendar_resources", lambda *args, **kwargs: [])


def element(items, label):
    return next(item for item in items if item.label == label)


def test_completion_requires_actual_date_then_durable_ack():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    element(app.selectbox, "진행 상태").select("completed")
    element(app.text_input, "변경 이유").set_value("실제 수업 확인")
    element(app.checkbox, "실제 수업을 확인했으며, 선택한 상태와 날짜를 저장합니다.").check()
    element(app.button, "진도 저장").click().run()
    assert any("실제 수업일" in item.value for item in app.error)
    store, cid = app.session_state["test_store"], app.session_state["test_course"]
    assert store.get("courses", cid)["lesson_records"] == {}
    element(app.date_input, "실제 수업일").set_value(date(2026, 10, 20))
    element(app.button, "진도 저장").click().run()
    assert not app.exception
    record = store.get("courses", cid)["lesson_records"]["one"]
    assert record["progress"] == "completed" and record["actual_date"] == "2026-10-20"
    assert "GitHub" in app.session_state["classroom_t_flash"]


def test_storage_failure_preserves_form_and_never_acknowledges():
    app = AppTest.from_string(SCRIPT).run()
    store = app.session_state["test_store"]
    store.fail = True
    element(app.text_area, "어디까지 진행했나요?").set_value("이어서 설명할 풀이")
    element(app.text_input, "변경 이유").set_value("진행 중 메모")
    element(app.checkbox, "실제 수업을 확인했으며, 선택한 상태와 날짜를 저장합니다.").check()
    element(app.button, "진도 저장").click().run()
    assert not app.exception
    assert any("저장 실패" in item.value for item in app.error)
    assert element(app.text_area, "어디까지 진행했나요?").value == "이어서 설명할 풀이"
    assert not app.success
    assert "classroom_t_flash" not in app.session_state
    assert store.get("courses", app.session_state["test_course"])["lesson_records"] == {}


def test_concurrent_update_preserves_draft_until_latest_record_review():
    app = AppTest.from_string(SCRIPT).run()
    element(app.text_area, "어디까지 진행했나요?").set_value("잃으면 안 되는 작성 중 메모")
    store, cid = app.session_state["test_store"], app.session_state["test_course"]
    latest = store.get("courses", cid)
    latest["lesson_records"]["one"] = {"progress": "scheduled", "period": "다른 창의 3교시"}
    store.put("courses", cid, latest, latest["version"])
    element(app.text_input, "변경 이유").set_value("작성 내용 저장")
    element(app.checkbox, "실제 수업을 확인했으며, 선택한 상태와 날짜를 저장합니다.").check()
    element(app.button, "진도 저장").click().run()
    assert not app.exception
    assert any("다른 창" in item.value for item in app.error)
    assert element(app.text_area, "어디까지 진행했나요?").value == "잃으면 안 되는 작성 중 메모"
    assert store.get("courses", cid)["lesson_records"]["one"]["period"] == "다른 창의 3교시"
    element(app.button, "최신 기록 확인 · 작성 중인 입력 유지").click().run()
    assert element(app.text_area, "어디까지 진행했나요?").value == "잃으면 안 되는 작성 중 메모"
    element(app.button, "진도 저장").click().run()
    assert store.get("courses", cid)["lesson_records"]["one"]["memo"] == "잃으면 안 되는 작성 중 메모"


def test_teacher_dashboard_uses_saved_courses_and_missing_plan_label():
    app = AppTest.from_string(SCRIPT)
    app.session_state["test_mode"] = "dashboard"
    app.run()
    assert not app.exception
    assert {item.label for item in app.selectbox} >= {"학기", "과목", "정규·방과후", "단원"}
    assert any(item.value == "수업안 미설정" for item in app.metric)
    assert any("계획 미설정" in item.value for item in app.info)
    assert [item.value for item in app.metric if item.label == "완료 / 적용 차시"] == ["0 / 2", "0 / 0"]


def test_matrix_separates_distinct_curricula_and_shows_state_text():
    app = AppTest.from_string(SCRIPT)
    app.session_state["test_mode"] = "matrix"
    app.run()
    assert not app.exception
    group = element(app.selectbox, "같은 공통 수업안의 학급끼리 비교")
    assert len(group.options) == 2
    frame = app.dataframe[0].value
    assert frame.iloc[0, 1] == "⚪ 미배정"


def test_pending_student_course_is_not_opened_or_exposed():
    app = AppTest.from_string(SCRIPT)
    app.session_state["test_mode"] = "student"
    app.run()
    assert not app.exception
    assert any("참여 승인 대기" in item.value for item in app.info)
    picker = element(app.selectbox, "수업 선택")
    assert len(picker.options) == 1 and "수학 수업" in picker.options[0]
    assert not app.error


def test_edited_curriculum_preserves_resource_reference_ids():
    plan = {"lessons": [{"id": "lesson", "title": "자료", "resources": [
        {"kind": "material", "id": "stable", "title": "자료 원본", "url": "https://example.com"}]}]}
    rows = view._curriculum_editor_rows(plan)
    assert view._edited_lessons(rows, plan)[0]["resources"][0]["id"] == "stable"
    rows[0]["연결 자료 · 제목|주소"] = "안전하지 않은 주소|javascript:alert(1)"
    with pytest.raises(ValueError):
        view._edited_lessons(rows, plan)


WORK_SCRIPT = '''
import streamlit as st
from classroom_core import ClassroomService, MemoryStore
from classroom_core.work import WorkService
from views import classroom_work as view

class NoExternalActivities:
    def __getattr__(self, name):
        raise AssertionError("Classroom attempted an external activity call: " + name)

users = {"t": {"id":"t", "role":"teacher", "name":"교사"},
         "s": {"id":"s", "role":"student", "name":"학생", "class":"1-1"}}
if "work_store" not in st.session_state:
    store = MemoryStore()
    teacher = ClassroomService(store, users["t"], users.get, lock_checker=lambda _:False)
    course = teacher.create_course("수학", "2026-2", "수학", class_name="1-1", student_ids=["s"])
    work = WorkService(teacher, legacy=NoExternalActivities())
    task = work.save_assignment(course["id"], "일반 과제", "풀이를 설명하세요", published=True)
    material = work.save_material(course["id"], "일반 자료", body="설명", published=True)
    for namespace, original in (("assignments", task), ("materials", material)):
        linked = dict(original, id="old-" + namespace, title="이전 연결 " + namespace,
                      activity_id="preserved-old-activity")
        if namespace == "assignments":
            linked["methods"] = ["snorkl"]
        store.put(namespace, linked["id"], linked, None)
    st.session_state.work_store = store
    st.session_state.work_course = course["id"]
store = st.session_state.work_store
uid = st.session_state.get("work_uid", "t")
service = ClassroomService(store, users[uid], users.get, lock_checker=lambda _:False)
course = service.get_course(st.session_state.work_course)
work = WorkService(service, legacy=NoExternalActivities())
mode = st.session_state.get("work_mode", "assignment_form")
if mode == "assignment_form":
    view._assignment_form(work, course)
elif mode == "material_form":
    view._material_form(work, course)
elif mode == "assignments":
    view.render_assignments(work, course)
elif mode == "materials":
    view.render_materials(work, course)
elif mode == "today":
    view.render_today(work, [course])
elif mode == "resources":
    view.render_lesson_resources(work, course, {"id":"lesson", "activity_id":"preserved-old-activity",
        "resources":[{"kind":"snorkl", "id":"old"},
                     {"kind":"assignment", "id":"old-assignments"},
                     {"kind":"material", "id":"old-materials"}]})
elif mode == "calendar":
    st.session_state.calendar_rows = view.calendar_resources(work, course)
'''


def work_app(mode, uid="t"):
    app = AppTest.from_string(WORK_SCRIPT)
    app.session_state["work_mode"] = mode
    app.session_state["work_uid"] = uid
    return app.run()


def assert_no_activity_widgets(app):
    for kind in ("selectbox", "multiselect", "button", "text_input", "caption", "info"):
        for item in getattr(app, kind):
            shown = str(getattr(item, "label", "")) + str(getattr(item, "options", ""))
            if kind in ("caption", "info"):
                shown += str(item.value)
            assert "snorkl" not in shown.lower() and "소노클" not in shown


def test_assignment_form_saves_text_and_file_options_without_external_activity():
    app = work_app("assignment_form")
    assert not app.exception
    methods = element(app.multiselect, "허용할 제출 방식")
    assert methods.options == ["앱 안에서 답변", "파일·사진"]
    methods.set_value(["text", "file"])
    element(app.text_input, "과제 제목").set_value("새 과제")
    element(app.text_area, "안내").set_value("앱에서 작성하거나 파일을 제출하세요")
    element(app.button, "대상·공개 여부 확인 후 과제 저장").click().run()
    assert not app.exception
    saved = next(row for row in app.session_state["work_store"].list("assignments") if row["title"] == "새 과제")
    assert saved["methods"] == ["text", "file"]
    assert not saved.get("activity_id")
    assert_no_activity_widgets(app)


def test_material_form_has_no_external_activity_selector_and_saves():
    app = work_app("material_form")
    assert not app.exception
    element(app.text_input, "자료 제목").set_value("새 자료")
    element(app.text_area, "자료 설명").set_value("수업 설명")
    element(app.button, "배부 대상 확인 후 자료 저장").click().run()
    assert not app.exception
    saved = next(row for row in app.session_state["work_store"].list("materials") if row["title"] == "새 자료")
    assert not saved.get("activity_id")
    assert_no_activity_widgets(app)


@pytest.mark.parametrize("uid", ["t", "s"])
def test_old_linked_assignment_has_no_submit_or_grading_controls(uid):
    app = work_app("assignments", uid)
    element(app.selectbox, "과제 선택").select("old-assignments").run()
    assert not app.exception
    assert any("외부 활동 연결은 비활성화" in item.value for item in app.info)
    assert not any(item.label in ("내 답안", "교사 피드백 초안") for item in app.text_area)
    assert not any(item.label in ("제출 요청", "평가 초안 저장", "GitHub 임시 저장", "양식 복사") for item in app.button)
    old = app.session_state["work_store"].get("assignments", "old-assignments")
    assert old["activity_id"] == "preserved-old-activity"
    assert old["methods"] == ["snorkl"] and old["version"] == 1
    assert_no_activity_widgets(app)


def test_regular_student_assignment_keeps_draft_and_submission_flow():
    app = work_app("assignments", "s")
    assert not app.exception
    element(app.text_area, "내 답안").set_value("유지해야 할 풀이 과정")
    element(app.button, "GitHub 임시 저장").click().run()
    assert not app.exception
    assert element(app.text_area, "내 답안").value == "유지해야 할 풀이 과정"
    saved = app.session_state["work_store"].list("submissions")[0]
    assert saved["draft"]["text"] == "유지해야 할 풀이 과정"
    element(app.button, "제출 요청").click().run()
    assert not app.exception
    saved = app.session_state["work_store"].list("submissions")[0]
    assert len(saved["versions"]) == 1
    assert saved["versions"][0]["text"] == "유지해야 할 풀이 과정"
    assert any("제출 완료" in item.value for item in app.success)
    assert_no_activity_widgets(app)


@pytest.mark.parametrize("mode", ["materials", "resources", "today", "calendar"])
def test_old_links_do_not_load_or_launch_external_activities(mode):
    app = work_app(mode, "s" if mode == "today" else "t")
    assert not app.exception
    assert_no_activity_widgets(app)
    if mode == "calendar":
        assert len(app.session_state["calendar_rows"]) == 2
        assert all(not row["id"].startswith("old-") and "activity_id" not in row
                   for row in app.session_state["calendar_rows"])
    if mode == "today":
        assert list(app.dataframe[0].value["할일"]) == ["일반 과제"]


def test_curriculum_hides_old_activity_id_and_preserves_existing_metadata():
    plan = {"lessons": [{"id":"lesson", "title":"기존 차시", "activity_id":"preserved-old-activity"}]}
    rows = view._curriculum_editor_rows(plan)
    assert "소노클 활동 ID" not in rows[0]
    rows[0]["차시명"] = "변경한 차시"
    saved = view._edited_lessons(rows, plan)[0]
    assert saved["title"] == "변경한 차시"
    assert saved["activity_id"] == "preserved-old-activity"
