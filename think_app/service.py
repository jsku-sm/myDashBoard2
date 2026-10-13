import base64
import copy
import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from collections import Counter
from .storage import AppError

CLASSES = [f"1-{i}" for i in range(1, 8)]
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


def pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()


def pw_check(password, encoded):
    return hmac.compare_digest(pw_hash(password, encoded.split("$")[0]), encoded)


def require_password(password):
    if len(password) < 10 or len(password) > 128:
        raise AppError("비밀번호는 10~128자로 입력하세요.")


def public_user(user):
    return {k: user[k] for k in ("id", "name", "role", "class_id")}


def safe_csv(rows):
    if not rows:
        return b""
    f = io.StringIO()
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
                         for k, v in row.items()})
    return f.getvalue().encode("utf-8-sig")


class Service:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def bootstrap(self):
        if self.store.read()["users"]:
            return
        if self.settings.mode == "demo":
            self._demo_seed()
            return
        require_password(self.settings.teacher_password)
        teacher_id = self.settings.teacher_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", teacher_id):
            raise AppError("교사 아이디는 영문·숫자 3~40자로 설정하세요.")
        user = {"id": teacher_id, "name": "구쌤", "role": "teacher", "class_id": "",
                "password": pw_hash(self.settings.teacher_password), "version": 1, "active": True}
        def change(s):
            if not s["users"]:
                s["users"][teacher_id] = user
        self.store.transaction(change)

    def _demo_seed(self):
        def change(s):
            if s["users"]:
                return
            for uid, name, role, cls in [("demo_teacher", "구쌤", "teacher", ""),
                                        ("10101", "연습학생", "student", "1-1")]:
                s["users"][uid] = {"id": uid, "name": name, "role": role, "class_id": cls,
                                   "password": pw_hash(secrets.token_urlsafe(24)), "version": 1, "active": True}
            s["classes"]["1-1"] = {"code_hash": "", "created": now()}
            s["activities"]["demo_circle"] = {
                "id": "demo_circle", "title": "원의 중심은 어디에 있을까?", "subject": "공통수학2",
                "prompt": "원의 방정식 (x-2)²+(y+1)²=9에서 중심과 반지름을 구하세요. 부호를 어떻게 판단했는지 설명하고 좌표평면에 그려 보세요.",
                "expected": "중심은 (2, -1), 반지름은 3. (x-a)²+(y-b)²=r²와 비교한다. y+1=y-(-1)이므로 중심의 y좌표는 -1이다.",
                "criteria": ["원의 표준형과 비교하여 중심을 설명한다.", "반지름의 제곱과 반지름을 구분한다.", "그림·식·말의 연결을 설명한다."],
                "classes": ["1-1"], "max_attempts": 5, "created": now(), "open": True,
                "creator": "demo_teacher"}
        self.store.transaction(change)

    def _token(self, user):
        body = base64.urlsafe_b64encode(json.dumps({"id": user["id"], "v": user["version"],
                    "exp": int(time.time()) + 8 * 3600}).encode()).decode()
        sig = hmac.new(self.store.signing_key, body.encode(), hashlib.sha256).hexdigest()
        return body + "." + sig

    def user(self, token, state=None, teacher=False):
        try:
            body, signature = token.split(".")
            expected = hmac.new(self.store.signing_key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(body))
            user = (state or self.store.read())["users"][data["id"]]
            if data["exp"] < time.time() or data["v"] != user["version"] or not user["active"]:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AppError("로그인이 만료되었습니다. 다시 로그인하세요.") from None
        if teacher and user["role"] != "teacher":
            raise AppError("교사만 사용할 수 있는 기능입니다.")
        return user

    def demo_login(self, role):
        if self.settings.mode != "demo":
            raise AppError("체험 로그인은 운영 모드에서 사용할 수 없습니다.")
        uid = "demo_teacher" if role == "teacher" else "10101"
        return self._token(self.store.read()["users"][uid])

    def login(self, uid, password):
        uid = uid.strip()
        bucket = hashlib.sha256(uid.encode()).hexdigest()
        def change(s):
            # Persist failures even when credentials are wrong.
            failures = [t for t in s["login_failures"].get(bucket, []) if t > time.time() - 300]
            if len(failures) >= 5:
                return {"error": "로그인 시도가 많습니다. 5분 후 다시 시도하세요."}
            user = s["users"].get(uid)
            valid = user and user["active"] and pw_check(password, user["password"])
            if not valid:
                s["login_failures"][bucket] = failures + [time.time()]
                return {"error": "아이디 또는 비밀번호를 확인하세요."}
            s["login_failures"].pop(bucket, None)
            return {"user": user}
        result = self.store.transaction(change)
        if "error" in result:
            raise AppError(result["error"])
        return self._token(result["user"])

    def change_password(self, token, old, new):
        require_password(new)
        def change(s):
            u = self.user(token, s)
            if not pw_check(old, u["password"]):
                raise AppError("현재 비밀번호를 확인하세요.")
            u["password"], u["version"] = pw_hash(new), u["version"] + 1
        self.store.transaction(change)

    def class_code(self, token, class_id):
        if class_id not in CLASSES:
            raise AppError("학급을 확인하세요.")
        code = secrets.token_hex(4).upper()
        def change(s):
            self.user(token, s, teacher=True)
            s["classes"][class_id] = {"code_hash": hashlib.sha256(code.encode()).hexdigest(), "created": now()}
        self.store.transaction(change)
        return code

    def register(self, uid, name, class_id, code, password):
        uid, name = uid.strip(), name.strip()
        if not re.fullmatch(r"\d{4,10}", uid) or not name or len(name) > 40:
            raise AppError("학번(숫자 4~10자리)과 이름(40자 이내)을 확인하세요.")
        require_password(password)
        hashed = pw_hash(password)
        def change(s):
            cls = s["classes"].get(class_id)
            if not cls or not hmac.compare_digest(cls["code_hash"], hashlib.sha256(code.strip().upper().encode()).hexdigest()):
                raise AppError("학급 또는 교사 발급 가입코드를 확인하세요.")
            if uid in s["users"]:
                raise AppError("이미 등록된 학번입니다. 로그인하거나 선생님께 문의하세요.")
            s["users"][uid] = {"id": uid, "name": name, "role": "student", "class_id": class_id,
                               "password": hashed, "active": True, "version": 1}
        self.store.transaction(change)

    def create_activity(self, token, title, prompt, expected, criteria, classes, max_attempts, subject):
        if not title.strip() or not prompt.strip() or not expected.strip() or not criteria or not classes:
            raise AppError("제목·문제·모범 풀이·평가 기준·배정 학급을 모두 입력하세요.")
        if len(title) > 120 or max(map(len, [prompt, expected])) > 10000 or len(criteria) > 8:
            raise AppError("제목은 120자, 문제·모범풀이는 각 10000자, 평가 기준은 8개까지 가능합니다.")
        if not 1 <= int(max_attempts) <= 10 or any(len(c) > 500 for c in criteria):
            raise AppError("시도 횟수는 1~10회, 평가 기준은 항목당 500자 이내로 입력하세요.")
        aid = uuid.uuid4().hex
        def change(s):
            teacher = self.user(token, s, teacher=True)
            if any(c not in s["classes"] for c in classes):
                raise AppError("먼저 학급 가입코드를 발급해 학급을 열어주세요.")
            s["activities"][aid] = {"id": aid, "title": title.strip(), "prompt": prompt.strip(),
                "expected": expected.strip(), "criteria": criteria, "classes": classes,
                "max_attempts": int(max_attempts), "subject": subject, "creator": teacher["id"],
                "created": now(), "open": True}
            return aid
        return self.store.transaction(change)

    def toggle_activity(self, token, aid):
        def change(s):
            self.user(token, s, teacher=True)
            s["activities"][aid]["open"] = not s["activities"][aid]["open"]
        self.store.transaction(change)

    def snapshot(self, token):
        s = self.store.read()
        u = self.user(token, s)
        teacher = u["role"] == "teacher"
        tasks = [copy.deepcopy(a) for a in s["activities"].values() if teacher or u["class_id"] in a["classes"]]
        if not teacher:
            for task in tasks:
                task.pop("expected", None)
        attempts = [self._public_attempt(a, teacher) for a in s["attempts"].values() if teacher or a["student_id"] == u["id"]]
        users = [public_user(x) for x in s["users"].values() if teacher or x["id"] == u["id"]]
        return {"user": public_user(u), "classes": list(s["classes"]) if teacher else [u["class_id"]],
                "activities": tasks, "attempts": sorted(attempts, key=lambda a: (a["created"], a["number"])), "users": users}

    @staticmethod
    def _public_attempt(a, teacher=False):
        a = copy.deepcopy(a)
        a.pop("lease", None)
        a.pop("lease_until", None)
        a.pop("activity_snapshot", None)
        return a

    def _access_attempt(self, token, attempt_id, s):
        user = self.user(token, s)
        a = s["attempts"].get(attempt_id)
        if not a or (user["role"] != "teacher" and a["student_id"] != user["id"]):
            raise AppError("이 제출물을 볼 권한이 없습니다.")
        return user, a

    def submit(self, token, aid, text, transcript, images, reflection, consent, request_id):
        if not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise AppError("제출 식별자를 다시 생성하세요.")
        if not text.strip() and not transcript.strip() and not images:
            raise AppError("설명, 음성 전사 또는 풀이 이미지를 한 가지 이상 남겨주세요.")
        if len(text) + len(transcript) > 12000 or len(reflection) > 2000 or len(images) > 2:
            raise AppError("설명은 12000자, 성찰은 2000자, 이미지는 2개까지 제출할 수 있습니다.")
        s = self.store.read()
        u = self.user(token, s)
        if u["role"] != "student":
            raise AppError("학생 계정으로 제출하세요.")
        if request_id in s["attempts"]:
            self._access_attempt(token, request_id, s)
            return request_id
        activity = s["activities"].get(aid)
        if not activity or u["class_id"] not in activity["classes"] or not activity["open"]:
            raise AppError("현재 제출할 수 없는 과제입니다.")
        refs = []
        for data in images:
            if len(data) > 600000:
                raise AppError("이미지가 너무 큽니다. 더 작게 저장하세요.")
            bid = uuid.uuid4().hex
            self.store.put_blob(bid, data)
            refs.append(bid)
        def change(s):
            user = self.user(token, s)
            task = s["activities"].get(aid)
            if request_id in s["attempts"]:
                self._access_attempt(token, request_id, s)
                return request_id
            if not task or user["class_id"] not in task["classes"] or not task["open"]:
                raise AppError("현재 제출할 수 없는 과제입니다.")
            previous = [a for a in s["attempts"].values() if a["activity_id"] == aid and a["student_id"] == user["id"]]
            if len(previous) >= task["max_attempts"]:
                raise AppError("이 과제의 최대 제출 횟수에 도달했습니다.")
            s["attempts"][request_id] = {"id": request_id, "activity_id": aid, "student_id": user["id"],
                "class_id": user["class_id"], "number": len(previous) + 1, "created": now(),
                "text": text.strip(), "transcript": transcript.strip(), "images": refs,
                "reflection": reflection.strip(), "consent": bool(consent), "status": "pending",
                "feedback": None, "review": None, "ai_runs": 0, "activity_snapshot": copy.deepcopy(task)}
            return request_id
        return self.store.transaction(change)

    def image(self, token, attempt_id, index):
        _, a = self._access_attempt(token, attempt_id, self.store.read())
        return self.store.get_blob(a["images"][index])

    def allow_ai(self, token, attempt_id):
        def change(s):
            u, a = self._access_attempt(token, attempt_id, s)
            if u["id"] != a["student_id"]:
                raise AppError("학생 본인이 AI 사용을 선택해야 합니다.")
            a["consent"] = True
        self.store.transaction(change)

    def evaluate(self, token, attempt_id, ai):
        if not ai.available:
            raise AppError("AI 연결이 설정되지 않았습니다. 제출물은 저장되어 있습니다.")
        lease = uuid.uuid4().hex
        def reserve(s):
            _, a = self._access_attempt(token, attempt_id, s)
            if not a["consent"]:
                raise AppError("학생이 AI 피드백 사용에 동의하지 않은 제출물입니다.")
            if a["status"] == "ready":
                return None
            if a.get("lease_until", 0) > time.time():
                raise AppError("이미 AI가 분석 중입니다. 잠시 후 새로고침하세요.")
            if a["ai_runs"] >= 3:
                raise AppError("이 제출물의 AI 재시도 한도(3회)에 도달했습니다. 교사 피드백을 요청하세요.")
            a.update(status="processing", lease=lease, lease_until=time.time()+180, ai_runs=a["ai_runs"]+1)
            return copy.deepcopy(a)
        attempt = self.store.transaction(reserve)
        if attempt is None:
            return
        try:
            images = [self.store.get_blob(ref) for ref in attempt["images"]]
            feedback = ai.feedback(attempt["activity_snapshot"], attempt, images)
            error = None
        except AppError as exc:
            feedback, error = None, str(exc)
        except Exception:
            feedback, error = None, "AI 결과를 처리하지 못했습니다. 제출물은 저장되어 있습니다."
        def finish(s):
            a = s["attempts"][attempt_id]
            if a.get("lease") != lease:
                return
            a.update(status="error" if error else "ready", feedback=feedback, error=error,
                     lease_until=0, evaluated_at=now())
            a.pop("lease", None)
        self.store.transaction(finish)
        if error:
            raise AppError(error)

    def review(self, token, attempt_id, correctness, score, comment):
        if correctness not in ("correct", "partial", "incorrect", "uncertain") or score not in [None, 0, 1, 2, 3, 4]:
            raise AppError("평가 값을 확인하세요.")
        if not comment.strip() or len(comment) > 3000:
            raise AppError("교사 피드백을 1~3000자로 남겨주세요.")
        def change(s):
            teacher = self.user(token, s, teacher=True)
            _, a = self._access_attempt(token, attempt_id, s)
            a["review"] = {"correctness": correctness, "score": score, "comment": comment.strip(),
                           "teacher": teacher["name"], "updated": now()}
        self.store.transaction(change)


