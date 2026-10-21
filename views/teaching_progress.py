"""교사전용 → 진도관리. No quiz widgets or student-facing schedule publication."""
from __future__ import annotations

import calendar
import hashlib
import uuid
from datetime import date

import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS
import teaching_progress_service as svc
from teaching_progress_visuals import hero_html, cards_html, table_html


def _prefix(user):
    return "tp_" + hashlib.sha256(str(user["id"]).encode()).hexdigest()[:12]


def _as_date(value):
    return date.fromisoformat(value) if value else None


def _finish(prefix, action):
    if action == "create":
        st.session_state[prefix + "_nonce"] = uuid.uuid4().hex
    st.session_state.pop(prefix + "_editor", None)
    st.session_state.pop(prefix + "_pending_action", None)
    st.session_state[prefix + "_notice"] = {
        "create": "기록을 저장했어요. 선택한 학급별로 독립된 기록이 만들어졌습니다.",
        "update": "수정한 내용을 저장했어요.", "complete": "선택한 수업을 완료로 기록했어요.",
        "delete": "기록을 휴지통으로 이동했어요. 아래에서 복원할 수 있습니다.",
        "restore": "기록을 복원했어요.",
    }.get(action, "영구 저장을 확인했어요.")


def _run(prefix, action, fn, *args, **kwargs):
    try:
        with st.spinner("기록을 저장하는 중..."):
            fn(*args, **kwargs)
    except svc.SavePendingError:
        # Keep the action and immutable creation request ID across retries.
        st.session_state[prefix + "_pending_action"] = action
        st.rerun()
    except (PermissionError, ValueError) as error:
        st.error(str(error))
    except Exception:
        st.error("저장 요청을 완료하지 못했어요. 입력 내용을 유지한 상태에서 연결을 확인해 주세요.")
    else:
        _finish(prefix, action)
        st.rerun()


def _form(prefix, row=None, *, disabled=False):
    """Values stay in widgets on validation/flush failures; no clear_on_submit."""
    row = row or {}
    editing = bool(row)
    with st.form(prefix + "_form", clear_on_submit=False, enter_to_submit=False):
        c1, c2, c3 = st.columns([1, 1.3, 1])
        lesson_day = c1.date_input("수업·기록일", value=_as_date(row.get("date")) or db.now().date(),
                                  min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                  format="YYYY-MM-DD", key=prefix + "_date", disabled=disabled)
        if editing:
            classes = [c2.selectbox("학급", CLASSES, index=CLASSES.index(row["class"]), key=prefix + "_class", disabled=disabled)]
        else:
            classes = c2.multiselect("학급 (여러 반 동시 등록 가능)", CLASSES, default=[CLASSES[0]],
                                     key=prefix + "_classes", disabled=disabled)
        subject = c3.selectbox("과목", SUBJECTS,
                               index=SUBJECTS.index(row.get("subject", SUBJECTS[-1])),
                               key=prefix + "_subject", disabled=disabled)
        c4, c5 = st.columns(2)
        period = c4.selectbox("수업 교시", svc.PERIODS, index=svc.PERIODS.index(row.get("period", "미정")),
                             key=prefix + "_period", disabled=disabled)
        status = c5.selectbox("진행 상태", svc.LESSON_STATUSES,
                             index=svc.LESSON_STATUSES.index(row.get("status", "예정")),
                             key=prefix + "_status", disabled=disabled)
        content = st.text_area("수업내용", value=row.get("content", ""), height=100, max_chars=4000,
                               placeholder="예: 원의 방정식 — 중심과 반지름, 학습지 3번까지 진행",
                               key=prefix + "_content", disabled=disabled)
        st.markdown("**수행평가 일정 (선택)**")
        st.caption("수업일과 다른 날짜로 등록할 수 있어요. 날짜가 정해지지 않았다면 비워 두세요. "
                   "수행평가만 기록하려면 수업내용은 비워 두어도 됩니다.")
        title = st.text_input("수행평가명", value=row.get("assessment_title", ""), max_chars=300,
                              placeholder="예: 도형의 방정식으로 픽토그램 제작", key=prefix + "_assessment_title", disabled=disabled)
        a1, a2, a3 = st.columns(3)
        assessment_day = a1.date_input("수행평가일 (미정이면 비우기)", value=_as_date(row.get("assessment_date")),
                                       min_value=date(2000, 1, 1), max_value=date(2100, 12, 31), format="YYYY-MM-DD",
                                       key=prefix + "_assessment_date", disabled=disabled)
        assessment_period = a2.selectbox("평가 교시", svc.PERIODS,
                                         index=svc.PERIODS.index(row.get("assessment_period") or "미정"),
                                         key=prefix + "_assessment_period", disabled=disabled)
        assessment_status = a3.selectbox("평가 상태", svc.ASSESSMENT_STATUSES,
                                         index=svc.ASSESSMENT_STATUSES.index(row.get("assessment_status") or "예정"),
                                         key=prefix + "_assessment_status", disabled=disabled)
        memo = st.text_area("메모 · 준비물 · 다음 수업", value=row.get("memo", ""), height=80, max_chars=4000,
                           placeholder="예: 다음 시간 평행이동 연결 / 아이패드·충전기 준비", key=prefix + "_memo", disabled=disabled)
        save = st.form_submit_button("수정 저장" if editing else "선택 학급에 기록 저장", type="primary", disabled=disabled)
    payload = {"date": lesson_day, "subject": subject, "period": period, "content": content,
               "status": status, "assessment_title": title, "assessment_date": assessment_day,
               "assessment_period": assessment_period, "assessment_status": assessment_status, "memo": memo}
    return save, classes, payload


