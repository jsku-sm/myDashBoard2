"""Only published, own assessment results reach the student score report."""
import copy
import json

import pytest
from streamlit.testing.v1 import AppTest

import storage as db
from think_app import embedded, student_scores
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager
from think_app.storage import MemoryStore
from snorkl_navigation import REQUESTED_COURSE


USER = dict(id="10101", name="학생", role="student", must_change="0", **{"class": "1-1"})


def state_with_activity():
    return dict(courses={"course": dict(id="course", title="수학 수업", classes=["1반"])},
                course_activities={"activity": dict(id="activity", course_id="course", title="설명하는 풀이",
                    status="진행 중", distribution_required=True, distributed_at="2026-10-01T09:00:00+09:00",
                    start="2026-10-01", end="2026-10-02", duration_minutes=15,
                    timer_ended_at="2026-10-02T10:00:00+09:00", expected="PRIVATE_EXPECTED",
                    criteria=["PRIVATE_CRITERIA"], prompt="PRIVATE_PROMPT")}, course_attempts={})


def attempt(identity, *, number=1, status="published", score=84, **changes):
    row = dict(id=identity, activity_id="activity", course_id="course", student_id=USER["id"],
               class_id="1반", number=number, created=f"2026-10-01T09:{number:02d}:00+09:00", preview=False,
               text="PRIVATE_WORK", teacher_comment="PRIVATE_LEGACY_COMMENT",
               feedback={"praise": "PRIVATE_LEGACY_FEEDBACK"},
               activity_snapshot={"expected": "PRIVATE_SNAPSHOT"}, images=["PRIVATE_IMAGE"],
               assessment_result=dict(status=status, score=score, max_score=100,
                                      graded_at="2026-10-02T10:00:00+09:00", published_at="2026-10-03T09:00:00+09:00",
                                      feedback={"teacher_comment": "풀이의 근거가 좋아요.", "praise": "식을 잘 정리했어요.",
                                                "teacher_notes": "PRIVATE_TEACHER_NOTES", "answer_key": "PRIVATE_KEY"}))
    row.update(changes)
    return row


def build(state, user=USER):
    return student_scores.build_student_scores(user, state)


def test_published_scores_are_accessible_after_period_and_teacher_end_and_are_safe_projections():
    state = state_with_activity()
    state["course_attempts"]["own"] = attempt("own")
    before = copy.deepcopy(state)

    reports = build(state)

    assert reports[0]["latest_published"]["score"] == 84
    assert reports[0]["latest_published"]["max_score"] == 100
    assert reports[0]["latest_published"]["feedback"] == "풀이의 근거가 좋아요.\n식을 잘 정리했어요."
    assert reports[0]["status"] == "published"
    assert "PRIVATE" not in json.dumps(reports)
    assert "student_id" not in json.dumps(reports)
    assert "assessment_result" not in json.dumps(reports)
    assert state == before


def test_latest_published_submission_and_all_rounds_are_reported_while_new_review_stays_private():
    state = state_with_activity()
    state["course_attempts"] = {"first": attempt("first", number=1, score=75),
                                "second": attempt("second", number=2, score=91),
                                "third": attempt("third", number=3, status="review", score=99)}
    report = build(state)[0]
    assert report["latest_published"]["number"] == 2
    assert report["latest_published"]["score"] == 91
    assert [row["number"] for row in report["attempts"]] == [3, 2, 1]
    assert report["attempts"][0] == dict(number=3, submitted_at="2026-10-01T09:03:00+09:00", status="review")
    assert "99" not in json.dumps(report)


@pytest.mark.parametrize("result", [dict(status="review", score=99), dict(status="published", score=None),
                                     dict(status="published", score=float("nan")), dict(status="published", score=True),
                                     dict(status="published", score=101), dict(status="draft", score=88), None])
def test_unpublished_invalid_or_uncertain_grades_only_show_review_status(result):
    state = state_with_activity()
    result = {"max_score": 100, **result} if isinstance(result, dict) else result
    state["course_attempts"]["own"] = attempt("own", assessment_result=result)
    report = build(state)[0]
    assert report["latest_published"] is None
    assert report["attempts"][0]["status"] == "review"
    assert "score" not in report["attempts"][0]
    assert "feedback" not in report["attempts"][0]


