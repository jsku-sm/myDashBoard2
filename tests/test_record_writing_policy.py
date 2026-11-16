"""Writing-policy contracts with synthetic facts, fake storage and mocked HTTP.

These tests check evidence boundaries, reference matching, actual request payloads
and teacher finalization. They do not certify the prose quality of live model
responses, factual entailment of every sentence, or complete guideline compliance.
"""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from record_core.ai import AIConfig, RecordAI, draft_input
from record_core.archive import ArchiveError
from record_core.semester import SemesterRecords
from record_core.service import check_final
from record_core.writing_policy import DRAFT_RULES, writing_context
from test_student_record_vault import env, review, SID, OTHER, api, api_response
from test_semester_writer_ui import ui, pick


def fact(text, token="a", *, day="2026-10-23", source="학생 자기기록"):
    return {
        "evidence_id": "E" + token * 16,
        "date": day,
        "source": source,
        "title": "수업에서 남긴 기록",
        "confirmed_fact": text,
        "provenance": "학생 자기기록 · 교사 직접 관찰 아님" if source == "학생 자기기록" else "교사가 직접 관찰하여 작성한 기록",
    }


def by_code(context):
    return {s["code"].strip("[]"): s for s in context["curriculum"]["standards"]}


@pytest.mark.parametrize("text,expected", [
    ("그래프에서 함숫값을 읽고 답을 골랐다고 기록함.", "10공수2-03-01"),
    ("함수의 조건을 만족하는 예를 골랐다고 기록함.", "10공수2-03-01"),
    ("두 집합 사이의 대응 관계를 살펴봄.", "10공수2-03-01"),
    ("합성함수의 값을 차례로 대입하여 구함.", "10공수2-03-02"),
])
def test_common_math2_matches_the_relevant_reference_without_awarding_achievement(text, expected):
    selected = fact(text)
    context = writing_context("공통수학2", [selected], academic_year=2026)
    standard = by_code(context)[expected]
    assert standard["text"] and standard["match_note"]
    assert standard["evidence_ids"] == [selected["evidence_id"]]
    assert standard["achievement_verified"] is False
    assert context["curriculum"]["subject"] == "공통수학2"
    assert context["curriculum"]["revision"] == 2022


@pytest.mark.parametrize("reflection", [
    "일대일함수와 일대일대응이 무엇이 다른지 더 공부하고 싶다고 적음.",
    "일대일대응인지 확인하는 방법이 어려워 다시 살펴보겠다고 적음.",
])
def test_one_to_one_reflection_alone_does_not_claim_inverse_function_standard(reflection):
    standards = by_code(writing_context("공통수학2", [fact(reflection)]))
    assert "10공수2-03-03" not in standards


def test_references_only_link_to_the_selected_relevant_evidence():
    composition = fact("합성함수의 값을 구하는 문제에 답함.", "a")
    correspondence = fact("두 집합의 대응 관계가 함수의 조건에 맞는지 판단함.", "b")
    context = writing_context("공통수학2", [composition, correspondence])
    standards = by_code(context)
    assert standards["10공수2-03-02"]["evidence_ids"] == [composition["evidence_id"]]
    assert standards["10공수2-03-01"]["evidence_ids"] == [correspondence["evidence_id"]]
    selected_ids = {composition["evidence_id"], correspondence["evidence_id"]}
    assert all(set(s["evidence_ids"]) <= selected_ids for s in standards.values())


@pytest.mark.parametrize("text,expected,excluded", [
    ("명제의 대우를 이용하여 증명하는 과정을 설명함.", "10공수2-02-07", "10공수2-02-06"),
    ("유리함수에서 두 변수의 대응 관계를 살펴봄.", "10공수2-03-04", "10공수2-03-01"),
    ("함수의 합성에서 정의역을 확인함.", "10공수2-03-02", "10공수2-03-01"),
])
def test_specific_mathematical_topic_is_not_diluted_by_generic_vocabulary(text, expected, excluded):
    standards = by_code(writing_context("공통수학2", [fact(text)]))
    assert expected in standards and excluded not in standards


def test_inverse_notation_is_distinct_from_subtracting_one():
    inverse = by_code(writing_context("공통수학2", [fact("f⁻¹의 값을 구하는 방법을 적음.")]))
    subtraction = by_code(writing_context("공통수학2", [fact("f−1의 값을 계산한 결과를 적음.")]))
    assert "10공수2-03-03" in inverse
    assert "10공수2-03-03" not in subtraction


def test_common_math1_never_inherits_common_math2_references():
    context = writing_context("공통수학1", [fact("합성함수와 함수의 조건을 공부함.")], academic_year=2026)
    assert context["curriculum"]["subject"] == "공통수학1"
    assert context["curriculum"]["standards"] == []
    assert context["curriculum"]["status"] == "not_supported"


