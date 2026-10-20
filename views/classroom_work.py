"""Classroom work views inside the existing dashboard login/navigation."""
from __future__ import annotations

import copy
import base64
from datetime import datetime
import hashlib
import io
import json
import csv
import uuid
from zoneinfo import ZoneInfo

import streamlit as st

from classroom_core.store import ClassroomError
from classroom_core.work import WorkService

TZ = ZoneInfo("Asia/Seoul")
KINDS = {"assignment": "과제", "quiz": "간단 퀴즈", "performance": "수행평가"}
METHODS = {"text": "앱 안에서 답변", "file": "파일·사진"}
POLICIES = {"requested": "교사의 수정 요청 후", "always": "언제든 재제출", "never": "재제출 불가"}
DISABLED_ACTIVITY = "이전 외부 활동 연결은 비활성화되었습니다. 새 자료나 과제를 등록하세요."


def _work(service):
    return service if isinstance(service, WorkService) else WorkService(service)


def _key(*parts):
    return "cw_" + hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


def _teacher(service, course):
    user = _work(service).service.actor()
    return user.get("role") == "teacher" and user["id"] in course.get("teacher_ids", [])


def _user(service):
    return _work(service).service.actor()


def _when(instant):
    if not instant:
        return "미설정"
    return datetime.fromisoformat(instant).astimezone(TZ).strftime("%Y-%m-%d %H:%M") + " (한국 시간)"


def _uploads(items):
    return [dict(filename=item.name, data=item.getvalue()) for item in (items or [])]


def _dedup_files(files):
    output, seen = [], set()
    for item in files:
        raw = item.get("data")
        if raw is None:
            raw = base64.b64decode(item.get("content", ""))
        identity = (item.get("filename"), hashlib.sha256(raw).hexdigest())
        if identity not in seen:
            output.append(item)
            seen.add(identity)
    return output


def _notice_error(error):
    st.error(str(error))
    st.caption("입력 내용을 유지했습니다. 연결과 권한을 확인한 뒤 같은 저장 버튼으로 다시 시도하세요.")


def _publication(key, record=None):
    record = record or {}
    published = st.checkbox("학생에게 공개", value=record.get("published", False), key=key + "_published")
    scheduled = st.checkbox("공개 시작 시각 지정", value=bool(record.get("publish_at")), key=key + "_scheduled")
    instant = None
    if scheduled:
        current = datetime.fromisoformat(record["publish_at"]).astimezone(TZ) if record.get("publish_at") else datetime.now(TZ)
        left, right = st.columns(2)
        day = left.date_input("공개일", current.date(), key=key + "_pub_day")
        clock = right.time_input("공개 시각 · 한국 시간", current.time().replace(tzinfo=None), key=key + "_pub_time")
        instant = datetime.combine(day, clock, TZ).isoformat()
        st.caption("예약 시각 이후 앱에서 자료를 읽을 때 공개됩니다. 앱이 꺼진 동안 외부 알림을 발송하지 않습니다.")
    return published, instant


def _targets(work, course, key, selected=()):
    members = work.service.members(course["id"])
    mapping = {m["id"]: m for m in members}
    individual = st.checkbox("특정 학생에게만 배부", value=bool(selected), key=key + "_individual")
    if not individual:
        st.caption(f"배부 대상: 승인된 참여 학생 전체 ({len(members)}명)")
        return []
    targets = st.multiselect("배부할 학생 확인", list(mapping), default=[i for i in selected if i in mapping],
                             format_func=lambda sid: f"{mapping[sid]['class']} · {mapping[sid]['name']} · {sid}", key=key + "_targets")
    if not targets:
        st.warning("특정 학생 배부를 선택했습니다. 한 명 이상 선택해야 저장할 수 있습니다.")
        return None
    return targets


def render_stream(service, course, user=None):
    work = _work(service)
    teacher = _teacher(work, course)
    archived = course.get("archived", False)
    st.subheader("스트림")
    if teacher and not archived:
        with st.expander("공지 작성"):
            _post_form(work, course)
    posts = work.posts(course["id"])
    if not posts:
        st.info("아직 공개된 공지가 없습니다." if not teacher else "아직 등록한 공지가 없습니다. 공지를 작성해 주세요.")
    for post in posts:
        key = _key("post", course["id"], post["id"], _user(work)["id"])
        with st.container(border=True):
            st.markdown(("📌 " if post.get("pinned") else "") + "**" + post["title"] + "**")
            st.write(post["body"])
            st.caption(("공개" if post.get("published") else "비공개 초안") + " · 공개 시작 " + _when(post.get("publish_at")))
            for comment in post.get("comments", []):
                st.write(f"{comment['author_id']} · {comment['body']}")
            if post.get("comments_allowed") and course.get("comments_enabled", True) and not archived:
                with st.form(key + "_comment_form", clear_on_submit=False):
                    text = st.text_input("댓글", key=key + "_comment")
                    clicked = st.form_submit_button("댓글 저장")
                if clicked:
                    token = st.session_state.setdefault(key + "_comment_request", uuid.uuid4().hex)
                    try:
                        work.add_comment(course["id"], post["id"], text, token)
                    except ClassroomError as error:
                        _notice_error(error)
                    else:
                        st.session_state.pop(key + "_comment_request", None)
                        st.success("댓글을 GitHub에 저장했습니다.")
            if teacher and not archived:
                with st.expander("공지 수정·고정·공개 설정"):
                    _post_form(work, course, post)
    _render_questions(work, course)
    render_records(work, course, user)