def effective(a):
    if a.get("review"):
        return a["review"]["score"], a["review"]["correctness"]
    if a.get("feedback"):
        f = a["feedback"]
        return f["explanation_score"], f["correctness"]
    return None, "pending"


def report_rows(snapshot, activity_id):
    task = next(a for a in snapshot["activities"] if a["id"] == activity_id)
    students = [u for u in snapshot["users"] if u["role"] == "student" and u["class_id"] in task["classes"]]
    rows = []
    for student in students:
        attempts = sorted([a for a in snapshot["attempts"] if a["student_id"] == student["id"] and a["activity_id"] == activity_id], key=lambda a: a["number"])
        first, latest = (attempts[0], attempts[-1]) if attempts else (None, None)
        first_score = effective(first)[0] if first else None
        latest_score, correctness = effective(latest) if latest else (None, "pending")
        rows.append({"학급": student["class_id"], "학번": student["id"], "이름": student["name"],
                     "제출횟수": len(attempts), "첫설명점수": first_score, "최근설명점수": latest_score,
                     "변화": latest_score-first_score if latest_score is not None and first_score is not None else None,
                     "판정": correctness, "교사확인": bool(latest and latest.get("review")),
                     "최근제출": latest["created"] if latest else ""})
    return rows


def misconception_counts(attempts):
    latest = {}
    for a in sorted(attempts, key=lambda x: x["number"]):
        latest[(a["student_id"], a["activity_id"])] = a
    return Counter(tag for a in latest.values() if a.get("feedback") and not a.get("review")
                   for tag in set(a["feedback"]["misconceptions"]))
