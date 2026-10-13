"""Teacher grading is durable and becomes student-visible only on publication."""
import copy
import csv
import io
import json
from types import SimpleNamespace
import zipfile

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app.classroom import Classroom, grade
from think_app.courses import CourseManager, now
from think_app.grading import assessment_score_published, public_score, student_feedback
from think_app.question_files import QuestionFiles
from think_app.reference_images import ReferenceImages
from think_app.storage import AppError, LocalStore, MemoryStore
from think_app.uploads import UploadedFiles


CRITERIA = ["풀이의 근거를 설명한다."]


def result(score=93, **updates):
    value = dict(score=score, max_score=100, correctness="correct", explanation_score=4,
                 praise="풀이의 근거를 설명했어요.", observation="두 수를 더했어요.",
                 hint="계산을 확인해 보세요.", next_question="다른 방법도 있을까요?",
                 criteria=[dict(criterion=CRITERIA[0], level="met", evidence="2+2=4")],
                 misconceptions=[], needs_teacher_review=False, uncertainty_reason="",
                 rationale="정확한 계산과 근거가 있어요.", model="mock-model")
    value.update(updates)
    return value


def ai_result(value=None):
    value = result() if value is None else value
    return SimpleNamespace(available=True, grade=lambda *args, **kwargs: copy.deepcopy(value))


def assessment(store=None, consent=False):
    store = MemoryStore() if store is None else store
    room = Classroom(store)
    cid = CourseManager(store).create("수행평가", "#123456", ["1반"])
    aid = room.save_activity(cid, "풀이 설명", "2+2를 구하세요.", "4", CRITERIA, 2, now()[:10], None)
    room.distribute_activity(aid)
    request = room.submit(aid, "1001", "학생", "1반", "2+2=4입니다.", [], consent, "a" * 32)
    return store, room, cid, aid, request


def attempt(store, request):
    return store.read()["course_attempts"][request]


def image():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    return output.getvalue()


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_teacher_grading_is_independent_of_optional_student_feedback_consent():
    store, room, _, _, request = assessment(consent=False)
    returned = room.grade_attempt(request, ai_result())
    value = attempt(store, request)
    assert returned == value["assessment_result"]
    assert returned["score"] == 93 and returned["max_score"] == 100 and returned["status"] == "review"
    assert returned["graded_at"] and "published_at" not in returned
    assert value["feedback"] is None and "grading_token" not in value and value["grading_error"] == ""
    assert public_score(value) is None and student_feedback(value) is None and grade(value) == "탁월"
    with pytest.raises(AppError, match="동의"):
        room.evaluate(request, SimpleNamespace(available=True))


def test_immediate_publication_exposes_only_the_new_score_and_feedback():
    store, room, _, _, request = assessment()
    room.grade_attempt(request, ai_result(), publish=True)
    value = attempt(store, request)
    assert value["assessment_result"]["status"] == "published"
    assert value["assessment_result"]["published_at"] == value["assessment_result"]["graded_at"]
    assert assessment_score_published(value) and public_score(value) == 93
    visible = student_feedback(value)
    assert visible["rationale"] == "정확한 계산과 근거가 있어요."
    visible["praise"] = "mutated"
    assert value["assessment_result"]["feedback"]["praise"] != "mutated"
    assert value["feedback"] is None


@pytest.mark.parametrize("changes", [
    {"score": None}, {"correctness": "uncertain"}, {"needs_teacher_review": True},
    {"explanation_score": None},
    {"criteria": [dict(criterion=CRITERIA[0], level="uncertain", evidence="판독 불가")]},
])
def test_uncertain_automatic_grade_requires_explicit_teacher_score_even_in_immediate_mode(changes):
    store, room, _, _, request = assessment()
    room.grade_attempt(request, ai_result(result(**changes)), publish=True)
    value = attempt(store, request)
    assert value["assessment_result"]["status"] == "review" and value["assessment_result"]["score"] is None
    assert value["assessment_result"]["feedback"]["needs_teacher_review"]
    assert grade(value) == "교사 확인 필요" and public_score(value) is None
    with pytest.raises(AppError, match="확인|입력"):
        room.publish_score(request)
    reviewed = room.review_score(request, 83, "학생 원본을 직접 확인했습니다.", publish=True)
    assert reviewed["reviewed_at"] and reviewed["feedback"]["needs_teacher_review"] is False
    assert public_score(attempt(store, request)) == 83


def test_untranscribed_recording_is_not_sent_or_graded_as_an_empty_answer():
    store, room, _, _, request = assessment()
    store.put_blob("b" * 32, b"private-audio")
    store.transaction(lambda state: state["course_attempts"][request].update(audio="b" * 32, transcript=""))
    room.grade_attempt(request, ai_result(), publish=True)
    value = attempt(store, request)
    assert value["transcript"] == "" and value["assessment_result"]["score"] is None
    assert value["assessment_result"]["status"] == "review"