def _post_form(work, course, post=None):
    post = post or {}
    key = _key("post_form", course["id"], post.get("id", "new"), _user(work)["id"])
    title = st.text_input("공지 제목", post.get("title", ""), max_chars=160, key=key + "_title")
    body = st.text_area("공지 내용", post.get("body", ""), max_chars=10000, key=key + "_body")
    pinned = st.checkbox("상단 고정", value=post.get("pinned", False), key=key + "_pinned")
    comments = st.checkbox("댓글 허용", value=post.get("comments_allowed", True), key=key + "_comments")
    published, instant = _publication(key, post)
    if st.button("공지 저장", key=key + "_save", width="stretch"):
        try:
            work.save_post(course["id"], title, body, post_id=post.get("id"), pinned=pinned,
                           comments_allowed=comments, published=published, publish_at=instant)
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("공지를 GitHub에 저장했습니다.")
            st.rerun()


def _render_questions(work, course):
    teacher = _teacher(work, course)
    archived = course.get("archived", False)
    st.subheader("질문")
    if not archived and (teacher or course.get("comments_enabled", True)):
        key = _key("question_new", course["id"], _user(work)["id"])
        with st.expander("질문 작성"):
            body = st.text_area("질문 내용", max_chars=5000, key=key + "_body")
            visibility = st.radio("질문 공개 범위", ["private", "course"],
                                  format_func=lambda v: "나와 담당 교사만" if v == "private" else "승인된 수업 참여자", key=key + "_visibility")
            if st.button("질문 저장", key=key + "_save"):
                request_id = st.session_state.setdefault(key + "_request", uuid.uuid4().hex)
                try:
                    work.save_question(course["id"], body, visibility=visibility, question_id=request_id)
                except ClassroomError as error:
                    _notice_error(error)
                else:
                    st.session_state.pop(key + "_request", None)
                    st.success("질문을 GitHub에 저장했습니다.")
                    st.rerun()
    questions = work.questions(course["id"])
    if not questions:
        st.caption("아직 확인할 질문이 없습니다. 비공개 질문은 작성자와 담당 교사만 볼 수 있습니다.")
    for question in questions:
        key = _key("question", course["id"], question["id"], _user(work)["id"])
        with st.container(border=True):
            st.caption(("해결됨" if question.get("resolved") else "미해결") + " · " +
                       ("수업 참여자 공개" if question["visibility"] == "course" else "작성자·담당 교사만"))
            st.write(question["body"])
            if question.get("answer"):
                st.write("교사 답변: " + question["answer"])
            if teacher and not archived:
                answer = st.text_area("답변", question.get("answer", ""), key=key + "_answer")
                resolved = st.checkbox("해결 표시", question.get("resolved", False), key=key + "_resolved")
                if st.button("답변·해결 상태 저장", key=key + "_save"):
                    try:
                        work.answer_question(course["id"], question["id"], answer, resolved=resolved)
                    except ClassroomError as error:
                        _notice_error(error)
                    else:
                        st.rerun()


def render_materials(service, course, user=None):
    work = _work(service)
    teacher = _teacher(work, course)
    st.subheader("수업·자료")
    if teacher and not course.get("archived"):
        with st.expander("자료 등록 · 파일만으로도 배부할 수 있습니다"):
            _material_form(work, course)
    materials = work.materials(course["id"])
    if not materials:
        st.info("아직 확인할 자료가 없습니다.")
    for material in materials:
        with st.container(border=True):
            _material_body(work, course, material, _key("material", material["id"], _user(work)["id"]))
            if teacher and not course.get("archived") and not material.get("disabled"):
                with st.expander("자료 수정·공개 설정"):
                    _material_form(work, course, material)


def _material_body(work, course, material, key):
    st.markdown("**" + material["title"] + "**")
    st.caption(material.get("unit", "") + " · " + ("공개" if material.get("published") else "비공개 초안"))
    if material.get("body"):
        st.write(material["body"])
    if material.get("url"):
        st.link_button("연결 원본 자료 열기", material["url"], width="stretch")
        st.caption("외부 원본 자료입니다. 외부 서비스의 열람 권한이 별도로 필요할 수 있습니다.")
    for index, attachment in enumerate(material.get("attachments", [])):
        # Resolve again for every download render; no public raw URL exists.
        saved = work.download_material(course["id"], material["id"], index)
        st.download_button("파일 내려받기 · " + attachment["filename"], saved["data"],
                           file_name=saved["filename"], mime=saved["mime"], key=key + "_file_" + str(index),
                           width="stretch")
    if material.get("disabled") or material.get("activity_id"):
        st.info(material.get("disabled_reason") or DISABLED_ACTIVITY)
    st.caption("자료 열기와 내려받기는 수업 진도를 변경하지 않습니다.")


