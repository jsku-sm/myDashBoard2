"""Common-math-2 evaluation cards: public visual summary, teacher-only editor."""
from __future__ import annotations

import html
import uuid

import streamlit as st
import storage as db
import ui
import evaluation_plan_service as plans
from evaluation_plan_visuals import render_plan_html


def _slot(material_id: str, teacher_id: str) -> str:
    return f"_eval_plan_editor_{teacher_id}_{material_id}"


def _start_edit(user, material_id):
    row = plans.get_plan(user, material_id)
    # New keys per editing session avoid accidentally reusing a cancelled form
    # or a different teacher's old draft after logout/login in the same browser.
    token = "ep_edit_" + uuid.uuid4().hex
    st.session_state[_slot(material_id, user["id"])] = {
        "token": token, "revision": plans.revision_of(row), "preview": None,
        "title": row.get("title", ""), "description": row.get("description", ""),
        "pending": False,
    }


def _end_edit(user, material_id):
    # Widget state is intentionally not mutated after the widgets were rendered.
    # The unused old widget keys are cleaned up by Streamlit on the next run.
    st.session_state.pop(_slot(material_id, user["id"]), None)


def _editor(user, row):
    key = _slot(row["id"], user["id"])
    state = st.session_state.get(key)
    if not state:
        return
    # Recheck permissions on every render and again in the mutation service.
    if not plans.can_manage(user):
        st.session_state.pop(key, None)
        return
    prefix = state["token"]
    st.markdown("#### 평가계획 텍스트 수정")
    st.caption("제목과 설명만 수정합니다. 기존 PDF·첨부파일과 등록일은 그대로 유지됩니다.")
    if state.get("pending"):
        st.warning("GitHub 저장 확인이 필요해요. 저장을 다시 눌러 확인하세요. 수정 취소는 저장 대기를 되돌리지 않습니다.")
    with st.form(prefix + "_form", clear_on_submit=False, enter_to_submit=False):
        title = st.text_input("평가계획 제목", value=state["title"], max_chars=plans.MAX_TITLE,
                              key=prefix + "_title")
        description = st.text_area("평가계획 내용", value=state["description"], height=320,
                                    max_chars=plans.MAX_DESCRIPTION, key=prefix + "_description",
                                    help="전체 원문을 수정하세요. 아래 ‘시각화 미리보기’는 저장하지 않고 내용을 확인합니다.")
        a, b, c = st.columns([1, 1.4, 1])
        with a:
            save = st.form_submit_button("저장", type="primary", key=prefix + "_save")
        with b:
            preview = st.form_submit_button("시각화 미리보기", key=prefix + "_preview")
        with c:
            cancel = st.form_submit_button("수정 취소", key=prefix + "_cancel")
    if cancel:
        _end_edit(user, row["id"])
        st.rerun()
    if preview:
        state["preview"] = {"title": title, "description": description}
    if save:
        try:
            with st.spinner("평가계획을 저장하는 중..."):
                plans.update_plan_text(user, row["id"], title, description, state["revision"])
        except plans.PlanSavePendingError as error:
            state["revision"] = error.revision
            state["pending"] = True
            st.warning(str(error))
        except (PermissionError, ValueError) as error:
            st.error(str(error))
        except Exception:
            st.error("저장을 완료하지 못했어요. 입력한 내용은 이 수정 창에 유지됩니다. 저장소 연결을 확인한 뒤 다시 시도해 주세요.")
        else:
            _end_edit(user, row["id"])
            st.session_state["_eval_plan_notice_" + user["id"]] = "평가계획 텍스트를 저장했어요. 시각화에도 수정 내용을 반영했습니다."
            st.rerun()
    draft = state.get("preview")
    if draft:
        st.info("미리보기 · 아직 저장하지 않은 내용입니다. 수정 후에는 ‘시각화 미리보기’를 다시 눌러 주세요.")
        st.markdown("**" + ui.esc(draft["title"]) + "**")
        st.html(render_plan_html(draft["description"]))


def render_evaluation_plan_card(user, row):
    """Called only for materials(category=평가계획, subject=공통수학2)."""
    is_teacher = plans.can_manage(user)
    notice_key = "_eval_plan_notice_" + str(user.get("id", ""))
    if notice := st.session_state.pop(notice_key, None):
        st.success(notice)
    with st.container(border=True):
        if is_teacher:
            heading, edit = st.columns([5, 1])
        else:
            heading = st.container()
        with heading:
            # Unlike the original template, teacher text is always escaped.
            st.markdown("### " + ui.esc(row.get("title", "평가계획")))
            st.caption("등록일 " + str(row.get("uploaded_at", ""))[:10])
        if is_teacher:
            with edit:
                if st.button("✏️ 수정", key="eval_plan_edit_" + row["id"],
                             disabled=bool(st.session_state.get(_slot(row["id"], user["id"])))):
                    try:
                        _start_edit(user, row["id"])
                    except (ValueError, PermissionError) as error:
                        st.error(str(error))
                    else:
                        st.rerun()
        if plans.pending_material_save():
            st.warning("자료 변경 사항을 GitHub에 저장하는 중입니다. 저장 완료는 아직 확인되지 않았어요.")
        if is_teacher and st.session_state.get(_slot(row["id"], user["id"])):
            _editor(user, row)
        st.html(render_plan_html(row.get("description", "")))
        with st.expander("📄 평가계획 원문 보기", expanded=False):
            if row.get("description"):
                # Display plaintext instead of interpreting ~ ranges or raw HTML.
                st.html('<div style="white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8">' +
                        html.escape(row["description"], quote=True) + '</div>')
            else:
                st.caption("등록된 설명이 없어요. 첨부파일을 확인해 주세요.")
        ui.file_widget(row, row["id"])
        if is_teacher:
            with st.expander("평가계획 삭제", expanded=False):
                st.caption("삭제하면 이 평가계획과 첨부 연결을 제거합니다. 텍스트만 바꾸려면 위의 수정 버튼을 사용하세요.")
                confirm = st.checkbox("이 평가계획을 삭제합니다", key="eval_plan_del_confirm_" + row["id"])
                if st.button("삭제", key="del_m_" + row["id"], disabled=not confirm):
                    try:
                        plans.delete_plan(user, row["id"], plans.revision_of(row))
                    except plans.PlanSavePendingError:
                        st.warning("삭제 요청은 서버에 반영됐지만 GitHub 저장은 아직 확인되지 않았어요. 연결을 확인하고 앱을 종료하지 마세요.")
                    except (PermissionError, ValueError) as error:
                        st.error(str(error))
                    except Exception:
                        st.error("삭제를 완료하지 못했어요. 저장소 연결과 목록을 다시 확인해 주세요.")
                    else:
                        _end_edit(user, row["id"])
                        st.rerun()
