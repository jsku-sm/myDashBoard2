"""Teacher-facing content upload, seven-class distribution and saved checklist."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import streamlit as st

from config import SUBJECTS, TZ
from classroom_core import ClassroomError, ValidationError
from classroom_core.teaching_board import CLASSES, TeachingBoardService, board_model
from views.classroom_progress_grid import render_grid


def _key(user, part):
    return f"teaching_board_{user['id']}_{part}"


def _choose(label, options, key, *, format_func=str):
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    return st.selectbox(label, options, key=key, format_func=format_func)


def _error(exc):
    if isinstance(exc, ClassroomError):
        st.error(str(exc))
    else:
        st.error("저장을 확인하지 못했습니다. 작성 내용을 유지하고 다시 시도하세요.")


def handle_event(board, event, model, actual_date):
    """Validate the displayed cell on the server, then use fresh authorization/CAS."""
    if not isinstance(event, dict):
        raise ValidationError("체크 요청을 확인하세요.")
    if event.get("type") != "toggle":
        raise ValidationError("지원하지 않는 진도 요청입니다.")
    found = next((cell for row in model["rows"] for cell in row["cells"].values()
                  if cell["course_id"] == event.get("course_id") and cell["lesson_id"] == event.get("lesson_id")), None)
    if not found or found.get("disabled"):
        raise ValidationError("현재 화면에서 수정할 수 없는 수업내용입니다.")
    return board.set_completed(event["course_id"], event["lesson_id"], event.get("completed"),
                               expected_version=event.get("expected_version"), actual_date=actual_date)


def _mapping(service, scoped, user, term, subject, kind, scope_key):
    choices = {cls: [course for course in scoped if course.get("class_name") == cls] for cls in CLASSES}
    mapping = {}
    with st.expander("학급별 수업 연결 · 처음 사용할 때 설정", expanded=not scoped):
        st.caption("1-1반~1-7반을 모두 표시합니다. 수업이 여러 개면 이 화면에서 비교할 수업을 반마다 선택하세요.")
        for cls in CLASSES:
            options = choices[cls]
            if len(options) == 1:
                mapping[cls] = options[0]
                st.caption(f"{cls}반 → {options[0]['title']}")
            elif len(options) > 1:
                by_id = {course["id"]: course for course in options}
                chosen = _choose(f"{cls}반 수업 선택", [""] + list(by_id), _key(user, f"course_{scope_key}_{cls}"),
                                 format_func=lambda cid: by_id[cid]["title"] if cid else "수업을 선택하세요")
                if chosen:
                    mapping[cls] = by_id[chosen]
            else:
                st.caption(f"{cls}반 → 수업 미개설")
        missing = [cls for cls in CLASSES if not choices[cls]]
        if missing:
            setup_key = _key(user, f"setup_classes_{scope_key}")
            if setup_key in st.session_state:
                st.session_state[setup_key] = [cls for cls in st.session_state[setup_key] if cls in missing]
            selected = st.multiselect("새로 개설할 학급", missing, default=missing, key=setup_key)
            st.caption("개설할 때 학생 계정을 만들거나 강제로 가입시키지 않습니다. 기존 수업의 구성원·승인코드를 사용하세요.")
            if st.button("선택 학급 수업 개설", key=_key(user, f"setup_{scope_key}"), type="primary"):
                try:
                    if not selected:
                        raise ValidationError("개설할 학급을 선택하세요.")
                    with st.spinner("수업을 저장하는 중…"):
                        for cls in selected:
                            # A partial request can be retried without duplicating already created courses.
                            existing = service.list_courses()
                            if any(c.get("term") == term and c.get("subject") == subject and c.get("kind") == kind
                                   and c.get("class_name") == cls and not c.get("archived") for c in existing):
                                continue
                            service.create_course(f"{subject} · {cls}반", term, subject, kind=kind, class_name=cls)
                    st.session_state[_key(user, "success")] = "선택한 학급의 수업을 저장했습니다. 자료를 등록하고 반별로 배포하세요."
                    st.rerun()
                except Exception as exc:
                    _error(exc)
                    st.caption("일부 수업이 저장됐다면 다시 시도할 때 그대로 재사용합니다.")
    return mapping


def _uploads(board, mapping, user, term, subject, scope_key, empty):
    epoch_key = _key(user, f"upload_epoch_{scope_key}")
    epoch = st.session_state.get(epoch_key, 0)
    prefix = _key(user, f"upload_{scope_key}_{epoch}")
    request_id = st.session_state.setdefault(prefix + "_request", uuid.uuid4().hex)
    if prefix + "_classes" in st.session_state:
        st.session_state[prefix + "_classes"] = [cls for cls in st.session_state[prefix + "_classes"] if cls in mapping]
    with st.expander("＋ 수업내용 업로드 · 반별 배포", expanded=empty):
        st.caption("제목을 한 줄의 수업내용으로 등록합니다. 파일은 한 번 보관하고 선택한 반의 ‘수업·자료’에 배포합니다.")
        with st.form(prefix, clear_on_submit=False):
            title = st.text_input("수업내용", max_chars=160, placeholder="예: 원의 방정식 — 중심과 반지름 찾기", key=prefix + "_title")
            body = st.text_area("수업 설명 · 선택", max_chars=10000, key=prefix + "_body")
            url = st.text_input("자료 링크 · 선택", placeholder="https://...", key=prefix + "_url")
            files = st.file_uploader("수업 파일 업로드 · 최대 2개 / 합계 2 MiB",
                                     type=["pdf", "png", "jpg", "jpeg", "txt", "docx", "hwp", "hwpx"],
                                     accept_multiple_files=True, key=prefix + "_files")
            targets = st.multiselect("배포할 학급", list(mapping), format_func=lambda cls: cls + "반",
                                     key=prefix + "_classes", help="전체 7개 반 또는 필요한 반만 선택할 수 있습니다.")
            a, b = st.columns(2)
            publish = a.form_submit_button("등록하고 선택 반에 배포", type="primary", width="stretch")
            draft = b.form_submit_button("수업내용만 저장", width="stretch")
            st.caption("저장만 한 자료는 학생에게 보이지 않습니다. 배포해도 완료 체크는 자동으로 켜지지 않습니다.")
        if publish or draft:
            try:
                if publish and not targets:
                    raise ValidationError("배포할 반을 선택하세요. 반이 없으면 위에서 수업을 먼저 개설하세요.")
                with st.spinner("수업내용을 GitHub에 저장하는 중…"):
                    content = board.create(title, term=term, subject=subject, body=body, url=url,
                                           files=[{"filename": item.name, "data": item.getvalue()} for item in (files or [])],
                                           request_id=request_id)
                    st.session_state[prefix + "_saved_id"] = content["id"]
                    if publish:
                        board.distribute(content["id"], [mapping[cls]["id"] for cls in targets])
                st.session_state[epoch_key] = epoch + 1
                st.session_state[_key(user, "selected")] = "board:" + content["id"]
                st.session_state[_key(user, "success")] = (
                    "수업내용 저장·배포 완료: " + ", ".join(cls + "반" for cls in targets)
                    if publish else "수업내용을 저장했습니다. 제목을 눌러 나중에 배포할 반을 선택할 수 있습니다.")
                st.rerun()
            except Exception as exc:
                _error(exc)
                if st.session_state.get(prefix + "_saved_id"):
                    st.warning("수업내용 원본은 저장됐지만 배포를 완료하지 못했습니다. 같은 버튼으로 재시도하거나 아래 자료 상세에서 다시 배포하세요.")


def _detail(board, service, model, contents, mapping, user):
    if not model["rows"]:
        return
    rows = {row["id"]: row for row in model["rows"]}
    selected_key = _key(user, "selected")
    options = [""] + list(rows)
    chosen = _choose("자료 확인·반별 배포할 수업내용", options, selected_key,
                     format_func=lambda rid: rows[rid]["title"] if rid else "표의 수업내용 제목을 누르거나 여기에서 선택하세요")
    if not chosen:
        return
    row = rows[chosen]
    entries = {entry["id"]: entry for entry in contents}
    entry = entries.get(row.get("content_id"))
    with st.container(border=True):
        st.markdown("#### " + row["title"])
        if entry:
            if entry.get("body"):
                st.write(entry["body"])
            if entry.get("url"):
                st.link_button("연결 자료 열기", entry["url"])
            for index, item in enumerate(entry.get("attachments", [])):
                saved = board.download(entry["id"], index)
                st.download_button("자료 내려받기 · " + item["filename"], saved["data"], file_name=saved["filename"],
                                   mime=saved["mime"], key=_key(user, f"download_{entry['id']}_{index}"))
            published = [cls for cls, course in mapping.items() if course["id"] in entry.get("published_course_ids", [])]
            st.caption("배포 완료: " + (", ".join(cls + "반" for cls in published) or "없음 · 교사만 확인"))
            targets_key = _key(user, "targets_" + entry["id"])
            if targets_key in st.session_state:
                st.session_state[targets_key] = [cls for cls in st.session_state[targets_key] if cls in mapping]
            with st.form(_key(user, "distribution_" + entry["id"])):
                targets = st.multiselect("추가 배포할 학급", list(mapping), format_func=lambda cls: cls + "반", key=targets_key)
                clicked = st.form_submit_button("선택 반에 배포", type="primary")
                st.caption("추가 배포 방식입니다. 이미 배포한 반을 선택해도 자료가 중복되거나 진도가 초기화되지 않습니다.")
            if clicked:
                try:
                    with st.spinner("선택 반에 배포하는 중…"):
                        board.distribute(entry["id"], [mapping[cls]["id"] for cls in targets])
                    st.session_state[_key(user, "success")] = "배포 완료: " + ", ".join(cls + "반" for cls in targets)
                    st.rerun()
                except Exception as exc:
                    _error(exc)
        else:
            st.caption("기존 수업안의 차시입니다. 아래에서 반별 연결 자료와 일정·메모를 확인할 수 있습니다.")
        if row["cells"]:
            cls = _choose("반별 자료·진도 상세", list(row["cells"]),
                          _key(user, "detail_class_" + hashlib.sha256(chosen.encode()).hexdigest()[:12]),
                          format_func=lambda name: name + "반")
            cell = row["cells"][cls]
            course = service.get_course(cell["course_id"])
            lesson = next(item for item in course["lessons"] if item["id"] == cell["lesson_id"])
            from views.classroom import _resources, _open_course
            if not entry:
                _resources(service, course, lesson, user, _key(user, "detail_resources_" + course["id"]))
            record = course.get("lesson_records", {}).get(lesson["id"], {})
            st.caption(f"계획일: {record.get('planned_date') or '미설정'} · 실제 수업일: {record.get('actual_date') or '미완료'}")
            if st.button("이 반의 달력·진도 상세 열기", key=_key(user, "open_" + course["id"])):
                _open_course(user, course["id"], lesson["id"])


def render_board(service, courses, user):
    service.require_teacher()
    st.markdown("### 전체 학급 진도")
    success = st.session_state.pop(_key(user, "success"), None)
    failure = st.session_state.pop(_key(user, "error"), None)
    if success:
        st.success(success)
    if failure:
        st.error(failure)
    owned = [course for course in courses if user["id"] in course.get("teacher_ids", []) and not course.get("archived")]
    today = datetime.now(TZ).date()
    terms = sorted({course.get("term", "") for course in owned if course.get("term")}, reverse=True)
    default_term = f"{today.year}-{1 if today.month <= 7 else 2}"
    if not terms:
        terms = [default_term]
    a, b, c, d = st.columns([1.1, 1.1, 1, 1.2])
    with a:
        term = _choose("학기", terms + ["새 학기 입력"], _key(user, "term"))
        if term == "새 학기 입력":
            term = st.text_input("학기 이름", value=default_term, max_chars=160, key=_key(user, "custom_term")).strip()
    with b:
        subjects = sorted(set(SUBJECTS) | {course["subject"] for course in owned if course.get("subject")})
        subject = _choose("과목", subjects, _key(user, "subject"))
    with c:
        kind = _choose("수업 구분", ["regular", "after_school"], _key(user, "kind"),
                       format_func=lambda value: "정규 수업" if value == "regular" else "방과후 수업")
    with d:
        actual_date = st.date_input("체크 시 실제 수업일", value=today, max_value=today, key=_key(user, "actual_date"))
    st.caption("체크하면 선택한 날짜로 ‘수업 완료’를 저장하고, 해제하면 완료 기록을 취소합니다. 기존 메모·계획일은 유지됩니다.")
    if not term:
        st.info("학기를 입력하세요.")
        return
    scope_key = hashlib.sha256(json_encode(term, subject, kind).encode()).hexdigest()[:12]
    scoped = [course for course in owned if course.get("term") == term and course.get("subject") == subject and course.get("kind") == kind]
    mapping = _mapping(service, scoped, user, term, subject, kind, scope_key)
    board = TeachingBoardService(service)
    contents = board.contents(term, subject)
    model = board_model(mapping, contents, today=today.isoformat())
    _uploads(board, mapping, user, term, subject, scope_key, empty=not model["rows"])
    event = render_grid(model, term=term, subject=subject, selected=st.session_state.get(_key(user, "selected"), ""),
                        key=_key(user, "grid_" + scope_key))
    if event:
        # v2 triggers reset after consumption; the bounded event list also guards replay.
        handled = st.session_state.setdefault(_key(user, "handled"), [])
        eid = event.get("event_id")
        if isinstance(eid, str) and 0 < len(eid) < 150 and eid not in handled:
            handled.append(eid)
            del handled[:-40]
            try:
                if event.get("type") == "open":
                    if event.get("row_id") not in {row["id"] for row in model["rows"]}:
                        raise ValidationError("현재 화면의 수업내용을 다시 선택하세요.")
                    st.session_state[_key(user, "selected")] = event["row_id"]
                else:
                    with st.spinner("수업 완료 여부를 저장하는 중…"):
                        handle_event(board, event, model, actual_date.isoformat())
                    st.session_state[_key(user, "success")] = "수업 완료 기록을 저장했습니다." if event.get("completed") else "수업 완료 체크를 해제했습니다. 계획일·메모는 그대로 유지됩니다."
            except Exception as exc:
                st.session_state[_key(user, "error")] = str(exc) if isinstance(exc, ClassroomError) else "저장 결과를 확인하지 못했습니다. 저장된 상태를 다시 확인하고 재시도하세요."
            st.rerun()
    _detail(board, service, model, contents, mapping, user)
    if model["rows"]:
        from views.classroom import _csv
        export = []
        for row in model["rows"]:
            values = {"수업내용": row["title"]}
            for cls in CLASSES:
                cell = row["cells"].get(cls)
                values[cls + "반"] = "미배포 / 미적용" if not cell else cell.get("reason") or ("수업 완료" if cell["completed"] else "미수업")
            export.append(values)
        st.download_button("전체 학급 진도표 내려받기", _csv(export), "classroom-seven-class-progress.csv", "text/csv",
                           key=_key(user, "export"))


def json_encode(*parts):
    import json
    return json.dumps(parts, ensure_ascii=False)