def _material_form(work, course, material=None):
    material = material or {}
    if material.get("disabled") or material.get("activity_id"):
        st.info(material.get("disabled_reason") or DISABLED_ACTIVITY)
        return
    key = _key("material_form", course["id"], material.get("id", "new"), _user(work)["id"])
    title = st.text_input("자료 제목", material.get("title", ""), max_chars=160, key=key + "_title")
    unit = st.text_input("단원·주제", material.get("unit", ""), max_chars=160, key=key + "_unit")
    body = st.text_area("자료 설명", material.get("body", ""), max_chars=10000, key=key + "_body")
    url = st.text_input("외부 자료 또는 기존 Google Drive 링크 · 선택", material.get("url", ""), key=key + "_url")
    uploads = st.file_uploader("배부할 원본 파일 · 최대 2개, 합계 2 MiB", accept_multiple_files=True,
                               type=["pdf", "png", "jpg", "jpeg", "txt", "docx", "hwp", "hwpx"], key=key + "_files")
    keep_files = st.checkbox("기존 첨부 유지", value=True, key=key + "_keep") if material.get("attachments") else False
    targets = _targets(work, course, key, material.get("target_student_ids", []))
    published, instant = _publication(key, material)
    if st.button("배부 대상 확인 후 자료 저장", key=key + "_save", width="stretch"):
        files = _dedup_files((material.get("attachments", []) if keep_files else []) + _uploads(uploads))
        try:
            work.save_material(course["id"], title, body=body, unit=unit, url=url, files=files,
                               material_id=material.get("id"), published=published,
                               publish_at=instant, target_student_ids=targets)
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("자료와 배부 설정을 GitHub에 저장했습니다.")
            st.rerun()


def render_assignments(service, course, user=None):
    work = _work(service)
    teacher = _teacher(work, course)
    st.subheader("과제·퀴즈·수행평가")
    if teacher and not course.get("archived"):
        with st.expander("새 과제·퀴즈·수행평가 등록"):
            _assignment_form(work, course)
    assignments = work.assignments(course["id"])
    if not assignments:
        st.info("아직 확인할 과제가 없습니다.")
        return
    mapping = {a["id"]: a for a in assignments}
    key = _key("assignment_picker", course["id"], _user(work)["id"])
    assignment_id = st.selectbox("과제 선택", list(mapping), format_func=lambda aid: mapping[aid]["title"], key=key)
    assignment = mapping[assignment_id]
    _assignment_body(work, course, assignment, _key("assignment_body", assignment_id, _user(work)["id"]))
    if assignment.get("disabled") or assignment.get("activity_id"):
        return
    if teacher:
        if not course.get("archived"):
            with st.expander("과제 수정·배부 설정"):
                _assignment_form(work, course, assignment)
            with st.expander("다른 수업에 안내·평가 기준 복사"):
                courses = [c for c in work.service.list_courses() if c["id"] != course["id"] and not c.get("archived")]
                mapping_courses = {c["id"]: c for c in courses}
                if mapping_courses:
                    target = st.selectbox("복사할 수업", list(mapping_courses), format_func=lambda cid: mapping_courses[cid]["title"], key=key + "_copy_target")
                    st.caption("안내와 평가 기준을 비공개 새 과제로 복사합니다. 학생 답안·점수·개인 댓글과 마감일은 복사하지 않습니다.")
                    if st.button("양식 복사", key=key + "_copy"):
                        try:
                            work.clone_assignment(course["id"], assignment_id, target)
                        except ClassroomError as error:
                            _notice_error(error)
                        else:
                            st.success("대상 수업에 비공개 과제 양식을 저장했습니다.")
        _teacher_submissions(work, course, assignment)
    else:
        _student_assignment(work, course, assignment)


def _assignment_body(work, course, assignment, key):
    st.markdown("**" + KINDS[assignment["kind"]] + " · " + assignment["title"] + "**")
    st.write(assignment["instructions"])
    st.caption("마감 " + _when(assignment.get("due_at")) + " · " +
               ("늦은 제출 허용" if assignment["allow_late"] else "늦은 제출 불가") + " · " + POLICIES[assignment["resubmit_policy"]])
    st.caption("무점수" if assignment["max_points"] is None else f"배점 {assignment['max_points']:g}점")
    if assignment.get("rubric"):
        st.dataframe([dict(평가요소=r["label"], 배점=r.get("max_points")) for r in assignment["rubric"]],
                     hide_index=True, width="stretch")
    materials = {r["id"]: r for r in work.materials(course["id"])}
    for mid in assignment.get("material_ids", []):
        if mid in materials:
            with st.expander("연결 자료 · " + materials[mid]["title"]):
                _material_body(work, course, materials[mid], key + "_material_" + mid)
    if assignment.get("disabled") or assignment.get("activity_id"):
        st.info(assignment.get("disabled_reason") or DISABLED_ACTIVITY)


