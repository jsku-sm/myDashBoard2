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

from .courses import now
from .service import safe_csv
from .storage import AppError, student_submission_path
from .media import MODES, activity_mode, validate_audio, validated_graph
from .uploads import owned_uploads
from .reference_images import owned_reference_images

STATUSES = ["진행 중", "보기만 가능", "숨김"]
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
                max_attempts=5, start=timestamp[:10], end=None, mode="graph", quiz_options=[],
                status="진행 중", created=timestamp)
            return aid
        return self.store.transaction(change)

    def save_activity(self, course_id, title, prompt, expected, criteria, max_attempts, start, end, aid=None,
                      mode="writing", quiz_options=None, duration_minutes=None, expected_images=None):
        if (not all(isinstance(v, str) and v.strip() for v in (title, prompt)) or
                not isinstance(expected, str) or not criteria):
            raise AppError("활동 이름, 문제, 모범답안과 평가 기준을 모두 입력하세요.")
        if len(title) > 120 or max(len(prompt), len(expected)) > 10000 or not 1 <= max_attempts <= 10:
            raise AppError("입력 길이 또는 최대 시도 횟수를 확인하세요.")
        if len(criteria) > 8 or any(not c.strip() or len(c) > 500 for c in criteria):
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
                expected_images=references,
                mode=mode, quiz_options=quiz_options if mode == "quiz" else [],
                status=old.get("status", "진행 중"), created=old.get("created", now()), duration_minutes=duration)
        self.store.transaction(change)
        return aid

    def set_status(self, aid, status):
        if status not in STATUSES:
            raise AppError("상태를 확인하세요.")
        self.activity(aid)
        self.store.transaction(lambda s: s["course_activities"][aid].update(status=status))

    def start_timer(self, aid, duration_minutes=None):
        """Start a shared assessment clock once, at the teacher's distribution time."""
        if duration_minutes is not None:
            _duration(duration_minutes, allow_zero=False)
        def change(state):
            task = state.get("course_activities", {}).get(aid)
            if not task:
                raise AppError("활동을 찾을 수 없습니다.")
            duration = _duration(task.get("duration_minutes", 0) if duration_minutes is None else duration_minutes,
                                 allow_zero=False)
            if not self._within_submission_period(task):
                raise AppError("활동 상태와 시작일·마감일을 확인한 뒤 평가를 시작하세요.")
            if task.get("timer_started_at"):
                raise AppError("이미 시작한 평가입니다. 남은 시간을 조정하세요.")
            instant = _timer_now()
            task.update(duration_minutes=duration, timer_started_at=instant.isoformat(timespec="seconds"),
                        timer_deadline=(instant + timedelta(minutes=duration)).isoformat(timespec="seconds"),
                        timer_ended_at=None)
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
            instant = _timer_now().isoformat(timespec="seconds")
            task.update(timer_deadline=instant, timer_ended_at=instant)
        self.store.transaction(change)

    def attempts(self, aid):
        return sorted([a for a in self.store.read().get("course_attempts", {}).values() if a["activity_id"] == aid],
                      key=lambda a: (a["created"], a["number"]))

    @staticmethod
    def _within_submission_period(task):
        today = now()[:10]
        return task["status"] == "진행 중" and task["start"] <= today and (not task["end"] or today <= task["end"])

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
        for upload in selected_uploads:
            raw = self.store.get_blob(upload["blob_ref"])
            if len(raw) > 600000 or hashlib.sha256(raw).hexdigest() != upload["sha256"]:
                raise AppError("저장된 업로드 이미지를 확인할 수 없습니다. 파일을 다시 올려주세요.")
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
        refs.extend(upload["blob_ref"] for upload in selected_uploads)
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
                    task.get("expected_images", []) != current.get("expected_images", [])):
                raise AppError("활동 내용이 변경되었습니다. 새 문제를 확인한 뒤 다시 제출하세요.")
            course = state.get("courses", {}).get(current["course_id"])
            if not course or class_id not in course["classes"]:
                raise AppError("참여 대상 학급을 확인하세요.")
            current_uploads = owned_uploads(state, upload_ids, aid, student_id, class_id, preview)
            if current_uploads != selected_uploads:
                raise AppError("업로드 파일이 변경되었습니다. 파일을 다시 확인하세요.")
            previous = previous_attempts(attempts)
            if len(previous) >= current["max_attempts"]:
                raise AppError("최대 시도 횟수에 도달했습니다.")
            attempt = dict(id=request_id, activity_id=aid, course_id=current["course_id"], student_id=student_id,
                name=name, class_id=class_id, text=text.strip(), images=refs, number=len(previous)+1,
                created=now(), feedback=None, teacher_comment="", consent=bool(consent), preview=bool(preview),
                transcript=transcript.strip(), audio=audio_ref, graph=graph_data, quiz_answer=quiz_answer,
                graph_source=graph_source,
                upload_ids=list(upload_ids),
                mode=mode, reflection="", activity_snapshot=copy.deepcopy(current))
            attempt["submission_file"] = student_submission_path(attempt)
            attempts[request_id] = attempt
            return request_id
        return self.store.transaction(change)

    def evaluate(self, attempt_id, ai):
        attempt = self.store.read()["course_attempts"][attempt_id]
        if not attempt["consent"]:
            raise AppError("학생이 AI 피드백 사용에 동의하지 않았습니다.")
        if attempt["activity_snapshot"].get("expected_images"):
            raise AppError("모범답안 이미지가 첨부된 활동은 교사가 직접 평가해 주세요. 현재 AI 평가는 이미지 모범답안을 비교하지 않습니다.")
        if not ai.available:
            raise AppError("AI 연결이 설정되지 않았습니다. 답안은 저장되었습니다.")
        if attempt.get("audio") and not attempt.get("transcript"):
            transcript = ai.transcribe(self.store.get_blob(attempt["audio"]))
            self.store.transaction(lambda s: s["course_attempts"][attempt_id].update(transcript=transcript))
            attempt["transcript"] = transcript
        feedback = ai.feedback(attempt["activity_snapshot"], attempt,
                               [self.store.get_blob(ref) for ref in attempt["images"]])
        self.store.transaction(lambda s: s["course_attempts"][attempt_id].update(feedback=feedback, error=""))

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
                     AI피드백=json.dumps(a["feedback"], ensure_ascii=False), 교사피드백=a["teacher_comment"]) for a in attempts]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("학생결과.csv", safe_csv(rows) if rows else "학급,학번,이름,활동,시도\n".encode("utf-8-sig"))
            archive.writestr("전체기록.json", json.dumps(dict(activities=activities, attempts=attempts), ensure_ascii=False, indent=2))
            for attempt in attempts:
                for index, ref in enumerate(attempt["images"]):
                    archive.writestr(f"답안/{attempt['id']}/{index+1}.jpg", self.store.get_blob(ref))
                if attempt.get("audio"):
                    archive.writestr(f"답안/{attempt['id']}/녹음.wav", self.store.get_blob(attempt["audio"]))
                if attempt.get("graph"):
                    archive.writestr(f"답안/{attempt['id']}/그래프.json", json.dumps(attempt["graph"], ensure_ascii=False))
        return output.getvalue()
