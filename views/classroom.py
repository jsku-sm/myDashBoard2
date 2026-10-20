"""Classroom screens integrated with the existing authenticated Streamlit app.

All reads and writes go through the permission-checking classroom services.
Widget drafts are deliberately retained when durable storage rejects a write.
"""
from __future__ import annotations

import copy
import csv
from datetime import date, datetime, timedelta
import io
import re
from time import monotonic
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

import auth
import storage as legacy_storage
import ui
from config import CLASSES, SUBJECTS, TZ


PROGRESS = {"unassigned": "⚪ 미배정", "scheduled": "🔵 수업 예정",
            "in_progress": "🟡 진행 중", "completed": "🟢 수업 완료"}
SCHEDULE = {"normal": "정상", "changed": "일정 변경", "cancelled": "휴강"}
KINDS = {"regular": "정규 수업", "after_school": "방과후 수업"}


def _today():
    return datetime.now(TZ).date()


def _key(user, suffix):
    return f"classroom_{user['id']}_{suffix}"


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None


def _iso(value):
    return value.isoformat() if value else ""


def _name(course):
    name = str(course.get("title") or "").strip() or str(course.get("class_name") or "").strip()
    parts = [str(part).strip() for part in (name, KINDS.get(course.get("kind"), course.get("kind")))
             if part and str(part).strip()]
    return " · ".join(dict.fromkeys(parts))


def _course_sort_key(course):
    name = str(course.get("title") or course.get("class_name") or "").strip()
    natural = tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                    for part in re.split(r"([0-9]+)", name))
    return course.get("kind") == "after_school", natural, str(course.get("id", ""))


def _lesson_name(lesson):
    if not lesson:
        return "없음"
    if not isinstance(lesson, dict):
        return str(lesson)
    return " · ".join(str(lesson.get(part, "")) for part in ("unit", "title") if lesson.get(part)) or "제목 없는 차시"


def _record(course, lesson_id):
    return course.get("lesson_records", {}).get(lesson_id, {})


def _teacher(user, course=None):
    return user.get("role") == "teacher" and (course is None or str(user["id"]) in course.get("teacher_ids", []))


def _editable(user, course):
    return _teacher(user, course) and not course.get("archived", False)


def _error(error):
    from classroom_core import ClassroomError
    if isinstance(error, ClassroomError):
        st.error(str(error))
    else:
        st.error("연결 또는 처리 중 오류가 발생했어요. 입력 내용은 유지됩니다. 잠시 뒤 다시 시도해 주세요.")


def _save(user, action, message, *, clear_prefix=""):
    """Only acknowledge a mutation after the durable service returns."""
    try:
        with st.spinner("GitHub에 저장하고 확인하는 중…"):
            result = action()
        if clear_prefix:
            for key in list(st.session_state):
                if key == clear_prefix or key.startswith(clear_prefix + "_"):
                    del st.session_state[key]
        st.session_state[_key(user, "flash")] = message
        st.rerun()
        return result
    except Exception as error:
        _error(error)
        return None


def _expected_version(record, prefix, *, details=None):
    """Keep the version shown when drafting, including across failed saves."""
    version_key = prefix + "_base_version"
    expected = st.session_state.setdefault(version_key, record["version"])
    snapshot = details if details is not None else {key: record.get(key) for key in (
        "title", "term", "class_name", "comments_enabled", "archived", "curriculum_id", "curriculum_version")}
    snapshot_key = prefix + "_base_snapshot"
    previous = st.session_state.setdefault(snapshot_key, copy.deepcopy(snapshot))
    if expected != record["version"] and previous == snapshot:
        # A different lesson or a membership change cannot overwrite this
        # draft. Only overlapping operating fields require a review.
        st.session_state[version_key] = expected = record["version"]
    if expected != record["version"]:
        st.warning("다른 창에서 이 기록이 변경됐어요. 작성 중인 입력은 유지했습니다. 최신 기록을 확인한 뒤 다시 저장해 주세요.")
        with st.expander("최신 저장 기록 확인", expanded=True):
            st.json(snapshot, expanded=False)
            if st.button("최신 기록 확인 · 작성 중인 입력 유지", key=prefix + "_rebase", width="stretch"):
                st.session_state[version_key] = record["version"]
                st.session_state[snapshot_key] = copy.deepcopy(snapshot)
                st.rerun()
    return expected


def _open_course(user, course_id, lesson_id=""):
    st.session_state[_key(user, "next_section")] = "내 수업"
    st.session_state[_key(user, "next_course")] = course_id
    if lesson_id:
        st.session_state[_key(user, "focus_lesson")] = {"course_id": course_id, "lesson_id": lesson_id}
    st.rerun()


def _class_names():
    # Use the current roster first. The existing configurable defaults are only
    # examples when no class information has been registered yet.
    names = sorted({str(student.get("class", "")).strip() for student in auth.students()
                    if str(student.get("class", "")).strip()})
    try:
        setting = legacy_storage.get_setting("classes")
        configured = [part.strip() for part in setting.replace(",", "\n").splitlines() if part.strip()]
    except Exception:
        configured = []
    return sorted(set(names + configured)) or list(CLASSES)


def _safe_url(value):
    try:
        parsed = urlparse(str(value))
        return str(value) if parsed.scheme in ("https", "http") and parsed.netloc and not parsed.username else ""
    except ValueError:
        return ""


def _resources(service, course, lesson, user, key):
    """Launch references without ever changing the lesson completion state."""
    try:
        from views import classroom_work
        renderer = getattr(classroom_work, "render_lesson_resources", None)
        if renderer:
            renderer(service, course, {**lesson, **_record(course, lesson.get("id", ""))}, user, key=key)
            return
    except ImportError:
        pass
    record = _record(course, lesson.get("id", ""))
    resources = record.get("resources", lesson.get("resources", []))
    for index, resource in enumerate(resources):
        if resource.get("activity_id") or resource.get("kind", resource.get("type")) == "snorkl":
            st.caption("이전 외부 활동 연결은 비활성화되었습니다. 새 자료나 과제를 등록하세요.")
            continue
        url = _safe_url(resource.get("url", ""))
        if url:
            st.link_button(resource.get("title") or "연결 자료 열기", url, width="stretch")
        elif resource.get("title"):
            st.caption(resource["title"])
    if lesson.get("activity_id"):
        st.caption("이전 외부 활동 연결은 비활성화되었습니다. 새 자료나 과제를 등록하세요.")
    if not resources and not lesson.get("activity_id"):
        st.caption("연결 자료가 아직 없어요. 수업·자료에서 등록할 수 있어요.")


def _count(summary, field):
    value = summary.get(field, [])
    return len(value) if isinstance(value, (list, tuple, set, dict)) else int(value or 0)


def _summary_row(course, summary):
    recent = summary.get("recent_completed")
    return {
        "학급": course.get("class_name") or "학급 미지정", "수업": course.get("title", ""),
        "과목": course.get("subject", ""), "진행 중": _lesson_name(summary.get("current_lesson")),
        "최근 완료": _lesson_name(recent),
        "실제 수업일": recent.get("actual_date", "") if isinstance(recent, dict) else "",
        "완료 / 적용 차시": f"{summary.get('completed', 0)} / {summary.get('total', 0)}",
        "진도율": f"{summary['percent']:.1f}%" if summary.get("percent") is not None else "수업안 미설정",
        "예정 차시 미완료": _count(summary, "due_incomplete"),
        "예정보다 먼저 완료": _count(summary, "early_completed"),
        "계획": summary.get("plan_label", ""),
        "보충 필요": "필요" if summary.get("makeup_needed") else "없음",
        "다음 수업": _lesson_name(summary.get("next_lesson")), "마지막 수정": summary.get("updated_at", ""),
    }


def _csv(rows):
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@"))
                         else value for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


def _dashboard(service, courses, user):
    mode = st.segmented_control("전체 학급 진도 보기", ["수업내용 체크", "기존 상세 진도"],
                                default="수업내용 체크", key=_key(user, "dashboard_layout")) or "수업내용 체크"
    if mode == "기존 상세 진도":
        _legacy_dashboard(service, courses, user)
    else:
        from views.classroom_progress_board import render_board
        render_board(service, courses, user)


