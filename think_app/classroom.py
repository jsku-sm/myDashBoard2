"""Course activities and durable, append-only student submissions."""
import copy
import hashlib
from datetime import datetime, timedelta, timezone
import io
import json
import math
import re
import uuid
import zipfile

from .courses import KST, now
from .service import safe_csv
from .storage import AppError, student_submission_path, student_pdf_attachments
from .media import MODES, activity_mode, validate_audio, validated_graph
from .uploads import owned_uploads, upload_kind, UploadedFiles
from .reference_images import owned_reference_images
from .question_files import owned_question_files
from .curriculum import validate_selection, criteria_text
from .grading import valid_score, validated_grading, reviewed_feedback

STATUSES = ["배포 전", "진행 중", "보기만 가능", "숨김"]
GRADES = ["탁월", "성취", "발전 중", "성장 중"]


def _timer_now():
    """Compare timer instants in UTC while course dates continue to use KST."""
    return datetime.fromisoformat(now()).astimezone(timezone.utc)


def _timer_instant(value):
    try:
        instant = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if instant.tzinfo is None:
        return None
    return instant.astimezone(timezone.utc)


def _duration(value, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, int) or not (0 if allow_zero else 1) <= value <= 1440:
        raise AppError("풀이 시간은 1~1440분으로 설정하세요. 시간 제한 없이 진행하려면 0분으로 설정하세요.")
    return value


def grade(attempt):
    if "assessment_result" in attempt:
        result = attempt.get("assessment_result")
        result = result if isinstance(result, dict) else {}
        score = result.get("score")
        if valid_score(score):
            return "탁월" if score >= 90 else "성취" if score >= 75 else "발전 중" if score >= 50 else "성장 중"
        return "교사 확인 필요" if result.get("feedback") or attempt.get("grading_error") else "평가 대기"
    feedback = attempt.get("feedback") or {}
    if feedback.get("needs_teacher_review") or feedback.get("correctness") == "uncertain":
        return "교사 확인 필요"
    score = feedback.get("explanation_score")
    if score is None:
        return "평가 대기"
    if feedback.get("correctness") == "correct" and score >= 4:
        return "탁월"
    if feedback.get("correctness") == "correct" and score >= 3:
        return "성취"
    return "발전 중" if score >= 2 else "성장 중"


def _score_comment(attempt):
    result = attempt.get("assessment_result")
    feedback = result.get("feedback") if isinstance(result, dict) else None
    if isinstance(feedback, dict) and "teacher_comment" in feedback:
        return feedback["teacher_comment"]
    if "grading_previous_comment" in attempt:
        return attempt["grading_previous_comment"]
    return attempt.get("teacher_comment", "")


