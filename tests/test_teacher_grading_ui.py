"""Submit, grade, review and release scores through the real Streamlit UI."""
import copy
import json
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import storage as db
from snorkl_navigation import REQUESTED_COURSE
from think_app import classroom_ui, embedded
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager, now
from think_app.grading import public_score
from think_app.storage import MemoryStore
from think_app.teacher_grading_ui import REVIEW, PUBLISH


USER = dict(id="10101", name="시험학생", role="student", **{"class": "1-1"})


def grading_result(task, score=88, uncertain=False):
    return dict(score=score, max_score=100, correctness="uncertain" if uncertain else "correct",
                explanation_score=None if uncertain else 3, praise="근거를 잘 연결했어요.",
                observation="각 단계의 식을 확인했어요.", hint="마지막 계산을 확인해 보세요.",
                next_question="다른 풀이도 생각해 볼까요?", misconceptions=[],
                criteria=[dict(criterion=value, level="uncertain" if uncertain else "met",
                               evidence="학생이 작성한 풀이의 근거") for value in task["criteria"]],
                needs_teacher_review=uncertain, uncertainty_reason="글씨 확인 필요" if uncertain else "",
                rationale="PRIVATE_TEACHER_SCORING_RATIONALE", model="test-model")


@pytest.fixture
def grading_ui(tmp_path, monkeypatch):
    backend = db.LocalBackend(str(tmp_path / "dashboard"))
    db._cache.clear()
    monkeypatch.setattr(db, "get_backend", lambda: backend)
    db.append("users", USER)
    store = MemoryStore()
    manager = CourseManager(store)
    cid = manager.create("계산 수행평가", "#123456", ["1-1", "1-2"])
    course = manager.get(cid)
    room = Classroom(store)
    aid = room.save_activity(cid, "계산과 설명", "2+2의 값을 설명하세요.", "PRIVATE_MODEL_ANSWER",
                             ["풀이의 근거를 설명한다."], 2, now()[:10], now()[:10])
    room.distribute_activity(aid)
    calls, behavior = [], {"uncertain": False, "error": False}
    def grade(task, attempt, images, **kwargs):
        from think_app.storage import AppError
        calls.append(copy.deepcopy(attempt))
        if behavior["error"]:
            raise AppError("연결을 확인하고 다시 시도하세요.")
        return grading_result(task, uncertain=behavior["uncertain"])
    ai = SimpleNamespace(available=True, settings=Settings(), grade=grade)
    monkeypatch.setattr(classroom_ui, "AI", lambda settings: ai)
    monkeypatch.setattr(embedded, "get_store", lambda settings: store)
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: Settings())
    monkeypatch.setattr(embedded, "_grading_user", USER, raising=False)
    monkeypatch.setattr(classroom_ui, "_grading_store", store, raising=False)
    monkeypatch.setattr(classroom_ui, "_grading_course", course, raising=False)
    def student():
        app = AppTest.from_string("from think_app import embedded\nembedded.render(embedded._grading_user)\n")
        app.session_state["user"] = dict(USER)
        app.session_state[REQUESTED_COURSE] = cid
        return app.run()
    def teacher():
        app = AppTest.from_string(
            "from think_app import classroom_ui as view\nfrom think_app.config import Settings\n"
            "view.course_detail(view._grading_store, view._grading_course, Settings())\n").run()
        app.radio(key="workspace_" + cid).set_value("학생 제출함").run()
        return app
    try:
        yield room, aid, calls, behavior, student, teacher
    finally:
        db._cache.clear()


def content(app):
    return "\n".join(str(item.value) for kind in (app.title, app.subheader, app.markdown, app.caption, app.info, app.warning) for item in kind)


def submit(app, room, aid):
    next(item for item in app.text_area if item.label == "나의 답안").set_value("2개와 2개를 더하면 4개입니다.")
    next(item for item in app.button if item.label == "답안 제출").click().run()
    assert not app.exception and not app.error
    attempt = room.attempts(aid)[0]
    assert attempt["consent"] is False
    return attempt["id"]