def _legacy_dashboard(service, courses, user):
    st.markdown("### 전체 학급 진도")
    st.caption("교사가 확인한 고유 차시의 완료 기록으로 계산해요. 자료 열기·학생 제출은 진도를 바꾸지 않아요.")
    owned = [course for course in courses if _teacher(user, course)]
    if not owned:
        st.info("담당 수업이 아직 없어요. ‘내 수업’에서 수업을 개설하고 공통 수업안을 적용해 주세요.")
        return
    top = st.columns([1, 1, 1, 1])
    term = top[0].selectbox("학기", ["전체"] + sorted({course.get("term", "") for course in owned}), key=_key(user, "filter_term"))
    subject = top[1].selectbox("과목", ["전체"] + sorted({course.get("subject", "") for course in owned}), key=_key(user, "filter_subject"))
    kind = top[2].selectbox("정규·방과후", ["전체"] + list(KINDS), format_func=lambda value: KINDS.get(value, value), key=_key(user, "filter_kind"))
    as_of = top[3].date_input("기준일", value=_today(), key=_key(user, "asof"))
    lower = st.columns([2, 2, 1])
    classes = lower[0].multiselect("담당 학급", sorted({course.get("class_name", "") for course in owned}), key=_key(user, "filter_classes"), placeholder="선택하지 않으면 전체 학급")
    units = sorted({lesson.get("unit", "") for course in owned for lesson in course.get("lessons", []) if lesson.get("unit")})
    unit = lower[1].selectbox("단원", ["전체"] + units, key=_key(user, "filter_unit"))
    archived = lower[2].checkbox("보관 수업 포함", key=_key(user, "filter_archive"))
    filtered = [course for course in owned
                if (term == "전체" or course.get("term") == term)
                and (subject == "전체" or course.get("subject") == subject)
                and (kind == "전체" or course.get("kind") == kind)
                and (not classes or course.get("class_name", "") in classes)
                and (archived or not course.get("archived"))
                and (unit == "전체" or any(lesson.get("unit") == unit for lesson in course.get("lessons", [])))]
    if not filtered:
        st.info("선택한 조건에 맞는 수업이 없어요. 필터를 바꾸거나 수업을 개설해 주세요.")
        return
    mode = st.segmented_control("진도 보기", ["반별 요약", "차시별 비교표", "주간 달력"], default="반별 요약", key=_key(user, "progress_mode")) or "반별 요약"
    if mode == "반별 요약":
        _summary_cards(service, filtered, user, as_of, unit)
    elif mode == "차시별 비교표":
        _matrix(service, filtered, user, unit)
    else:
        _calendar(service, filtered, user, as_of, unit, key="overall")


def _summary_cards(service, courses, user, as_of, unit):
    rows = []
    for course in courses:
        summary = service.progress_summary(course["id"], as_of=_iso(as_of), unit=None if unit == "전체" else unit)
        rows.append(_summary_row(course, summary))
        with st.container(border=True):
            a, b, c = st.columns([3, 2, 2])
            a.markdown(f"**{course.get('class_name') or '학급 미지정'} · {course.get('title', '')}**")
            a.caption(f"{course.get('subject', '')} · {course.get('curriculum_title', '공통 수업안')} · {KINDS.get(course.get('kind'), '')}")
            percent = summary.get("percent")
            b.metric("완료 / 적용 차시", f"{summary.get('completed', 0)} / {summary.get('total', 0)}")
            c.metric("진도율", f"{percent:.1f}%" if percent is not None else "수업안 미설정")
            if percent is not None:
                st.progress(min(1.0, max(0.0, percent / 100)))
            current, recent, next_lesson = summary.get("current_lesson"), summary.get("recent_completed"), summary.get("next_lesson")
            st.write(f"진행 중: {_lesson_name(current)}")
            recent_date = recent.get("actual_date", "실제일 미입력") if isinstance(recent, dict) else ""
            st.write(f"최근 완료: {_lesson_name(recent)} {f'({recent_date})' if recent else ''}")
            st.write(f"다음 수업: {_lesson_name(next_lesson)}")
            due, early = _count(summary, "due_incomplete"), _count(summary, "early_completed")
            if summary.get("plan_label") == "계획 미설정":
                st.info("계획 미설정 · 수업 달력에서 날짜를 배치해 주세요.")
            elif due:
                st.warning(f"기준일까지 예정된 차시 중 미완료 {due}개 · 예정보다 먼저 완료 {early}개")
            else:
                st.caption(f"예정 차시 미완료 {due}개 · 예정보다 먼저 완료 {early}개")
            if summary.get("makeup_needed"):
                st.warning("보충 설명이 필요한 차시가 있어요.")
            cancelled = _count(summary, "reschedule_needed")
            if cancelled:
                st.caption(f"휴강 후 재배치 대상 {cancelled}개")
            st.caption(f"마지막 진도 수정: {summary.get('updated_at') or '기록 없음'}")
            left, right = st.columns(2)
            if left.button("달력·진도 상세", key=_key(user, f"summary_open_{course['id']}"), width="stretch"):
                _open_course(user, course["id"])
            if right.button("다음 수업 시작", key=_key(user, f"summary_next_{course['id']}"), disabled=not next_lesson, width="stretch"):
                _open_course(user, course["id"], next_lesson.get("id", "") if isinstance(next_lesson, dict) else str(next_lesson))
            if isinstance(next_lesson, dict):
                with st.expander("다음 수업 연결 자료"):
                    _resources(service, course, next_lesson, user, _key(user, f"summary_resources_{course['id']}"))
    st.download_button("반별 진도표 내려받기", _csv(rows), "classroom-progress.csv", "text/csv", key=_key(user, "progress_export"))


def _matrix(service, courses, user, unit):
    groups = {}
    for course in courses:
        # A snapshot revision can differ after curriculum editing. Comparing its
        # titles against a different revision would create a misleading matrix.
        signature = (course.get("subject"), course.get("curriculum_id"),
                     tuple((lesson.get("id"), lesson.get("unit"), lesson.get("title")) for lesson in course.get("lessons", [])))
        groups.setdefault(signature, []).append(course)
    options = list(groups)
    chosen = st.selectbox("같은 공통 수업안의 학급끼리 비교", options,
                          format_func=lambda group: f"{group[0]} · {groups[group][0].get('curriculum_title') or groups[group][0].get('title', '')} · {len(groups[group])}개 수업",
                          key=_key(user, "matrix_group"))
    selected = groups[chosen]
    lessons = [lesson for lesson in selected[0].get("lessons", []) if unit == "전체" or lesson.get("unit") == unit]
    if not lessons:
        st.info("비교할 차시가 없어요. 공통 수업안을 먼저 적용해 주세요.")
        return
    columns = {f"{index + 1}. {_lesson_name(lesson)}": lesson["id"] for index, lesson in enumerate(lessons)}
    data = []
    for course in selected:
        row = {"학급 / 수업": f"{course.get('class_name') or '학급 미지정'} · {course.get('title', '')}"}
        for column, lesson_id in columns.items():
            record = _record(course, lesson_id)
            status = PROGRESS.get(record.get("progress", "unassigned"), "⚪ 미배정") if record.get("applied", True) else "미적용"
            if record.get("schedule_status") == "cancelled":
                status += " · 휴강"
            elif record.get("schedule_status") == "changed":
                status += " · 일정 변경"
            if record.get("makeup_needed"):
                status += " · 보충 필요"
            row[column] = status
        data.append(row)
    st.caption("칸을 선택하면 아래에서 날짜·진도·보충 여부를 수정할 수 있어요. 표는 가로로 스크롤할 수 있어요.")
    event = st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch", on_select="rerun",
                         selection_mode="single-cell", key=_key(user, "matrix_cells"),
                         column_config={"학급 / 수업": st.column_config.TextColumn("학급 / 수업", pinned=True, width="medium"),
                                        **{column: st.column_config.TextColumn(column, width="medium") for column in columns}})
    cells = event.selection.cells
    if cells:
        cell = cells[0]
        row_index, column = (cell.get("row"), cell.get("column")) if isinstance(cell, dict) else cell
        if isinstance(row_index, int) and 0 <= row_index < len(selected) and column in columns:
            course = selected[row_index]
            lesson = next(lesson for lesson in lessons if lesson["id"] == columns[column])
            _lesson_editor(service, course, lesson, user, key="matrix")
            return
    # The alternative also works with a keyboard or an iPad without a cell tap.
    a, b = st.columns(2)
    course = a.selectbox("진도를 볼 수업", selected, format_func=_name, key=_key(user, "matrix_course"))
    lesson = b.selectbox("차시", lessons, format_func=_lesson_name, key=_key(user, "matrix_lesson"))
    _lesson_editor(service, course, lesson, user, key="matrix_fallback")