@pytest.mark.parametrize("facts", [[], [fact("문제 3번 정답, 힌트 0회, 재시도 0회.")]])
def test_no_curriculum_standard_is_guessed_from_a_bare_score_log(facts):
    context = writing_context("공통수학2", facts)
    assert context["curriculum"]["standards"] == []
    assert context["curriculum"]["status"] == "no_topic_match"


def test_curriculum_revision_guideline_year_and_academic_year_are_distinct():
    context = writing_context("공통수학2", [fact("함숫값을 구함.")], academic_year=2025)
    assert context["academic_year"] == 2025
    assert context["guideline_year"] == 2026
    assert context["curriculum"]["revision"] == 2022
    assert context["year_caution"]
    assert context["policy_version"] and context["guideline_sources"]
    assert context["writing_principles"] and context["curriculum"]["sources"]


def test_context_keeps_dates_provenance_and_teacher_confirmed_words_unmodified():
    # The later observation deliberately appears first: no implicit chronology,
    # growth claim or promotion of student reflection into teacher observation.
    facts = [
        fact("함수의 조건을 표로 설명하는 모습을 관찰함.", "b", day="2026-10-30", source="교사 관찰"),
        fact("함숫값 읽기가 어려워 다시 살펴보고 싶다고 적음.", "a", day="2026-10-20"),
    ]
    original = copy.deepcopy(facts)
    payload = json.loads(draft_input("공통수학2", facts, academic_year=2026))
    assert facts == original and payload["facts"] == original
    assert payload["writing_context"] == writing_context("공통수학2", original, academic_year=2026)


def test_added_policy_is_built_from_redacted_facts_without_corrupting_evidence_ids():
    selected = fact("가상학생가(1101)가 함숫값을 읽었다고 적음. 010-1234-5678 test@example.com")
    selected["evidence_id"] = "E" + "a" * 12 + "1101"
    selected["title"] = "가상학생가의 수업 기록"
    raw = draft_input("공통수학2", [selected], ("가상학생가", "1101"), academic_year=2026)
    payload = json.loads(raw)
    assert all(secret not in raw for secret in ("가상학생가", "010-1234-5678", "test@example.com"))
    assert "1101" not in payload["facts"][0]["confirmed_fact"]
    assert payload["facts"][0]["evidence_id"] == selected["evidence_id"]
    assert payload["writing_context"] == writing_context("공통수학2", payload["facts"], academic_year=2026)


@pytest.mark.parametrize("use_semester_writer", [False, True])
def test_preview_and_actual_request_include_identical_anonymous_policy_context(env, use_semester_writer):
    if use_semester_writer:
        service = SemesterRecords(env.b, lambda: env.actor[0])
        workspace = service.load_term(SID, "공통수학2", 2026, 2)
    else:
        service, workspace = env.s, env.load()
    item = next(e for e in workspace["data"]["evidence"] if e["category"] == "sudanotes")
    reviews = [review(item, fact="가상학생가(1101)가 함숫값을 구하는 과정을 다시 살펴보고 싶다고 적음.")]
    expected = service.input_preview(workspace, reviews)
    reply = {"sentences": [{"text": "함숫값을 구하는 과정을 더 살펴보려는 목표를 기록함.", "evidence_ids": [item["id"]]}], "cautions": []}
    post = Mock(return_value=api_response(reply))
    if use_semester_writer:
        service.generate(workspace, reviews, api(post), "policy_preview_1", consent=True)
    else:
        service.draft(workspace, reviews, api(post), consent=True)
    body = post.call_args.kwargs["json"]
    transmitted = body["input"][0]["content"][0]["text"]
    assert transmitted == expected and post.call_count == 1
    assert DRAFT_RULES in body["instructions"]
    parsed = json.loads(transmitted)
    assert parsed["writing_context"]["academic_year"] == (2026 if use_semester_writer else None)
    assert parsed["writing_context"]["guideline_year"] == 2026
    assert parsed["facts"][0]["date"] == item["date"]
    assert parsed["facts"][0]["provenance"] == item["origin"]
    assert parsed["facts"][0]["evidence_id"] == item["id"]
    assert "가상학생가" not in transmitted and "다른 학생 비공개" not in transmitted