def test_manual_score_without_ai_supports_review_publish_and_unpublish_on_a_new_review():
    store, room, _, _, request = assessment()
    reviewed = room.review_score(request, 77.5, "  교사가 직접 확인한 의견  ")
    assert reviewed["status"] == "review" and reviewed["feedback"]["teacher_comment"] == "교사가 직접 확인한 의견"
    assert attempt(store, request)["teacher_comment"] == "" and student_feedback(attempt(store, request)) is None
    published = room.publish_score(request)
    assert public_score(attempt(store, request)) == 77.5 and grade(attempt(store, request)) == "성취"
    assert room.publish_score(request) == published
    room.review_score(request, 60, "공개 전에 다시 검토")
    value = attempt(store, request)
    assert public_score(value) is None and "published_at" not in value["assessment_result"]
    assert value["assessment_result"]["feedback"]["teacher_comment"] == "공개 전에 다시 검토"


def test_automatic_grading_preserves_legacy_teacher_feedback_privately_until_publication():
    store, room, _, _, request = assessment()
    room.comment(request, "기존 교사가 남긴 의견")
    room.grade_attempt(request, ai_result())
    value = attempt(store, request)
    assert value["assessment_result"]["feedback"]["teacher_comment"] == "기존 교사가 남긴 의견"
    assert student_feedback(value) is None
    room.publish_score(request)
    assert student_feedback(attempt(store, request))["teacher_comment"] == "기존 교사가 남긴 의견"


@pytest.mark.parametrize("reviewed_comment", ["최신 채점 의견", ""])
def test_regrading_preserves_latest_review_comment_including_an_intentionally_empty_comment(reviewed_comment):
    store, room, cid, aid, request = assessment()
    room.comment(request, "오래된 의견")
    room.review_score(request, 90, reviewed_comment, publish=True)
    room.grade_attempt(request, ai_result(), publish=True)
    value = attempt(store, request)
    assert student_feedback(value)["teacher_comment"] == reviewed_comment
    with zipfile.ZipFile(io.BytesIO(room.export(cid, aid))) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("학생결과.csv").decode("utf-8-sig"))))
        assert rows[0]["교사피드백"] == reviewed_comment


@pytest.mark.parametrize("reviewed_comment", ["실패해도 보관할 교사 의견", ""])
def test_failed_regrade_keeps_the_previous_teacher_comment_for_a_later_retry(reviewed_comment):
    store, room, _, _, request = assessment()
    room.comment(request, "오래된 의견")
    room.review_score(request, 90, reviewed_comment, publish=True)

    def failed(*args, **kwargs):
        raise AppError("연결 실패")

    with pytest.raises(AppError, match="연결 실패"):
        room.grade_attempt(request, SimpleNamespace(available=True, grade=failed), publish=True)
    value = attempt(store, request)
    assert student_feedback(value) is None and value["grading_previous_comment"] == reviewed_comment
    room.grade_attempt(request, ai_result(), publish=True)
    value = attempt(store, request)
    assert student_feedback(value)["teacher_comment"] == reviewed_comment
    assert "grading_previous_comment" not in value


@pytest.mark.parametrize("score", [-1, 101, True, False, "90", None, float("nan"), float("inf"), 10**1000])
def test_invalid_manual_score_cannot_change_an_existing_published_result(score):
    store, room, _, _, request = assessment()
    room.review_score(request, 88, "공개", publish=True)
    before = store.read()
    with pytest.raises(AppError, match="점수"):
        room.review_score(request, score, "bad", publish=True)
    assert store.read() == before


@pytest.mark.parametrize("method,args", [
    ("review_score", (80, "x" * 3001)), ("review_score", (80, None)),
    ("review_score", (80, "", "yes")), ("grade_attempt", (None, "yes")),
])
def test_invalid_review_comment_or_publication_setting_does_not_mutate(method, args):
    store, room, _, _, request = assessment()
    before = store.read()
    if method == "grade_attempt":
        args = (ai_result(), args[1])
    with pytest.raises(AppError):
        getattr(room, method)(request, *args)
    assert store.read() == before


@pytest.mark.parametrize("changes", [
    {"score": True}, {"score": float("inf")}, {"score": 101}, {"max_score": 10},
    {"score": "93"}, {"correctness": "invented"}, {"unknown": "private"},
    {"criteria": [dict(criterion="다른 기준", level="met", evidence="wrong")]},
    {"criteria": []}, {"rationale": {"wrong": "type"}},
])
def test_invalid_ai_results_are_never_persisted_or_published(changes):
    store, room, _, _, request = assessment()
    with pytest.raises(AppError):
        room.grade_attempt(request, ai_result(result(**changes)), publish=True)
    value = attempt(store, request)
    assert value["assessment_result"] == dict(score=None, max_score=100, feedback=None, status="review")
    assert value["grading_error"] and "grading_token" not in value and public_score(value) is None


