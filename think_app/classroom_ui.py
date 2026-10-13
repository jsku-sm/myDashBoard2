"""Teacher activity list, response gallery, and student preview."""
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

import streamlit as st
from streamlit.components.v1 import declare_component

from .ai import AI, normalized_image, board_image
from .classroom import Classroom, STATUSES, GRADES, grade
from .courses import now
from .storage import AppError, GitHubStore, LocalStore, student_pdf_attachments
from .ui import board
from .media import MODES, activity_mode, validate_audio, validated_graph
from .design import section
from .model_answers import render_model_answer, render_question_model_answer, reference_image_key
from .timer_ui import teacher_timer_controls, student_timer, student_availability_watch
from .uploads import UploadedFiles, upload_kind, validated_pdf
from .question_files import render_question_files, display_question_files, question_file_key
from .curriculum_ui import render_curriculum_criteria
from .student_drafts import (capture_active_drafts, load_draft, remember_draft,
                            restore_draft_widgets, forget_draft)
from .grading import assessment_score_published, public_score, student_feedback
from .teacher_grading_ui import grading_controls, attempt_grading_controls

graph_calculator = declare_component("think_desmos", path=str(Path(__file__).parent / "graph"))


def answer_uploads(room, task, student_id, name, class_id, preview, key, uploads, restored_ids=()):
    """Save chosen files immediately; attach only this student's saved files."""
    service = UploadedFiles(room.store)
    identity_key = hashlib.sha256(json.dumps([task["id"], class_id, student_id.strip(), preview],
                                             ensure_ascii=False).encode()).hexdigest()[:16]
    selected_key = key + "_saved_uploads_" + identity_key
    incoming_key = selected_key + "_incoming"
    incoming, failed = [], False
    if len(uploads) > 2:
        st.error("첨부 파일은 이미지와 PDF를 합쳐 최대 2개까지 올려주세요.")
        failed = True
    elif uploads and not (student_id.strip() and name.strip()):
        st.info("학번과 이름을 입력하면 업로드한 파일을 저장합니다.")
        failed = True
    else:
        for upload in uploads:
            try:
                saved = service.save(task["id"], student_id, name, class_id,
                                     upload.name, upload.getvalue(), preview=preview)
                if saved["id"] not in incoming:
                    incoming.append(saved["id"])
            except AppError as error:
                failed = True
                st.error(upload.name + " · " + str(error))
    if failed:
        st.button("파일 저장 다시 시도", key=selected_key + "_retry",
                  help="선택한 파일과 입력한 답안을 유지한 채 다시 저장합니다.")
    saved_files = service.for_student(task["id"], student_id, class_id, preview)
    mapping = {item["id"]: item for item in saved_files}
    if selected_key not in st.session_state:
        st.session_state[selected_key] = [uid for uid in restored_ids if uid in mapping][:2]
        st.session_state[incoming_key] = []
    old_incoming = st.session_state.get(incoming_key, [])
    selected = [uid for uid in st.session_state.get(selected_key, []) if uid in mapping]
    if not failed:
        selected = [uid for uid in selected if uid not in old_incoming or uid in incoming]
        selected.extend(uid for uid in incoming if uid not in old_incoming and uid not in selected)
        if len(selected) > 2:
            selected = (incoming + [uid for uid in selected if uid not in incoming])[:2]
        st.session_state[incoming_key] = incoming
    st.session_state[selected_key] = selected
    if incoming and not failed:
        if isinstance(room.store, GitHubStore):
            st.success(f"파일 {len(incoming)}개를 GitHub {room.store.repo} 저장소에 저장했습니다.")
        elif isinstance(room.store, LocalStore):
            st.success(f"파일 {len(incoming)}개를 서버에 저장했습니다.")
        else:
            st.info(f"파일 {len(incoming)}개를 체험 모드에 임시 보관했습니다. GitHub 저장은 배포 환경에서 THINK_MODE=github 설정이 필요합니다.")
    if mapping:
        selected = st.multiselect("답안에 첨부할 저장 파일 · 최대 2개", list(mapping),
                                  format_func=lambda uid: mapping[uid]["filename"] + " · " + mapping[uid]["created"],
                                  max_selections=2, key=selected_key)
        st.caption("업로드 파일은 답안 제출 전에도 보관됩니다. 첨부 선택을 해제해도 저장된 원본은 유지됩니다.")
        for uid in selected:
            saved = mapping[uid]
            try:
                if upload_kind(saved) == "image":
                    st.image(service.read(saved, task["id"], student_id, class_id, preview),
                             caption=saved["filename"], use_container_width=True)
                else:
                    st.caption("PDF 첨부 · " + saved["filename"])
                st.download_button("저장한 원본 파일 내려받기", service.read(saved, task["id"], student_id, class_id,
                                                                               preview, original=True),
                                   file_name=saved["filename"], mime=saved["original_mime"],
                                   key=selected_key + "_download_" + uid)
            except AppError as error:
                failed = True
                st.error(str(error))
    return selected, not failed