def _lesson_editor(service, course, lesson, user, *, key):
    record = _record(course, lesson["id"])
    prefix = _key(user, f"{key}_{course['id']}_{lesson['id']}")
    st.markdown(f"#### {course.get('class_name', '')} · {_lesson_name(lesson)}")
    st.write(lesson.get("objective") or "학습 목표가 아직 없어요.")
    _resources(service, course, lesson, user, prefix)
    if not _editable(user, course):
        st.write(f"계획일: {record.get('planned_date') or '미설정'} · 실제일: {record.get('actual_date') or '미입력'}")
        st.write(PROGRESS.get(record.get("progress", "unassigned"), "미배정"))
        if record.get("memo"):
            st.write(record["memo"])
        if record.get("next_note"):
            st.write("다음 시간: " + record["next_note"])
        if record.get("makeup_needed"):
            st.info("보충 필요 · " + record.get("makeup_reason", ""))
        return
    expected_version = _expected_version(course, prefix, details=record)
    with st.form(prefix, clear_on_submit=False):
        dates = st.columns(3)
        planned = dates[0].date_input("계획 수업일", value=_date(record.get("planned_date")), key=prefix + "_plan")
        actual = dates[1].date_input("실제 수업일", value=_date(record.get("actual_date")), key=prefix + "_actual")
        period = dates[2].text_input("교시", value=record.get("period", ""), key=prefix + "_period", placeholder="예: 3교시")
        a, b = st.columns(2)
        status = a.selectbox("진행 상태", list(PROGRESS), index=list(PROGRESS).index(record.get("progress", "unassigned")), format_func=PROGRESS.get, key=prefix + "_status")
        schedule = b.selectbox("일정 상태", list(SCHEDULE), index=list(SCHEDULE).index(record.get("schedule_status", "normal")), format_func=SCHEDULE.get, key=prefix + "_schedule")
        memo = st.text_area("어디까지 진행했나요?", value=record.get("memo", ""), key=prefix + "_memo")
        next_note = st.text_area("다음 시간에 이어 할 내용", value=record.get("next_note", ""), key=prefix + "_next")
        makeup = st.checkbox("보충 설명·재수업 필요", value=record.get("makeup_needed", False), key=prefix + "_makeup")
        makeup_reason = st.text_input("보충이 필요한 이유", value=record.get("makeup_reason", ""), key=prefix + "_makeup_reason")
        applied = st.checkbox("이 반에 적용하는 차시", value=record.get("applied", True), key=prefix + "_applied")
        reason = st.text_input("변경 이유", key=prefix + "_reason", placeholder="일정·차시 적용 여부·진도 변경 이유를 남겨 주세요.")
        confirm = st.checkbox("실제 수업을 확인했으며, 선택한 상태와 날짜를 저장합니다.", key=prefix + "_confirm")
        save = st.form_submit_button("진도 저장", type="primary", width="stretch")
    if save:
        if not confirm or not reason.strip():
            st.warning("변경 이유와 실제 수업 확인을 입력해 주세요. 입력 내용은 유지돼요.")
        else:
            changes = {"planned_date": _iso(planned), "actual_date": _iso(actual), "period": period,
                       "progress": status, "schedule_status": schedule, "memo": memo, "next_note": next_note,
                       "makeup_needed": makeup, "makeup_reason": makeup_reason, "applied": applied}
            _save(user, lambda: service.set_lesson(course["id"], lesson["id"], changes,
                                                 expected_version=expected_version, reason=reason),
                  "진도를 GitHub에 저장했어요. 전체 현황과 이 반 달력에 같은 기록이 반영됩니다.", clear_prefix=prefix)
    with st.expander("빠른 입력: 다음 날짜에 이어하기"):
        continuation = st.date_input("이어 할 날짜", value=_today() + timedelta(days=1), key=prefix + "_continue_date")
        continuation_reason = st.text_input("이어하기 이유", key=prefix + "_continue_reason")
        if st.button("진행 중으로 저장하고 이어 할 날짜 배치", key=prefix + "_continue_save", width="stretch"):
            if not continuation_reason.strip():
                st.warning("이어하기 이유를 입력해 주세요.")
            else:
                _save(user, lambda: service.set_lesson(course["id"], lesson["id"],
                                                     {"planned_date": _iso(continuation), "progress": "in_progress", "schedule_status": "changed"},
                                                     expected_version=expected_version, reason=continuation_reason),
                      "이어 할 날짜를 저장했어요. 완료 차시는 늘어나지 않습니다.", clear_prefix=prefix)
    with st.expander("보충·재수업·분할 수업 기록"):
        for session in record.get("sessions", []):
            label = {"makeup": "보충 수업", "repeat": "재수업", "split": "분할 수업"}.get(session.get("kind"), "추가 수업")
            st.write(f"{label} · 계획 {session.get('planned_date') or '미설정'} · 실제 {session.get('actual_date') or '미입력'}")
            if session.get("note"):
                st.caption(session["note"])
        with st.form(prefix + "_extra_session", clear_on_submit=False):
            session_kind = st.selectbox("추가 수업 종류", ["makeup", "repeat", "split"],
                                        format_func={"makeup": "보충 수업", "repeat": "재수업", "split": "분할 수업"}.get)
            a, b = st.columns(2)
            session_planned = a.date_input("추가 수업 계획일", value=_today())
            session_actual = b.date_input("추가 수업 실제일", value=None)
            session_note = st.text_area("추가 수업 이유·진행 내용")
            st.caption("같은 차시의 추가 수업을 기록해도 완료 차시 수는 중복 증가하지 않아요.")
            add_session = st.form_submit_button("추가 수업 기록 저장", width="stretch")
        if add_session:
            if not session_note.strip():
                st.warning("추가 수업 이유를 입력해 주세요.")
            else:
                _save(user, lambda: service.add_session(course["id"], lesson["id"], planned_date=_iso(session_planned),
                                                       actual_date=_iso(session_actual), kind=session_kind, note=session_note,
                                                       expected_version=expected_version),
                      "추가 수업을 GitHub에 기록했어요. 고유 차시의 완료 수는 유지됩니다.", clear_prefix=prefix)
    audit = [entry for entry in course.get("audit", []) if lesson["id"] in entry.get("lesson_changes", {})]
    if audit:
        with st.expander("이 차시 변경 이력"):
            for entry in reversed(audit[-20:]):
                st.caption(f"{entry.get('at', entry.get('created_at', ''))} · {entry.get('reason', '')}")
                change = entry["lesson_changes"][lesson["id"]]
                st.json({"변경 전": change.get("before"), "변경 후": change.get("after")}, expanded=False)


def _calendar_resources(service, course, user):
    try:
        from views import classroom_work
        loader = getattr(classroom_work, "calendar_resources", None)
        return loader(service, course, user) if loader else []
    except ImportError:
        return []