def test_regrading_unpublishes_before_call_and_failure_cannot_restore_old_public_score():
    store, room, _, _, request = assessment()
    store.transaction(lambda state: state["course_attempts"][request].update(feedback={"praise": "legacy"}))
    room.review_score(request, 100, "old", publish=True)

    def failing(*args, **kwargs):
        current = attempt(store, request)
        assert public_score(current) is None and student_feedback(current) is None
        assert current["grading_token"] and current["assessment_result"]["feedback"] is None
        raise RuntimeError("secret-api-key-test-do-not-expose")

    with pytest.raises(AppError, match="자동 채점에 실패"):
        room.grade_attempt(request, SimpleNamespace(available=True, grade=failing), publish=True)
    value = attempt(store, request)
    assert public_score(value) is None and student_feedback(value) is None and grade(value) == "교사 확인 필요"
    assert "secret-api-key" not in value["grading_error"]


def test_teacher_review_during_ai_call_wins_over_stale_automatic_result():
    store, room, _, _, request = assessment()

    def overlapping(*args, **kwargs):
        room.review_score(request, 67, "교사가 원본을 확인했습니다.", publish=True)
        return result(99)

    with pytest.raises(AppError, match="변경"):
        room.grade_attempt(request, SimpleNamespace(available=True, grade=overlapping), publish=True)
    value = attempt(store, request)
    assert public_score(value) == 67 and value["assessment_result"]["feedback"]["teacher_comment"].startswith("교사가")
    assert value["grading_error"] == ""


def test_second_grade_during_first_call_wins_and_first_cannot_publish_stale_result():
    store, room, _, _, request = assessment()

    def overlapping(*args, **kwargs):
        room.grade_attempt(request, ai_result(result(79)), publish=True)
        return result(99)

    with pytest.raises(AppError, match="변경"):
        room.grade_attempt(request, SimpleNamespace(available=True, grade=overlapping), publish=True)
    assert public_score(attempt(store, request)) == 79


def test_answer_changed_while_grading_cannot_receive_the_stale_score():
    store, room, _, _, request = assessment()

    def changed(*args, **kwargs):
        store.transaction(lambda state: state["course_attempts"][request].update(reflection="추가 설명"))
        return result()

    with pytest.raises(AppError, match="변경"):
        room.grade_attempt(request, SimpleNamespace(available=True, grade=changed), publish=True)
    value = attempt(store, request)
    assert public_score(value) is None and value["grading_error"] and "grading_token" not in value


def test_unconfigured_ai_preserves_an_existing_published_score():
    store, room, _, _, request = assessment()
    room.review_score(request, 90, publish=True)
    before = store.read()
    with pytest.raises(AppError, match="AI 연결"):
        room.grade_attempt(request, SimpleNamespace(available=False), publish=True)
    assert store.read() == before


def test_grading_uses_submission_snapshot_and_canonical_question_model_and_student_pdf_assets():
    store, room, cid, aid, _ = assessment()
    questions, references, uploads = QuestionFiles(store), ReferenceImages(store), UploadedFiles(store)
    question = questions.save(cid, "2+2를 구하세요.".encode(), "문제.txt")
    reference = references.save(cid, image(), "모범.png")
    room.save_activity(cid, "첨부 풀이", "원래 문제", "원래 모범답안", CRITERIA, 2, now()[:10], None,
                       aid=aid, question_files=[question], expected_images=[reference])
    document = uploads.save(aid, "1001", "학생", "1반", "학생풀이.pdf", pdf())
    request = room.submit(aid, "1001", "학생", "1반", "4", [image()], False, "c" * 32,
                          upload_ids=[document["id"]])
    submitted = attempt(store, request)
    room.save_activity(cid, "수정된 활동", "새 문제", "새 답안", ["새 기준"], 2, now()[:10], None,
                       aid=aid, question_files=[], expected_images=[])
    store.transaction(lambda state: state["course_uploads"].pop(document["id"]))

    def inspect(task, value, images, **kwargs):
        assert task == submitted["activity_snapshot"] and task["prompt"] == "원래 문제"
        assert value["consent"] is False and images == [image()]
        assert kwargs["documents"] == [("학생풀이.pdf", pdf())]
        assert kwargs["question_files"] == [(question, store.get_blob(question["blob_ref"]))]
        assert kwargs["expected_images"] == [store.get_blob(reference["blob_ref"])]
        task["criteria"][0] = "mutated by mock"
        value["text"] = "mutated by mock"
        return result()

    # The AI call receives private copies; its own mutation cannot alter the
    # criteria against which the persisted response is validated.
    room.grade_attempt(request, SimpleNamespace(available=True, grade=inspect), publish=True)
    assert attempt(store, request)["activity_snapshot"] == submitted["activity_snapshot"]
    assert attempt(store, request)["text"] == "4"
    assert public_score(attempt(store, request)) == 93