def start_activity_draft(course_id):
    """Begin a clean draft after the previous activity was saved."""
    if st.session_state.get("adding_activity"):
        return
    prefix = "activity_form_" + course_id + "_"
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    st.session_state.adding_activity = True


def activity_form(room, course_id, task=None, ai=None):
    task = task or {}
    form_key = "activity_form_" + task.get("id", course_id)
    with st.container(border=True):
        title = st.text_input("활동 이름", value=task.get("title", ""), max_chars=120, key=form_key + "_title")
        mode = st.selectbox("활동 모드", list(MODES), index=list(MODES).index(activity_mode(task)),
                            format_func=MODES.get, key=form_key + "_mode")
        st.caption("활동 이름에 ‘데스모스’ 또는 ‘Desmos’를 입력하면 그래프 모드로 저장됩니다.")
        prompt = st.text_area("학생에게 제시할 문제", value=task.get("prompt", ""), max_chars=10000, key=form_key + "_prompt")
        question_key = question_file_key(form_key)
        previous_questions = st.session_state.get(question_key, task.get("question_files", []))
        previous_ids = {record["id"] for record in previous_questions}
        writing = activity_mode({"title": title, "mode": mode}) == "writing"
        if writing or previous_questions:
            render_question_files(task, form_key, room, course_id)
        if writing:
            questions = st.session_state.get(question_key, [])
            render_question_model_answer(
                dict(task, title=title, prompt=prompt), ai, form_key, room, course_id,
                auto_generate=any(record["id"] not in previous_ids for record in questions))
        expected_key = render_model_answer(task, ai, form_key, room=room, course_id=course_id)
        expected = st.text_area("모범답안", max_chars=10000, key=expected_key)
        criteria, curriculum = render_curriculum_criteria(task, form_key)
        options = st.text_area("퀴즈 선택지 · 한 줄에 하나", value="\n".join(task.get("quiz_options", [])),
                               help="퀴즈 모드에서만 사용됩니다. 선택지를 비우면 단답형, 2~8개 입력하면 객관식입니다.", key=form_key + "_options")
        maximum = st.number_input("최대 시도 횟수", 1, 10, task.get("max_attempts", 2), key=form_key + "_maximum")
        left, right = st.columns(2)
        start = left.date_input("시작일", value=date.fromisoformat(task["start"]) if task else date.fromisoformat(now()[:10]),
                                key=form_key + "_start")
        same_day = right.checkbox("마감일을 시작일과 동일하게", value=not task or task.get("end") == task.get("start"),
                                  key=form_key + "_same_day")
        end_key = form_key + "_end"
        st.session_state.setdefault(end_key, date.fromisoformat(task["end"]) if task.get("end") else None)
        if same_day:
            st.session_state[end_key] = start
        end = right.date_input("마감일 · 선택", disabled=same_day, key=end_key)
        duration_key = form_key + "_duration"
        st.session_state.setdefault(duration_key, task.get("duration_minutes", 0))
        if task.get("timer_started_at"):
            st.session_state[duration_key] = task.get("duration_minutes", 0)
        duration = st.number_input("문제 풀이 시간 · 분", min_value=0, max_value=1440,
                                    help="학생에게 배포하면 풀이 시간이 시작됩니다. 예약 배포한 활동은 시작일에 ‘평가 시작’을 누르세요. 0분은 시간 제한 없음입니다.",
                                    key=duration_key, disabled=bool(task.get("timer_started_at")))
        if task.get("timer_started_at"):
            st.caption("진행 중인 평가의 남은 시간은 활동 화면의 수행평가 타이머에서 조정하세요.")
        if not task:
            st.caption("저장한 활동은 배포 전 상태로 보관됩니다. 활동 목록에서 ‘학생에게 배포’를 누르면 참여 학급에 공개됩니다.")
        if st.button("활동 저장", type="primary", key=form_key + "_save"):
            try:
                room.save_activity(course_id, title, prompt, expected, criteria,
                                   maximum, start.isoformat(), end.isoformat() if end else None, task.get("id"),
                                   mode, [o.strip() for o in options.splitlines() if o.strip()],
                                   duration_minutes=None if task.get("timer_started_at") else duration,
                                   expected_images=st.session_state.get(reference_image_key(form_key), []),
                                   question_files=st.session_state.get(question_key, []), curriculum=curriculum)
            except AppError as error:
                st.error(str(error))
            else:
                st.session_state["activity_saved_notice_" + course_id] = (
                    "활동을 수정했습니다." if task else
                    "활동을 저장했습니다. ‘학생에게 배포’를 눌러 참여 학급에 공개하세요.")
                st.session_state.pop("adding_activity", None)
                st.rerun()


