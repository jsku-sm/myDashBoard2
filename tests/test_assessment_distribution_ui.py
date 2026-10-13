"""Create, distribute and submit through the actual teacher and student widgets."""
from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from think_app import classroom_ui, embedded
from think_app.classroom import Classroom
from think_app.courses import CourseManager, now
from think_app.storage import MemoryStore


@pytest.fixture
def distribution_ui(monkeypatch):
    store = MemoryStore()
    manager = CourseManager(store)
    cid = manager.create("수행평가 배포", "#123456", ["1-1"])
    course = manager.get(cid)
    for module in (classroom_ui, embedded):
        monkeypatch.setattr(module, "_distribution_test_store", store, raising=False)
        monkeypatch.setattr(module, "_distribution_test_course", course, raising=False)

    def app(role):
        if role == "teacher":
            source = ("from think_app import classroom_ui as view\n"
                      "from think_app.config import Settings\n"
                      "view.course_detail(view._distribution_test_store, view._distribution_test_course, Settings())\n")
        else:
            source = ("from think_app import embedded as view\n"
                      "from think_app.config import Settings\n"
                      "from think_app.courses import CourseManager\n"
                      "view.student_view(view._distribution_test_store, CourseManager(view._distribution_test_store), "
                      "Settings(), {'id': '10101', 'name': '학생', 'class': '1-1', 'role': 'student'}, "
                      "view._distribution_test_course['id'])\n")
        return AppTest.from_string(source).run()

    return Classroom(store), cid, app


def create_task(room, cid, **changes):
    values = dict(title="세부 활동", prompt="2+2의 값을 구하세요.", expected="4",
                  criteria=["풀이의 근거를 설명한다."], max_attempts=2, start=now()[:10], end=now()[:10])
    values.update(changes)
    return room.save_activity(cid, **values)


@pytest.mark.parametrize("duration", [0, 15])
def test_teacher_saves_distributes_and_student_submits(distribution_ui, duration):
    room, cid, make_app = distribution_ui
    teacher = make_app("teacher")
    next(button for button in teacher.button if button.label == "＋ 활동 추가하기").click().run()
    prefix = "activity_form_" + cid
    teacher.text_input(key=prefix + "_title").set_value("계산과 설명")
    teacher.text_area(key=prefix + "_prompt").set_value("2+2의 값을 구하세요.")
    teacher.text_area(key=prefix + "_expected").set_value("4")
    teacher.text_area(key=prefix + "_criteria").set_value("풀이의 근거를 설명한다.")
    teacher.number_input(key=prefix + "_duration").set_value(duration)
    teacher.button(key=prefix + "_save").click().run()
    assert not teacher.exception and not teacher.error
    task = room.activities(cid)[0]
    aid = task["id"]
    assert task["status"] == "배포 전" and not room._can_submit(task)
    student = make_app("student")
    assert not student.exception
    assert "수행평가 기간이 아닙니다." in [item.value for item in student.info]
    assert not student.text_area and not student.get("download_button")

    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    task = room.activity(aid)
    assert task["status"] == "진행 중" and task["distributed_at"]
    assert room.timer_state(task)["phase"] == ("running" if duration else "unlimited")
    assert teacher.button(key="distribute_activity_" + aid).disabled
    assert any("학생에게 배포했습니다." in item.value for item in teacher.success)
    student.run()
    assert not student.exception
    answer = next(item for item in student.text_area if item.label == "나의 답안")
    answer.set_value("2개와 2개를 더하면 4개입니다.")
    next(button for button in student.button if button.label == "답안 제출").click().run()
    assert not student.exception and not student.error
    attempts = room.attempts(aid)
    assert len(attempts) == 1 and attempts[0]["student_id"] == "10101"
    assert attempts[0]["activity_snapshot"]["distributed_at"] == task["distributed_at"]


def test_activity_detail_has_distribution_button(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    teacher = make_app("teacher")
    teacher.button(key="activity_" + aid).click().run()
    assert not teacher.exception
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.student_activity_available(room.activity(aid))


def test_teacher_workbench_also_has_distribution_button(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    teacher = make_app("teacher")
    teacher.radio(key="workspace_" + cid).set_value("작업하기").run()
    assert not teacher.exception
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.student_activity_available(room.activity(aid))


def test_teacher_can_republish_hidden_activity_without_stale_status_override(distribution_ui):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid)
    room.distribute_activity(aid)
    distributed = room.activity(aid)["distributed_at"]
    room.set_status(aid, "숨김")
    teacher = make_app("teacher")
    assert teacher.button(key="distribute_activity_" + aid).label == "학생에게 다시 배포"
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["status"] == "진행 중"
    assert room.activity(aid)["distributed_at"] == distributed
    teacher.run()
    assert not teacher.exception and room.activity(aid)["status"] == "진행 중"


def test_future_activity_can_be_distributed_but_students_wait_for_period(distribution_ui):
    room, cid, make_app = distribution_ui
    today = date.fromisoformat(now()[:10])
    aid = create_task(room, cid, start=(today + timedelta(days=2)).isoformat(),
                      end=(today + timedelta(days=3)).isoformat())
    teacher = make_app("teacher")
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert room.activity(aid)["distributed_at"]
    assert any("예약 배포" in item.value for item in teacher.success)
    student = make_app("student")
    assert not student.exception and not student.text_area
    assert "수행평가 기간이 아닙니다." in [item.value for item in student.info]


def test_direct_student_preview_hides_question_after_period_ends(distribution_ui, monkeypatch):
    room, cid, _ = distribution_ui
    aid = create_task(room, cid)
    room.distribute_activity(aid)
    monkeypatch.setattr(classroom_ui, "_distribution_test_aid", aid, raising=False)
    student = AppTest.from_string(
        "from think_app import classroom_ui as view\n"
        "from think_app.ai import AI\n"
        "from think_app.config import Settings\n"
        "from think_app.classroom import Classroom\n"
        "room = Classroom(view._distribution_test_store)\n"
        "view.student_preview(room, view._distribution_test_course, room.activity(view._distribution_test_aid), "
        "AI(Settings()), identity=('10101', '학생', '1-1'))\n"
    ).run()
    assert not student.exception and student.text_area
    yesterday = (date.fromisoformat(now()[:10]) - timedelta(days=1)).isoformat()
    room.store.transaction(lambda state: state["course_activities"][aid].update(start=yesterday, end=yesterday))
    student.run()
    assert not student.exception and not student.text_area and not student.get("component_instance")
    assert [item.value for item in student.info] == ["수행평가 기간이 아닙니다."]


@pytest.mark.parametrize("phase", ["expired", "ended"])
def test_redistributing_closed_timer_reports_students_are_still_blocked(distribution_ui, phase):
    room, cid, make_app = distribution_ui
    aid = create_task(room, cid, duration_minutes=1)
    room.distribute_activity(aid)
    if phase == "expired":
        room.adjust_timer(aid, 0)
    else:
        room.end_timer(aid)
    room.set_status(aid, "숨김")
    teacher = make_app("teacher")
    teacher.button(key="distribute_activity_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert not room.student_activity_available(room.activity(aid))
    assert any("학생에게 표시되지 않습니다." in item.value for item in teacher.success)
    assert not any("학생 메뉴에 활동이 표시됩니다." in item.value for item in teacher.success)
