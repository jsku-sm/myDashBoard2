"""Choose official curriculum standards while retaining custom legacy criteria."""
import streamlit as st

from .curriculum import (SOURCE_URL, criteria_text, selection_metadata,
                         standards_for, subject_names, unit_names)
from .storage import AppError


def render_curriculum_criteria(task, form_key):
    saved = task.get("curriculum") or {}
    subjects = subject_names()
    subject_key, unit_key, codes_key = (form_key + suffix for suffix in
                                      ("_subject", "_unit", "_standards"))
    st.markdown("**평가 기준 · 2022 개정 교육과정**")
    st.session_state.setdefault(subject_key, saved.get("subject", subjects[0]))
    if st.session_state[subject_key] not in subjects:
        st.session_state[subject_key] = subjects[0]
    subject = st.selectbox("과목명", subjects, key=subject_key)
    units = unit_names(subject)
    st.session_state.setdefault(unit_key, saved.get("unit", units[0]))
    if st.session_state[unit_key] not in units:
        st.session_state[unit_key] = units[0]
    unit = st.selectbox("단원명", units, key=unit_key)
    standards = {item["code"]: item["text"] for item in standards_for(subject, unit)}
    st.session_state.setdefault(codes_key, list(saved.get("standard_codes", [])))
    st.session_state[codes_key] = [code for code in st.session_state[codes_key] if code in standards]
    codes = st.multiselect("성취기준", list(standards), key=codes_key, max_selections=8,
                           format_func=lambda code: f"[{code}] {standards[code]}")
    official = criteria_text(subject, unit, codes) if codes else []
    metadata = selection_metadata(subject, unit, codes) if codes else {}
    try:
        previous_official = criteria_text(saved.get("subject"), saved.get("unit"),
                                         saved.get("standard_codes")) if saved else []
    except AppError:
        previous_official = []
    custom_key = form_key + "_criteria"
    st.session_state.setdefault(custom_key, "\n".join(
        criterion for criterion in task.get("criteria", []) if criterion not in previous_official))
    with st.expander("추가 평가 기준 · 선택"):
        custom = st.text_area("추가 평가 기준 · 한 줄에 하나", key=custom_key,
                              help="선택한 성취기준과 추가 기준을 합쳐 최대 8개까지 저장할 수 있습니다.")
    criteria = list(dict.fromkeys(official + [line.strip() for line in custom.splitlines() if line.strip()]))
    preview_key = form_key + "_criteria_preview"
    st.session_state[preview_key] = "\n".join(criteria)
    st.text_area("평가 기준 · 한 줄에 하나", key=preview_key, disabled=True,
                 help="선택한 성취기준은 평가 기준에 자동 입력됩니다. 추가 기준은 위의 ‘추가 평가 기준’에서 입력하세요.")
    st.caption(f"[2022 개정 수학과 교육과정 원문]({SOURCE_URL}) · 단원명은 공식 교육과정의 영역명입니다.")
    return criteria, metadata