def teacher_distribution_controls(room, course, task):
    """Publish a saved activity to its enrolled classes with one explicit action."""
    task = room.activity(task["id"])
    notice_key = "activity_distribution_notice_" + task["id"]
    if notice_key in st.session_state:
        st.success(st.session_state.pop(notice_key))
    unpublished = not room.is_distributed(task) or task["status"] == "배포 전"
    label = ("학생에게 배포" if unpublished else
             "학생에게 다시 배포" if task["status"] != "진행 중" else "배포 완료")
    expired = bool(task.get("end") and task["end"] < now()[:10])
    st.caption("배포 대상 · " + ", ".join(course["classes"]) +
               " · 수행평가 기간 · " + task["start"] + " ~ " + (task.get("end") or "마감일 없음"))
    if st.button(label, type="primary", key="distribute_activity_" + task["id"],
                 disabled=expired or (room.is_distributed(task) and task["status"] == "진행 중")):
        try:
            room.distribute_activity(task["id"])
        except AppError as error:
            st.error(str(error))
        else:
            current = room.activity(task["id"])
            if current["start"] > now()[:10]:
                message = "학생에게 예약 배포했습니다. 시작일에 수행평가가 표시됩니다."
                if current.get("duration_minutes"):
                    message = "학생에게 예약 배포했습니다. 시작일에 ‘평가 시작’을 누르면 학생에게 표시되고 풀이 타이머가 시작됩니다."
            elif room.timer_state(current)["phase"] == "expired":
                message = "배포 상태를 변경했습니다. 풀이 시간이 끝나 학생에게 표시되지 않습니다. 수행평가 타이머에서 남은 시간을 조정하세요."
            elif room.timer_state(current)["phase"] == "ended":
                message = "배포 상태를 변경했습니다. 종료된 평가는 학생에게 표시되지 않습니다."
            else:
                message = "학생에게 배포했습니다. 참여 학급의 학생 메뉴에 활동이 표시됩니다."
            st.session_state[notice_key] = message
            st.rerun()
    if expired:
        st.caption("마감일이 지났습니다. 편집에서 수행평가 기간을 수정한 뒤 배포하세요.")
    elif unpublished:
        st.caption("학생에게 배포하기 전에는 학생 메뉴에 활동이 표시되지 않습니다.")
    elif task["start"] > now()[:10]:
        st.caption("예약 배포 완료 · 시작일에 ‘평가 시작’을 누르세요." if task.get("duration_minutes") else
                   "예약 배포 완료 · 시작일부터 학생이 참여할 수 있습니다.")


def feedback_view(attempt, teacher=True):
    if not teacher and "assessment_result" in attempt and not assessment_score_published(attempt):
        st.markdown("### 채점 결과")
        st.info("선생님이 채점 결과를 검토 중입니다. 배포되면 ‘내 점수 확인하기’에서 확인할 수 있습니다.")
        return
    result = attempt.get("assessment_result")
    if isinstance(result, dict):
        st.markdown("### 채점 결과")
        score = result.get("score") if teacher else public_score(attempt)
        if not teacher and score is None:
            st.info("선생님이 채점 결과를 검토 중입니다. 배포되면 ‘내 점수 확인하기’에서 확인할 수 있습니다.")
            return
        if score is not None:
            st.metric("수행평가 점수", f"{score:g} / 100")
        else:
            st.info("점수를 확정하려면 선생님의 확인이 필요합니다.")
        if teacher:
            st.caption("학생에게 배포됨" if result.get("status") == "published" else "검토 대기 · 학생에게 미공개")
        feedback = result.get("feedback") if teacher else student_feedback(attempt)
    else:
        st.markdown("### AI 피드백")
        st.write("평가: **" + grade(attempt) + "**")
        feedback = attempt.get("feedback")
    if feedback:
        for label, field in [("잘한 점", "praise"), ("풀이 분석", "observation"), ("힌트", "hint"), ("다음 질문", "next_question")]:
            st.markdown(f"**{label}**")
            st.write(feedback.get(field, ""))
        if feedback.get("needs_teacher_review"):
            st.warning(feedback.get("uncertainty_reason") or "교사의 확인이 필요합니다.")
        with st.expander("평가 기준별 분석"):
            for result in feedback.get("criteria", []):
                st.write(result["criterion"] + " · " + result["evidence"])
        if teacher and feedback.get("rationale"):
            with st.expander("점수 산정 근거"):
                st.write(feedback["rationale"])
    else:
        st.info("아직 채점 결과가 없습니다.")
    comment = (feedback or {}).get("teacher_comment") if isinstance(attempt.get("assessment_result"), dict) else attempt.get("teacher_comment")
    if comment:
        st.markdown("### 선생님 피드백")
        st.write(comment)