def _assignment_form(work, course, assignment=None):
    assignment = assignment or {}
    if assignment.get("disabled") or assignment.get("activity_id"):
        st.info(assignment.get("disabled_reason") or DISABLED_ACTIVITY)
        return
    key = _key("assignment_form", course["id"], assignment.get("id", "new"), _user(work)["id"])
    title = st.text_input("과제 제목", assignment.get("title", ""), max_chars=160, key=key + "_title")
    instructions = st.text_area("안내", assignment.get("instructions", ""), max_chars=10000, key=key + "_instructions")
    kind = st.selectbox("유형", list(KINDS), index=list(KINDS).index(assignment.get("kind", "assignment")), format_func=KINDS.get, key=key + "_kind")
    methods = st.multiselect("허용할 제출 방식", list(METHODS),
                             default=[method for method in assignment.get("methods", ["text"]) if method in METHODS],
                             format_func=METHODS.get, key=key + "_methods")
    graded = st.checkbox("점수형 평가", value=assignment.get("max_points") is not None, key=key + "_graded")
    maximum = st.number_input("전체 배점", min_value=0.0, max_value=100000.0,
                              value=float(assignment["max_points"] if assignment.get("max_points") is not None else 100),
                              key=key + "_maximum") if graded else None
    rubric_text = st.text_area("평가 기준 · 한 줄에 평가 요소 | 배점 (무점수는 요소만)",
                               "\n".join(r["label"] + (" | " + str(r["max_points"]) if r.get("max_points") is not None else "") for r in assignment.get("rubric", [])),
                               key=key + "_rubric")
    has_due = st.checkbox("마감 설정", value=bool(assignment.get("due_at")), key=key + "_has_due")
    due_at = None
    if has_due:
        current = datetime.fromisoformat(assignment["due_at"]).astimezone(TZ) if assignment.get("due_at") else datetime.now(TZ).replace(hour=23, minute=59)
        left, right = st.columns(2)
        due_day = left.date_input("마감일", current.date(), key=key + "_due_day")
        due_time = right.time_input("마감 시각 · 한국 시간", current.time().replace(tzinfo=None), key=key + "_due_time")
        due_at = datetime.combine(due_day, due_time, TZ).isoformat()
    late = st.checkbox("늦은 제출 허용", value=assignment.get("allow_late", True), key=key + "_late")
    policy = st.selectbox("재제출 정책", list(POLICIES), index=list(POLICIES).index(assignment.get("resubmit_policy", "requested")), format_func=POLICIES.get, key=key + "_policy")
    materials = work.materials(course["id"])
    mapping = {m["id"]: m for m in materials}
    material_ids = st.multiselect("연결할 보기 자료", list(mapping), default=[m for m in assignment.get("material_ids", []) if m in mapping],
                                  format_func=lambda mid: mapping[mid]["title"], key=key + "_materials")
    targets = _targets(work, course, key, assignment.get("target_student_ids", []))
    published, instant = _publication(key, assignment)
    if st.button("대상·공개 여부 확인 후 과제 저장", key=key + "_save", width="stretch"):
        try:
            rubric = []
            for line in rubric_text.splitlines():
                if not line.strip():
                    continue
                fields = line.rsplit("|", 1)
                rubric.append(dict(label=fields[0].strip(), max_points=float(fields[1].strip()) if len(fields) == 2 else None))
            work.save_assignment(course["id"], title, instructions, assignment_id=assignment.get("id"), kind=kind,
                                 methods=methods, max_points=maximum, rubric=rubric, due_at=due_at,
                                 publish_at=instant, published=published, allow_late=late, resubmit_policy=policy,
                                 target_student_ids=targets, material_ids=material_ids)
        except ValueError:
            st.error("평가 기준의 배점은 숫자로 입력하세요.")
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("과제와 배부 설정을 GitHub에 저장했습니다.")
            st.rerun()


