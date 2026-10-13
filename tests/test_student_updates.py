import copy
from datetime import datetime, timezone
import json

import pytest

from student_updates import build_student_updates


USER = dict(id="00101", name="학생", role="student", **{"class": "1-1"})
NOW = "2026-10-13T10:00:00+09:00"


def build(*, user=None, materials=None, submissions=None, questions=None, announcements=None,
          state=None, now=NOW):
    return build_student_updates(USER if user is None else user, materials or [], submissions or [],
                                 questions or [], announcements or [], state or {}, now=now)


def state_with_activity(**changes):
    activity = dict(id="activity", course_id="course", title="설명하는 풀이", status="진행 중",
                    distribution_required=True, distributed_at="2026-10-13T09:00:00+09:00",
                    start="2026-10-13", end="2026-10-13", duration_minutes=0, max_attempts=2,
                    created="2026-10-12T09:00:00+09:00", updated="2026-10-12T09:00:00+09:00",
                    prompt="PRIVATE_PROMPT", expected="PRIVATE_EXPECTED", criteria=["PRIVATE_CRITERIA"],
                    expected_images=[dict(blob_ref="PRIVATE_IMAGE")])
    activity.update(changes)
    return dict(courses={"course": dict(id="course", title="수학 수업", classes=["1반"])},
                course_activities={"activity": activity}, course_attempts={})


def attempt(identity, **changes):
    row = dict(id=identity, activity_id="activity", course_id="course", student_id=USER["id"],
               class_id="1반", number=1, created="2026-10-13T09:30:00+09:00", preview=False,
               teacher_comment="풀이의 근거를 잘 설명했어요.", reviewed="2026-10-13T09:40:00+09:00",
               feedback=None, text="PRIVATE_STUDENT_TEXT", activity_snapshot={"expected": "PRIVATE_SNAPSHOT"},
               images=["PRIVATE_ATTACHMENT"], documents=[{"filename": "PRIVATE_FILE"}])
    row.update(changes)
    return row


def notice(identity, classes='["1-1"]', **changes):
    row = dict(id=identity, title="수업 안내", content="활동지를 준비하세요.", classes=classes,
               active="1", created_at="2026-10-12 09:00:00", updated_at="2026-10-13 09:00:00",
               author_id="PRIVATE_TEACHER_ID", author_name="선생님")
    row.update(changes)
    return row


def test_public_documents_are_projected_from_current_subjects_and_categories():
    material = dict(id="math1", subject="공통수학1", category="학습지", unit="다항식", title="학습지",
                    description="다항식을 계산해 보세요.", uploaded_at="2026-10-13 09:00:00",
                    file_id="file1", file_name="활동지.pdf", file_url="https://example.org/file1", mime="application/pdf",
                    teacher_notes="PRIVATE_NOTES", expected="PRIVATE_EXPECTED")
    plan = {**material, "id": "math2", "subject": "공통수학2", "category": "평가계획",
            "uploaded_at": "2026-10-13 10:00:00"}
    rows = [material, plan, {**material, "subject": "교사 전용"}, {**material, "category": "비공개"}]

    documents = build(materials=rows)["documents"]

    assert [row["id"] for row in documents] == ["math2", "math1"]
    assert documents[1] == {key: material[key] for key in
                            ("id", "title", "subject", "category", "unit", "description", "uploaded_at",
                             "file_id", "file_name", "file_url", "mime")}
    assert "PRIVATE" not in json.dumps(documents)


@pytest.mark.parametrize("user", [{}, {**USER, "role": "teacher"}, {**USER, "id": ""}, {**USER, "class": ""}])
def test_unauthenticated_or_nonstudent_users_receive_no_updates(user):
    updates = build(user=user, materials=[dict(subject="공통수학1", category="학습지")],
                    announcements=[notice("notice")], state=state_with_activity())
    assert updates == dict(documents=[], feedback=[], assessments=[], announcements=[])