def attempt_view(room, attempt, ai, teacher=True):
    left, right = st.columns([1.4, 1], gap="large")
    with left:
        st.subheader(f"{attempt['name']} · {attempt['number']}번째 시도")
        for ref in attempt["images"]:
            st.image(room.store.get_blob(ref), use_container_width=True)
        files = UploadedFiles(room.store)
        pdfs = student_pdf_attachments(room.store, attempt)
        pdf_ids = {saved["id"] for saved, _ in pdfs}
        for saved, raw in pdfs:
            st.caption("PDF 답안 · " + saved["filename"])
            st.download_button("업로드한 원본 내려받기 · " + saved["filename"], raw,
                               file_name=saved["filename"], mime="application/pdf",
                               key="attempt_original_" + attempt["id"] + "_" + saved["id"])
        for uid in attempt.get("upload_ids", []):
            if uid in pdf_ids:
                continue
            saved = files.get(uid, attempt["activity_id"], attempt["student_id"], attempt["class_id"], attempt["preview"])
            st.download_button("업로드한 원본 내려받기 · " + saved["filename"],
                               files.read(saved, attempt["activity_id"], attempt["student_id"], attempt["class_id"],
                                          attempt["preview"], original=True),
                               file_name=saved["filename"], mime=saved["original_mime"],
                               key="attempt_original_" + attempt["id"] + "_" + uid)
        if attempt.get("graph"):
            st.markdown("**제출한 그래프 수식·표**")
            for expression in attempt["graph"]["expressions"]:
                if expression.get("latex"):
                    st.latex(expression["latex"])
                elif expression.get("type") == "table":
                    st.json(expression)
            st.download_button("그래프 상태 저장", json.dumps(attempt["graph"], ensure_ascii=False),
                               file_name="그래프.json", mime="application/json", key="graph_download_" + attempt["id"])
        if attempt.get("quiz_answer"):
            st.markdown("**퀴즈 답**")
            st.write(attempt["quiz_answer"])
        if attempt.get("audio"):
            st.audio(room.store.get_blob(attempt["audio"]), format="audio/wav")
        if attempt.get("transcript"):
            st.markdown("**음성 설명**")
            st.write(attempt["transcript"])
        st.write(attempt["text"])
        st.caption(attempt["created"].replace("T", " "))
    with right:
        feedback_view(attempt, teacher=teacher)
        if teacher:
            attempt_grading_controls(room, attempt, ai)
            if not isinstance(attempt.get("assessment_result"), dict):
                with st.form("comment_" + attempt["id"]):
                    comment = st.text_area("학생에게 전할 피드백", value=attempt["teacher_comment"], max_chars=3000)
                    if st.form_submit_button("피드백 저장", type="primary"):
                        room.comment(attempt["id"], comment)
                        st.rerun()