class Classroom:
    def __init__(self, store):
        self.store = store

    def activities(self, course_id, status=None):
        values = self.store.read().get("course_activities", {}).values()
        return [a for a in values if a["course_id"] == course_id and (status is None or a["status"] == status)]

    def activity(self, aid):
        activity = self.store.read().get("course_activities", {}).get(aid)
        if not activity:
            raise AppError("활동을 찾을 수 없습니다.")
        return activity

    def ensure_desmos_activity(self, course):
        if activity_mode({"title": course.get("title", "")}) != "graph":
            return None
        course_id = course["id"]
        existing = [task for task in self.activities(course_id) if activity_mode(task) == "graph"]
        if existing:
            return sorted(existing, key=lambda task: task["status"] == "숨김")[0]["id"]
        aid = uuid.uuid5(uuid.NAMESPACE_URL, "think-learning/desmos/" + course_id).hex

        def change(state):
            current_course = state.get("courses", {}).get(course_id)
            if not current_course:
                raise AppError("수업을 찾을 수 없습니다.")
            if activity_mode({"title": current_course["title"]}) != "graph":
                return None
            activities = state.setdefault("course_activities", {})
            graphs = [task for task in activities.values()
                      if task["course_id"] == course_id and activity_mode(task) == "graph"]
            if graphs:
                return sorted(graphs, key=lambda task: task["status"] == "숨김")[0]["id"]
            if aid in activities:
                raise AppError("기본 데스모스 활동 식별자를 확인하세요.")
            timestamp = now()
            activities[aid] = dict(id=aid, course_id=course_id, title="데스모스 그래프",
                prompt="자유롭게 수식을 입력하고 그래프의 특징을 설명해보세요.",
                expected="입력한 수식과 그래프가 일치하고, 기울기·절편·교점 등 그래프의 특징을 근거와 함께 설명한다.",
                criteria=["수식에 맞는 그래프를 나타낸다", "그래프의 특징을 수식과 연결하여 설명한다"],
                max_attempts=2, start=timestamp[:10], end=None, mode="graph", quiz_options=[],
                status="배포 전", distribution_required=True, created=timestamp)
            return aid
        return self.store.transaction(change)

    def save_activity(self, course_id, title, prompt, expected, criteria, max_attempts, start, end, aid=None,
                      mode="writing", quiz_options=None, duration_minutes=None, expected_images=None,
                      question_files=None, curriculum=None):
        if (not isinstance(title, str) or not title.strip() or not isinstance(prompt, str) or
                not isinstance(expected, str) or not isinstance(criteria, (list, tuple)) or not criteria):
            raise AppError("활동 이름, 문제, 모범답안과 평가 기준을 모두 입력하세요.")
        if len(title) > 120 or max(len(prompt), len(expected)) > 10000 or not 1 <= max_attempts <= 10:
            raise AppError("입력 길이 또는 최대 시도 횟수를 확인하세요.")
        if len(criteria) > 8 or any(not isinstance(c, str) or not c.strip() or len(c) > 500 for c in criteria):
            raise AppError("평가 기준은 500자 이내로 최대 8개 입력하세요.")
        if end and end < start:
            raise AppError("마감일은 시작일 이후로 설정하세요.")
        mode = activity_mode(dict(title=title, mode=mode))
        if mode not in MODES:
            raise AppError("활동 모드를 확인하세요.")
        quiz_options = quiz_options or []
        if (not isinstance(quiz_options, list) or len(quiz_options) > 8 or
                any(not isinstance(o, str) or not o.strip() or len(o) > 500 for o in quiz_options) or
                len(set(quiz_options)) != len(quiz_options) or len(quiz_options) == 1):
            raise AppError("객관식 선택지는 서로 다른 내용으로 2~8개 입력하세요. 단답형은 선택지를 비워두세요.")
        if duration_minutes is not None:
            _duration(duration_minutes)
        aid = aid or uuid.uuid4().hex
        def change(state):
            if course_id not in state.get("courses", {}):
                raise AppError("수업을 찾을 수 없습니다.")
            activities = state.setdefault("course_activities", {})
            old = activities.get(aid, {})
            if old and old["course_id"] != course_id:
                raise AppError("활동의 수업이 일치하지 않습니다.")
            questions = owned_question_files(state,
                old.get("question_files", []) if question_files is None else question_files, course_id)
            if not prompt.strip() and not questions:
                raise AppError("학생에게 제시할 문제를 입력하거나 문제 파일을 첨부하세요.")
            for question in questions:
                for ref, digest, expected_bytes, limit in (
                    (question["blob_ref"], question["sha256"], question["bytes"],
                     600_000 if question["kind"] == "image" else 10_000_000),
                    (question["original_ref"], question["original_sha256"], question["original_bytes"], 10_000_000),
                ):
                    raw = self.store.get_blob(ref)
                    if (not raw or len(raw) != expected_bytes or len(raw) > limit or
                            hashlib.sha256(raw).hexdigest() != digest):
                        raise AppError("저장된 문제 파일을 확인할 수 없습니다. 다시 업로드하세요.")
            selected_curriculum = old.get("curriculum", {}) if curriculum is None else curriculum
            if not isinstance(selected_curriculum, dict):
                raise AppError("교육과정 선택 정보를 확인하세요.")
            if selected_curriculum:
                selected_curriculum = validate_selection(selected_curriculum)
                official = criteria_text(selected_curriculum["subject"], selected_curriculum["unit"],
                                         selected_curriculum["standard_codes"])
                if any(criterion not in criteria for criterion in official):
                    raise AppError("선택한 성취기준이 평가 기준에 포함되어야 합니다.")
            references = owned_reference_images(state,
                old.get("expected_images", []) if expected_images is None else expected_images, course_id)
            if not expected.strip() and not references:
                raise AppError("모범답안 내용을 입력하거나 모범답안 이미지를 첨부하세요.")
            for reference in references:
                raw = self.store.get_blob(reference["blob_ref"])
                if not raw or len(raw) > 600000 or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
                    raise AppError("저장된 모범답안 이미지를 확인할 수 없습니다. 다시 업로드하세요.")
            duration = old.get("duration_minutes", 0) if duration_minutes is None else duration_minutes
            if old.get("timer_started_at") and duration != old.get("duration_minutes", 0):
                raise AppError("평가 시작 후에는 평가 타이머에서 남은 시간을 조정하세요.")
            activities[aid] = dict(old, id=aid, course_id=course_id, title=title.strip(), prompt=prompt.strip(),
                expected=expected.strip(), criteria=criteria, max_attempts=max_attempts, start=start, end=end,
                expected_images=references, question_files=questions, curriculum=selected_curriculum,
                mode=mode, quiz_options=quiz_options if mode == "quiz" else [],
                status=old.get("status", "배포 전"), created=old.get("created", now()), duration_minutes=duration,
                distribution_required=old.get("distribution_required", not bool(old)))
        self.store.transaction(change)
        return aid

    def set_status(self, aid, status):
        if status not in STATUSES:
            raise AppError("상태를 확인하세요.")
        self.activity(aid)
        self.store.transaction(lambda s: s["course_activities"][aid].update(status=status))

    @staticmethod
    def is_distributed(task):
        """Keep legacy published activities available without backfilling state."""
        return not task.get("distribution_required", False) or bool(task.get("distributed_at"))

    @staticmethod
    def activity_within_dates(task):
        """Course dates include both boundaries and are compared in Korea time."""
        today = datetime.fromisoformat(now()).astimezone(KST).date().isoformat()
        start, end = task.get("start"), task.get("end")
        return (isinstance(start, str) and start <= today and
                (not end or isinstance(end, str) and today <= end))

    @staticmethod
    def _begin_timer(task, duration):
        instant = _timer_now()
        task.update(duration_minutes=duration, timer_started_at=instant.isoformat(timespec="seconds"),
                    timer_deadline=(instant + timedelta(minutes=duration)).isoformat(timespec="seconds"),
                    timer_ended_at=None)

    def distribute_activity(self, aid):
        """Publish a saved activity and start an in-period timer atomically."""
        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            if task.get("course_id") not in state.get("courses", {}):
                raise AppError("수업을 찾을 수 없습니다.")
            today = datetime.fromisoformat(now()).astimezone(KST).date().isoformat()
            if task.get("end") and task["end"] < today:
                raise AppError("마감일이 지난 활동입니다. 평가 기간을 수정한 뒤 배포하세요.")
            duration = _duration(task.get("duration_minutes", 0))
            task.update(status="진행 중", distributed_at=task.get("distributed_at") or now())
            if (duration and self.activity_within_dates(task) and not task.get("timer_started_at") and
                    not task.get("timer_ended_at")):
                self._begin_timer(task, duration)
            return task
        return self.store.transaction(change)

    def start_timer(self, aid, duration_minutes=None):
        """Start a shared assessment clock once after distribution."""
        if duration_minutes is not None:
            _duration(duration_minutes, allow_zero=False)
        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            if not self.is_distributed(task):
                raise AppError("학생에게 활동을 배포한 뒤 평가를 시작하세요.")
            duration = _duration(task.get("duration_minutes", 0) if duration_minutes is None else duration_minutes,
                                 allow_zero=False)
            if not self._within_submission_period(task):
                raise AppError("활동 상태와 시작일·마감일을 확인한 뒤 평가를 시작하세요.")
            if task.get("timer_started_at"):
                raise AppError("이미 시작한 평가입니다. 남은 시간을 조정하세요.")
            self._begin_timer(task, duration)
        self.store.transaction(change)

    def adjust_timer(self, aid, remaining_minutes):
        """Apply a teacher's new remaining time to every student, including after expiry."""
        _duration(remaining_minutes)
        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            if not task.get("timer_started_at"):
                raise AppError("평가를 시작한 뒤 남은 시간을 조정하세요.")
            if task.get("timer_ended_at"):
                raise AppError("교사가 종료한 평가입니다.")
            instant = _timer_now()
            task["timer_deadline"] = (instant + timedelta(minutes=remaining_minutes)).isoformat(timespec="seconds")
        self.store.transaction(change)

    def end_timer(self, aid):
        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            if not task.get("timer_started_at"):
                raise AppError("평가를 시작한 뒤 종료하세요.")
            if task.get("timer_ended_at"):
                return
            instant = _timer_now()
            deadline = _timer_instant(task.get("timer_deadline"))
            remaining = max(0, (deadline - instant).total_seconds()) if deadline else 0
            timestamp = instant.isoformat(timespec="seconds")
            task.update(timer_deadline=timestamp, timer_ended_at=timestamp,
                        timer_remaining_seconds_at_end=remaining)
        self.store.transaction(change)

    @staticmethod
    def timer_resume_minutes(task):
        """Suggest the saved time at explicit end, or the original duration."""
        seconds = task.get("timer_remaining_seconds_at_end", 0) if task.get("timer_ended_at") else 0
        if (isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and
                math.isfinite(seconds) and seconds >= 1):
            minutes = math.ceil(seconds / 60)
        else:
            minutes = task.get("duration_minutes", 0)
        return _duration(minutes, allow_zero=False)

    def resume_timer(self, aid, remaining_minutes=None):
        """Reopen an ended or expired assessment without resetting its history."""
        if remaining_minutes is not None:
            _duration(remaining_minutes, allow_zero=False)

        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            if task.get("course_id") not in state.get("courses", {}):
                raise AppError("수업을 찾을 수 없습니다.")
            if not self.is_distributed(task) or task.get("status") == "배포 전":
                raise AppError("학생에게 배포한 활동만 평가를 재개할 수 있습니다.")
            phase = self.timer_state(task)["phase"]
            if phase == "running":
                return task
            if not task.get("timer_ended_at") and phase != "expired":
                raise AppError("종료되었거나 풀이 시간이 끝난 평가만 재개할 수 있습니다.")
            minutes = self.timer_resume_minutes(task) if remaining_minutes is None else remaining_minutes
            instant = _timer_now()
            timestamp = instant.isoformat(timespec="seconds")
            today = instant.astimezone(KST).date().isoformat()
            deadline = instant + timedelta(minutes=minutes)
            deadline_day = deadline.astimezone(KST).date().isoformat()
            task.update(timer_deadline=deadline.isoformat(timespec="seconds"),
                        timer_ended_at=None, timer_resumed_at=timestamp, status="진행 중",
                        start=min(task["start"], today),
                        end=max(task["end"], deadline_day) if task.get("end") else None)
            return task

        return self.store.transaction(change)

    def attempts(self, aid):
        return sorted([a for a in self.store.read().get("course_attempts", {}).values() if a["activity_id"] == aid],
                      key=lambda a: (a["created"], a["number"]))

    @staticmethod
    def _within_submission_period(task):
        return (task.get("status") == "진행 중" and Classroom.is_distributed(task) and
                Classroom.activity_within_dates(task))

    @staticmethod
    def timer_state(task):
        duration = task.get("duration_minutes", 0)
        if not duration:
            return dict(phase="unlimited", remaining_seconds=None, duration_minutes=0)
        if task.get("timer_ended_at"):
            return dict(phase="ended", remaining_seconds=0, duration_minutes=duration)
        if not task.get("timer_started_at"):
            return dict(phase="waiting", remaining_seconds=duration * 60, duration_minutes=duration)
        deadline = _timer_instant(task.get("timer_deadline"))
        seconds = (deadline - _timer_now()).total_seconds() if deadline else 0
        return dict(phase="running" if seconds > 0 else "expired", remaining_seconds=max(0, math.ceil(seconds)),
                    duration_minutes=duration)

    @staticmethod
    def _can_submit(task):
        return (Classroom._within_submission_period(task) and
                Classroom.timer_state(task)["phase"] in ("unlimited", "running"))

    @staticmethod
    def student_activity_available(task):
        """Hide unpublished, out-of-period and inactive timed activities."""
        return (Classroom.is_distributed(task) and task.get("status") in ("진행 중", "보기만 가능") and
                Classroom.activity_within_dates(task) and
                Classroom.timer_state(task)["phase"] in ("unlimited", "running"))

    @staticmethod
    def student_unavailable_notice(task):
        """Distinguish the teacher ending an assessment from its date limits."""
        if (Classroom.is_distributed(task) and task.get("status") in ("진행 중", "보기만 가능") and
                task.get("timer_ended_at")):
            return "선생님이 평가를 종료했습니다."
        return "수행평가 기간이 아닙니다."

    def submit(self, aid, student_id, name, class_id, text, images, consent, request_id, preview=False,
               transcript="", audio=None, graph=None, quiz_answer=None, upload_ids=None):
        if (not all(isinstance(value, str) for value in (student_id, name, class_id, text, transcript)) or
                not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id)):
            raise AppError("학생 정보와 제출 식별자를 확인하세요.")
        student_id, name = student_id.strip(), name.strip()
        if not student_id or not name or len(student_id) > 40 or len(name) > 40:
            raise AppError("학번과 이름을 40자 이내로 입력하세요.")
        if not isinstance(images, (list, tuple)):
            raise AppError("답안 이미지 형식을 확인하세요.")
        state = self.store.read()

        def same_request(attempt):
            if (attempt["activity_id"] != aid or attempt["student_id"] != student_id or
                    attempt["class_id"] != class_id or bool(attempt["preview"]) != bool(preview)):
                raise AppError("다른 학생이나 활동의 제출 식별자를 사용할 수 없습니다.")
            return request_id

        existing = state.get("course_attempts", {}).get(request_id)
        if existing:
            return same_request(existing)
        task = state.get("course_activities", {}).get(aid)
        if not task:
            raise AppError("활동을 찾을 수 없습니다.")
        upload_ids = [] if upload_ids is None else upload_ids
        selected_uploads = owned_uploads(state, upload_ids, aid, student_id, class_id, preview)
        mode = activity_mode(task)
        graph_data = None
        graph_source = None
        images = list(images)
        if mode == "graph":
            if isinstance(graph, dict) and graph.get("mode") == "embed":
                # The official embedded site cannot expose state or screenshots
                # across origins. Keep the student's actual explanation/uploads.
                graph_source = "embed"
            else:
                graph_source = "sdk"
                graph_data, capture = validated_graph(graph)
                images.insert(0, capture)
        if mode == "quiz":
            if not isinstance(quiz_answer, str) or not quiz_answer.strip() or len(quiz_answer) > 2000:
                raise AppError("퀴즈 답을 입력하거나 선택하세요.")
            if task.get("quiz_options") and quiz_answer not in task["quiz_options"]:
                raise AppError("퀴즈 선택지를 확인하세요.")
        else:
            quiz_answer = None
        if audio is not None:
            audio = validate_audio(audio)
        if not (text.strip() or images or selected_uploads or transcript.strip() or audio or quiz_answer):
            raise AppError("답안을 입력하세요.")
        if len(text) + len(transcript) > 12000 or len(images) + len(selected_uploads) > 3:
            raise AppError("학생 정보나 답안의 허용 길이를 초과했습니다.")
        for raw in images:
            if not isinstance(raw, (bytes, bytearray)) or not raw or len(raw) > 600000:
                raise AppError("답안 이미지를 600KB 이하로 저장하세요.")
        upload_service = UploadedFiles(self.store)
        for upload in selected_uploads:
            upload_service.read(upload, aid, student_id, class_id, preview)
        if not self._can_submit(task):
            raise AppError("현재 제출할 수 없는 활동입니다.")
        course = state.get("courses", {}).get(task["course_id"])
        if not course or class_id not in course["classes"]:
            raise AppError("참여 대상 학급을 확인하세요.")

        def previous_attempts(attempts):
            return [attempt for attempt in attempts.values() if attempt["activity_id"] == aid and
                    attempt["student_id"] == student_id and attempt["class_id"] == class_id and
                    bool(attempt["preview"]) == bool(preview)]

        if len(previous_attempts(state.get("course_attempts", {}))) >= task["max_attempts"]:
            raise AppError("최대 시도 횟수에 도달했습니다.")
        refs = []
        for raw in images:
            ref = uuid.uuid4().hex
            self.store.put_blob(ref, bytes(raw))
            refs.append(ref)
        refs.extend(upload["blob_ref"] for upload in selected_uploads if upload_kind(upload) == "image")
        audio_ref = None
        if audio:
            audio_ref = uuid.uuid4().hex
            self.store.put_blob(audio_ref, audio)

        def change(state):
            attempts = state.setdefault("course_attempts", {})
            if request_id in attempts:
                return same_request(attempts[request_id])
            current = state.get("course_activities", {}).get(aid)
            if not current or not self._can_submit(current):
                raise AppError("현재 제출할 수 없는 활동입니다.")
            if (any(task.get(field) != current.get(field) for field in
                    ("prompt", "expected", "criteria", "mode", "quiz_options")) or
                    task.get("expected_images", []) != current.get("expected_images", []) or
                    task.get("question_files", []) != current.get("question_files", []) or
                    task.get("curriculum", {}) != current.get("curriculum", {})):
                raise AppError("활동 내용이 변경되었습니다. 새 문제를 확인한 뒤 다시 제출하세요.")
            course = state.get("courses", {}).get(current["course_id"])
            if not course or class_id not in course["classes"]:
                raise AppError("참여 대상 학급을 확인하세요.")
            current_uploads = owned_uploads(state, upload_ids, aid, student_id, class_id, preview)
            if current_uploads != selected_uploads:
                raise AppError("업로드 파일이 변경되었습니다. 파일을 다시 확인하세요.")
            for upload in current_uploads:
                upload_service.read(upload, aid, student_id, class_id, preview)
            previous = previous_attempts(attempts)
            if len(previous) >= current["max_attempts"]:
                raise AppError("최대 시도 횟수에 도달했습니다.")
            attempt = dict(id=request_id, activity_id=aid, course_id=current["course_id"], student_id=student_id,
                name=name, class_id=class_id, text=text.strip(), images=refs, number=len(previous)+1,
                created=now(), feedback=None, teacher_comment="", consent=bool(consent), preview=bool(preview),
                transcript=transcript.strip(), audio=audio_ref, graph=graph_data, quiz_answer=quiz_answer,
                graph_source=graph_source,
                upload_ids=list(upload_ids),
                documents=copy.deepcopy([upload for upload in current_uploads if upload_kind(upload) == "pdf"]),
                mode=mode, reflection="", activity_snapshot=copy.deepcopy(current))
            attempt["submission_file"] = student_submission_path(attempt)
            attempts[request_id] = attempt
            return request_id
        return self.store.transaction(change)

    def evaluate(self, attempt_id, ai):
        attempt = self.store.read()["course_attempts"][attempt_id]
        if not attempt["consent"]:
            raise AppError("학생이 AI 피드백 사용에 동의하지 않았습니다.")
        if attempt["activity_snapshot"].get("question_files"):
            raise AppError("문제 파일이 첨부된 활동은 교사가 직접 평가해 주세요. 현재 AI 평가는 첨부 문제 파일을 읽지 않습니다.")
        if attempt["activity_snapshot"].get("expected_images"):
            raise AppError("모범답안 이미지가 첨부된 활동은 교사가 직접 평가해 주세요. 현재 AI 평가는 이미지 모범답안을 비교하지 않습니다.")
        if not ai.available:
            raise AppError("AI 연결이 설정되지 않았습니다. 답안은 저장되었습니다.")
        if attempt.get("audio") and not attempt.get("transcript"):
            transcript = ai.transcribe(self.store.get_blob(attempt["audio"]))
            self.store.transaction(lambda s: s["course_attempts"][attempt_id].update(transcript=transcript))
            attempt["transcript"] = transcript
        images = [self.store.get_blob(ref) for ref in attempt["images"]]
        documents = [(document["filename"], raw) for document, raw in student_pdf_attachments(self.store, attempt)]
        if documents:
            feedback = ai.feedback(attempt["activity_snapshot"], attempt, images, documents=documents)
        else:
            feedback = ai.feedback(attempt["activity_snapshot"], attempt, images)
        self.store.transaction(lambda s: s["course_attempts"][attempt_id].update(feedback=feedback, feedback_at=now(), error=""))

    @staticmethod
    def _grading_attempt(state, attempt_id):
        attempt = state.get("course_attempts", {}).get(attempt_id)
        if not isinstance(attempt, dict):
            raise AppError("채점할 학생 답안을 찾을 수 없습니다.")
        task = attempt.get("activity_snapshot")
        if (not isinstance(task, dict) or task.get("id") != attempt.get("activity_id") or
                task.get("course_id") != attempt.get("course_id") or
                attempt.get("course_id") not in state.get("courses", {})):
            raise AppError("제출 당시의 수업과 평가 정보를 확인할 수 없습니다.")
        return attempt

    @staticmethod
    def _grading_input(attempt):
        fields = ("id", "activity_id", "course_id", "student_id", "name", "class_id", "preview",
                  "text", "images", "transcript", "audio", "graph", "quiz_answer", "mode", "reflection",
                  "documents", "upload_ids", "activity_snapshot")
        return {field: copy.deepcopy(attempt.get(field)) for field in fields}

    def grade_attempt(self, attempt_id, ai, publish=False):
        """Teacher-initiated grading; student optional feedback consent is separate."""
        if type(publish) is not bool:
            raise AppError("점수 공개 방법을 확인하세요.")
        if not ai.available:
            raise AppError("AI 연결을 설정한 뒤 자동 채점하세요. 교사가 점수를 직접 입력할 수도 있습니다.")
        token = uuid.uuid4().hex

        def begin(state):
            attempt = self._grading_attempt(state, attempt_id)
            previous_comment = _score_comment(attempt)
            # Unpublish before the remote call, including retries and failures.
            attempt["assessment_result"] = dict(score=None, max_score=100, feedback=None, status="review")
            attempt.update(grading_token=token, grading_started_at=now(), grading_error="",
                           grading_previous_comment=previous_comment)
            return attempt, previous_comment

        attempt, previous_comment = self.store.transaction(begin)
        original = self._grading_input(attempt)
        try:
            task = copy.deepcopy(attempt["activity_snapshot"])
            images = []
            for ref in attempt.get("images", []):
                raw = self.store.get_blob(ref)
                if not isinstance(raw, bytes) or not raw or len(raw) > 600_000:
                    raise AppError("저장된 학생 답안 이미지를 확인할 수 없습니다.")
                images.append(raw)
            documents = [(document["filename"], raw)
                         for document, raw in student_pdf_attachments(self.store, attempt)]
            state = self.store.read()
            questions = owned_question_files(state, task.get("question_files", []), attempt["course_id"])
            references = owned_reference_images(state, task.get("expected_images", []), attempt["course_id"])
            question_files, expected_images = [], []
            for question in questions:
                raw = self.store.get_blob(question["blob_ref"])
                if (not isinstance(raw, bytes) or len(raw) != question["bytes"] or
                        hashlib.sha256(raw).hexdigest() != question["sha256"]):
                    raise AppError("저장된 문제 파일을 확인할 수 없습니다.")
                question_files.append((question, raw))
            for reference in references:
                raw = self.store.get_blob(reference["blob_ref"])
                if (not isinstance(raw, bytes) or len(raw) != reference["bytes"] or
                        hashlib.sha256(raw).hexdigest() != reference["sha256"]):
                    raise AppError("저장된 모범답안 이미지를 확인할 수 없습니다.")
                expected_images.append(raw)
            raw_result = ai.grade(copy.deepcopy(task), copy.deepcopy(attempt), images, documents=documents,
                                  question_files=question_files, expected_images=expected_images)
            score, feedback = validated_grading(raw_result, task["criteria"])
            if isinstance(previous_comment, str):
                feedback["teacher_comment"] = previous_comment
            if attempt.get("audio") and not attempt.get("transcript"):
                score = None
                feedback["needs_teacher_review"] = True
            timestamp = now()
            result = dict(score=score, max_score=100, feedback=feedback,
                          status="published" if publish and score is not None else "review", graded_at=timestamp)
            if result["status"] == "published":
                result["published_at"] = timestamp

            def finish(state):
                current = self._grading_attempt(state, attempt_id)
                if current.get("grading_token") != token or self._grading_input(current) != original:
                    raise AppError("채점 중 답안 또는 교사 평가가 변경되었습니다. 현재 내용을 확인한 뒤 다시 채점하세요.")
                current["assessment_result"] = result
                current["grading_error"] = ""
                current.pop("grading_token", None)
                current.pop("grading_previous_comment", None)
                return result

            return self.store.transaction(finish)
        except Exception as exc:
            message = str(exc) if isinstance(exc, AppError) else "자동 채점에 실패했습니다. 다시 시도하거나 교사가 직접 검토하세요."

            def failed(state):
                current = state.get("course_attempts", {}).get(attempt_id)
                if isinstance(current, dict) and current.get("grading_token") == token:
                    current["grading_error"] = message
                    current.pop("grading_token", None)

            self.store.transaction(failed)
            if isinstance(exc, AppError):
                raise
            raise AppError(message) from None

    def publish_score(self, attempt_id):
        """Only a durable, definite score can become student-visible."""
        def change(state):
            attempt = self._grading_attempt(state, attempt_id)
            result = attempt.get("assessment_result")
            if (not isinstance(result, dict) or not valid_score(result.get("score")) or
                    result.get("max_score") != 100 or result.get("status") not in ("review", "published")):
                raise AppError("점수를 확인하거나 직접 입력한 뒤 공개하세요.")
            feedback = result.get("feedback") or {}
            if not result.get("reviewed_at") and (feedback.get("needs_teacher_review") or
                    feedback.get("correctness") == "uncertain" or
                    any(item.get("level") == "uncertain" for item in feedback.get("criteria", []))):
                raise AppError("불확실한 채점 결과는 교사가 점수를 확인한 뒤 공개하세요.")
            if result["status"] != "published":
                result.update(status="published", published_at=now())
            attempt.pop("grading_token", None)
            return result
        return self.store.transaction(change)

    def review_score(self, attempt_id, score, comment="", publish=False):
        if not valid_score(score):
            raise AppError("점수는 0~100점으로 입력하세요.")
        if not isinstance(comment, str) or len(comment) > 3000:
            raise AppError("피드백은 3000자 이내로 입력하세요.")
        if type(publish) is not bool:
            raise AppError("점수 공개 방법을 확인하세요.")

        def change(state):
            attempt = self._grading_attempt(state, attempt_id)
            previous = attempt.get("assessment_result")
            previous = previous if isinstance(previous, dict) else {}
            timestamp = now()
            result = dict(score=score, max_score=100,
                          feedback=reviewed_feedback(previous.get("feedback"), comment.strip()),
                          status="published" if publish else "review", reviewed_at=timestamp)
            if previous.get("graded_at"):
                result["graded_at"] = previous["graded_at"]
            if publish:
                result["published_at"] = timestamp
            attempt["assessment_result"] = result
            attempt["grading_error"] = ""
            attempt.pop("grading_token", None)
            attempt.pop("grading_previous_comment", None)
            return result
        return self.store.transaction(change)

    def comment(self, attempt_id, comment):
        if len(comment) > 3000:
            raise AppError("피드백은 3000자 이내로 입력하세요.")
        self.store.transaction(lambda s: s["course_attempts"][attempt_id].update(teacher_comment=comment, reviewed=now()))

    def export(self, course_id, aid=None):
        activities = self.activities(course_id)
        if aid:
            activities = [a for a in activities if a["id"] == aid]
        attempts = [a for task in activities for a in self.attempts(task["id"]) if not a["preview"]]
        names = {a["id"]: a["title"] for a in activities}
        rows = [dict(학급=a["class_id"], 학번=a["student_id"], 이름=a["name"], 활동=names[a["activity_id"]],
                     시도=a["number"], 제출일시=a["created"], 평가=grade(a), 답안=a["text"],
                     모드=MODES.get(a.get("mode", "writing")), 퀴즈답=a.get("quiz_answer") or "",
                     음성전사=a.get("transcript", ""), 그래프수식=json.dumps((a.get("graph") or {}).get("expressions", []), ensure_ascii=False),
                     AI피드백=json.dumps((a.get("assessment_result") or {}).get("feedback", a["feedback"]), ensure_ascii=False),
                     교사피드백=_score_comment(a), 점수=(a.get("assessment_result") or {}).get("score"),
                     만점=(a.get("assessment_result") or {}).get("max_score"),
                     점수공개상태=(a.get("assessment_result") or {}).get("status", ""),
                     점수공개일시=(a.get("assessment_result") or {}).get("published_at", "")) for a in attempts]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("학생결과.csv", safe_csv(rows) if rows else "학급,학번,이름,활동,시도\n".encode("utf-8-sig"))
            archive.writestr("전체기록.json", json.dumps(dict(activities=activities, attempts=attempts), ensure_ascii=False, indent=2))
            exported_questions = set()
            for task in activities + [attempt["activity_snapshot"] for attempt in attempts]:
                for question in owned_question_files(self.store.read(), task.get("question_files", []), course_id):
                    if question["id"] in exported_questions:
                        continue
                    raw = self.store.get_blob(question["original_ref"])
                    if not raw or hashlib.sha256(raw).hexdigest() != question["original_sha256"]:
                        raise AppError("내보낼 문제 파일을 확인할 수 없습니다.")
                    archive.writestr(f"문제/{question['id']}/{question['filename']}", raw)
                    exported_questions.add(question["id"])
            for attempt in attempts:
                for index, ref in enumerate(attempt["images"]):
                    archive.writestr(f"답안/{attempt['id']}/{index+1}.jpg", self.store.get_blob(ref))
                for index, (document, raw) in enumerate(student_pdf_attachments(self.store, attempt)):
                    archive.writestr(f"답안/{attempt['id']}/첨부-{index+1}-{document['filename']}", raw)
                if attempt.get("audio"):
                    archive.writestr(f"답안/{attempt['id']}/녹음.wav", self.store.get_blob(attempt["audio"]))
                if attempt.get("graph"):
                    archive.writestr(f"답안/{attempt['id']}/그래프.json", json.dumps(attempt["graph"], ensure_ascii=False))
        return output.getvalue()