def _calendar_data(service, courses, user, unit):
    """Build the same agenda with each actor's permitted resources only."""
    items, tray, resources = [], [], []
    for course in courses:
        visible = _calendar_resources(service, course, user)
        resource_map = {(resource["kind"], resource["id"]): resource for resource in visible}
        for resource in visible:
            resources.append({**resource, "resource_kind": resource["kind"], "item_kind": "resource",
                              "course_id": course["id"], "movable": _editable(user, course), "expected_version": course["version"]})
        for lesson in course.get("lessons", []):
            if unit != "전체" and lesson.get("unit") != unit:
                continue
            record = _record(course, lesson["id"])
            if not record.get("applied", True):
                continue
            status = PROGRESS.get(record.get("progress", "unassigned"), "미배정")
            if record.get("schedule_status") in ("changed", "cancelled"):
                status += " · " + SCHEDULE[record["schedule_status"]]
            titles = []
            for reference in record.get("resources", lesson.get("resources", [])):
                if reference.get("kind") in {"material", "assignment"}:
                    allowed = resource_map.get((reference["kind"], reference.get("id")))
                    if allowed:
                        titles.append(allowed["title"])
                elif not reference.get("activity_id") and reference.get("kind") not in {"snorkl", "activity"}:
                    titles.append(reference.get("title", "자료"))
            item = {"id": lesson["id"], "course_id": course["id"], "title": _lesson_name(lesson),
                    "date": record.get("planned_date", ""), "progress": record.get("progress", "unassigned"),
                    "schedule_status": record.get("schedule_status", "normal"),
                    "subtitle": f"{course.get('class_name', '')} {record.get('period', '')} · {status}",
                    "detail": " · ".join(titles), "movable": _editable(user, course), "expected_version": course["version"]}
            (items if item["date"] else tray).append(item)
            for session in record.get("sessions", []):
                label = {"makeup": "보충 수업", "repeat": "재수업", "split": "분할 수업"}.get(session.get("kind"), "추가 수업")
                items.append({**item, "date": session.get("planned_date", ""), "movable": False,
                              "subtitle": f"{course.get('class_name', '')} · {label}",
                              "detail": f"실제 수업일: {session.get('actual_date') or '미입력'}"})
        for entry in course.get("calendar_resources", {}).values():
            allowed = resource_map.get((entry.get("kind"), entry.get("id")))
            if allowed:
                label = "수업 자료" if entry["kind"] == "material" else "과제"
                items.append({**allowed, "course_id": course["id"], "date": entry["date"],
                              "item_kind": "resource", "resource_kind": entry["kind"],
                              "subtitle": f"{_name(course)} · {label}", "movable": _editable(user, course), "expected_version": course["version"]})
        for day, note in course.get("calendar_notes", {}).items():
            items.append({"id": day, "course_id": course["id"], "date": day, "title": "메모",
                          "subtitle": _name(course), "detail": note, "item_kind": "note", "movable": False,
                          "editable": _editable(user, course)})
    return items, tray, resources


def _save_calendar_drop(service, course, event):
    """A drop changes the plan only; resource deadlines and progress stay intact."""
    if event["kind"] == "resource":
        return service.place_calendar_resource(course["id"], event["resource_kind"], event["id"],
                                               event["date"], event["expected_version"])
    record = _record(course, event["id"])
    changes = {"planned_date": event["date"]}
    if record.get("planned_date") and record["planned_date"] != event["date"]:
        changes["schedule_status"] = "changed"
    if record.get("progress", "unassigned") == "unassigned":
        changes["progress"] = "scheduled"
    return service.set_lesson(course["id"], event["id"], changes, event["expected_version"], "달력에서 차시 날짜 배치")


def _calendar(service, courses, user, anchor, unit="전체", *, key):
    from views.classroom_calendar import render_week
    prefix = _key(user, "calendar_" + key)
    anchor = st.date_input("주간 달력 기준일", value=anchor, key=prefix + "_anchor")
    monday = anchor - timedelta(days=anchor.weekday())
    days = [{"date": _iso(monday + timedelta(days=index)),
             "label": f"{(monday + timedelta(days=index)):%m/%d} {'월화수목금토일'[index]}"} for index in range(7)]
    items, tray, resources = _calendar_data(service, courses, user, unit)
    editable = any(_editable(user, course) for course in courses)
    event = render_week(days=days, items=items, tray=tray, resources=resources, editable=editable, key=prefix + "_week")
    course_map = {course["id"]: course for course in courses}
    if event and event.get("course_id") in course_map:
        course = course_map[event["course_id"]]
        valid_lesson = any(lesson["id"] == event.get("id") and _record(course, lesson["id"]).get("applied", True)
                           for lesson in course.get("lessons", []))
        valid_resource = any(resource["id"] == event.get("id") and resource["course_id"] == course["id"]
                             and resource["kind"] == event.get("resource_kind") for resource in resources)
        if event.get("kind") == "open" and valid_lesson:
            st.session_state[prefix + "_focus"] = {"course_id": course["id"], "lesson_id": event["id"]}
        elif event.get("kind") == "open_resource" and valid_resource:
            st.session_state[prefix + "_resource_focus"] = event
        elif _editable(user, course) and event.get("date") in {day["date"] for day in days}:
            if type(event.get("expected_version")) is int and ((event.get("kind") == "lesson" and valid_lesson)
                                                               or (event.get("kind") == "resource" and valid_resource)):
                current_date = (_record(course, event["id"]).get("planned_date") if event["kind"] == "lesson" else
                                course.get("calendar_resources", {}).get(event["resource_kind"] + ":" + event["id"], {}).get("date"))
                if current_date != event["date"]:
                    st.session_state[prefix + "_pending"] = event
                    _save(user, lambda: _save_calendar_drop(service, course, event),
                          "달력에 배치하고 저장했어요.", clear_prefix=prefix + "_pending")
    if (event and event.get("kind") == "note" and editable and event.get("date") in {day["date"] for day in days}
            and (not event.get("course_id") or (event["course_id"] in course_map and _editable(user, course_map[event["course_id"]])))):
        st.session_state[prefix + "_note_target"] = event
    st.caption("차시·자료·과제를 날짜에 끌어 놓으면 저장됩니다. 실제 수업일·자료 공개 시각·과제 마감은 따로 유지됩니다."
               if editable else "수업 일정과 메모를 확인할 수 있어요. 일정 편집은 담당 교사가 합니다.")
    if editable:
        pending = st.session_state.get(prefix + "_pending")
        if pending and pending.get("course_id") in course_map:
            st.warning("달력 배치를 저장하지 못했습니다. 다시 시도하거나 아래 날짜 배치를 이용해 주세요.")
            st.caption("달력의 최신 일정을 확인한 뒤 다시 저장해 주세요.")
            if st.button("달력 배치 다시 저장", key=prefix + "_retry"):
                _save(user, lambda: _save_calendar_drop(service, course_map[pending["course_id"]],
                                                       {**pending, "expected_version": course_map[pending["course_id"]]["version"]}),
                      "달력에 배치하고 저장했어요.", clear_prefix=prefix + "_pending")
        _place_date(service, courses, user, prefix, resources)
        _calendar_note_editor(service, courses, user, prefix, anchor)
    resource_focus = st.session_state.get(prefix + "_resource_focus", {})
    resource_course = course_map.get(resource_focus.get("course_id"))
    if resource_course and any(resource["id"] == resource_focus.get("id") and resource["kind"] == resource_focus.get("resource_kind")
                               and resource["course_id"] == resource_course["id"] for resource in resources):
        _resources(service, resource_course,
                   {"id": "calendar_resource", "resources": [{"kind": resource_focus["resource_kind"], "id": resource_focus["id"]}]},
                   user, prefix + "_resource_detail")
    focus = st.session_state.get(prefix + "_focus")
    if focus and focus["course_id"] in course_map:
        course = course_map[focus["course_id"]]
        lesson = next((lesson for lesson in course.get("lessons", []) if lesson["id"] == focus["lesson_id"]), None)
        if lesson:
            _lesson_editor(service, course, lesson, user, key=key + "_calendar_cell")
    elif len(courses) == 1 and courses[0].get("lessons"):
        course = courses[0]
        lessons = [lesson for lesson in course["lessons"] if unit == "전체" or lesson.get("unit") == unit]
        if lessons:
            lesson = st.selectbox("진도 상세 차시", lessons, format_func=_lesson_name, key=prefix + "_detail")
            _lesson_editor(service, course, lesson, user, key=key + "_calendar_detail")


