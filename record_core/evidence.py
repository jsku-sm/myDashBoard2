# GOOD_RECORDS_1.1_FINAL5
"""Deterministic evidence projections. No inferred proficiency or hidden grading."""
from __future__ import annotations
import copy
import hashlib
import json
from .archive import canonical, fingerprint, ArchiveError

LABELS = {"sudanotes":"수다노트", "assessments":"수행평가", "games":"게임 학습", "quizzes":"퀴즈",
          "points":"상점·벌점", "observations":"교사 관찰", "submissions":"수업 제출물", "questions":"질문", "uploads":"평가 업로드"}

def as_json(value, default):
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return copy.deepcopy(default)


def _date(row):
    return str(next((row.get(key) for key in ("date", "created_at", "submitted_at", "created", "updated_at", "started_at") if row.get(key)), ""))[:10]


def _subject(task, course=None):
    for obj in (task, course or {}, task.get("curriculum", {})):
        if isinstance(obj, dict):
            for key in ("subject", "subject_name", "course_subject"):
                value = obj.get(key)
                if value in ("공통수학1", "공통수학2"):
                    return value
    # Do not guess the subject from names or fabricate its assignment.
    return ""


def evidence_id(category, source):
    return "E" + hashlib.sha256((category + ":" + str(source)).encode()).hexdigest()[:16]


def project(bundles, *, sid, teacher_id, legacy_teacher_id, subject, start, end):
    result = []
    def add(bundle, row, identity, title, text, origin, row_subject="", attachments=None, eligible=True, extra=None):
        day = _date(row)
        if day and not (str(start)[:10] <= day <= str(end)[:10]):
            return
        if row_subject and row_subject != subject:
            return
        category = bundle["category"]
        obj = {"id": evidence_id(category, identity), "student_id": str(sid), "category": category,
               "label": LABELS.get(category, category), "date": day, "subject": row_subject,
               "title": title, "text": text, "origin": origin, "eligible": bool(eligible),
               "attachments": copy.deepcopy(bundle.get("attachments", []) if attachments is None else attachments),
               "raw": copy.deepcopy(row), "source_path": bundle.get("_path", ""), "archive_version": bundle.get("version", ""),
               "extra": extra or {}}
        obj["evidence_hash"] = fingerprint({k: obj[k] for k in ("raw", "text", "attachments", "subject")})
        result.append(obj)

    for bundle in bundles:
        if bundle.get("student_id") != str(sid):
            raise ArchiveError("학생별 자료가 섞여 있어 불러오기를 중단했습니다.")
        cat, payload = bundle.get("category"), bundle.get("payload", {})
        if payload.get("deleted"):
            continue
        if cat in ("assessments", "uploads"):
            item, task, course = payload.get("item", {}), payload.get("activity", {}), payload.get("course", {})
            owner = course.get("owner_id") or course.get("creator") or legacy_teacher_id
            if teacher_id != owner and teacher_id not in course.get("shared_teachers", []):
                continue
            if str(item.get("student_id")) != str(sid) or item.get("preview"):
                continue
            title = str(task.get("title") or "수행평가 자료")
            text = "\n".join([f"활동: {title}", "문제: " + str(task.get("prompt", "")),
                "학생 풀이: " + str(item.get("text", "")), "학생 설명 전사: " + str(item.get("transcript", "")),
                "학생 성찰: " + str(item.get("reflection", "")), "제출 선택: " + str(item.get("quiz_answer") or ""),
                "교사 피드백: " + str(item.get("teacher_comment", "")),
                "평가 관련 원본: " + json.dumps({k:v for k,v in item.items() if k in ("feedback", "grading", "teacher_grade", "teacher_score", "score", "graph")}, ensure_ascii=False)])
            if cat == "uploads":
                title = "제출 전 업로드 · " + str(item.get("filename", "첨부파일"))
                text = "학생이 저장한 첨부파일입니다. 최종 제출이나 교사 관찰을 자동으로 의미하지 않습니다."
            add(bundle, item, payload.get("source_table", "") + ":" + str(item.get("id")), title, text,
                "학생 제출 / 자동 분석·교사 피드백은 원본에서 구분", _subject(task, course), extra={"course_id":course.get("id", "")})
            continue
        table = payload.get("table", "")
        for row in payload.get("rows", []):
            if str(row.get("student_id")) != str(sid):
                raise ArchiveError("학생별 표의 소유자가 일치하지 않습니다.")
            rid = table + ":" + str(row.get("id"))
            if table in ("observations", "records") and (row.get("author_id") or legacy_teacher_id) != teacher_id:
                continue
            if table == "sudanotes":
                text = "\n".join(f"질문{i} 응답: {row.get('q'+str(i), '')}" for i in range(1,6))
                add(bundle, row, rid, "오늘의 수업, 나의 언어로 정리하기", text, "학생 자기기록 · 교사 관찰 아님", row.get("subject", ""))
            elif table == "observations":
                add(bundle, row, rid, row.get("category") or "교사 관찰", row.get("content", ""), "교사 입력 관찰", row.get("subject", ""))
            elif table == "points":
                add(bundle, row, rid, f"{row.get('kind')} {row.get('score')}점", row.get("reason", ""), "상벌점 관리 · AI 초안 제외", eligible=False)
            elif table in ("submissions", "questions"):
                text = "\n".join(f"{k}: {row.get(k, '')}" for k in ("unit", "content", "feedback", "teacher_comment", "answer"))
                attachments = [f for f in bundle.get("attachments", []) if f.get("id") == row.get("file_id")]
                add(bundle, row, rid, row.get("title", "학습 기록"), text, "학생 기록 / 피드백", row.get("subject", ""), attachments)
            elif table == "quiz_attempts":
                quiz = next((q for q in payload.get("quiz_sets", []) if q.get("id") == row.get("quiz_id")), {})
                if (quiz.get("teacher_id") or legacy_teacher_id) != teacher_id:
                    continue
                text = "\n".join(["퀴즈: " + quiz.get("title", ""), "상태: " + row.get("state", ""),
                    "문항 원본: " + quiz.get("question_json", "[]"), "학생 답: " + row.get("answers_json", "{}"),
                    "채점 결과: " + row.get("marks_json", "{}"), "점수: " + row.get("score", ""),
                    "채점자: " + ("교사" if row.get("graded_by") else "미확인")])
                add(bundle, row, rid, quiz.get("title", "퀴즈 풀이"), text, "풀이·채점 기록 · 점수만으로 숙달 추정 금지", quiz.get("subject", ""))
            elif table == "game_profiles":
                profile = as_json(row.get("state_json"), {})
                from game_core.curriculum import TOPICS
                for session in profile.get("sessions", []):
                    topic = TOPICS.get(session.get("topic_id"), {})
                    text = "\n".join(["세부 주제: " + topic.get("label", session.get("topic_id", "")),
                        "상태: " + session.get("status", ""), "문항과 답·힌트·재도전: " + json.dumps({"questions":session.get("questions", []), "answers":session.get("answers", [])}, ensure_ascii=False),
                        "학생 한 줄 기록: " + session.get("reflection", "")])
                    add(bundle, session, "session:" + str(session.get("id")), topic.get("label", "개념 학습게임"), text,
                        "자동 학습 로그 · 보상/아이템과 교과 성취는 구분", topic.get("subject", ""), extra={"mission_id":session.get("mission_id", "")})
    # Stable opaque IDs make widget keys and teacher approval survive sorting.
    return sorted(result, key=lambda r: (r["date"], r["id"]), reverse=True)