def _student_assignment(work, course, assignment):
    record = work.submission(course["id"], assignment["id"])
    if record.get("disabled") or record.get("source") == "disabled":
        st.info(record.get("disabled_reason") or DISABLED_ACTIVITY)
        return
    st.info("내 제출 상태 · " + record["status"])
    if record.get("revision_requested"):
        st.warning("교사의 수정 요청 · " + record.get("revision_reason", ""))
    _submission_history(work, course, assignment, record, _user(work)["id"])
    if course.get("archived"):
        st.caption("학기 보관 중 · 답안은 읽기 전용입니다.")
        return
    key = _key("student_answer", course["id"], assignment["id"], _user(work)["id"])
    flash = st.session_state.pop(key + "_receipt_flash", None)
    if flash:
        st.success(f"제출 완료 · {flash['number']}차 · 제출번호 {flash['submission_id']}")
        st.caption("GitHub 영구 저장 확인 · " + _when(flash["submitted_at"]))
        st.write("첨부: " + (", ".join(f["filename"] for f in flash["attachments"]) or "없음"))
    private_key = key + "_preserved"
    # A non-widget backup survives menu changes and the app's input lock. It is
    # identity scoped and is never described as durable storage.
    remembered = st.session_state.get(private_key) or record.get("draft") or {}
    st.session_state.setdefault(key + "_text", remembered.get("text", ""))
    def remember_text():
        preserved = copy.deepcopy(st.session_state.get(private_key, remembered))
        preserved["text"] = st.session_state.get(key + "_text", "")
        st.session_state[private_key] = preserved
    def remember_files():
        # Widget callbacks run before the full script, including its global
        # lock gate. Capture bytes before a lock/navigation hides the uploader.
        preserved = copy.deepcopy(st.session_state.get(private_key, remembered))
        preserved["pending_uploads"] = _uploads(st.session_state.get(key + "_files") or [])
        st.session_state[private_key] = preserved
    text = st.text_area("내 답안", max_chars=40000, key=key + "_text", on_change=remember_text,
                        disabled="text" not in assignment["methods"])
    uploads = st.file_uploader("파일·사진 첨부 · 최대 2개, 합계 2 MiB", accept_multiple_files=True,
                               type=["pdf", "png", "jpg", "jpeg", "txt", "docx", "hwp", "hwpx"],
                               key=key + "_files", disabled="file" not in assignment["methods"], on_change=remember_files)
    existing = remembered.get("attachments", [])
    selected = st.multiselect("계속 첨부할 임시 보관 파일", list(range(len(existing))), default=list(range(len(existing))),
                              format_func=lambda i: existing[i]["filename"], key=key + "_restored") if existing else []
    pending_uploads = _uploads(uploads) if uploads else remembered.get("pending_uploads", [])
    files = _dedup_files([existing[i] for i in selected] + pending_uploads)
    st.session_state[private_key] = dict(text=text, attachments=files, pending_uploads=pending_uploads)
    if record.get("draft"):
        st.caption("GitHub에 임시 저장됨 · " + _when(record["draft"]["saved_at"]))
    else:
        st.caption("현재 입력은 이 로그인 세션에만 임시 보관됩니다. ‘GitHub 임시 저장’을 누르면 재접속 후에도 불러옵니다.")
    left, right = st.columns(2)
    if left.button("GitHub 임시 저장", key=key + "_draft", width="stretch"):
        try:
            with st.spinner("GitHub에 임시 저장 중…"):
                saved = work.save_draft(course["id"], assignment["id"], text, files,
                                        expected_revision=record.get("draft", {}).get("revision", 0))
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.session_state[private_key] = saved
            st.rerun()
    if right.button("제출 요청", type="primary", key=key + "_submit", width="stretch"):
        signature = hashlib.sha256(json.dumps([text, [f.get("filename") for f in files],
                                               [hashlib.sha256(f.get("data", b"")).hexdigest() if "data" in f else f.get("sha256") for f in files]],
                                              ensure_ascii=False).encode()).hexdigest()
        request_key = key + "_request"
        pending = st.session_state.get(request_key)
        if not pending or pending["signature"] != signature:
            pending = dict(id=uuid.uuid4().hex, signature=signature)
            st.session_state[request_key] = pending
        try:
            with st.spinner("GitHub 영구 저장 확인 중…"):
                receipt = work.submit(course["id"], assignment["id"], pending["id"], text, files)
        except ClassroomError as error:
            _notice_error(error)
        else:
            # Preserve request ID for identical repeat clicks/retries. Editing
            # the answer generates the next operation ID on the next click.
            st.session_state.pop(private_key, None)
            st.session_state[key + "_receipt_flash"] = receipt
            st.rerun()


def _submission_history(work, course, assignment, record, sid):
    for version in reversed(record.get("versions", [])):
        key = _key("history", course["id"], assignment["id"], sid, version["number"], _user(work)["id"])
        with st.expander(f"{version['number']}차 제출 · {_when(version['submitted_at'])}" + (" · 늦은 제출" if version["late"] else "")):
            st.caption("제출번호 " + version["submission_id"] + " · GitHub 저장 확인됨")
            st.write(version["text"])
            for index, attachment in enumerate(version.get("attachments", [])):
                saved = work.download_submission(course["id"], assignment["id"], sid, version["number"], index)
                if saved["mime"].startswith("image/"):
                    st.image(saved["data"], caption=saved["filename"], width="stretch")
                st.download_button("내려받기 · " + saved["filename"], saved["data"], file_name=saved["filename"], mime=saved["mime"], key=key + "_download_" + str(index))
            review = record.get("reviews", {}).get(str(version["number"]), {})
            published = review.get("published", review)
            if published.get("published_at"):
                st.write("공개 피드백: " + published.get("feedback", ""))
                if published.get("score_status") == "final" and published.get("score") is not None:
                    st.write(f"확정 점수: {published['score']:g}점")
                elif published.get("score") is not None:
                    st.caption("점수는 아직 확정 전입니다.")
                if published.get("rubric_scores"):
                    st.dataframe(published["rubric_scores"], hide_index=True, width="stretch")
                if published.get("needs_check"):
                    st.warning("답안 판독 확인이 필요합니다.")


