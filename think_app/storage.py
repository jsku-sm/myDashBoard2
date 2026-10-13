"""Encrypted JSON files. GitHub writes use SHA compare-and-swap retries."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from cryptography.fernet import Fernet, InvalidToken
import requests


class AppError(Exception):
    pass


def blank():
    return {"schema": 1, "users": {}, "classes": {}, "activities": {}, "attempts": {}, "login_failures": {},
            "courses": {}}


def student_submission_path(attempt):
    """Use opaque identity folders; student names never appear in GitHub paths."""
    request_id = attempt.get("id", "")
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise AppError("제출 식별자가 올바르지 않습니다.")
    course_id = attempt.get("course_id") or (attempt.get("activity_snapshot") or {}).get("course_id")
    identities = (course_id, attempt.get("class_id"), attempt.get("student_id"))
    if any(not isinstance(value, str) or not value.strip() for value in identities):
        raise AppError("제출의 수업과 학생 정보를 확인하세요.")
    folders = [hashlib.sha256((label + ":" + value.strip()).encode()).hexdigest()[:32]
               for label, value in zip(("course", "class", "student"), identities)]
    prefix = "preview-submissions" if attempt.get("preview") else "student-submissions"
    directory = "/".join([prefix, *folders]) + "/"
    existing = attempt.get("submission_file")
    if existing is not None:
        if (not isinstance(existing, str) or not existing.startswith(directory) or
                not re.fullmatch(request_id + r"-[a-f0-9]{32}\.json\.enc", existing[len(directory):])):
            raise AppError("학생 제출 파일 경로를 확인하세요.")
        return existing
    fingerprint = hashlib.sha256(json.dumps(attempt, sort_keys=True, ensure_ascii=False,
                                            allow_nan=False).encode()).hexdigest()[:32]
    return directory + request_id + "-" + fingerprint + ".json.enc"


def uploaded_file_path(upload):
    """Keep names and student identifiers out of image draft paths."""
    upload_id = upload.get("id", "")
    if not isinstance(upload_id, str) or not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise AppError("업로드 파일 식별자를 확인하세요.")
    identities = (upload.get("course_id"), upload.get("class_id"), upload.get("student_id"))
    if any(not isinstance(value, str) or not value.strip() for value in identities):
        raise AppError("업로드 파일의 수업과 학생 정보를 확인하세요.")
    folders = [hashlib.sha256((label + ":" + value.strip()).encode()).hexdigest()[:32]
               for label, value in zip(("course", "class", "student"), identities)]
    prefix = "preview-course-uploads" if upload.get("preview") else "course-uploads"
    path = "/".join([prefix, *folders, upload_id + ".json.enc"])
    if upload.get("upload_file", path) != path:
        raise AppError("업로드 파일 경로를 확인하세요.")
    return path


def _existing_upload(payload, candidate):
    existing = payload.get("upload")
    fields = ("id", "activity_id", "course_id", "class_id", "student_id", "preview",
              "original_ref", "blob_ref", "original_mime", "mime", "original_sha256",
              "sha256", "original_bytes", "bytes", "saved")
    if (not isinstance(existing, dict) or not existing.get("saved") or
            any(existing.get(field) != candidate.get(field) for field in fields) or
            uploaded_file_path(existing) != uploaded_file_path(candidate)):
        raise AppError("업로드 파일이 기존 저장 내용과 다릅니다. 저장소를 확인하세요.")
    # A simultaneous retry may use a new timestamp or filename. Keep the first
    # fully stored copy; these fields do not change the upload's identity.
    return copy.deepcopy(existing)


def _submission_bundle(store, attempt):
    assets = {}
    references = [(ref, "image/jpeg") for ref in attempt.get("images", [])]
    if attempt.get("audio"):
        references.append((attempt["audio"], "audio/wav"))
    for reference, mime_type in references:
        raw = store.get_blob(reference)
        assets[reference] = {"mime_type": mime_type, "sha256": hashlib.sha256(raw).hexdigest(),
                             "base64": base64.b64encode(raw).decode()}
    return {"schema": 1, "submission": copy.deepcopy(attempt), "assets": assets}


def _prepare_submissions(store, previous, state):
    """Write complete student files before publishing their shared state records."""
    old_attempts = previous.get("course_attempts", {})
    for request_id, attempt in state.get("course_attempts", {}).items():
        old = old_attempts.get(request_id)
        if old is None or old.get("submission_file") != attempt.get("submission_file"):
            store.save_student_submission(attempt)


class MemoryStore:
    def __init__(self):
        self.state = blank()
        self.blobs = {}
        self.submissions = {}
        self.uploads = {}
        self.lock = threading.RLock()
        self.signing_key = os.urandom(32)

    def read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def transaction(self, change):
        with self.lock:
            state = copy.deepcopy(self.state)
            result = change(state)
            _prepare_submissions(self, self.state, state)
            self.state = state
            return copy.deepcopy(result)

    def save_student_submission(self, attempt):
        path = student_submission_path(attempt)
        with self.lock:
            self.submissions[path] = _submission_bundle(self, attempt)
        return path

    def get_student_submission(self, attempt):
        with self.lock:
            path = student_submission_path(attempt)
            if path not in self.submissions:
                raise AppError("학생 제출 파일을 찾을 수 없습니다.")
            return copy.deepcopy(self.submissions[path])

    def save_uploaded_file(self, upload):
        path = uploaded_file_path(upload)
        with self.lock:
            if path in self.uploads:
                return _existing_upload(self.uploads[path], upload)
            self.uploads[path] = {"schema": 1, "upload": copy.deepcopy(upload)}
            return copy.deepcopy(upload)

    def get_uploaded_file(self, upload):
        with self.lock:
            payload = self.uploads.get(uploaded_file_path(upload))
            if payload is None:
                raise AppError("업로드 저장 파일을 찾을 수 없습니다.")
            return _existing_upload(payload, upload)

    def put_blob(self, name, data):
        with self.lock:
            self.blobs[name] = data

    def get_blob(self, name):
        with self.lock:
            if name not in self.blobs:
                raise AppError("풀이 이미지가 없습니다.")
            return self.blobs[name]


class LocalStore:
    def __init__(self, directory, key):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fernet = make_cipher(key)
        self.signing_key = key.encode()
        self.lock = threading.RLock()

    def read(self):
        path = self.root / "state.enc"
        with self.lock:
            return decode(self.fernet, path.read_bytes()) if path.exists() else blank()

    def transaction(self, change):
        with self.lock:
            state = self.read()
            previous = copy.deepcopy(state)
            result = change(state)
            _prepare_submissions(self, previous, state)
            raw = self.fernet.encrypt(json.dumps(state, ensure_ascii=False).encode())
            temp = self.root / "state.tmp"
            temp.write_bytes(raw)
            temp.replace(self.root / "state.enc")
            return copy.deepcopy(result)

    def save_student_submission(self, attempt):
        relative = student_submission_path(attempt)
        raw = self.fernet.encrypt(json.dumps(_submission_bundle(self, attempt), ensure_ascii=False).encode())
        with self.lock:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(raw)
                temporary.replace(path)
            except OSError:
                raise AppError("학생 제출 파일 저장에 실패했습니다. 입력을 유지한 채 다시 시도하세요.") from None
            finally:
                temporary.unlink(missing_ok=True)
        return relative

    def get_student_submission(self, attempt):
        path = self.root / student_submission_path(attempt)
        with self.lock:
            try:
                return decode(self.fernet, path.read_bytes())
            except OSError:
                raise AppError("학생 제출 파일을 찾을 수 없습니다.") from None

    def save_uploaded_file(self, upload):
        path = self.root / uploaded_file_path(upload)
        with self.lock:
            if path.exists():
                return _existing_upload(decode(self.fernet, path.read_bytes()), upload)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": 1, "upload": copy.deepcopy(upload)}
            raw = self.fernet.encrypt(json.dumps(payload, ensure_ascii=False).encode())
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(raw)
                temporary.replace(path)
            except OSError:
                raise AppError("업로드 파일 저장에 실패했습니다. 파일을 유지한 채 다시 시도하세요.") from None
            finally:
                temporary.unlink(missing_ok=True)
            return copy.deepcopy(upload)

    def get_uploaded_file(self, upload):
        path = self.root / uploaded_file_path(upload)
        with self.lock:
            try:
                return _existing_upload(decode(self.fernet, path.read_bytes()), upload)
            except OSError:
                raise AppError("업로드 저장 파일을 찾을 수 없습니다.") from None

    def put_blob(self, name, data):
        if not re.fullmatch(r"[a-f0-9]{32}", name):
            raise AppError("파일 식별자가 올바르지 않습니다.")
        (self.root / (name + ".enc")).write_bytes(self.fernet.encrypt(data))

    def get_blob(self, name):
        if not re.fullmatch(r"[a-f0-9]{32}", name):
            raise AppError("파일 식별자가 올바르지 않습니다.")
        try:
            return self.fernet.decrypt((self.root / (name + ".enc")).read_bytes())
        except (OSError, InvalidToken):
            raise AppError("이미지를 읽지 못했습니다. 저장소와 암호화키를 확인하세요.") from None


def make_cipher(key):
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise AppError("ENCRYPTION_KEY에 올바른 Fernet 암호화키를 설정하세요.") from None


def decode(cipher, raw):
    try:
        result = json.loads(cipher.decrypt(raw))
        if result.get("schema") != 1:
            raise ValueError()
        return result
    except (InvalidToken, ValueError, KeyError):
        raise AppError("저장 데이터를 열지 못했습니다. 기존 암호화키를 확인하세요. 새 키로 바꾸지 마세요.") from None


class GitHubStore:
    PREFIX = "think-learning-v1"

    def __init__(self, repo, branch, token, key, session=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise AppError("GITHUB_REPO와 GITHUB_TOKEN을 설정하세요.")
        self.fernet = make_cipher(key)
        self.signing_key = key.encode()
        self.repo, self.branch = repo, branch
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": "Bearer " + token,
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
        self.base = "https://api.github.com/repos/" + repo
        self._read_lock = threading.RLock()
        self._cached_state = None
        self._cache_until = 0
        self._check_private()

    def _request(self, method, url, **kwargs):
        try:
            return self.http.request(method, url, timeout=25, **kwargs)
        except requests.RequestException:
            raise AppError("GitHub 연결이 지연되었습니다. 입력을 유지한 채 다시 시도하세요.") from None

    def _check_private(self):
        response = self._request("GET", self.base)
        if response.status_code != 200:
            raise AppError("GitHub 저장소 접근 실패: 저장소 이름과 토큰 권한을 확인하세요.")
        if not response.json().get("private"):
            raise AppError("학생 기록은 비공개(Private) 저장소에만 저장할 수 있습니다.")

    def _get(self, path):
        r = self._request("GET", self.base + "/contents/" + self.PREFIX + "/" + path,
                          params={"ref": self.branch})
        if r.status_code == 404:
            return None, None
        if r.status_code != 200:
            raise AppError("GitHub 읽기 실패: 브랜치·토큰 권한·요청 제한을 확인하세요.")
        data = r.json()
        if data.get("encoding") == "none":
            # Contents endpoint omits base64 for files larger than 1 MB.
            b = self._request("GET", self.base + "/git/blobs/" + data["sha"])
            if b.status_code != 200:
                raise AppError("큰 데이터 파일을 읽지 못했습니다.")
            return base64.b64decode(b.json()["content"]), data["sha"]
        return base64.b64decode(data["content"]), data["sha"]

    def _put(self, path, raw, sha=None):
        body = {"message": "Update learning record", "content": base64.b64encode(raw).decode(), "branch": self.branch}
        if sha:
            body["sha"] = sha
        return self._request("PUT", self.base + "/contents/" + self.PREFIX + "/" + path, json=body)

    def read(self):
        # All Streamlit sessions share this store. Pointer events from the board
        # must not cause one GitHub GET per student per pen stroke.
        with self._read_lock:
            if self._cached_state is None or time.monotonic() >= self._cache_until:
                raw, _ = self._get("state.enc")
                self._cached_state = blank() if raw is None else decode(self.fernet, raw)
                self._cache_until = time.monotonic() + 3
            return copy.deepcopy(self._cached_state)

    def invalidate(self):
        with self._read_lock:
            self._cache_until = 0

    def transaction(self, change):
        self._check_private()
        for n in range(6):
            raw, sha = self._get("state.enc")
            state = blank() if raw is None else decode(self.fernet, raw)
            previous = copy.deepcopy(state)
            result = change(state)
            encrypted = self.fernet.encrypt(json.dumps(state, ensure_ascii=False).encode())
            if len(encrypted) > 12_000_000:
                raise AppError("학습 기록 파일이 커졌습니다. 교사 화면에서 기록을 내보내고 새 운영 저장소를 준비하세요.")
            _prepare_submissions(self, previous, state)
            r = self._put("state.enc", encrypted, sha)
            if r.status_code in (200, 201):
                self.invalidate()
                return copy.deepcopy(result)
            if r.status_code not in (409, 422):
                raise AppError("GitHub 저장 실패: 토큰 쓰기 권한과 요청 제한을 확인하세요.")
            time.sleep(0.15 * (n + 1))
        raise AppError("동시 제출로 저장이 지연되었습니다. 같은 제출 버튼을 다시 눌러주세요.")

    def save_student_submission(self, attempt):
        path = student_submission_path(attempt)
        payload = _submission_bundle(self, attempt)
        self._check_private()
        for retry in range(6):
            existing, sha = self._get(path)
            if existing is not None:
                if decode(self.fernet, existing) == payload:
                    return path
                raise AppError("학생 제출 파일이 기존 답안과 다릅니다. 저장소 내용을 확인하세요.")
            response = self._put(path, self.fernet.encrypt(json.dumps(payload, ensure_ascii=False).encode()), sha)
            if response.status_code in (200, 201):
                return path
            if response.status_code not in (409, 422):
                raise AppError("학생 제출 파일을 GitHub에 저장하지 못했습니다. 입력을 유지한 채 다시 시도하세요.")
            time.sleep(0.15 * (retry + 1))
        raise AppError("학생 제출 파일 저장이 지연되었습니다. 같은 제출 버튼을 다시 눌러주세요.")

    def get_student_submission(self, attempt):
        raw, _ = self._get(student_submission_path(attempt))
        if raw is None:
            raise AppError("학생 제출 파일을 찾을 수 없습니다.")
        return decode(self.fernet, raw)

    def save_uploaded_file(self, upload):
        path = uploaded_file_path(upload)
        self._check_private()
        payload = {"schema": 1, "upload": copy.deepcopy(upload)}
        encrypted = self.fernet.encrypt(json.dumps(payload, ensure_ascii=False).encode())
        for retry in range(6):
            existing, sha = self._get(path)
            if existing is not None:
                return _existing_upload(decode(self.fernet, existing), upload)
            response = self._put(path, encrypted, sha)
            if response.status_code in (200, 201):
                return copy.deepcopy(upload)
            if response.status_code not in (409, 422):
                raise AppError("업로드 파일을 GitHub에 저장하지 못했습니다. 파일을 유지한 채 다시 시도하세요.")
            time.sleep(0.15 * (retry + 1))
        raise AppError("업로드 파일 저장이 지연되었습니다. 같은 파일을 다시 올려주세요.")

    def get_uploaded_file(self, upload):
        raw, _ = self._get(uploaded_file_path(upload))
        if raw is None:
            raise AppError("업로드 저장 파일을 찾을 수 없습니다.")
        return _existing_upload(decode(self.fernet, raw), upload)

    def put_blob(self, name, data):
        self._check_private()
        if not re.fullmatch(r"[a-f0-9]{32}", name):
            raise AppError("파일 식별자가 올바르지 않습니다.")
        path = "images/" + name + ".enc"
        encrypted = self.fernet.encrypt(data)
        for retry in range(6):
            existing, sha = self._get(path)
            if existing is not None:
                try:
                    if self.fernet.decrypt(existing) == data:
                        return
                except InvalidToken:
                    raise AppError("이미지 암호화키가 일치하지 않습니다.") from None
                raise AppError("파일 식별자의 기존 이미지와 내용이 다릅니다. 다시 올려주세요.")
            response = self._put(path, encrypted, sha)
            if response.status_code in (200, 201):
                return
            if response.status_code not in (409, 422):
                raise AppError("풀이 이미지 저장에 실패했습니다. 다시 시도하세요.")
            time.sleep(0.15 * (retry + 1))
        raise AppError("이미지 저장이 지연되었습니다. 같은 파일을 다시 올려주세요.")

    def get_blob(self, name):
        if not re.fullmatch(r"[a-f0-9]{32}", name):
            raise AppError("파일 식별자가 올바르지 않습니다.")
        raw, _ = self._get("images/" + name + ".enc")
        if raw is None:
            raise AppError("풀이 이미지가 없습니다.")
        try:
            return self.fernet.decrypt(raw)
        except InvalidToken:
            raise AppError("이미지 암호화키가 일치하지 않습니다.") from None

    def save_course_archive(self, course, archived_at):
        archive_id = uuid.uuid4().hex
        payload = {"id": archive_id, "archived_at": archived_at, "course": course}
        raw = self.fernet.encrypt(json.dumps(payload, ensure_ascii=False).encode())
        self._check_private()
        response = self._put("course-archives/" + archive_id + ".json.enc", raw)
        if response.status_code not in (200, 201):
            raise AppError("수업 보관 파일을 GitHub에 저장하지 못했습니다. 토큰 쓰기 권한을 확인하세요.")
        return archive_id

    def list_course_archives(self):
        self._check_private()
        response = self._request(
            "GET",
            self.base + "/contents/" + self.PREFIX + "/course-archives",
            params={"ref": self.branch},
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise AppError("GitHub 보관 파일 목록을 읽지 못했습니다. 토큰 읽기 권한을 확인하세요.")
        files = response.json()
        if not isinstance(files, list):
            raise AppError("GitHub 보관 파일 목록 형식이 올바르지 않습니다.")
        archives = []
        for item in files:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            match = re.fullmatch(r"([a-f0-9]{32})\.json\.enc", name)
            if not match:
                continue
            archive = self.get_course_archive(match.group(1))
            archives.append(archive)
        return sorted(archives, key=lambda archive: archive["archived_at"], reverse=True)

    def get_course_archive(self, archive_id):
        if not re.fullmatch(r"[a-f0-9]{32}", archive_id):
            raise AppError("보관 파일 식별자가 올바르지 않습니다.")
        raw, _ = self._get("course-archives/" + archive_id + ".json.enc")
        if raw is None:
            raise AppError("보관 파일을 찾을 수 없습니다.")
        try:
            payload = json.loads(self.fernet.decrypt(raw))
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise AppError("보관 파일을 읽지 못했습니다. 암호화키와 파일 형식을 확인하세요.") from None
        if (not isinstance(payload, dict) or payload.get("id") != archive_id
                or not isinstance(payload.get("course"), dict)
                or not isinstance(payload.get("archived_at"), str)):
            raise AppError("보관 파일의 내용이 올바르지 않습니다.")
        return payload