def _calendar_note_editor(service, courses, user, prefix, anchor):
    owned = [course for course in courses if _editable(user, course)]
    if not owned:
        return
    target = st.session_state.get(prefix + "_note_target", {})
    with st.expander("날짜별 메모 · 학생에게도 표시", expanded=bool(target)):
        selected = next((index for index, course in enumerate(owned) if course["id"] == target.get("course_id")), 0)
        nkey = prefix + "_notes_" + str(target.get("course_id", "")) + "_" + str(target.get("date", ""))
        course = st.selectbox("메모할 수업", owned, index=selected, format_func=_name, key=nkey + "_course")
        day = st.date_input("메모 날짜", value=_date(target.get("date")) or anchor, key=nkey + "_date")
        day_text = _iso(day)
        note = course.get("calendar_notes", {}).get(day_text, "")
        form_key = nkey + "_" + course["id"] + "_" + day_text
        expected = _expected_version(course, form_key, details={day_text: note})
        with st.form(form_key):
            body = st.text_area("날짜 메모", value=note, max_chars=1000, key=form_key + "_text", placeholder="예: 학습지 지참, 3교시 보충 설명")
            st.caption("이 메모는 해당 수업의 학생에게도 보입니다. 내용을 비워 저장하면 삭제됩니다.")
            save = st.form_submit_button("메모 저장", type="primary")
        if save:
            _save(user, lambda: service.set_calendar_note(course["id"], day_text, body, expected),
                  "날짜 메모를 저장했어요.", clear_prefix=form_key)


def _place_date(service, courses, user, prefix, resources):
    _place_resource_date(service, courses, user, prefix, resources)
    owned = [course for course in courses if _editable(user, course) and course.get("lessons")]
    if not owned:
        st.info("날짜에 배치하려면 수업에 공통 수업안을 적용해 주세요.")
        return
    pending = st.session_state.get(prefix + "_pending", {})
    # Changing the key for each drag proposal refreshes defaults without
    # overwriting an already rendered widget or a failed-save draft.
    proposal = "_".join(str(pending.get(part, "")) for part in ("kind", "resource_kind", "course_id", "id", "date"))
    pkey = prefix + "_place_" + proposal
    with st.expander("날짜에 배치 · 터치·버튼 방식", expanded=pending.get("kind") == "lesson"):
        selected_index = next((index for index, course in enumerate(owned) if course["id"] == pending.get("course_id")), 0)
        course = st.selectbox("배치할 수업", owned, index=selected_index, format_func=_name, key=pkey + "_course")
        lessons = course["lessons"]
        lesson_index = next((index for index, lesson in enumerate(lessons) if lesson["id"] == pending.get("id")), 0)
        lesson = st.selectbox("배치할 차시", lessons, index=lesson_index, format_func=_lesson_name, key=pkey + "_lesson")
        record = _record(course, lesson["id"])
        form_key = pkey + "_" + course["id"] + "_" + lesson["id"]
        expected_version = _expected_version(course, form_key, details=record)
        linked = [resource for resource in resources if resource["course_id"] == course["id"]]
        defaults = [resource for resource in linked if pending.get("kind") == "resource" and resource["id"] == pending.get("id")
                    and resource["kind"] == pending.get("resource_kind")]
        with st.form(form_key + "_form", clear_on_submit=False):
            a, b = st.columns(2)
            planned = a.date_input("계획 수업일", value=_date(pending.get("date")) or _date(record.get("planned_date")) or _today(), key=form_key + "_date")
            period = b.text_input("교시", value=record.get("period", ""), key=form_key + "_period")
            chosen_resources = st.multiselect("함께 연결할 자료·과제", linked, default=defaults, format_func=lambda resource: resource.get("title", "자료"), key=form_key + "_resources")
            reason = st.text_input("일정 배치·변경 이유", key=form_key + "_reason")
            confirm = st.checkbox("대상 수업·차시·날짜를 확인했습니다.", key=form_key + "_confirm")
            save = st.form_submit_button("날짜에 배치", type="primary", width="stretch")
        if save:
            if not reason.strip() or not confirm:
                st.warning("변경 이유와 대상 확인이 필요해요. 입력은 유지됩니다.")
            else:
                changes = {"planned_date": _iso(planned), "period": period,
                           "schedule_status": "changed" if record.get("planned_date") and record["planned_date"] != _iso(planned) else record.get("schedule_status", "normal")}
                if record.get("progress", "unassigned") == "unassigned":
                    changes["progress"] = "scheduled"
                if chosen_resources:
                    saved_resources = list(record.get("resources", lesson.get("resources", [])))
                    existing = {(item.get("kind"), item.get("id")) for item in saved_resources}
                    for resource in chosen_resources:
                        item = {part: resource[part] for part in ("kind", "id", "title", "url") if part in resource}
                        if (item.get("kind"), item.get("id")) not in existing:
                            saved_resources.append(item)
                            existing.add((item.get("kind"), item.get("id")))
                    changes["resources"] = saved_resources
                _save(user, lambda: service.set_lesson(course["id"], lesson["id"], changes,
                                                     expected_version=expected_version, reason=reason),
                      "수업 날짜를 GitHub에 저장했어요. 과제 마감과 다른 반 일정은 유지됩니다.", clear_prefix=pkey)


def _place_resource_date(service, courses, user, prefix, resources):
    owned = [course for course in courses if _editable(user, course)]
    available = [resource for resource in resources if any(course["id"] == resource["course_id"] for course in owned)]
    if not available:
        return
    pending = st.session_state.get(prefix + "_pending", {})
    pending = pending if pending.get("kind") == "resource" else {}
    proposal = "_".join(str(pending.get(part, "")) for part in ("course_id", "resource_kind", "id", "date"))
    with st.expander("자료·과제 날짜 배치 · 터치·버튼 방식", expanded=bool(pending)):
        pkey = prefix + "_resource_place_" + proposal
        selected = next((index for index, item in enumerate(available) if item["course_id"] == pending.get("course_id")
                         and item["id"] == pending.get("id") and item["kind"] == pending.get("resource_kind")), 0)
        resource = st.selectbox("배치할 자료·과제", available,
                                index=selected, format_func=lambda item: ("자료 · " if item["kind"] == "material" else "과제 · ") + item["title"], key=pkey + "_resource")
        course = next(course for course in owned if course["id"] == resource["course_id"])
        current = course.get("calendar_resources", {}).get(resource["kind"] + ":" + resource["id"], {})
        expected = _expected_version(course, pkey + "_" + course["id"] + "_" + resource["kind"] + "_" + resource["id"], details=current)
        with st.form(pkey + "_form"):
            day = st.date_input("자료·과제 배치일", value=_date(pending.get("date")) or _date(current.get("date")) or _today(), key=pkey + "_date_" + course["id"] + resource["kind"] + resource["id"])
            save = st.form_submit_button("자료·과제 날짜 저장", type="primary")
        if save:
            _save(user, lambda: service.place_calendar_resource(course["id"], resource["kind"], resource["id"], _iso(day), expected),
                  "자료·과제를 달력에 배치했어요.", clear_prefix=pkey)


def _create_course(service, user):
    with st.expander("수업 개설"):
        curricula = service.list_curricula()
        with st.form(_key(user, "create_course"), clear_on_submit=False):
            title = st.text_input("수업명", key=_key(user, "new_title"))
            a, b = st.columns(2)
            term = a.text_input("학기", placeholder="예: 2026학년도 2학기", key=_key(user, "new_term"))
            subject = b.text_input("과목", placeholder=" / ".join(SUBJECTS), key=_key(user, "new_subject"))
            a, b = st.columns(2)
            kind = a.selectbox("수업 구분", list(KINDS), format_func=KINDS.get, key=_key(user, "new_kind"))
            class_name = b.selectbox("대상 학급", _class_names() + ["직접 입력"], key=_key(user, "new_class"))
            custom_class = st.text_input("학급 직접 입력 · 선택한 학급이 ‘직접 입력’일 때 사용", key=_key(user, "new_custom_class"))
            curriculum = st.selectbox("공통 수업안", [None] + curricula,
                                      format_func=lambda plan: "나중에 적용" if plan is None else f"{plan.get('subject', '')} · {plan.get('title', '')}", key=_key(user, "new_curriculum"))
            co_teachers = st.text_input("함께 담당할 교사 아이디 · 쉼표로 구분, 선택", key=_key(user, "new_teachers"))
            confirm = st.checkbox("학기·과목·대상 학급과 공동 담당 교사를 확인했습니다.", key=_key(user, "new_confirm"))
            save = st.form_submit_button("수업 개설", type="primary", width="stretch")
        if save:
            selected_class = custom_class.strip() if class_name == "직접 입력" else class_name
            if not title.strip() or not term.strip() or not subject.strip() or not confirm:
                st.warning("수업명·학기·과목과 대상 확인을 입력해 주세요.")
            elif not selected_class:
                st.warning("학생이 참여할 수 있도록 대상 학급을 입력해 주세요.")
            elif curriculum and curriculum.get("subject") != subject.strip():
                st.warning("공통 수업안과 수업의 과목을 같게 설정해 주세요.")
            else:
                teachers = list(dict.fromkeys([str(user["id"])] + [value.strip() for value in co_teachers.split(",") if value.strip()]))
                _save(user, lambda: service.create_course(title=title.strip(), term=term.strip(), subject=subject.strip(),
                                                         kind=kind, class_name=selected_class,
                                                         curriculum_id=curriculum["id"] if curriculum else "", teacher_ids=teachers),
                      "수업을 GitHub에 개설했어요. 구성원 탭의 6자리 승인코드를 해당 학급 학생에게 안내해 주세요.")