def validate_reviews(evidence, reviews, subject):
    """Return only teacher-confirmed in-class observations, never raw point data."""
    items = {e["id"]: e for e in evidence}
    facts = []
    for review in reviews:
        e = items.get(review.get("evidence_id"))
        if not e or not e.get("eligible") or e["category"] == "points":
            raise ArchiveError("선택한 근거 자료가 없거나 세특 작성 대상으로 사용할 수 없습니다.")
        if review.get("evidence_hash") != e["evidence_hash"]:
            raise ArchiveError("원본 자료가 바뀌었습니다. 변경된 근거를 다시 확인하세요.")
        if review.get("context") != "정규 교과수업" or not review.get("teacher_confirmed"):
            raise ArchiveError("교사가 정규 교과수업에서 관찰·평가한 사실만 초안 근거로 확정하세요.")
        if review.get("subject") != subject:
            raise ArchiveError("선택한 교과와 근거 확인 과목이 다릅니다.")
        text = str(review.get("fact", "")).strip()
        if not 5 <= len(text) <= 6000:
            raise ArchiveError("교사가 확인한 구체적인 사실을 5~6000자로 기록하세요.")
        facts.append({"evidence_id":e["id"], "date":e["date"], "source":e["label"], "title":e["title"],
                      "confirmed_fact":text, "provenance":e["origin"]})
    if not facts:
        raise ArchiveError("교사가 확인한 근거가 없습니다. 먼저 자료를 선택하고 사실을 확인하세요.")
    return facts