def _editor(user, prefix, rows, disabled):
    if not rows:
        return
    with st.expander("✏️ 기록 수정 · 수업 완료 · 삭제", expanded=bool(st.session_state.get(prefix + "_editor"))):
        by_id = {r["id"]: r for r in rows}
        label = lambda rid: (f'{by_id[rid]["date"]} · {by_id[rid]["class"]}반 · {by_id[rid]["subject"]} · '
                              + (by_id[rid]["content"] or by_id[rid]["assessment_title"])[:60])
        selected = st.selectbox("관리할 기록", list(by_id), format_func=label, index=None,
                                placeholder="위 표의 기록 중 하나를 선택하세요", key=prefix + "_selected", disabled=disabled)
        c1, c2 = st.columns(2)
        if c1.button("선택 기록 수정", key=prefix + "_open_edit", disabled=not selected or disabled):
            try:
                st.session_state[prefix + "_editor"] = svc.get_record(user, selected)
                st.session_state[prefix + "_edit_epoch"] = uuid.uuid4().hex
            except (PermissionError, ValueError) as error:
                st.error(str(error))
        if c2.button("선택 수업 완료로 표시", key=prefix + "_complete", disabled=not selected or disabled,
                     help="예정일이 미래라면 실제 수업일을 먼저 수정하세요."):
            _run(prefix, "complete", svc.set_completed, user, selected, by_id[selected]["revision"])
        snapshot = st.session_state.get(prefix + "_editor")
        if snapshot:
            st.caption(f'편집 중: {snapshot["date"]} · {snapshot["class"]}반. 선택만으로는 기록이 바뀌지 않아요.')
            edit_key = prefix + "_edit_" + snapshot["id"] + "_r" + snapshot["revision"] + "_" + st.session_state.setdefault(prefix + "_edit_epoch", uuid.uuid4().hex)
            save, classes, payload = _form(edit_key, snapshot, disabled=disabled)
            if save:
                _run(prefix, "update", svc.update_record, user, snapshot["id"], payload, classes[0], snapshot["revision"])
            r1, r2 = st.columns(2)
            if r1.button("편집 닫기", key=prefix + "_cancel_edit", disabled=disabled):
                st.session_state.pop(prefix + "_editor", None)
                st.rerun()
            if r2.button("최신 기록 다시 불러오기", key=prefix + "_reload_edit", disabled=disabled):
                try:
                    latest = svc.get_record(user, snapshot["id"])
                    # A new widget namespace reloads the latest values without
                    # mutating widget state after those widgets were rendered.
                    st.session_state[prefix + "_editor"] = latest
                    st.session_state[prefix + "_edit_epoch"] = uuid.uuid4().hex
                    st.rerun()
                except (PermissionError, ValueError) as error:
                    st.error(str(error))
        if selected:
            confirm = st.checkbox("선택 기록을 휴지통으로 이동합니다", key=prefix + "_confirm_" + selected, disabled=disabled)
            if st.button("기록 삭제", key=prefix + "_delete_" + selected, disabled=disabled or not confirm):
                _run(prefix, "delete", svc.delete_record, user, selected, by_id[selected]["revision"])