def student_preview(room, course, task, ai, identity=None, editor_key=None, compact=False):
    task = room.activity(task["id"])
    preview = identity is None
    student_id, name, class_id = identity or ("preview", "체험 학생", course["classes"][0])
    draft_identity = (student_id, name, class_id)
    capture_active_drafts(course["id"], draft_identity, preview)
    if not preview and not room.student_activity_available(task):
        st.info(room.student_unavailable_notice(task))
        student_availability_watch(room, course["id"], task["id"], closed=True)
        return
    if not compact:
        st.subheader("학생 모드 체험" if preview else "학생 답안 작성")
    if preview:
        st.caption("체험 답안은 실제 학생 목록과 내보내기에서 제외되며, 체험 기록에서 확인할 수 있습니다.")
    if not compact:
        st.markdown("### " + task["title"])
    student_timer(room, task["id"], require_visible=not preview)
    st.write(task["prompt"])
    display_question_files(room.store, task)
    st.caption("평가 기준: " + " / ".join(task["criteria"]))
    notice_key = f"submission_notice_{task['id']}_{class_id}_{student_id}"
    if st.session_state.get(notice_key):
        st.success(st.session_state.pop(notice_key))
    previous = [a for a in room.attempts(task["id"]) if a["preview"] == preview and a["student_id"] == student_id and a["class_id"] == class_id]
    if room._within_submission_period(task) and len(previous) < task["max_attempts"]:
        key = (f"student_{editor_key}_{len(previous)}" if editor_key else
               f"student_{task['id']}_{class_id}_{student_id}_{len(previous)}")
        draft = load_draft(task, draft_identity, preview, len(previous), editor_key)
        restore_draft_widgets(draft, key)
        st.session_state.pop(key + "_consent", None)
        mode = activity_mode(task)
        image, graph, quiz_answer = None, None, None
        if mode == "graph":
            graph = graph_calculator(api_key=ai.settings.desmos_api_key,
                                     draft_filename=course["title"] + "-그래프.json",
                                     initial_state=(draft.get("graph") or {}).get("state"),
                                     key=key + "_graph", default=draft.get("graph"))
            if not ai.settings.desmos_api_key or (graph and graph.get("mode") == "embed"):
                st.caption("현재 화면에서 데스모스를 사용할 수 있습니다. ‘캡처하기’에서 현재 탭을 선택하고 영역을 드래그해 PNG로 저장한 뒤 아래에 첨부하세요. 수식과 설명은 나의 답안에 적을 수 있습니다.")
        elif mode == "quiz":
            if task.get("quiz_options"):
                quiz_answer = st.radio("퀴즈 답 선택", task["quiz_options"], index=None, key=key + "_quiz")
            else:
                quiz_answer = st.text_input("퀴즈 답", max_chars=2000, key=key + "_quiz")
        else:
            st.caption("펜이나 손가락으로 풀이를 쓰세요. 사진으로 푼 문제도 아래에서 첨부할 수 있습니다.")
            saved_board = draft.get("board") or {}
            image = board(initial_image=saved_board.get("image") if saved_board.get("hasInk") else None,
                          key=key + "_board", default=draft.get("board"))
        uploads = st.file_uploader("답안 이미지·PDF 첨부 · 최대 2개", type=["png", "jpg", "jpeg", "pdf"],
                                   accept_multiple_files=True, key=key + "_uploads",
                                   help="PNG/JPG 이미지 또는 PDF를 올리세요. PDF는 10MB 이하, 1~200쪽, 암호가 없는 파일을 지원합니다. 학번과 이름을 입력한 파일은 업로드 즉시 저장됩니다.")
        upload_ids, uploads_saved = answer_uploads(room, task, student_id, name, class_id, preview, key, uploads,
                                                   restored_ids=draft.get("upload_ids", ()))
        text = st.text_area("나의 답안", max_chars=12000, key=key + "_text")
        audio = st.audio_input("목소리로 설명하기 · 2분 이내", sample_rate=16000, key=key + "_audio")
        raw_audio = audio.getvalue() if audio else draft.get("raw_audio")
        if not audio and raw_audio:
            st.audio(raw_audio, format="audio/wav")
            if st.button("보관된 녹음 삭제", key=key + "_clear_saved_audio"):
                raw_audio = None
        audio_hash = hashlib.sha256(raw_audio).hexdigest() if raw_audio else ""
        if audio_hash != st.session_state.get(key + "_audio_hash", ""):
            st.session_state[key + "_audio_hash"] = audio_hash
            st.session_state[key + "_transcript"] = ""
        transcript = st.text_area("음성 설명 확인·수정", max_chars=12000, key=key + "_transcript")
        st.caption("녹음과 확인·수정한 음성 설명은 답안과 함께 저장됩니다.")
        remember_draft(task, draft_identity, preview, len(previous), editor_key,
                       widget_key=key, text=text, transcript=transcript, quiz_answer=quiz_answer,
                       board=image, graph=graph, upload_ids=upload_ids, raw_audio=raw_audio, consent=False)
        with st.popover("작업 전체 저장", use_container_width=True):
            st.caption("파일 준비를 누른 시점의 글·수식·풀이 이미지·첨부 PDF·녹음을 ZIP으로 저장합니다. 교사 제출은 답안 제출을 눌러주세요.")
            if st.button("작업 파일 준비", key=key + "_prepare_work"):
                try:
                    archive_uploads = uploads
                    if uploads_saved:
                        files = UploadedFiles(room.store)
                        archive_uploads = []
                        for uid in upload_ids:
                            saved = files.get(uid, task["id"], student_id, class_id, preview)
                            document = io.BytesIO(files.read(saved, task["id"], student_id, class_id, preview,
                                                            original=True))
                            document.name = saved["filename"]
                            archive_uploads.append(document)
                    st.session_state[key + "_work_file"] = work_archive(task, text, transcript, quiz_answer, graph,
                                                                       image, archive_uploads, raw_audio)
                except AppError as error:
                    st.error(str(error))
            if st.session_state.get(key + "_work_file"):
                st.download_button("내 작업 ZIP 저장", st.session_state[key + "_work_file"],
                                   file_name="내작업.zip", mime="application/zip", key=key + "_download_work")
        embedded_graph = mode == "graph" and (not ai.settings.desmos_api_key or bool(graph and graph.get("mode") == "embed"))
        graph_ready = mode != "graph" or embedded_graph or bool(graph and graph.get("ready"))
        can_submit = room._can_submit(room.activity(task["id"]))
        if not preview and (not student_id.strip() or not name.strip()):
            st.caption("학번과 이름을 입력하면 선생님에게 제출할 수 있습니다.")
        if st.button("답안 제출", type="primary", disabled=not can_submit or not graph_ready or not uploads_saved or not student_id.strip() or not name.strip(), key=key + "_submit"):
            try:
                if len(uploads) > 2:
                    raise AppError("첨부 파일은 이미지와 PDF를 합쳐 최대 2개까지 제출할 수 있습니다.")
                images = []
                drawing = board_image(image)
                if drawing:
                    images.insert(0, drawing)
                request = st.session_state.setdefault(key + "_request", uuid.uuid4().hex)
                with st.spinner("답안과 첨부 파일을 저장하고 있습니다…"):
                    room.submit(task["id"], student_id, name, class_id, text, images,
                                False, request, preview=preview, transcript=transcript, audio=raw_audio,
                                graph={"mode": "embed"} if embedded_graph else graph, quiz_answer=quiz_answer,
                                upload_ids=upload_ids)
                forget_draft(task, draft_identity, preview, len(previous), editor_key)
                st.session_state[notice_key] = "체험 답안이 저장되었습니다." if preview else "선생님에게 답안을 제출했습니다. 제출한 작업과 녹음을 아래에서 확인할 수 있습니다."
            except AppError as error:
                if st.session_state.get(notice_key):
                    st.session_state.preview_error = str(error)
                    st.rerun()
                st.error(str(error))
            else:
                st.rerun()
    else:
        st.info("현재 추가 제출이 불가능합니다. 상태, 기간 또는 최대 시도 횟수를 확인하세요.")
    if st.session_state.get("preview_error"):
        st.warning(st.session_state.pop("preview_error"))
    if previous:
        tabs = st.tabs([f"{a['number']}번째 시도" for a in previous])
        for tab, attempt in zip(tabs, previous):
            with tab:
                attempt_view(room, attempt, ai, teacher=False)