def open_scores(app):
    next(button for button in app.button if button.label == "내 점수 확인하기").click().run()
    assert not app.exception and not app.error


def test_teacher_reviews_corrects_and_releases_score_student_can_check_after_end(grading_ui):
    room, aid, calls, _, make_student, make_teacher = grading_ui
    student = make_student()
    request = submit(student, room, aid)
    teacher = make_teacher()
    assert teacher.radio(key="grading_publication_" + aid).value == REVIEW
    assert not teacher.button(key="grade_pending_" + aid).disabled
    teacher.button(key="grade_pending_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert len(calls) == 1 and public_score(room.attempts(aid)[0]) is None
    student.run()
    assert not student.exception and not student.error
    assert "각 단계의 식을 확인했어요." not in content(student)
    assert not any("88" in item.value for item in student.metric)
    teacher.button(key="open_answer_" + request).click().run()
    next(item for item in teacher.number_input if item.label == "수행평가 점수 · 100점 만점").set_value(93)
    next(item for item in teacher.text_area if item.label == "채점 피드백").set_value("검토 후 풀이 점수를 조정했어요.")
    next(item for item in teacher.button if item.label == "검토 저장").click().run()
    assert not teacher.exception and not teacher.error
    assert public_score(room.attempts(aid)[0]) is None
    student.run()
    assert "검토 후 풀이 점수를 조정했어요." not in content(student)
    teacher.button(key="publish_attempt_" + request).click().run()
    assert not teacher.exception and not teacher.error
    assert public_score(room.attempts(aid)[0]) == 93
    room.start_timer(aid, 10)
    room.end_timer(aid)
    student.run()
    open_scores(student)
    assert "계산과 설명" in content(student)
    assert any("93" in item.value for item in student.metric)
    assert "검토 후 풀이 점수를 조정했어요." in content(student)
    assert "PRIVATE" not in content(student)


def test_teacher_can_publish_automatic_score_immediately(grading_ui):
    room, aid, calls, _, make_student, make_teacher = grading_ui
    student = make_student()
    submit(student, room, aid)
    teacher = make_teacher()
    teacher.radio(key="grading_publication_" + aid).set_value(PUBLISH).run()
    teacher.button(key="grade_pending_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert len(calls) == 1 and public_score(room.attempts(aid)[0]) == 88
    student.run()
    open_scores(student)
    assert any("88" in item.value for item in student.metric)
    assert "각 단계의 식을 확인했어요." in content(student)
    assert "PRIVATE" not in content(student)


def test_uncertain_automatic_score_waits_for_review_even_when_immediate_release_is_selected(grading_ui):
    room, aid, _, behavior, make_student, make_teacher = grading_ui
    student = make_student()
    submit(student, room, aid)
    behavior["uncertain"] = True
    teacher = make_teacher()
    teacher.radio(key="grading_publication_" + aid).set_value(PUBLISH).run()
    teacher.button(key="grade_pending_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert public_score(room.attempts(aid)[0]) is None
    assert "교사 확인 필요" in content(teacher)
    student.run()
    open_scores(student)
    assert not student.metric
    assert "각 단계의 식을 확인했어요." not in content(student)


def test_batch_grades_all_attempts_in_selected_class_and_keeps_other_classes_and_previews_ungraded(grading_ui):
    room, aid, calls, _, make_student, make_teacher = grading_ui
    student = make_student()
    submit(student, room, aid)
    room.submit(aid, USER["id"], USER["name"], "1-1", "다시 설명한 답안", [], False, "b" * 32)
    room.submit(aid, "10201", "다른 반", "1-2", "다른 반 답안", [], False, "c" * 32)
    room.submit(aid, "preview", "체험", "1-1", "체험 답안", [], False, "d" * 32, preview=True)
    teacher = make_teacher()
    teacher.selectbox(key="class_filter_" + aid).set_value("1-1").run()
    assert teacher.button(key="grade_pending_" + aid).label.endswith("2개")
    teacher.button(key="grade_pending_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert len(calls) == 2
    assert all(attempt["student_id"] == USER["id"] and not attempt["preview"] for attempt in calls)
    assert all("assessment_result" not in attempt for attempt in room.attempts(aid)
               if attempt["student_id"] in ("10201", "preview"))


def test_teacher_connection_works_with_student_ai_disabled_and_does_not_store_key_in_assessment(grading_ui, monkeypatch):
    from think_app import teacher_grading_ui
    room, aid, calls, _, make_student, make_teacher = grading_ui
    submit(make_student(), room, aid)
    grade = classroom_ui.AI(Settings()).grade
    monkeypatch.setattr(classroom_ui, "AI", lambda settings: SimpleNamespace(
        available=False, settings=Settings(api_key="test-secret", ai_enabled=False)))
    monkeypatch.setattr(teacher_grading_ui, "AI", lambda settings, client=None:
                        SimpleNamespace(available=True, settings=settings, grade=grade))
    teacher = make_teacher()
    assert not teacher.button(key="grade_pending_" + aid).disabled
    teacher.button(key="grade_pending_" + aid).click().run()
    assert not teacher.exception and not teacher.error
    assert len(calls) == 1 and room.attempts(aid)[0]["assessment_result"]["score"] == 88
    assert "test-secret" not in json.dumps(room.store.read())


@pytest.mark.parametrize("malformed", [None, "invalid", [], {"status": "review", "score": 88, "max_score": 100}])
def test_student_attempt_view_does_not_fall_back_to_legacy_feedback_for_private_or_malformed_grades(grading_ui, malformed):
    room, aid, _, _, make_student, _ = grading_ui
    student = make_student()
    request = submit(student, room, aid)
    room.store.transaction(lambda state: state["course_attempts"][request].update(
        assessment_result=malformed, feedback={"praise": "PRIVATE_LEGACY_FEEDBACK"},
        teacher_comment="PRIVATE_LEGACY_TEACHER_COMMENT"))
    student.run()
    assert not student.exception and not student.error
    assert "PRIVATE" not in content(student)
    assert not student.metric


def test_failed_individual_regrade_removes_the_old_published_score_from_both_views(grading_ui):
    room, aid, _, behavior, make_student, make_teacher = grading_ui
    student = make_student()
    request = submit(student, room, aid)
    teacher = make_teacher()
    teacher.radio(key="grading_publication_" + aid).set_value(PUBLISH).run()
    teacher.button(key="grade_pending_" + aid).click().run()
    assert public_score(room.attempts(aid)[0]) == 88
    teacher.button(key="open_answer_" + request).click().run()
    behavior["error"] = True
    teacher.button(key="grade_attempt_" + request).click().run()
    assert not teacher.exception and teacher.error
    assert public_score(room.attempts(aid)[0]) is None
    assert not any("88" in item.value for item in teacher.metric)
    student.run()
    open_scores(student)
    assert not student.metric
    assert "각 단계의 식을 확인했어요." not in content(student)


def test_manual_grading_without_ai_preserves_an_existing_teacher_comment(grading_ui, monkeypatch):
    room, aid, calls, _, make_student, make_teacher = grading_ui
    student = make_student()
    request = submit(student, room, aid)
    room.comment(request, "이미 확인한 풀이에 남긴 선생님 의견")
    monkeypatch.setattr(classroom_ui, "AI", lambda settings: SimpleNamespace(available=False, settings=Settings()))
    teacher = make_teacher()
    assert teacher.button(key="grade_pending_" + aid).disabled
    teacher.button(key="open_answer_" + request).click().run()
    comment = next(item for item in teacher.text_area if item.label == "채점 피드백")
    assert comment.value == "이미 확인한 풀이에 남긴 선생님 의견"
    next(item for item in teacher.number_input if item.label == "수행평가 점수 · 100점 만점").set_value(83)
    next(item for item in teacher.button if item.label == "저장하고 학생에게 배포").click().run()
    assert not teacher.exception and not teacher.error
    assert not calls and public_score(room.attempts(aid)[0]) == 83
    student.run()
    open_scores(student)
    assert "이미 확인한 풀이에 남긴 선생님 의견" in content(student)