def test_legacy_ungraded_and_unsubmitted_assessments_have_waiting_status_without_invented_scores():
    state = state_with_activity()
    assert build(state)[0]["status"] == "not_submitted"
    row = attempt("legacy")
    del row["assessment_result"]
    state["course_attempts"]["legacy"] = row
    report = build(state)[0]
    assert report["status"] == "waiting"
    assert report["latest_published"] is None
    assert "PRIVATE" not in json.dumps(report)


def test_other_students_classes_courses_previews_and_orphan_attempts_are_excluded():
    state = state_with_activity()
    state["course_attempts"] = {
        "own": attempt("own"), "other": attempt("other", student_id="10102"),
        "preview": attempt("preview", preview=True), "wrong-class": attempt("wrong-class", class_id="2반"),
        "wrong-course": attempt("wrong-course", course_id="different"),
        "wrong-activity": attempt("wrong-activity", activity_id="different"),
    }
    assert len(build(state)[0]["attempts"]) == 1
    assert build(state, {**USER, "class": "2-1"}) == []
    assert build(state, {**USER, "class": "1-2"}) == []
    assert build(state, {**USER, "role": "teacher"}) == []


@pytest.mark.parametrize("changes", [dict(status="배포 전"), dict(status="숨김"), dict(distributed_at=None)])
def test_hidden_or_undistributed_activities_are_not_reported(changes):
    state = state_with_activity()
    state["course_activities"]["activity"].update(changes)
    state["course_attempts"]["own"] = attempt("own")
    assert build(state) == []


def test_archived_or_missing_courses_are_not_reported():
    state = state_with_activity()
    state["course_attempts"]["own"] = attempt("own")
    state["courses"]["course"]["archived"] = True
    assert build(state) == []
    del state["courses"]["course"]
    assert build(state) == []


def test_legacy_distribution_and_dashboard_class_alias_remain_supported():
    state = state_with_activity()
    task = state["course_activities"]["activity"]
    del task["distribution_required"]
    del task["distributed_at"]
    assert len(build(state)) == 1
    state["courses"]["course"]["classes"] = ["1-1"]
    state["course_attempts"]["own"] = attempt("own", class_id="1-1")
    assert build(state)[0]["latest_published"]["score"] == 84


def test_all_current_enrolled_courses_and_assessments_are_reported_without_other_classes():
    state = state_with_activity()
    second = {**state["course_activities"]["activity"], "id": "second", "title": "두 번째 평가"}
    state["course_activities"]["second"] = second
    state["courses"]["second-course"] = dict(id="second-course", title="두 번째 수업", classes=["1-1"])
    state["course_activities"]["third"] = {**second, "id": "third", "course_id": "second-course"}
    state["courses"]["other-course"] = dict(id="other-course", title="PRIVATE_OTHER_CLASS", classes=["1-2"])
    state["course_activities"]["private"] = {**second, "id": "private", "course_id": "other-course"}
    reports = build(state)
    assert {row["activity_id"] for row in reports} == {"activity", "second", "third"}
    assert {row["course_id"] for row in reports} == {"course", "second-course"}
    assert "PRIVATE" not in json.dumps(reports)


@pytest.fixture
def score_ui(tmp_path, monkeypatch):
    backend = db.LocalBackend(str(tmp_path))
    db._cache.clear()
    monkeypatch.setattr(db, "get_backend", lambda: backend)
    db.append("users", USER)
    store = MemoryStore()
    manager = CourseManager(store)
    room = Classroom(store)
    cid = manager.create("수학 수업", "#123456", ["1반"])
    aid = room.save_activity(cid, "설명하는 풀이", "PRIVATE_PROMPT", "PRIVATE_EXPECTED", ["PRIVATE_CRITERION"],
                             2, db.today_str(), db.today_str())
    room.distribute_activity(aid)
    first_id = room.submit(aid, USER["id"], USER["name"], "1반", "PRIVATE_WORK", [], False, "a" * 32)
    second_id = room.submit(aid, USER["id"], USER["name"], "1반", "PRIVATE_WORK", [], False, "b" * 32)
    other_id = room.submit(aid, "10102", "다른 학생", "1반", "PRIVATE_OTHER_WORK", [], False, "c" * 32)
    def insert(state):
        state["course_attempts"][first_id]["assessment_result"] = attempt("first")["assessment_result"]
        state["course_attempts"][second_id]["assessment_result"] = attempt("second", status="review", score=99)["assessment_result"]
        state["course_attempts"][other_id]["assessment_result"] = attempt("other")["assessment_result"]
        state["course_activities"][aid].update(start="2025-01-01", end="2025-01-02", duration_minutes=15,
                                               timer_ended_at="2025-01-02T10:00:00+09:00")
    store.transaction(insert)
    monkeypatch.setattr(embedded, "get_store", lambda settings: store)
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: Settings(mode="local"))
    def app(selected=False):
        result = AppTest.from_string("import streamlit as st\nfrom think_app.embedded import render\n"
                                     "render(st.session_state['user'])\n")
        result.session_state["user"] = dict(USER)
        if selected:
            result.session_state["_snorkl_student_course"] = cid
        return result.run()
    try:
        yield store, cid, aid, app
    finally:
        db._cache.clear()