def work_archive(task, text, transcript, quiz_answer, graph, drawing, uploads, audio):
    """Download a snapshot of unsubmitted work without sending it to a teacher."""
    if len(uploads) > 2:
        raise AppError("첨부 파일은 이미지와 PDF를 합쳐 최대 2개까지 저장할 수 있습니다.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("작업.json", json.dumps(dict(activity_id=task["id"], title=task["title"],
                            mode=activity_mode(task), text=text, transcript=transcript,
                            quiz_answer=quiz_answer, saved_at=now()), ensure_ascii=False, indent=2))
        if graph and isinstance(graph.get("state"), dict):
            archive.writestr("그래프.json", json.dumps(dict(state=graph["state"],
                                expressions=graph.get("expressions", [])), ensure_ascii=False, indent=2))
            if graph.get("ready"):
                _, capture = validated_graph(graph)
                archive.writestr("그래프.jpg", capture)
        image = board_image(drawing)
        if image:
            archive.writestr("손글씨.jpg", image)
        for index, upload in enumerate(uploads):
            raw = upload.getvalue()
            if Path(getattr(upload, "name", "")).suffix.lower() == ".pdf" or raw.startswith(b"%PDF-"):
                archive.writestr(f"첨부풀이-{index + 1}.pdf", validated_pdf(raw))
            else:
                archive.writestr(f"첨부풀이-{index + 1}.jpg", normalized_image(raw))
        if audio:
            archive.writestr("녹음.wav", validate_audio(audio))
    return output.getvalue()


def student_workbench(room, course, task, settings):
    """Open the editor immediately while collecting the real student's identity."""
    st.caption("나의 생각을 기록하고 선생님에게 제출하세요.")
    student, name, classroom = st.columns([1, 1.4, 1])
    cid = course["id"]
    identity_key = "workbench_identity_" + cid
    saved = st.session_state.get(identity_key, ("", "", course["classes"][0]))
    student_key, name_key, class_key = (prefix + cid for prefix in
                                       ("workbench_student_", "workbench_name_", "workbench_class_"))
    st.session_state.setdefault(student_key, saved[0])
    st.session_state.setdefault(name_key, saved[1])
    if st.session_state.get(class_key) not in course["classes"]:
        st.session_state[class_key] = saved[2] if saved[2] in course["classes"] else course["classes"][0]
    student_id = student.text_input("학번", max_chars=40, key=student_key)
    student_name = name.text_input("이름", max_chars=40, key=name_key)
    class_id = classroom.selectbox("학급", course["classes"], key=class_key)
    st.session_state[identity_key] = (student_id, student_name, class_id)
    student_preview(room, course, task, AI(settings), (student_id, student_name, class_id),
                    editor_key="workbench_" + task["id"], compact=True)