def test_teacher_comments_and_question_answers_are_personal_and_sorted_by_feedback_time():
    submissions = [dict(id="own", student_id=USER["id"], subject="공통수학1", title="나의 풀이", unit="다항식",
                        created_at="2026-10-10 09:00:00", teacher_comment_at="2026-10-13 10:00:00",
                        teacher_comment="좋은 설명이에요.", feedback="자동 격려", content="PRIVATE_TEXT"),
                   dict(id="other", student_id="101", subject="공통수학1", teacher_comment="PRIVATE_OTHER"),
                   dict(id="no-comment", student_id=USER["id"], subject="공통수학1", feedback="자동 격려"),
                   dict(id="hidden-subject", student_id=USER["id"], subject="교사 전용", teacher_comment="PRIVATE_OTHER")]
    questions = [dict(id="answered", student_id=USER["id"], subject="공통수학2", title="내 질문",
                      created_at="2026-10-12 09:00:00", answered_at="2026-10-13 09:50:00", answer="식을 먼저 정리해 봐요."),
                 dict(id="other-question", student_id="00202", subject="공통수학1", answer="PRIVATE_OTHER"),
                 dict(id="unanswered", student_id=USER["id"], subject="공통수학1", answer="")]

    feedback = build(submissions=submissions, questions=questions)["feedback"]

    assert [row["id"] for row in feedback] == ["own", "answered"]
    assert feedback[0]["updated_at"] == "2026-10-13 10:00:00"
    assert feedback[0]["content"] == "좋은 설명이에요."
    assert feedback[1]["answer"] == feedback[1]["content"] == "식을 먼저 정리해 봐요."
    assert "PRIVATE" not in json.dumps(feedback)
    assert all("student_id" not in row for row in feedback)


def test_legacy_teacher_comment_without_feedback_timestamp_keeps_creation_date():
    row = dict(id="legacy", student_id=USER["id"], subject="공통수학1", created_at="2026-10-12 09:00:00",
               teacher_comment="기존 피드백")
    assert build(submissions=[row])["feedback"][0]["updated_at"] == row["created_at"]


def test_mixed_korea_csv_and_utc_timestamps_sort_by_instant():
    submissions = [dict(id="csv", student_id=USER["id"], subject="공통수학1", teacher_comment="교사 피드백",
                        teacher_comment_at="2026-10-13 10:00:00")]
    state = state_with_activity()
    state["course_attempts"]["utc"] = attempt("utc", reviewed="2026-10-13T01:30:00+00:00")

    assert [row["id"] for row in build(submissions=submissions, state=state)["feedback"]] == ["utc", "csv"]


@pytest.mark.parametrize("activity_changes", [dict(status="숨김"), dict(status="배포 전"),
                                             dict(distributed_at=None), dict(course_id="missing")])
def test_unpublished_hidden_or_orphan_activities_and_their_feedback_are_excluded(activity_changes):
    state = state_with_activity(**activity_changes)
    state["course_attempts"]["own"] = attempt("own")
    updates = build(state=state)
    assert updates["assessments"] == updates["feedback"] == []


def test_enrollment_aliases_and_grade_boundaries_are_used_for_assessment_updates():
    state = state_with_activity()
    assert len(build(state=state)["assessments"]) == 1
    assert build(user={**USER, "class": "2-1"}, state=state)["assessments"] == []
    assert build(user={**USER, "class": "1-2"}, state=state)["assessments"] == []
    state["courses"]["course"]["classes"] = ["1-1"]
    state["course_attempts"]["dashboard"] = attempt("dashboard", class_id="1-1")
    assert len(build(state=state)["feedback"]) == 1


def test_only_own_real_attempts_are_counted_or_returned_without_raw_payloads():
    state = state_with_activity()
    state["course_attempts"] = {
        "own": attempt("own"), "other": attempt("other", student_id="00202", teacher_comment="PRIVATE_OTHER"),
        "preview": attempt("preview", preview=True, teacher_comment="PRIVATE_PREVIEW"),
        "wrong-class": attempt("wrong-class", class_id="2반", teacher_comment="PRIVATE_CLASS"),
        "wrong-course": attempt("wrong-course", course_id="missing", teacher_comment="PRIVATE_COURSE"),
        "wrong-activity": attempt("wrong-activity", activity_id="missing", teacher_comment="PRIVATE_ACTIVITY"),
    }

    updates = build(state=state)

    assert updates["assessments"][0]["attempt_count"] == 1
    assert updates["assessments"][0]["last_submitted_at"] == "2026-10-13T09:30:00+09:00"
    assert updates["assessments"][0]["max_attempts"] == 2
    assert [row["id"] for row in updates["feedback"]] == ["own"]
    serialized = json.dumps(updates)
    assert "PRIVATE" not in serialized
    assert "student_id" not in serialized
    assert "activity_snapshot" not in serialized


def test_ended_or_out_of_period_assessments_keep_own_feedback_and_overview():
    state = state_with_activity(start="2026-09-01", end="2026-09-30", duration_minutes=15,
                               timer_started_at="2026-09-30T10:00:00+09:00",
                               timer_deadline="2026-09-30T10:05:00+09:00", timer_ended_at="2026-09-30T10:05:00+09:00")
    state["course_attempts"]["own"] = attempt("own", reviewed="2026-10-13T09:40:00+09:00")

    updates = build(state=state)

    assert len(updates["feedback"]) == len(updates["assessments"]) == 1
    assessment = updates["assessments"][0]
    assert assessment["available"] is assessment["can_submit"] is False
    assert assessment["phase"] == "ended"
    assert assessment["period"] == "closed"
    assert assessment["notice"] == "선생님이 평가를 종료했습니다."