def _join_course(service, user, courses):
    if any(course.get("membership_status") == "approved" and not course.get("archived") for course in courses):
        return
    with st.container(border=True):
        st.markdown("### 수업 참여하기")
        st.caption("담당 교사가 알려 준 6자리 승인코드를 입력하면 본인 학급의 수업에 참여할 수 있어요.")
        prefix = _key(user, "join")
        with st.form(prefix, clear_on_submit=False):
            course_code = st.text_input("6자리 승인코드", key=prefix + "_code", max_chars=6,
                                        placeholder="예: 012345")
            join = st.form_submit_button("수업 참여하기", type="primary", width="stretch")
        if join:
            code = course_code.strip()
            if len(code) != 6 or not code.isascii() or not code.isdigit():
                st.warning("승인코드는 숫자 6자리로 입력해 주세요.")
                return
            attempt_key = prefix + "_attempts"
            attempts = [at for at in st.session_state.get(attempt_key, []) if monotonic() - at < 60]
            st.session_state[attempt_key] = attempts
            if len(attempts) >= 5:
                st.warning("승인코드를 여러 번 확인했어요. 1분 뒤에 다시 입력해 주세요.")
                return

            def join_and_open():
                from classroom_core import PermissionDenied, ValidationError
                try:
                    result = service.join_course(code)
                except (PermissionDenied, ValidationError):
                    st.session_state[attempt_key] = attempts + [monotonic()]
                    raise
                st.session_state[_key(user, "next_section")] = "내 수업"
                st.session_state[_key(user, "next_course")] = result["course_id"]
                st.session_state[_key(user, "my_kind")] = "전체"
                return result

            _save(user, join_and_open, "수업에 참여했어요. 내 수업에서 바로 확인할 수 있어요.", clear_prefix=prefix)


def _my_courses(service, courses, user):
    st.markdown("### 내 수업")
    if _teacher(user):
        _create_course(service, user)
    else:
        _join_course(service, user, courses)
    include_archive = st.checkbox("학기 보관 수업 보기", key=_key(user, "my_archive"))
    pending_courses = [course for course in courses if course.get("membership_status") == "pending"]
    for course in pending_courses:
        st.info(f"참여 승인 대기 · {_name(course)}")
    current = [course for course in courses if course.get("membership_status") != "pending"
               and (include_archive or not course.get("archived"))]
    regular, after = st.columns(2)
    regular.metric("정규 수업", sum(course.get("kind") == "regular" for course in current))
    after.metric("방과후 수업", sum(course.get("kind") == "after_school" for course in current))
    kind = st.segmented_control("수업 구분", ["전체", "regular", "after_school"], format_func=lambda value: KINDS.get(value, value), default="전체", key=_key(user, "my_kind")) or "전체"
    if _teacher(user) and kind == "전체":
        from views.classroom_work import render_announcement_distribution
        render_announcement_distribution(service, sorted(current, key=_course_sort_key), user)
    current = sorted((course for course in current if kind == "전체" or course.get("kind") == kind), key=_course_sort_key)
    if not current:
        st.info("표시할 수업이 없어요. 교사는 수업을 개설하고, 학생은 담당 교사에게 6자리 승인코드를 받아 수업에 참여해 주세요.")
        return
    pending = st.session_state.pop(_key(user, "next_course"), None)
    selected_key = _key(user, "course_picker")
    ids = [course["id"] for course in current]
    if pending in ids:
        st.session_state[selected_key] = pending
    if st.session_state.get(selected_key) not in ids:
        st.session_state.pop(selected_key, None)
    mapping = {course["id"]: course for course in current}
    selected = st.selectbox("수업 선택", ids, format_func=lambda course_id: _name(mapping[course_id]), key=selected_key)
    course = service.get_course(selected)
    _course_detail(service, course, user)


def _course_detail(service, course, user):
    st.markdown(f"### {course.get('title', '')}")
    st.caption(f"{course.get('term', '')} · {course.get('subject', '')} · {course.get('class_name', '')} · {KINDS.get(course.get('kind'), '')}")
    if course.get("archived"):
        st.info("학기 보관 수업 · 승인된 참여자가 기존 기록을 읽을 수 있어요.")
    focus = st.session_state.get(_key(user, "focus_lesson"), {})
    if focus.get("course_id") == course["id"]:
        lesson = next((lesson for lesson in course.get("lessons", []) if lesson["id"] == focus.get("lesson_id")), None)
        if lesson:
            with st.container(border=True):
                st.markdown("#### 바로 이어 할 수업 · " + _lesson_name(lesson))
                st.write(lesson.get("objective", ""))
                _resources(service, course, lesson, user, _key(user, "focused_resources"))
                if st.button("이 차시 진도 상세로 이동", key=_key(user, "focused_detail"), width="stretch"):
                    st.session_state[_key(user, "show_focus_editor")] = True
                if st.session_state.get(_key(user, "show_focus_editor")):
                    _lesson_editor(service, course, lesson, user, key="focused")
    teacher = _teacher(user)
    tabs = st.tabs([
        "공지", "수업·자료", "과제·퀴즈·수행평가", "수업 달력·진도",
        *(["구성원", "수업 설정"] if teacher else [])])
    stream, materials, assignments, calendar = tabs[:4]
    with stream:
        _work_tab("render_stream", service, course, user)
    with materials:
        _work_tab("render_materials", service, course, user)
        with st.expander("기존 자료실·과제방·수다노트 기록 연결"):
            if st.checkbox("기존 기록 불러오기", key=_key(user, "legacy_records_" + course["id"])):
                try:
                    from views.classroom_legacy_ui import render_legacy_records
                    render_legacy_records(service, course)
                except Exception as error:
                    _error(error)
    with assignments:
        _work_tab("render_assignments", service, course, user)
    with calendar:
        _calendar(service, [course], user, _today(), key="course_" + course["id"])
    if teacher:
        with tabs[4]:
            _members(service, course, user)
        with tabs[5]:
            _settings(service, course, user)


def _work_tab(function, service, course, user):
    try:
        from views import classroom_work
        getattr(classroom_work, function)(service, course, user)
    except Exception as error:
        _error(error)