def shared_student(store, course, settings):
    room = Classroom(store)
    default_graph = room.ensure_desmos_activity(course)
    activities = room.activities(course["id"])
    identity_key = "student_identity_" + course["id"]
    identity = st.session_state.get(identity_key)
    if identity:
        capture_active_drafts(course["id"], identity)
    tasks = [task for task in activities
             if room.student_activity_available(task)]
    if not tasks:
        notice = next((room.student_unavailable_notice(task) for task in activities
                       if room.student_unavailable_notice(task) == "선생님이 평가를 종료했습니다."),
                      "수행평가 기간이 아닙니다.")
        st.info(notice)
        student_availability_watch(room, course["id"], closed=True)
        return
    if not identity:
        with st.form("student_identity"):
            student_id = st.text_input("학번", max_chars=40)
            name = st.text_input("이름", max_chars=40)
            class_id = st.selectbox("학급", course["classes"])
            if st.form_submit_button("수업 참여하기", type="primary"):
                if not student_id.strip() or not name.strip():
                    st.error("학번과 이름을 입력하세요.")
                else:
                    st.session_state[identity_key] = (student_id.strip(), name.strip(), class_id)
                    st.rerun()
        return
    st.caption(f"{identity[2]} · {identity[1]}")
    if st.button("참여 정보 변경"):
        st.session_state.pop(identity_key, None)
        st.rerun()
    mapping = {t["id"]: t for t in tasks}
    ids = list(mapping)
    aid = st.selectbox("활동 선택", ids, index=ids.index(default_graph) if default_graph in ids else 0,
                       format_func=lambda aid: mapping[aid]["title"])
    student_preview(room, course, mapping[aid], AI(settings), identity)


def response_gallery(room, course, task, ai):
    teacher_distribution_controls(room, course, task)
    toolbar, export = st.columns([4, 1])
    view = toolbar.radio("활동 화면", ["답변", "분석", "편집", "학생으로 체험해보기"], horizontal=True,
                         key="activity_view_" + task["id"])
    with export.popover("내보내기"):
        if st.button("파일 준비", key="prepare_" + task["id"]):
            st.session_state["export_" + task["id"]] = room.export(course["id"], task["id"])
        if st.session_state.get("export_" + task["id"]):
            st.download_button("전체 학생 데이터 ZIP", st.session_state["export_" + task["id"]],
                               file_name="학생답안.zip", mime="application/zip")
    if view in ("답변", "분석"):
        st.write(task["prompt"])
        display_question_files(room.store, task, teacher=True)
    if view == "편집":
        teacher_timer_controls(room, task)
        activity_form(room, course["id"], task, ai)
        return
    if view == "학생으로 체험해보기":
        student_preview(room, course, task, ai)
        return
    teacher_timer_controls(room, task)
    attempts = [a for a in room.attempts(task["id"]) if not a["preview"]]
    selection = st.radio("시도 선택", ["최고 시도", "첫 시도", "최근 시도", "전체"], horizontal=True,
                         key="attempt_filter_" + task["id"])
    classes = st.selectbox("학급", ["전체"] + course["classes"], key="class_filter_" + task["id"])
    groups = {}
    for attempt in attempts:
        if classes == "전체" or attempt["class_id"] == classes:
            groups.setdefault((attempt["class_id"], attempt["student_id"]), []).append(attempt)
    grading_controls(room, task, [attempt for values in groups.values() for attempt in values], ai)
    visible = []
    for values in groups.values():
        if selection == "전체":
            visible.extend(values)
        elif selection == "첫 시도":
            visible.append(values[0])
        elif selection == "최근 시도":
            visible.append(values[-1])
        else:
            def rank(attempt):
                score = (attempt.get("assessment_result") or {}).get("score")
                return (score if score is not None else
                        (4-GRADES.index(grade(attempt))) * 25 if grade(attempt) in GRADES else -1,
                        attempt["number"])
            visible.append(max(values, key=rank))
    if view == "분석":
        columns = st.columns(4)
        for column, label in zip(columns, GRADES):
            column.metric(label, sum(grade(a) == label for a in visible))
        st.caption(f"제출 학생 {len(groups)}명 · 제출 시도 {sum(len(v) for v in groups.values())}회")
    st.caption("점수 구분: 탁월 90점 이상, 성취 75점 이상, 발전 중 50점 이상, 성장 중 50점 미만. 불확실한 답안은 교사 확인 필요로 표시됩니다.")
    if not visible:
        st.info("아직 제출된 학생 답안이 없습니다. 학생 모드에서 활동을 체험할 수 있습니다.")
    for label in GRADES + ["교사 확인 필요", "평가 대기"]:
        values = [a for a in visible if grade(a) == label]
        if not values:
            continue
        st.subheader(f"{label} · {len(values)}")
        columns = st.columns(4)
        for index, attempt in enumerate(values):
            with columns[index % 4]:
                with st.container(border=True):
                    if attempt["images"]:
                        st.image(room.store.get_blob(attempt["images"][0]), use_container_width=True)
                    else:
                        st.write(attempt["text"][:220])
                    if st.button(f"{attempt['name']} · {attempt['number']}번째 시도", key="open_answer_" + attempt["id"]):
                        st.session_state["answer_" + task["id"]] = (attempt["class_id"], attempt["student_id"])
                    st.caption(attempt["class_id"] + " · " + attempt["created"][:16].replace("T", " "))
                    result = attempt.get("assessment_result")
                    if isinstance(result, dict):
                        if result.get("score") is not None:
                            st.caption(f"{result['score']:g} / 100점")
                        st.caption("학생에게 배포됨" if result.get("status") == "published" else "채점 결과 검토 대기")
    student = st.session_state.get("answer_" + task["id"])
    if student in groups:
        st.divider()
        values = groups[student]
        st.subheader(values[0]["name"] + "의 전체 시도")
        tabs = st.tabs([f"{a['number']}번째 시도" for a in values])
        for tab, attempt in zip(tabs, values):
            with tab:
                attempt_view(room, attempt, ai)


