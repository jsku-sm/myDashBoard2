"""Validated assessment grades and the boundary for student-visible results."""
import copy
import math

from pydantic import ValidationError

from .ai import Feedback
from .storage import AppError


def valid_score(value):
    return (type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value))


def assessment_score_published(attempt):
    result = attempt.get("assessment_result")
    return (isinstance(result, dict) and result.get("status") == "published" and
            type(result.get("max_score")) in (int, float) and result["max_score"] == 100 and
            valid_score(result.get("score")))


def public_score(attempt):
    """Return only the numeric score explicitly published by a teacher."""
    return attempt["assessment_result"]["score"] if assessment_score_published(attempt) else None


def student_feedback(attempt):
    """A new private grade also hides any feedback left by an older evaluation."""
    if "assessment_result" in attempt:
        if not assessment_score_published(attempt):
            return None
        feedback = attempt["assessment_result"].get("feedback")
    else:
        feedback = attempt.get("feedback")
    return copy.deepcopy(feedback) if isinstance(feedback, dict) else None


def validated_grading(result, criteria):
    """Validate the AI result again before it enters durable classroom state."""
    if not isinstance(result, dict):
        raise AppError("AI 채점 결과의 형식을 확인할 수 없습니다. 다시 채점하거나 직접 검토하세요.")
    feedback_fields = set(Feedback.model_fields)
    allowed = feedback_fields | {"score", "max_score", "rationale", "model"}
    if set(result).difference(allowed) or result.get("max_score") != 100 or type(result.get("max_score")) is bool:
        raise AppError("AI 채점 결과의 점수 형식을 확인할 수 없습니다.")
    score = result.get("score")
    if score is not None and not valid_score(score):
        raise AppError("AI 채점 점수는 0~100점이어야 합니다.")
    try:
        feedback = Feedback.model_validate({key: result[key] for key in feedback_fields if key in result},
                                           strict=True).model_dump()
    except ValidationError:
        raise AppError("AI 채점 피드백을 확인할 수 없습니다. 다시 채점하거나 직접 검토하세요.") from None
    if [item["criterion"] for item in feedback["criteria"]] != list(criteria):
        raise AppError("AI 채점 기준이 제출 당시의 평가 기준과 일치하지 않습니다.")
    for field, limit in (("rationale", 3000), ("model", 200)):
        if field in result:
            if not isinstance(result[field], str) or len(result[field]) > limit:
                raise AppError("AI 채점 근거의 형식을 확인할 수 없습니다.")
            feedback[field] = result[field]
    if (score is None or feedback["correctness"] == "uncertain" or feedback["needs_teacher_review"] or
            feedback["explanation_score"] is None or
            any(item["level"] == "uncertain" for item in feedback["criteria"])):
        score = None
        feedback["needs_teacher_review"] = True
    return score, feedback


def reviewed_feedback(previous, comment):
    """Keep AI evidence when available, with the teacher's explicit assessment."""
    feedback = copy.deepcopy(previous) if isinstance(previous, dict) else {
        "correctness": "partial", "explanation_score": None, "praise": "", "observation": "",
        "hint": "", "next_question": "", "criteria": [], "misconceptions": [], "uncertainty_reason": "",
    }
    feedback["teacher_comment"] = comment
    feedback["needs_teacher_review"] = False
    return feedback