def test_batch_requests_use_the_same_policy_but_keep_each_students_facts_separate(ui, monkeypatch):
    statements = {
        SID: "함숫값을 읽는 과정을 다시 확인하고 싶다고 적음.",
        OTHER: "합성함수의 적용 순서를 더 공부하고 싶다고 적음.",
    }
    captured = []

    def respond(*args, **kwargs):
        payload = json.loads(kwargs["json"]["input"][0]["content"][0]["text"])
        captured.append(payload)
        reply = {"sentences": [{"text": "학습 후 더 확인하고 싶은 개념을 기록함.", "evidence_ids": [payload["facts"][0]["evidence_id"]]}], "cautions": []}
        return api_response(reply)

    post = Mock(side_effect=respond)
    monkeypatch.setattr(ui.v, "RecordAI", lambda config: RecordAI(config, SimpleNamespace(post=post)))
    for sid, statement in statements.items():
        next(r for r in ui.env.b.rows["sudanotes"] if r["student_id"] == sid)["q1"] = statement
        ui.s.sync_sources(sid)
        workspace = ui.s.load_term(sid, "공통수학2", 2026, 2)
        item = next(e for e in workspace["data"]["evidence"] if e["category"] == "sudanotes")
        ui.s.save_term(workspace, [review(item, fact=statement)], "")
    app = ui.app
    pick(app.button, "📂 전체 불러오기 · 저장된 초안과 완성본").click().run()
    pick(app.multiselect, "AI 초안을 생성할 학생").select(SID).select(OTHER)
    pick(app.checkbox, "선택한 학생들의 확인 근거를 AI에 전송합니다. 학생 수만큼 요청이 진행됩니다.").check().run()
    pick(app.button, "✨ 선택 학생 AI 초안 일괄 생성").click().run()
    assert not app.exception and not app.error and post.call_count == 2
    assert {p["facts"][0]["confirmed_fact"] for p in captured} == set(statements.values())
    assert len({p["facts"][0]["evidence_id"] for p in captured}) == 2
    for payload in captured:
        context = payload["writing_context"]
        assert len(payload["facts"]) == 1
        assert context == writing_context("공통수학2", payload["facts"], academic_year=2026)
        assert all(s["evidence_ids"] == [payload["facts"][0]["evidence_id"]] for s in context["curriculum"]["standards"])
    app.run()
    assert post.call_count == 2


@pytest.mark.parametrize("config", [AIConfig(api_key="", enabled=True), AIConfig(api_key="test-only", enabled=False)])
def test_no_key_or_disabled_ai_never_returns_an_offline_policy_example(config):
    post = Mock()
    client = RecordAI(config, SimpleNamespace(post=post))
    with pytest.raises(ArchiveError):
        client.draft("공통수학2", [fact("함숫값을 읽는 연습을 함.")], consent=True, academic_year=2026)
    assert not post.called


AI_ORIGINAL = "대응 관계를 비교하고 함숫값을 설명함."


@pytest.mark.parametrize("candidate", [
    AI_ORIGINAL,
    "  대응 관계를 비교하고\n함숫값을 설명함.  ",
    "대응 관계를 비교하고, 함숫값을 설명함!",
    "“대응 관계를 비교하고 함숫값을 설명함”",
    "대응 관계를 비교하고 함숫값을 설명함。",
])
@pytest.mark.parametrize("note", ["", "교사가 내용을 확인했다는 메모만 남김."])
def test_final_guard_rejects_ai_verbatim_or_surface_changes_even_with_a_review_note(candidate, note):
    with pytest.raises(ArchiveError):
        check_final(candidate, AI_ORIGINAL, confirmed=True, review_note=note)


def test_final_guard_accepts_teacher_revision_and_genuine_manual_writing_without_a_memo():
    check_final("대응 관계의 조건을 표로 설명하는 모습을 수업 중 관찰함.", AI_ORIGINAL, confirmed=True, review_note="")
    check_final("교사가 수업 중 관찰한 수행을 직접 작성함.", None, confirmed=True, review_note="")


def test_disconnect_and_save_keeps_ai_origin_guard_across_reload(env):
    service = SemesterRecords(env.b, lambda: env.actor[0])
    load = lambda: service.load_term(SID, "공통수학2", 2026, 2)
    workspace = load()
    item = next(e for e in workspace["data"]["evidence"] if e["category"] == "sudanotes")
    reviews = [review(item)]
    generated = {"text": AI_ORIGINAL, "evidence_hashes": {item["id"]: item["evidence_hash"]}}
    service.save_term(workspace, reviews, AI_ORIGINAL, generated)
    service.save_term(load(), reviews, AI_ORIGINAL, None)  # User disconnects AI.
    before = load()["data"]["current"]
    assert before["ai_draft"] is None and before["kind"] == "working_draft"
    with pytest.raises(ArchiveError):
        service.save_term(load(), reviews, AI_ORIGINAL, None, final=True, confirmed=True)
    after = load()["data"]["current"]
    assert after["revision"] == before["revision"] and after["text"] == AI_ORIGINAL
    revised = "대칭이동에서 좌표의 부호 오류를 점검하고 수정한 과정을 수다노트에 기록함."
    saved = service.save_term(load(), reviews, revised, None, final=True, confirmed=True)
    assert saved["kind"] == "final" and saved["text"] == revised and saved["review_note"] == ""


def test_newline_counts_as_one_byte_at_the_finalization_boundary():
    for text in ("가\n나", "가\r\n나", "가\r나"):
        check_final(text, None, confirmed=True, review_note="", byte_limit=7)
        with pytest.raises(ArchiveError):
            check_final(text, None, confirmed=True, review_note="", byte_limit=6)