@pytest.mark.parametrize("task_changes,phase,period,available", [
    ({}, "unlimited", "current", True),
    (dict(status="보기만 가능"), "unlimited", "current", True),
    (dict(start="2026-10-14", end="2026-10-14"), "unlimited", "scheduled", False),
    (dict(start="2026-10-12", end="2026-10-12"), "unlimited", "closed", False),
    (dict(duration_minutes=15), "waiting", "current", False),
    (dict(duration_minutes=15, start="2026-10-12", end="2026-10-12"), "waiting", "closed", False),
    (dict(duration_minutes=15, start="2026-10-14", end="2026-10-14"), "waiting", "scheduled", False),
    (dict(duration_minutes=15, timer_started_at="2026-10-13T09:50:00+09:00", timer_deadline="2026-10-13T01:05:00+00:00"), "running", "current", True),
    (dict(duration_minutes=15, timer_started_at="2026-10-13T09:45:00+09:00", timer_deadline=NOW), "expired", "current", False),
    (dict(duration_minutes=15, timer_started_at=NOW, timer_deadline="2026-10-13T10:30:00"), "expired", "current", False),
])
def test_calendar_and_shared_timer_status_are_reported_without_hiding_deployments(task_changes, phase, period, available):
    assessment = build(state=state_with_activity(**task_changes))["assessments"][0]
    assert assessment["phase"] == phase
    assert assessment["period"] == period
    assert assessment["available"] is available
    assert assessment["can_submit"] is (available and task_changes.get("status", "진행 중") == "진행 중")


def test_calendar_boundaries_use_korea_date_for_utc_now():
    state = state_with_activity(start="2026-10-14", end="2026-10-14")
    instant = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
    at_start = build(state=state, now=instant)["assessments"][0]
    at_end = build(state=state, now="2026-10-14T14:59:59+00:00")["assessments"][0]
    after_end = build(state=state, now="2026-10-14T15:00:00+00:00")["assessments"][0]
    assert at_start["available"] is at_end["available"] is True
    assert at_start["period"] == at_end["period"] == "current"
    assert after_end["available"] is False
    assert after_end["period"] == "closed"


@pytest.mark.parametrize("changes", [dict(start=""), dict(start=None), dict(start="not-a-date"),
                                     dict(end="not-a-date"), dict(start="2026-10-14", end="2026-10-13")])
def test_invalid_or_reversed_calendar_ranges_are_reported_as_invalid(changes):
    assessment = build(state=state_with_activity(**changes))["assessments"][0]
    assert assessment["period"] == "invalid"
    assert assessment["available"] is assessment["can_submit"] is False


def test_assessment_without_a_deadline_stays_current_after_its_start_date():
    assessment = build(state=state_with_activity(start="2026-09-01", end=None))["assessments"][0]
    assert assessment["period"] == "current"
    assert assessment["available"] is True


def test_legacy_published_activities_are_compatible_without_distribution_metadata():
    state = state_with_activity()
    task = state["course_activities"]["activity"]
    del task["distribution_required"]
    del task["distributed_at"]
    assert build(state=state)["assessments"][0]["available"] is True


def test_ai_feedback_is_a_student_string_allowlist_without_raw_criteria_or_teacher_notes():
    state = state_with_activity()
    state["course_attempts"]["ai"] = attempt("ai", teacher_comment="", feedback=dict(
        praise="근거가 좋아요.", observation="식을 잘 정리했어요.", hint="부호를 확인해 봐요.",
        next_question="다른 방법도 있을까요?", uncertainty_reason="교사의 확인이 필요해요.",
        teacher_notes="PRIVATE_NOTES", expected="PRIVATE_EXPECTED", prompt="PRIVATE_PROMPT",
        criteria=[dict(criterion="PRIVATE_CRITERIA", evidence="PRIVATE_EVIDENCE")],
        extra={"student_id": "PRIVATE_OTHER"}))

    feedback = build(state=state)["feedback"][0]

    assert feedback["student_feedback"] == "근거가 좋아요.\n식을 잘 정리했어요.\n부호를 확인해 봐요.\n다른 방법도 있을까요?\n교사의 확인이 필요해요."
    assert feedback["content"] == feedback["student_feedback"]
    assert "feedback" not in feedback
    assert "PRIVATE" not in json.dumps(feedback)