def _teacher_submissions(work, course, assignment):
    members = work.service.members(course["id"])
    members = [m for m in members if not assignment["target_student_ids"] or m["id"] in assignment["target_student_ids"]]
    if not members:
        st.info("승인된 배부 대상 학생이 없습니다.")
        return
    key = _key("grading", course["id"], assignment["id"], _user(work)["id"])
    export = work.export_assignment(course["id"], assignment["id"])
    st.dataframe(export, hide_index=True, width="stretch")
    buffer = io.StringIO()
    if export:
        writer = csv.DictWriter(buffer, fieldnames=list(export[0]))
        writer.writeheader()
        writer.writerows(export)
    st.download_button("제출·평가 현황 CSV 내려받기", buffer.getvalue().encode("utf-8-sig"),
                       file_name="classroom-assignment.csv", mime="text/csv", key=key + "_export")
    mapping = {m["id"]: m for m in members}
    sid = st.selectbox("학생 답안 확인", list(mapping), format_func=lambda sid: mapping[sid]["name"] + " · " + sid, key=key + "_student")
    record = work.submission(course["id"], assignment["id"], sid)
    st.write("제출 상태: " + record["status"])
    _submission_history(work, course, assignment, record, sid)
    if not record.get("versions") or course.get("archived"):
        return
    number = st.selectbox("평가 대상 제출 차수", [v["number"] for v in reversed(record["versions"])], key=key + "_number")
    version = next(v for v in record["versions"] if v["number"] == number)
    entry = record.get("reviews", {}).get(str(number), {})
    draft = entry.get("draft", {})
    form_key = key + "_review_" + str(number) + "_" + sid
    st.caption("검토 상태, 점수 확정, 결과 공개는 각각 저장합니다. 평가 초안은 학생에게 보이지 않습니다.")
    st.write("평가 대상 답안: " + version["text"])
    feedback = st.text_area("교사 피드백 초안", draft.get("feedback", ""), key=form_key + "_feedback")
    assessment = version.get("assignment_snapshot") or assignment
    maximum = assessment.get("max_points")
    score = st.number_input("전체 점수", min_value=0.0, max_value=float(maximum),
                            value=float(draft.get("score") or 0), key=form_key + "_score") if maximum is not None else None
    rubric_scores = []
    for index, criterion in enumerate(assessment.get("rubric", [])):
        previous = draft.get("rubric_scores", [])[index] if index < len(draft.get("rubric_scores", [])) else {}
        st.write("평가 요소: " + criterion["label"])
        level = st.text_input("수준", previous.get("level", ""), key=form_key + "_level_" + str(index))
        part_max = criterion.get("max_points")
        part_score = st.number_input("요소 점수", min_value=0.0, max_value=float(part_max), value=float(previous.get("score") or 0),
                                     key=form_key + "_part_score_" + str(index)) if part_max is not None else None
        part_feedback = st.text_input("요소 피드백", previous.get("feedback", ""), key=form_key + "_part_feedback_" + str(index))
        rubric_scores.append(dict(level=level, score=part_score, feedback=part_feedback))
    checked = st.checkbox("교사 검토 완료", draft.get("review_status") == "reviewed", key=form_key + "_checked")
    final = st.checkbox("점수 확정", draft.get("score_status") == "final", key=form_key + "_final")
    needs_check = st.checkbox("손글씨·답안 판독 확인 필요", draft.get("needs_check", False), key=form_key + "_needs_check")
    if st.button("평가 초안 저장", key=form_key + "_save", width="stretch"):
        try:
            work.save_review(course["id"], assignment["id"], sid, number, feedback=feedback, score=score,
                             rubric_scores=rubric_scores, review_status="reviewed" if checked else "in_review",
                             score_status="final" if final else "draft", needs_check=needs_check)
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("평가 초안을 저장했습니다. 아직 학생에게 공개되지 않았습니다.")
    confirmed = st.checkbox("저장한 평가 초안을 학생에게 공개하는 데 동의합니다", key=form_key + "_confirm_publish")
    if st.button("결과 공개", disabled=not confirmed, key=form_key + "_publish", width="stretch"):
        try:
            work.publish_review(course["id"], assignment["id"], sid, number)
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("저장한 평가 결과를 학생에게 공개했습니다.")
    if entry.get("published"):
        st.caption("현재 공개 결과 · " + _when(entry["published"]["published_at"]))
    reason = st.text_input("수정 요청 사유 · 학생에게 전달됩니다", key=form_key + "_revision_reason")
    if st.button("수정 요청 보내기", key=form_key + "_request_revision"):
        try:
            work.request_revision(course["id"], assignment["id"], sid, reason)
        except ClassroomError as error:
            _notice_error(error)
        else:
            st.success("수정 요청을 저장했습니다. 학생이 새 버전으로 재제출할 수 있습니다.")