def page(user):
    try:
        svc.require_teacher(user)
        rows = svc.list_records(user)
    except PermissionError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("진도 기록을 불러오지 못했어요. 저장소 연결을 확인해 주세요.")
        return
    prefix = _prefix(user)
    st.markdown(hero_html(), unsafe_allow_html=True)
    notice = st.session_state.pop(prefix + "_notice", None)
    if notice:
        st.success(notice)
    pending_action = st.session_state.get(prefix + "_pending_action")
    pending = svc.pending_save(user)
    disabled = bool(pending or pending_action)
    if disabled:
        st.warning("변경 내용은 서버에 반영되었으나 저장 확인이 필요합니다. 목록을 확인하고 ‘저장 다시 확인’을 눌러 주세요. "
                   "재등록·수정·삭제는 확인이 끝날 때까지 잠시 멈춥니다.")
        if st.button("저장 다시 확인", key=prefix + "_retry"):
            try:
                svc.retry_save(user)
            except svc.SavePendingError as error:
                st.warning(str(error))
            except PermissionError as error:
                st.error(str(error))
            else:
                _finish(prefix, pending_action or "retry")
                st.rerun()
    if db.get_backend().is_local:
        st.info("로컬 시험 모드입니다. 운영 시 기존 GitHub 저장 설정을 사용하세요. 배포 서버의 로컬 파일은 재시작 후 보존을 보장하지 않습니다.")
    st.caption("본인 교사 계정의 기록만 표시합니다. 학생 화면에는 공개되지 않으며, 퀴즈·점수·기존 클래스룸 자료를 변경하지 않습니다.")

    f1, f2 = st.columns(2)
    subject = f1.selectbox("조회 과목", ["전체"] + list(SUBJECTS), key=prefix + "_subject_filter")
    cls = f2.selectbox("조회 학급", ["전체"] + list(CLASSES), key=prefix + "_class_filter")
    st.markdown(cards_html(svc.summaries(rows, db.today_str(), subject), db.today_str()), unsafe_allow_html=True)

    nonce = st.session_state.setdefault(prefix + "_nonce", uuid.uuid4().hex)
    with st.expander("＋ 수업내용 · 수행평가 일정 기록", expanded=not rows):
        st.caption("같은 내용을 여러 반에 등록해도 각 반의 날짜·진행 상태는 따로 수정할 수 있어요. "
                   "등록만으로 수업 완료 처리되지 않습니다.")
        save, classes, payload = _form(prefix + "_new_" + nonce, disabled=disabled)
        if save:
            _run(prefix, "create", svc.create_records, user, classes, payload, nonce)

    st.markdown("#### 일자별 진도관리표")
    view = st.radio("표 보기", ["수업일 기준", "수행평가일 기준"], horizontal=True, key=prefix + "_mode")
    mode = "lesson" if view == "수업일 기준" else "assessment"
    today = db.now().date()
    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    f3, f4, f5 = st.columns([1, 1, 1.4])
    start = f3.date_input("조회 시작일", value=first, format="YYYY-MM-DD", key=prefix + "_start")
    end = f4.date_input("조회 종료일", value=last, format="YYYY-MM-DD", key=prefix + "_end")
    keyword = f5.text_input("수업내용·평가명·메모 검색", key=prefix + "_keyword")
    include_undated = True
    if mode == "assessment":
        include_undated = st.checkbox("날짜가 미정인 수행평가도 포함", value=True, key=prefix + "_undated")
        st.caption("연결된 수업일이 아닌 수행평가일로 조회합니다. 미정 일정은 기간과 관계없이 표 아래에 표시합니다.")
    else:
        st.caption("수업·기록일을 기준으로 조회합니다. 예정·진행 중·완료·휴강을 상태 문구로 구분합니다.")
    try:
        visible = svc.filter_records(rows, start.isoformat(), end.isoformat(), cls, subject, mode, keyword, include_undated)
    except ValueError as error:
        st.warning(str(error))
        return
    st.caption(f"현재 조회 {len(visible)}건 · 표가 넓으면 좌우로 스크롤하세요. 상세 내용은 아래 수정 화면에서 확인할 수 있습니다.")
    st.markdown(table_html(svc.display_rows(visible, mode)), unsafe_allow_html=True)
    if visible:
        st.download_button("현재 표 CSV 내려받기", svc.export_csv(user, start.isoformat(), end.isoformat(), cls, subject, mode, keyword, include_undated),
                           file_name=f'{"수행평가일정" if mode == "assessment" else "진도관리표"}_{start}_{end}.csv',
                           mime="text/csv", key=prefix + "_csv")
    _editor(user, prefix, visible, disabled)
    with st.expander("🗑️ 삭제 기록 복원"):
        deleted = [r for r in svc.list_records(user, include_deleted=True) if r.get("deleted_at")]
        if not deleted:
            st.caption("삭제한 기록이 없어요.")
        else:
            by_id = {r["id"]: r for r in deleted}
            restore_id = st.selectbox("복원할 기록", list(by_id), index=None,
                                     format_func=lambda rid: f'{by_id[rid]["date"]} · {by_id[rid]["class"]}반 · '
                                                            + (by_id[rid]["content"] or by_id[rid]["assessment_title"])[:60],
                                     key=prefix + "_restore_selected", disabled=disabled)
            if st.button("선택 기록 복원", key=prefix + "_restore", disabled=disabled or not restore_id):
                _run(prefix, "restore", svc.restore_record, user, restore_id, by_id[restore_id]["revision"])
        st.caption("삭제는 휴지통 이동입니다. GitHub 과거 버전까지 지우는 영구 삭제 기능이 아닙니다.")