def course_detail(store, course, settings):
    room = Classroom(store)
    ai = AI(settings)
    default_graph = room.ensure_desmos_activity(course)
    if st.button("← 수업 목록"):
        st.session_state.pop("selected_course", None)
        st.session_state.pop("selected_activity", None)
        st.rerun()
    st.title(course["title"])
    st.caption("참여 학급 · " + ", ".join(course["classes"]))
    notice = st.session_state.pop("activity_saved_notice_" + course["id"], None)
    if notice:
        st.success(notice)
    aid = st.session_state.get("selected_activity")
    if aid:
        if st.button("← 활동 목록"):
            st.session_state.pop("selected_activity", None)
            st.rerun()
        try:
            task = room.activity(aid)
        except AppError:
            st.session_state.pop("selected_activity", None)
            st.warning("활동이 삭제되었거나 변경되었습니다. 활동 목록으로 돌아가세요.")
            return
        if task["course_id"] != course["id"]:
            st.session_state.pop("selected_activity", None)
            st.rerun()
        st.subheader(task["title"])
        response_gallery(room, course, task, ai)
        return
    options = ["작업하기", "활동 관리", "학생 제출함"] if default_graph else ["활동 관리", "작업하기", "학생 제출함"]
    workspace = st.radio("수업 화면", options, horizontal=True, key="workspace_" + course["id"])
    if workspace != "활동 관리":
        tasks = [task for task in room.activities(course["id"]) if task["status"] != "숨김"]
        if workspace == "학생 제출함":
            tasks = room.activities(course["id"])
        if not tasks:
            st.info("활동 관리에서 먼저 활동을 만들어주세요.")
            return
        mapping = {task["id"]: task for task in tasks}
        ids = list(mapping)
        selected = st.selectbox("작업할 활동" if workspace == "작업하기" else "제출 확인할 활동", ids,
                                index=ids.index(default_graph) if default_graph in ids else 0,
                                format_func=lambda value: mapping[value]["title"],
                                key="workspace_activity_" + workspace + course["id"])
        task = mapping[selected]
        if workspace == "작업하기":
            teacher_distribution_controls(room, course, task)
            student_workbench(room, course, task, settings)
        else:
            response_gallery(room, course, task, ai)
        return
    section("01", "수업 활동")
    filter_col, add_col = st.columns([5, 1])
    selected = filter_col.radio("활동 상태", ["전체", "배포 전", "진행 중", "숨김"], horizontal=True)
    if add_col.button("＋ 활동 추가하기", type="primary"):
        start_activity_draft(course["id"])
    if st.session_state.get("adding_activity"):
        activity_form(room, course["id"], ai=ai)
    if st.button("수업 전체 데이터 내보내기 준비"):
        st.session_state["course_export_" + course["id"]] = room.export(course["id"])
    if st.session_state.get("course_export_" + course["id"]):
        st.download_button("수업 전체 데이터 ZIP 저장", st.session_state["course_export_" + course["id"]],
                           file_name="수업전체기록.zip", mime="application/zip")
    tasks = room.activities(course["id"], None if selected == "전체" else selected)
    if not tasks:
        st.info("표시할 활동이 없습니다. 활동 추가하기에서 문제와 모범답안을 등록하세요.")
    for task in tasks:
        with st.container(border=True):
            name, recent, start, end, status = st.columns([3, 2, 2, 2, 2])
            if name.button(task["title"], key="activity_" + task["id"]):
                st.session_state.selected_activity = task["id"]
                st.rerun()
            attempts = [a for a in room.attempts(task["id"]) if not a["preview"]]
            recent.write(attempts[-1]["created"][:10] if attempts else "—")
            recent.caption(f"{len(attempts)}개 답변")
            start.write("시작일 · " + task["start"])
            end.write("마감일 · " + (task["end"] or "—"))
            status_options = (["배포 전", "숨김"] if not room.is_distributed(task) or task["status"] == "배포 전"
                              else [value for value in STATUSES if value != "배포 전"])
            if task["status"] not in status_options:
                status_options.insert(0, task["status"])
            value = status.selectbox("상태", status_options, index=status_options.index(task["status"]),
                                     key="status_" + task["id"] + "_" + task["status"])
            if value != task["status"]:
                room.set_status(task["id"], value)
                st.rerun()
            teacher_distribution_controls(room, course, task)
            teacher_timer_controls(room, task)