def render_today(service, courses, user=None):
    work = _work(service)
    st.subheader("오늘 할 일")
    items, notices = [], []
    for course in courses:
        if course.get("membership_status") == "pending" or course.get("archived"):
            continue
        for assignment in work.assignments(course["id"]):
            if assignment.get("disabled") or assignment.get("activity_id"):
                continue
            record = work.submission(course["id"], assignment["id"])
            state = record["status"]
            if state in ("미제출", "작성 중", "수정 요청"):
                items.append(dict(수업=course["title"], 할일=assignment["title"], 상태=state,
                                  마감=_when(assignment.get("due_at"))))
        notices.extend([dict(n, course_title=course["title"]) for n in work.notifications(course["id"])])
    if items:
        st.dataframe(items, hide_index=True, width="stretch")
    else:
        st.info("현재 승인된 수업에 미제출 과제와 수정 요청이 없습니다.")
    with st.expander("과제·수정 요청·피드백 알림"):
        if not notices:
            st.caption("아직 알림이 없습니다.")
        for notice in sorted(notices, key=lambda n: n["created_at"], reverse=True)[:30]:
            st.write(notice["course_title"] + " · " + notice["title"] + " · " + notice["message"])
            st.caption(_when(notice["created_at"]))


def calendar_resources(service, course, user=None):
    work = _work(service)
    rows = [dict(kind="material", id=m["id"], title=m["title"], url=m.get("url", ""))
            for m in work.materials(course["id"]) if not m.get("disabled") and not m.get("activity_id")]
    rows += [dict(kind="assignment", id=a["id"], title=a["title"])
             for a in work.assignments(course["id"]) if not a.get("disabled") and not a.get("activity_id")]
    return rows


def render_lesson_resources(service, course, lesson, user=None, key=""):
    work = _work(service)
    materials = {m["id"]: m for m in work.materials(course["id"])}
    assignments = {a["id"]: a for a in work.assignments(course["id"])}
    resources = copy.deepcopy(lesson.get("resources", []))
    resources += [dict(kind="material", id=mid) for mid in lesson.get("material_ids", [])]
    resources += [dict(kind="assignment", id=aid) for aid in lesson.get("assignment_ids", [])]
    if lesson.get("activity_id"):
        st.caption(DISABLED_ACTIVITY)
    if not resources and not lesson.get("activity_id"):
        st.caption("이 차시에 연결한 자료·과제가 없습니다.")
    for index, resource in enumerate(resources):
        resource_key = _key("lesson_resource", course["id"], lesson.get("id"), index, _user(work)["id"], key)
        kind = resource.get("kind", resource.get("type", "link"))
        rid = resource.get("id", resource.get("resource_id", ""))
        if kind == "material":
            if rid in materials:
                with st.expander("수업 자료 · " + materials[rid]["title"]):
                    _material_body(work, course, materials[rid], resource_key)
            else:
                st.caption("연결 자료가 비공개이거나 접근할 수 없습니다.")
        elif kind == "assignment":
            if rid in assignments:
                with st.expander("과제 · " + assignments[rid]["title"]):
                    _assignment_body(work, course, assignments[rid], resource_key)
                    st.caption("답안 작성과 평가는 ‘과제·퀴즈·수행평가’에서 진행하세요.")
            else:
                st.caption("연결 과제가 비공개이거나 접근할 수 없습니다.")
        elif resource.get("activity_id") or kind == "snorkl":
            st.caption(DISABLED_ACTIVITY)
        elif resource.get("url", "").startswith(("https://", "http://")):
            st.link_button(resource.get("title") or "연결 자료 열기", resource["url"], width="stretch")
        else:
            st.caption("연결 자료가 비공개이거나 접근할 수 없습니다.")