def _members(service, course, user):
    if not _teacher(user, course):
        st.write(f"승인된 학생 {course.get('member_count', len(course.get('student_ids', [])))}명")
        st.caption("담당 교사가 수업 참여와 질문 공개 범위를 관리해요.")
        return
    st.markdown("#### 6자리 승인코드")
    if not str(course.get("class_name", "")).strip():
        st.warning("학생이 참여하려면 ‘수업 설정’에서 대상 학급을 먼저 지정해 주세요.")
    code = str(course.get("join_code", ""))
    if len(code) == 6 and code.isascii() and code.isdigit():
        st.code(code, language=None)
        st.caption("해당 학급 학생에게 알려 주세요. 학생이 승인코드를 입력하면 수업에 바로 참여해요.")
    elif not course.get("archived"):
        st.caption("기존 수업입니다. 승인코드를 발급해 해당 학급 학생에게 알려 주세요.")
        if st.button("승인코드 발급", key=_key(user, "issue_code_" + course["id"]), width="stretch"):
            _save(user, lambda: service.get_join_code(course["id"]), "6자리 승인코드를 GitHub에 저장했어요.")
    if course.get("archived"):
        st.caption("학기 보관 수업에는 새로 참여할 수 없어요.")
    pending = course.get("pending_student_ids", [])
    st.markdown(f"#### 승인 대기 · {len(pending)}명")
    if not pending:
        st.caption("대기 중인 참여 신청이 없어요.")
    for student_id in pending:
        student = auth.get_user(student_id) or {"id": student_id, "name": "사용자 확인 필요", "class": ""}
        a, b, c = st.columns([4, 1, 1])
        a.write(f"{student.get('class', '')} {student['id']} · {student.get('name', '')}")
        if b.button("승인", key=_key(user, f"approve_{course['id']}_{student_id}"), disabled=course.get("archived", False), width="stretch"):
            _save(user, lambda sid=student_id: service.approve_member(course["id"], sid, approve=True), "참여를 승인하고 GitHub에 저장했어요.")
        if c.button("반려", key=_key(user, f"reject_{course['id']}_{student_id}"), disabled=course.get("archived", False), width="stretch"):
            _save(user, lambda sid=student_id: service.approve_member(course["id"], sid, approve=False), "참여 신청을 반려했어요.")
    st.markdown(f"#### 승인된 학생 · {len(course.get('student_ids', []))}명")
    for student_id in course.get("student_ids", []):
        student = auth.get_user(student_id) or {"id": student_id, "name": "", "class": ""}
        a, b = st.columns([5, 1])
        a.write(f"{student.get('class', '')} {student_id} · {student.get('name', '')}")
        with b.popover("참여 관리", width="stretch"):
            confirm = st.checkbox("이 수업 접근을 해제합니다.", key=_key(user, f"remove_confirm_{course['id']}_{student_id}"))
            if st.button("참여 해제", key=_key(user, f"remove_{course['id']}_{student_id}"), disabled=not confirm or course.get("archived", False)):
                _save(user, lambda sid=student_id: service.remove_member(course["id"], sid, expected_version=course["version"]), "이 수업의 참여 권한을 해제했어요. 기존 제출 기록은 보존됩니다.")


def _settings(service, course, user):
    if not _teacher(user, course):
        st.caption("수업 설정은 담당 교사가 관리해요.")
        return
    prefix = _key(user, f"settings_{course['id']}")
    expected_version = _expected_version(course, prefix)
    if not course.get("archived"):
        with st.form(prefix, clear_on_submit=False):
            title = st.text_input("수업명", value=course.get("title", ""), key=prefix + "_title")
            a, b = st.columns(2)
            term = a.text_input("학기", value=course.get("term", ""), key=prefix + "_term")
            class_name = b.text_input("대상 학급", value=course.get("class_name", ""), key=prefix + "_class")
            comments = st.checkbox("학생 공개 질문·댓글 허용", value=course.get("comments_enabled", True), key=prefix + "_comments")
            reason = st.text_input("설정 변경 이유", key=prefix + "_reason")
            save = st.form_submit_button("수업 설정 저장", type="primary", width="stretch")
        if save:
            if not reason.strip():
                st.warning("설정 변경 이유를 입력해 주세요.")
            else:
                _save(user, lambda: service.update_course(course["id"],
                                                         {"title": title, "term": term, "class_name": class_name, "comments_enabled": comments},
                                                         expected_version=expected_version, reason=reason), "수업 설정을 GitHub에 저장했어요.", clear_prefix=prefix)
        with st.expander("공통 수업안 적용·최신 내용 반영"):
            plans = [plan for plan in service.list_curricula() if plan.get("subject") == course.get("subject")]
            if not plans:
                st.info("같은 과목의 수업안을 먼저 만들어 주세요.")
            else:
                plan = st.selectbox("적용할 공통 수업안", plans, format_func=lambda value: value.get("title", ""), key=prefix + "_plan")
                before = {lesson["id"] for lesson in course.get("lessons", [])}
                after = {lesson["id"] for lesson in plan.get("lessons", [])}
                st.write(f"추가 차시 {len(after - before)}개 · 빠지는 차시 {len(before - after)}개")
                completed_removed = [lesson["id"] for lesson in course.get("lessons", []) if lesson["id"] not in after and _record(course, lesson["id"]).get("progress") == "completed"]
                if completed_removed:
                    st.warning(f"완료 기록이 있는 차시 {len(completed_removed)}개가 새 수업안에서 빠집니다. 기존 운영 기록과 변경 이력은 보존돼요.")
                st.caption("공통 수업안 수정은 이 반에 자동 반영되지 않아요. 명시적으로 적용하면 같은 차시의 일정·완료 기록을 유지합니다.")
                reason = st.text_input("수업안 적용 이유", key=prefix + "_apply_reason")
                confirm = st.checkbox("이 반의 변경 영향을 확인했습니다.", key=prefix + "_apply_confirm")
                if st.button("이 수업에만 적용", key=prefix + "_apply", disabled=not confirm, width="stretch"):
                    if not reason.strip():
                        st.warning("수업안 적용 이유를 입력해 주세요.")
                    else:
                        _save(user, lambda: service.apply_curriculum(course["id"], plan["id"], expected_version=expected_version, reason=reason), "이 수업에 수업안을 적용했어요. 다른 반 일정은 유지됩니다.", clear_prefix=prefix)
    with st.expander("다음 학기 수업으로 복사"):
        with st.form(prefix + "_copy", clear_on_submit=False):
            title = st.text_input("새 수업명", value=course.get("title", ""), key=prefix + "_copy_title")
            term = st.text_input("새 학기", key=prefix + "_copy_term")
            class_name = st.text_input("새 대상 학급", value=course.get("class_name", ""), key=prefix + "_copy_class")
            st.caption("수업안과 자료·과제 양식을 재사용해요. 학생·답안·점수·개인 댓글·실제 진도는 새 수업에 복사하지 않아요.")
            copy = st.form_submit_button("새 학기 양식으로 복사", width="stretch")
        if copy:
            if not title.strip() or not term.strip() or not class_name.strip():
                st.warning("새 수업명·학기·대상 학급을 입력해 주세요.")
            else:
                _save(user, lambda: service.copy_course(course["id"], title=title, term=term, class_name=class_name), "새 학기 수업 양식을 만들었어요. 학생 제출물·평가·실제 진도는 복사하지 않았습니다.")
    if not course.get("archived"):
        with st.expander("학기 보관"):
            confirm = st.checkbox("기록을 보존하고 수업을 읽기 전용으로 보관합니다.", key=prefix + "_archive_confirm")
            if st.button("이 수업 학기 보관", key=prefix + "_archive", disabled=not confirm, width="stretch"):
                _save(user, lambda: service.archive_course(course["id"], expected_version=expected_version), "수업을 학기 보관했어요. 승인된 참여자의 기존 기록은 유지됩니다.", clear_prefix=prefix)


def _resource_text(resources):
    return "\n".join(f"{resource.get('title', '')}|{resource.get('url', '')}" for resource in resources if resource.get("url"))


def _curriculum_editor_rows(plan):
    return [{"id": lesson.get("id", ""), "단원": lesson.get("unit", ""), "차시명": lesson.get("title", ""),
             "학습 목표": lesson.get("objective", ""), "연결 자료 · 제목|주소": _resource_text(lesson.get("resources", []))}
            for lesson in plan.get("lessons", [])]


def _edited_lessons(rows, plan):
    old = {lesson["id"]: lesson for lesson in plan.get("lessons", [])}
    result = []
    for row in rows:
        title = str(row.get("차시명") or "").strip()
        if not title:
            continue
        lesson_id = str(row.get("id") or "").strip()
        existing = old.get(lesson_id, {})
        resources_text = str(row.get("연결 자료 · 제목|주소") or "")
        if resources_text == _resource_text(existing.get("resources", [])):
            resources = existing.get("resources", [])
        else:
            resources = []
            for line in resources_text.splitlines():
                if not line.strip():
                    continue
                label, separator, url = line.partition("|")
                url = _safe_url(url.strip() if separator else label.strip())
                if not url:
                    raise ValueError("연결 자료는 ‘제목|https://주소’ 형식으로 입력해 주세요.")
                resources.append({"kind": "link", "title": label.strip() if separator else url, "url": url})
        result.append({"id": lesson_id, "unit": str(row.get("단원") or "").strip(), "title": title,
                       "objective": str(row.get("학습 목표") or "").strip(), "resources": resources,
                       # Preserve old metadata without exposing or launching a
                       # removed integration from the curriculum editor.
                       "activity_id": existing.get("activity_id", "")})
    return result