def displayed(app):
    return "\n".join(str(item.value) for kind in (app.markdown, app.caption, app.info, app.error, app.title, app.subheader)
                     for item in kind)


@pytest.mark.parametrize("selected", [False, True])
def test_score_button_is_enabled_in_list_and_course_even_when_assessment_is_closed(score_ui, selected):
    _, _, _, make = score_ui
    app = make(selected)
    assert not app.exception and not app.error
    assert not app.button(key="snorkl_student_scores_open").disabled
    app.button(key="snorkl_student_scores_open").click().run()
    assert not app.exception and not app.error
    text = displayed(app)
    assert "내 점수 확인하기" in text and "최근 공개 점수 · 1차 제출" in text
    assert "선생님 검토 중" in text and "2차 제출" in text
    assert any(item.value == "84 / 100" for item in app.metric)
    assert "PRIVATE" not in text and "99 / 100" not in text
    app.button(key="snorkl_student_scores_back").click().run()
    assert not app.exception and not app.error
    assert "내 점수 확인하기" in [item.label for item in app.button]


def test_open_score_report_refreshes_after_teacher_publication_without_showing_draft(score_ui):
    store, _, _, make = score_ui
    app = make()
    app.button(key="snorkl_student_scores_open").click().run()
    assert any(item.value == "84 / 100" for item in app.metric)
    store.transaction(lambda state: state["course_attempts"]["b" * 32]["assessment_result"].update(
        status="published", score=91, published_at="2026-10-04T09:00:00+09:00"))
    app.run()
    assert not app.exception and not app.error
    assert any(item.value == "91 / 100" for item in app.metric)
    assert "최근 공개 점수 · 2차 제출" in displayed(app)


def test_score_report_rechecks_changed_enrollment_on_rerun(score_ui):
    _, _, _, make = score_ui
    app = make()
    app.button(key="snorkl_student_scores_open").click().run()
    db.update("users", USER["id"], {"class": "1-2"})
    app.run()
    assert not app.exception and not app.error
    assert not app.metric and "설명하는 풀이" not in displayed(app)
    assert "아직 우리 반에 배포된 수행평가가 없습니다." in displayed(app)


def test_home_or_shared_course_shortcut_leaves_the_score_report_route(score_ui):
    _, cid, _, make = score_ui
    app = make()
    app.button(key="snorkl_student_scores_open").click().run()
    app.session_state[REQUESTED_COURSE] = cid
    app.run()
    assert not app.exception and not app.error
    assert not app.metric
    assert not app.session_state.get("_snorkl_student_scores", False)
    assert app.session_state["_snorkl_student_course"] == cid
    assert not app.button(key="snorkl_student_scores_open").disabled


def test_polling_revalidates_deleted_or_reclassified_account_before_reading_scores(score_ui, monkeypatch):
    store, _, _, _ = score_ui
    db.update("users", USER["id"], {"role": "teacher"})
    monkeypatch.setattr(store, "read", lambda: pytest.fail("Student authorization must happen before score reads."))
    errors = []
    monkeypatch.setattr(student_scores.st, "error", errors.append)
    student_scores.render_student_scores.__wrapped__(store, USER)
    assert errors == ["로그인한 학생 정보를 다시 확인해 주세요."]