def render_records(service, course, user=None):
    work = _work(service)
    teacher = _teacher(work, course)
    key = _key("records", course["id"], _user(work)["id"])
    st.subheader("성찰·관찰 연결")
    if teacher:
        reflections = work.reflections(course["id"])
        if not reflections:
            st.caption("아직 수업에 연결한 성찰이 없습니다.")
        for reflection in reflections:
            st.caption(reflection["student_id"] + " · " + str(reflection.get("date") or reflection.get("updated_at", "")))
            _record_body(work, course, reflection, "sudanote")
        members = work.service.members(course["id"])
        mapping = {m["id"]: m for m in members}
        if mapping and not course.get("archived"):
            with st.expander("교사 개인 관찰 작성"):
                sid = st.selectbox("관찰 대상 학생", list(mapping), format_func=lambda sid: mapping[sid]["name"] + " · " + sid, key=key + "_student")
                body = st.text_area("교사 개인 관찰 · 학생에게 공개되지 않습니다", max_chars=10000, key=key + "_observation")
                shared = st.multiselect("명시적으로 공유할 담당 교사", [tid for tid in course["teacher_ids"] if tid != _user(work)["id"]], key=key + "_shared")
                if st.button("개인 관찰 저장", key=key + "_save_observation"):
                    oid = st.session_state.setdefault(key + "_observation_request", uuid.uuid4().hex)
                    try:
                        work.save_observation(course["id"], sid, body, observation_id=oid, shared_teacher_ids=shared)
                    except ClassroomError as error:
                        _notice_error(error)
                    else:
                        st.session_state.pop(key + "_observation_request", None)
                        st.success("교사 개인 관찰을 GitHub에 저장했습니다.")
            _link_existing_record(work, course, "observation", key)
        for observation in work.observations(course["id"]):
            with st.expander("교사 관찰 · " + observation["student_id"]):
                _record_body(work, course, observation, "observation")
                st.caption("교사 개인 기록 · 작성자와 명시적으로 공유받은 담당 교사만 열람")
    else:
        if not course.get("archived"):
            with st.expander("이 수업의 성찰 작성"):
                body = st.text_area("오늘 이해한 것, 생각의 변화, 다음에 해 볼 일", max_chars=10000, key=key + "_reflection")
                if st.button("성찰 저장", key=key + "_save_reflection"):
                    try:
                        work.save_reflection(course["id"], body)
                    except ClassroomError as error:
                        _notice_error(error)
                    else:
                        st.success("성찰을 GitHub에 저장했습니다. 기존 수다노트에서도 같은 기록을 확인할 수 있습니다.")
            _link_existing_record(work, course, "sudanote", key)
        for reflection in work.reflections(course["id"]):
            st.caption(str(reflection.get("date") or reflection.get("updated_at", "")))
            _record_body(work, course, reflection, "sudanote")
    st.caption("기존 수다노트·관찰 기록은 해당 메뉴에서 유지됩니다. 수업 연결은 원본 ID를 참조합니다.")


def _record_body(work, course, record, kind):
    if not record.get("legacy_ref"):
        st.write(record.get("body", ""))
        return
    try:
        original = work.legacy.resolve_reference(work.service.actor(), course["id"], kind, record["legacy_ref"])
    except ClassroomError as error:
        st.caption(str(error))
        return
    if kind == "sudanote":
        for i in range(1, 6):
            if original.get(f"q{i}"):
                st.write(f"{i}. " + original[f"q{i}"])
    else:
        st.write(original.get("content", ""))
    st.caption("기존 원본 참조 · 내용은 별도로 복제하지 않았습니다.")


def _link_existing_record(work, course, kind, key):
    """List only authenticated originals, then validate again when linking."""
    with st.expander("기존 " + ("수다노트" if kind == "sudanote" else "교사 관찰") + "를 이 수업에 연결"):
        import storage as db
        actor = work.service.actor()
        internal_course = work.service._course(course["id"], teacher=kind == "observation")
        table = "sudanotes" if kind == "sudanote" else "observations"
        rows = [r for r in db.read(table) if r.get("student_id") in internal_course.get("student_ids", [])]
        if kind == "sudanote":
            rows = [r for r in rows if r.get("student_id") == actor["id"] and r.get("subject") == course["subject"]]
        mapping = {r["id"]: r for r in rows}
        if not mapping:
            st.caption("이 수업과 연결할 수 있는 본인의 기존 기록이 없습니다.")
            return
        record_id = st.selectbox("연결할 원본 기록", list(mapping),
                                 format_func=lambda rid: str(mapping[rid].get("created_at", "")) + " · " +
                                 str(mapping[rid].get("name", "")) + " · " + str(mapping[rid].get("q1") or mapping[rid].get("content", ""))[:40],
                                 key=key + "_link_" + kind)
        assignments = work.assignments(course["id"])
        assignment_mapping = {a["id"]: a for a in assignments}
        assignment_id = st.selectbox("관련 과제 · 선택", [""] + list(assignment_mapping),
                                     format_func=lambda aid: assignment_mapping[aid]["title"] if aid else "수업에만 연결", key=key + "_link_assignment_" + kind)
        if st.button("원본 기록 연결 저장", key=key + "_link_save_" + kind):
            try:
                if kind == "sudanote":
                    work.save_reflection(course["id"], "", assignment_id=assignment_id or None, legacy_ref=record_id)
                else:
                    work.save_observation(course["id"], mapping[record_id]["student_id"], "",
                                          observation_id=_key("legacy_observation", course["id"], record_id),
                                          assignment_id=assignment_id or None, legacy_ref=record_id)
            except ClassroomError as error:
                _notice_error(error)
            else:
                st.success("원본 ID를 연결해 저장했습니다.")