def test_damaged_question_blob_fails_before_ai_and_leaves_the_score_private():
    store, room, cid, aid, _ = assessment()
    question = QuestionFiles(store).save(cid, b"2+2", "question.txt")
    room.save_activity(cid, "문제 파일", "2+2", "4", CRITERIA, 2, now()[:10], None,
                       aid=aid, question_files=[question])
    request = room.submit(aid, "1002", "학생2", "1반", "4", [], False, "d" * 32)
    store.put_blob(question["blob_ref"], b"damaged")
    with pytest.raises(AppError, match="문제 파일"):
        room.grade_attempt(request, ai_result(), publish=True)
    assert public_score(attempt(store, request)) is None and attempt(store, request)["grading_error"]


def test_review_and_publication_survive_encrypted_restart_without_rewriting_original_submission(tmp_path):
    key = Fernet.generate_key().decode()
    store, room, _, _, request = assessment(LocalStore(tmp_path, key))
    original = store.get_student_submission(attempt(store, request))
    room.grade_attempt(request, ai_result())
    restarted = LocalStore(tmp_path, key)
    value = attempt(restarted, request)
    assert value["assessment_result"]["score"] == 93 and public_score(value) is None
    Classroom(restarted).review_score(request, 95, "검토 완료", publish=True)
    persisted = LocalStore(tmp_path, key)
    value = attempt(persisted, request)
    assert public_score(value) == 95 and student_feedback(value)["teacher_comment"] == "검토 완료"
    assert persisted.get_student_submission(value) == original
    assert "검토 완료".encode() not in (tmp_path / "state.enc").read_bytes()


def test_teacher_export_contains_numeric_score_and_publication_state():
    store, room, cid, aid, request = assessment()
    room.grade_attempt(request, ai_result())
    with zipfile.ZipFile(io.BytesIO(room.export(cid, aid))) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("학생결과.csv").decode("utf-8-sig"))))
        assert rows[0]["점수"] == "93" and rows[0]["만점"] == "100" and rows[0]["점수공개상태"] == "review"
        assert rows[0]["점수공개일시"] == ""
        record = json.loads(archive.read("전체기록.json"))["attempts"][0]
        assert record["assessment_result"] == attempt(store, request)["assessment_result"]


@pytest.mark.parametrize("score,expected", [(100, "탁월"), (90, "탁월"), (89, "성취"), (75, "성취"),
                                         (74, "발전 중"), (50, "발전 중"), (49, "성장 중"), (0, "성장 중")])
def test_teacher_grouping_uses_the_new_hundred_point_score(score, expected):
    assert grade({"assessment_result": {"score": score}, "feedback": {"explanation_score": 0}}) == expected


@pytest.mark.parametrize("new_result", [None, {}, "malformed", {"status": "review", "score": 95, "max_score": 100},
    {"status": "published", "score": True, "max_score": 100},
    {"status": "published", "score": float("nan"), "max_score": 100},
    {"status": "published", "score": 101, "max_score": 100},
    {"status": "published", "score": 95, "max_score": 4}])
def test_unpublished_or_malformed_new_grades_never_fall_back_to_legacy_feedback(new_result):
    value = dict(assessment_result=new_result, feedback={"praise": "old private feedback"})
    assert public_score(value) is None and not assessment_score_published(value) and student_feedback(value) is None


def test_legacy_feedback_and_teacher_grouping_keep_existing_behavior():
    value = dict(feedback={"correctness": "correct", "explanation_score": 4, "praise": "기존 피드백"})
    assert public_score(value) is None and not assessment_score_published(value)
    assert student_feedback(value) == value["feedback"] and grade(value) == "탁월"
    student_feedback(value)["praise"] = "mutated"
    assert value["feedback"]["praise"] == "기존 피드백"


@pytest.mark.parametrize("method,args", [("grade_attempt", (ai_result(),)), ("review_score", (80,)), ("publish_score", ())])
def test_grading_apis_reject_missing_submissions_without_creating_records(method, args):
    store, room, _, _, _ = assessment()
    before = store.read()
    with pytest.raises(AppError, match="찾을"):
        getattr(room, method)("f" * 32, *args)
    assert store.read() == before