@pytest.mark.parametrize("result", [dict(status="review", score=99, max_score=100),
                                     dict(status="published", score=None, max_score=100),
                                     dict(status="published", score=88, max_score=10), None])
def test_private_assessment_grade_hides_numeric_and_all_unpublished_feedback_on_home(result):
    state = state_with_activity()
    state["course_attempts"]["review"] = attempt("review", teacher_comment="PRIVATE_DRAFT_COMMENT",
                                                 feedback={"praise": "PRIVATE_PREVIOUS_AI_FEEDBACK"},
                                                 assessment_result=result)
    updates = build(state=state)
    assert updates["feedback"] == []
    assert updates["assessments"][0]["attempt_count"] == 1
    assert "PRIVATE" not in json.dumps(updates)
    assert "score" not in updates["assessments"][0]


def test_published_assessment_home_feedback_uses_student_allowlist_and_publication_time():
    state = state_with_activity()
    state["course_attempts"]["published"] = attempt("published", teacher_comment="PRIVATE_OLD_COMMENT",
        feedback={"praise": "PRIVATE_OLD_AI_FEEDBACK"},
        assessment_result=dict(status="published", score=84, max_score=100,
            published_at="2026-10-13T10:05:00+09:00", graded_at="2026-10-13T09:50:00+09:00",
            model="PRIVATE_MODEL", rationale="PRIVATE_REASON",
            feedback=dict(teacher_comment="검토한 풀이 근거가 좋아요.", praise="계산이 정확해요.",
                          hint="방법을 비교해 봐요.", teacher_notes="PRIVATE_NOTES", expected="PRIVATE_KEY",
                          criteria=[{"evidence": "PRIVATE_EVIDENCE"}])))
    feedback = build(state=state)["feedback"][0]
    assert feedback["teacher_comment"] == feedback["content"] == "검토한 풀이 근거가 좋아요."
    assert feedback["student_feedback"] == "계산이 정확해요.\n방법을 비교해 봐요."
    assert feedback["updated_at"] == "2026-10-13T10:05:00+09:00"
    assert "PRIVATE" not in json.dumps(feedback)
    assert "assessment_result" not in feedback and "score" not in feedback


@pytest.mark.parametrize("classes", ["invalid", "{}", '"1-1"', "null", '[1]', '["1-1", "1-1"]',
                                     '["1-1", "2-1"]', None, {"class": "1-1"}])
def test_malformed_announcement_targets_are_not_treated_as_all_students(classes):
    assert build(announcements=[notice("invalid", classes)])["announcements"] == []


def test_only_active_own_class_or_legacy_all_class_announcements_are_shown():
    announcements = [notice("own"), notice("all", "[]"), notice("list", ["1-1", "1-2"]),
                     notice("other", '["1-2"]'), notice("inactive", active="0"),
                     notice("missing-active", active=""), notice("not-bool", active="yes")]

    rows = build(announcements=announcements)["announcements"]

    assert {row["id"] for row in rows} == {"own", "all", "list"}
    assert all(set(row) == {"id", "title", "content", "created_at", "updated_at", "author_name"} for row in rows)
    assert "PRIVATE_TEACHER_ID" not in json.dumps(rows)


def test_announcements_sort_by_real_update_time_and_stable_id_tie_breaker():
    rows = [notice("a", updated_at="2026-10-13 10:00:00"),
            notice("b", updated_at="2026-10-13T01:00:00+00:00"),
            notice("latest", updated_at="2026-10-13T01:01:00+00:00")]
    assert [row["id"] for row in build(announcements=rows)["announcements"]] == ["latest", "b", "a"]


def test_inputs_are_unchanged_and_output_rows_cannot_mutate_teacher_state():
    state = state_with_activity()
    state["course_attempts"]["own"] = attempt("own")
    rows = [notice("notice")]
    original = copy.deepcopy((state, rows, USER))

    updates = build(state=state, announcements=rows)
    updates["assessments"][0]["title"] = "수정된 출력"
    updates["announcements"][0]["content"] = "수정된 출력"

    assert (state, rows, USER) == original


def test_missing_or_corrupt_assessment_inputs_do_not_disclose_or_break_other_updates():
    state = state_with_activity()
    state["course_activities"]["corrupt"] = {"course_id": ["course"], "status": "진행 중"}
    state["course_attempts"]["corrupt"] = {"activity_id": ["activity"]}
    state["courses"]["course"]["classes"] = "1반"
    updates = build(state=state, announcements=[notice("notice")])
    assert updates["assessments"] == updates["feedback"] == []
    assert len(updates["announcements"]) == 1


def test_invalid_now_is_rejected_instead_of_reporting_a_false_period_status():
    with pytest.raises(ValueError, match="now"):
        build(now="yesterday")
