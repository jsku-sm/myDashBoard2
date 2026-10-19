"""Grade submitted assessments and explicitly control student publication."""
from dataclasses import replace
import hashlib
import json

import streamlit as st

from .ai import AI
from .config import Settings
from .grading import assessment_score_published
from .storage import AppError


def grading_ai(ai, api_key=""):
    """Teacher grading uses the existing connection independently of student AI."""
    if ai is not None and ai.available:
        return ai
    settings = getattr(ai, "settings", None)
    if not isinstance(settings, Settings):
        settings = Settings(api_key=getattr(settings, "api_key", "") or "",
                            model=getattr(settings, "model", "") or Settings().model)
    key = (settings.api_key or api_key).strip()
    if not key:
        return None
    return AI(replace(settings, ai_enabled=True, api_key=key), client=getattr(ai, "client", None))


def _connection(ai, aid):
    connection = grading_ai(ai)
    if connection is None:
        api_key = st.text_input("자동채점용 OpenAI API 키", type="password", key="grading_api_key_" + aid,
                                help="기존 서버 연결이 있으면 자동으로 사용합니다. 입력한 키는 교사의 현재 로그인 세션에서만 사용합니다.")
        connection = grading_ai(ai, api_key)
    if connection is None:
        st.info("OpenAI 연결을 설정하면 자동채점을 실행할 수 있습니다. 점수와 피드백은 직접 입력할 수도 있습니다.")
    return connection


def _notice(aid):
    notice = st.session_state.pop("grading_notice_" + aid, None)
    if notice:
        st.success(notice)


def grading_controls(room, task, attempts, ai):
    """Batch grading covers every real attempt in the selected class."""
    aid = task["id"]
    _notice(aid)
    with st.container(border=True):
        st.markdown("#### 자동채점")
        st.caption("모범답안과 평가 기준을 바탕으로 제출한 글·이미지·PDF를 100점 만점으로 채점합니다.")
        st.caption("자동채점 → 결과 분석 → 교사 확인 → 학생 피드백 배포 순서로 진행합니다.")
        st.caption("자동채점 결과는 교사 검토 대기로 저장됩니다. 답안별 점수와 피드백을 확인한 뒤 학생에게 배포하세요.")
        connection = _connection(ai, aid)
        pending = [attempt for attempt in attempts if not attempt.get("preview") and
                   (not attempt.get("assessment_result") or attempt.get("grading_error"))]
        if st.button(f"미채점 답안 자동채점 · {len(pending)}개", key="grade_pending_" + aid,
                     disabled=not pending or connection is None, type="primary", use_container_width=True):
            errors, completed, published = [], 0, 0
            progress = st.progress(0.0, text="제출 답안을 채점하고 있습니다…")
            for index, attempt in enumerate(pending):
                try:
                    room.grade_attempt(attempt["id"], connection, publish=False)
                    completed += 1
                    current = room.store.read().get("course_attempts", {}).get(attempt["id"], {})
                    published += int(assessment_score_published(current))
                except AppError as error:
                    errors.append(f"{attempt['name']} · {error}")
                progress.progress((index + 1) / len(pending), text=f"{index + 1}/{len(pending)}개 처리")
            st.session_state["grading_notice_" + aid] = f"{completed}개 채점 완료 · 학생에게 배포 {published}개 · 검토 대기 {completed - published}개"
            st.session_state["grading_errors_" + aid] = errors
            st.rerun()
        errors = st.session_state.pop("grading_errors_" + aid, [])
        for error in errors:
            st.error(error)
        drafts = [attempt for attempt in attempts if not attempt.get("preview") and
                  isinstance(attempt.get("assessment_result"), dict) and
                  attempt["assessment_result"].get("status") == "review" and
                  attempt["assessment_result"].get("score") is not None and
                  not attempt["assessment_result"].get("feedback", {}).get("needs_teacher_review")]
        if drafts:
            st.caption("학생 답안을 클릭해 점수와 피드백을 확인한 뒤 배포하세요. 점수는 아래 개별 답안에서 수정할 수 있습니다.")
            if st.button(f"검토한 채점 결과 학생에게 배포 · {len(drafts)}개", key="publish_scores_" + aid,
                         use_container_width=True):
                count, failures = 0, []
                for attempt in drafts:
                    try:
                        room.publish_score(attempt["id"])
                        count += 1
                    except AppError as error:
                        failures.append(f"{attempt['name']} · {error}")
                st.session_state["grading_notice_" + aid] = f"채점 결과 {count}개를 학생에게 배포했습니다."
                st.session_state["grading_errors_" + aid] = failures
                st.rerun()
    return connection


def attempt_grading_controls(room, attempt, ai):
    """A teacher may regrade, correct a score, and publish after review."""
    aid, attempt_id = attempt["activity_id"], attempt["id"]
    if error := st.session_state.pop("grading_attempt_error_" + attempt_id, None):
        st.error(error)
    connection = grading_ai(ai, st.session_state.get("grading_api_key_" + aid, ""))
    if st.button("자동채점 다시 실행" if attempt.get("assessment_result") else "이 답안 자동채점",
                 disabled=connection is None, key="grade_attempt_" + attempt_id, type="primary"):
        try:
            with st.spinner("모범답안과 평가 기준으로 채점하고 있습니다…"):
                room.grade_attempt(attempt_id, connection, publish=False)
        except AppError as error:
            st.session_state["grading_attempt_error_" + attempt_id] = str(error)
            st.rerun()
        else:
            st.session_state["grading_notice_" + aid] = "답안을 채점했습니다. 점수와 분석을 확인한 뒤 학생에게 배포하세요."
            st.rerun()
    result = attempt.get("assessment_result") or {}
    feedback = result.get("feedback") or {}
    previous_comment = (feedback["teacher_comment"] if "teacher_comment" in feedback else
                        attempt.get("grading_previous_comment", attempt.get("teacher_comment", "")))
    if attempt.get("grading_error"):
        st.warning(attempt["grading_error"])
    version = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    prefix = "score_review_" + attempt_id + "_" + version
    with st.form(prefix):
        score = st.number_input("수행평가 점수 · 100점 만점", min_value=0.0, max_value=100.0, step=1.0,
                                value=float(result.get("score") or 0), key=prefix + "_score")
        comment = st.text_area("채점 피드백", value=previous_comment, max_chars=3000,
                               key=prefix + "_comment", help="검토 저장한 내용은 학생에게 배포할 때 공개됩니다.")
        save, publish = st.columns(2)
        save_clicked = save.form_submit_button("검토 저장", key=prefix + "_save")
        publish_clicked = publish.form_submit_button("저장하고 학생에게 배포", key=prefix + "_publish", type="primary")
    if save_clicked or publish_clicked:
        try:
            room.review_score(attempt_id, score, comment, publish=publish_clicked)
        except AppError as error:
            st.error(str(error))
        else:
            st.session_state["grading_notice_" + aid] = "점수와 피드백을 학생에게 배포했습니다." if publish_clicked else "점수와 피드백을 검토 저장했습니다. 학생에게는 아직 공개되지 않습니다."
            st.rerun()
    if result and not assessment_score_published(attempt) and result.get("score") is not None:
        if st.button("이 채점 결과 학생에게 배포", key="publish_attempt_" + attempt_id,
                     disabled=bool(feedback.get("needs_teacher_review"))):
            try:
                room.publish_score(attempt_id)
            except AppError as error:
                st.error(str(error))
            else:
                st.session_state["grading_notice_" + aid] = "채점 결과를 학생에게 배포했습니다."
                st.rerun()