def _curricula(service, user):
    st.markdown("### 공통 수업안")
    st.caption("단원·차시·학습 목표·자료를 함께 설계하고, 반별 계획일과 실제 진도는 각각 저장해요.")
    plans = service.list_curricula()
    options = [""] + [plan["id"] for plan in plans]
    mapping = {plan["id"]: plan for plan in plans}
    selected = st.selectbox("공통 수업안 선택", options, format_func=lambda value: "새 공통 수업안" if not value else f"{mapping[value].get('subject', '')} · {mapping[value].get('title', '')}", key=_key(user, "plan_picker"))
    plan = service.get_curriculum(selected) if selected else {"id": "", "title": "", "subject": "", "lessons": [], "version": 0}
    prefix = _key(user, f"plan_{selected}")
    expected_version = _expected_version(plan, prefix, details={"수업안 이름": plan.get("title"), "차시": plan.get("lessons", [])}) if selected else None
    title = st.text_input("수업안 이름", value=plan.get("title", ""), key=prefix + "_title")
    subject = st.text_input("과목", value=plan.get("subject", ""), key=prefix + "_subject", disabled=bool(selected))
    rows = _curriculum_editor_rows(plan) or [{"id": "", "단원": "", "차시명": "", "학습 목표": "", "연결 자료 · 제목|주소": ""}]
    edited = st.data_editor(rows, num_rows="dynamic", hide_index=True, width="stretch", key=prefix + "_editor",
                            column_config={"id": None, "단원": st.column_config.TextColumn(width="medium"),
                                           "차시명": st.column_config.TextColumn(required=True, width="medium"),
                                           "학습 목표": st.column_config.TextColumn(width="large"),
                                           "연결 자료 · 제목|주소": st.column_config.TextColumn(width="large")}, disabled=["id"])
    shared = st.text_input("수업안을 함께 사용할 교사 아이디 · 쉼표 구분", value=", ".join(plan.get("shared_teacher_ids", [])), key=prefix + "_shared",
                           disabled=bool(selected) and plan.get("owner_id") != user["id"])
    reason = st.text_input("수업안 변경 이유", key=prefix + "_reason")
    preview_key = prefix + "_preview"
    if st.button("변경 영향 미리 보기" if selected else "새 수업안 미리 보기", key=prefix + "_preview_button", width="stretch"):
        try:
            lessons = _edited_lessons(edited, plan)
            if not title.strip() or not subject.strip() or not lessons or not reason.strip():
                raise ValueError("수업안 이름·과목·한 개 이상의 차시·변경 이유를 입력해 주세요.")
            impacts = service.preview_curriculum_changes(selected, lessons) if selected else []
            st.session_state[preview_key] = {"title": title, "subject": subject, "lessons": lessons,
                                             "shared_teacher_ids": [value.strip() for value in shared.split(",") if value.strip()],
                                             "reason": reason, "impacts": impacts}
        except ValueError as error:
            st.warning(str(error))
        except Exception as error:
            _error(error)
    preview = st.session_state.get(preview_key)
    if preview:
        st.markdown("#### 저장 전 확인")
        st.write(f"{preview['title']} · {preview['subject']} · {len(preview['lessons'])}차시")
        if preview["impacts"]:
            st.dataframe(pd.DataFrame(preview["impacts"]).rename(columns={"title": "수업", "added": "추가 차시", "removed": "제외 차시", "completed_removed": "완료 기록이 있는 제외 차시"}), hide_index=True, width="stretch", column_config={"course_id": None})
        else:
            st.caption("현재 영향을 확인할 담당 수업이 없어요.")
        st.info("저장하면 공통 수업안만 변경돼요. 운영 중인 반은 수업 설정에서 변경 영향을 확인하고 개별 적용해 주세요.")
        confirm = st.checkbox("표시된 변경안과 영향을 확인했습니다.", key=prefix + "_confirm")
        if st.button("확인한 수업안 저장", key=prefix + "_commit", disabled=not confirm, type="primary", width="stretch"):
            if selected:
                fields = ("title", "lessons", "shared_teacher_ids") if plan.get("owner_id") == user["id"] else ("title", "lessons")
                _save(user, lambda: service.update_curriculum(selected,
                                                             {part: preview[part] for part in fields},
                                                             expected_version=expected_version, reason=preview["reason"]),
                      "공통 수업안을 저장했어요. 각 반의 일정·완료 기록은 자동 변경하지 않습니다.", clear_prefix=prefix)
            else:
                _save(user, lambda: service.create_curriculum(title=preview["title"], subject=preview["subject"],
                                                              lessons=preview["lessons"], shared_teacher_ids=preview["shared_teacher_ids"]),
                      "새 공통 수업안을 GitHub에 저장했어요. 내 수업에서 적용할 수 있습니다.", clear_prefix=prefix)


def _storage_notice(store, user):
    if not _teacher(user):
        return
    if getattr(store, "storage_format", "") == "json":
        st.caption("저장 방식 · 비공개 GitHub에 JSON으로 저장 · 내용 암호화 없음")
        legacy = getattr(store, "legacy_data_present", None)
        if callable(legacy) and legacy() is True:
            st.info("이전 암호화 기록이 별도로 보존되어 있습니다. 현재는 새 JSON 저장 공간을 표시합니다. "
                    "이전 기록을 열려면 적용 안내의 기존 기록 열기 절차를 확인하세요.")


def page(user):
    """Entry point used by app.py; login and existing navigation stay shared."""
    ui.page_title("클래스룸", "수업의 계획부터 활동·제출·피드백까지 한곳에서 이어가요." if _teacher(user) else "")
    try:
        from classroom_core import ClassroomService, get_store
        service = ClassroomService(get_store(), user)
        flash = st.session_state.pop(_key(user, "flash"), None)
        if flash:
            st.success(flash)
        if st.button("저장된 기록 다시 불러오기", key=_key(user, "reload")):
            invalidate = getattr(service.store, "invalidate", None)
            if callable(invalidate):
                invalidate()
            st.rerun()
        courses = service.list_courses()
        _storage_notice(service.store, user)
        sections = ["전체 학급 진도", "내 수업", "공통 수업안"] if _teacher(user) else ["오늘 할 일", "내 수업"]
        section_key = _key(user, "section")
        pending = st.session_state.pop(_key(user, "next_section"), None)
        if pending in sections:
            st.session_state[section_key] = pending
        if st.session_state.get(section_key) not in sections:
            st.session_state.pop(section_key, None)
        selected = st.segmented_control("클래스룸 메뉴", sections, default=sections[0], key=section_key) or sections[0]
        if selected == "전체 학급 진도":
            _dashboard(service, courses, user)
        elif selected == "공통 수업안":
            _curricula(service, user)
        elif selected == "오늘 할 일":
            _join_course(service, user, courses)
            approved = [course for course in courses if course.get("membership_status") != "pending"]
            try:
                from views.classroom_work import render_today
                render_today(service, approved, user)
            except Exception as error:
                _error(error)
            st.markdown("### 내 수업")
            if not approved:
                st.info("참여한 수업이 아직 없어요. 위의 ‘수업 참여하기’에 담당 교사가 알려 준 6자리 승인코드를 입력해 주세요.")
            for course in courses:
                if course.get("membership_status") == "pending":
                    st.info(f"참여 승인 대기 · {_name(course)}")
                    continue
                if st.button(_name(course), key=_key(user, f"today_course_{course['id']}"), width="stretch"):
                    _open_course(user, course["id"])
        else:
            _my_courses(service, courses, user)
    except Exception as error:
        _error(error)
        st.caption("설정 누락은 배포 Secrets를 확인하고, 연결 오류는 네트워크 복구 후 다시 불러오세요. 비밀번호·토큰·암호화 키를 채팅에 붙여 넣지 마세요.")
