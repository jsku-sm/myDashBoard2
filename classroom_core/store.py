"""Isolated, encrypted synchronous classroom records with optimistic concurrency.

No existing CSV or Snorkl record is migrated, copied, or rewritten here.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import threading
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken


class ClassroomError(Exception):
    """Safe, user-facing classroom error (never include remote response bodies)."""


class ConfigurationError(ClassroomError):
    pass


class StorageError(ClassroomError):
    pass


class ConflictError(ClassroomError):
    pass


def _location(namespace, record_id):
    if not re.fullmatch(r"[a-z][a-z0-9_-]*(?:/[A-Za-z0-9_-]+)*", namespace):
        raise StorageError("올바르지 않은 저장 구분입니다.")
    if not isinstance(record_id, str) or not record_id or len(record_id) > 300:
        raise StorageError("올바르지 않은 기록 ID입니다.")
    digest = hashlib.sha256(record_id.encode()).hexdigest()
    return f"data/classroom/v1/{namespace}/{digest[:2]}/{digest}.json.enc"


def _record(record, version):
    result = copy.deepcopy(record)
    result["version"] = version
    result["schema_version"] = 1
    if len(json.dumps(result, ensure_ascii=False).encode()) > 12 * 1024 * 1024:
        raise StorageError("기록 크기 제한을 초과했습니다. 첨부 크기를 줄여 주세요.")
    return result


class MemoryStore:
    """Explicit test-only store. Never selected by the production factory."""
    durable = False

    def __init__(self):
        self._records = {}
        self._lock = threading.RLock()

    def get(self, namespace, record_id, fresh=False):
        _location(namespace, record_id)
        with self._lock:
            return copy.deepcopy(self._records.get((namespace, record_id)))

    def list(self, namespace, fresh=False):
        _location(namespace, "validation")
        with self._lock:
            return [copy.deepcopy(record) for (ns, _), record in self._records.items() if ns == namespace]

    def put(self, namespace, record_id, record, expected_version=None):
        _location(namespace, record_id)
        with self._lock:
            old = self._records.get((namespace, record_id))
            actual = old["version"] if old else None
            if actual != expected_version:
                raise ConflictError("다른 창에서 기록이 변경되었습니다. 새로 불러온 뒤 다시 저장해 주세요.")
            result = _record(record, (actual or 0) + 1)
            self._records[(namespace, record_id)] = result
            return copy.deepcopy(result)


class GitHubStore:
    """One encrypted CAS record per resource/student; success means remote commit.

    Contents API SHA is read on every write. A competing update of the same
    record fails visibly; unrelated branch commits retry at most three times.
    """
    durable = True
    MAX_ATTEMPTS = 3

    def __init__(self, repo, branch, token, key, session=None):
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo))
                or str(repo).split("/")[0] == "내깃허브아이디"
                or not str(branch).strip() or not str(token).strip()):
            raise ConfigurationError("배포 Secrets의 기존 [github] repo, branch, token을 확인하세요. 저장소 경로와 브랜치는 추측하지 않습니다.")
        try:
            self._cipher = Fernet(str(key).encode())
        except (ValueError, TypeError):
            raise ConfigurationError("[classroom] encryption_key에 올바른 Fernet 키를 설정하세요. 기존 클래스룸 기록이 있으면 처음 사용한 키를 유지하세요.") from None
        if session is None:
            import requests
            session = requests.Session()
        self._session = session
        self._session.headers.update({"Authorization": f"Bearer {token}",
                                      "Accept": "application/vnd.github+json",
                                      "X-GitHub-Api-Version": "2022-11-28"})
        self.repo, self.branch = str(repo), str(branch)
        self._base = f"https://api.github.com/repos/{repo}"
        self._cache_lock = threading.RLock()
        self._record_cache = {}
        self._tree_cache = None
        self._check_private()

    def _check_private(self):
        response = self._request("GET", "")
        if response.status_code != 200:
            self._error(response.status_code)
        if response.json().get("private") is not True:
            raise ConfigurationError("운영 데이터 저장소가 공개 상태입니다. 비공개 저장소로 설정하기 전에는 학생 자료를 저장할 수 없습니다.")

    def _request(self, method, path, **kwargs):
        try:
            return self._session.request(method, self._base + path, timeout=35, **kwargs)
        except Exception:
            raise StorageError("GitHub 연결이 끊겼습니다. 입력 내용을 유지하고 잠시 후 다시 시도해 주세요.") from None

    @staticmethod
    def _error(status):
        if status in (401, 403):
            raise StorageError("GitHub 접근 권한을 확인하세요. 토큰 및 저장소 Contents 권한이 필요합니다.")
        if status == 404:
            raise ConfigurationError("기존 [github] 저장소 경로·브랜치 및 토큰의 접근 권한을 확인하세요.")
        raise StorageError(f"GitHub 저장 응답을 확인하지 못했습니다 (HTTP {status}). 입력을 유지하고 다시 시도해 주세요.")

    def _read_path(self, path, fresh=False):
        with self._cache_lock:
            cached = self._record_cache.get(path)
            if not fresh and cached and time.monotonic() - cached[0] < 4:
                return copy.deepcopy(cached[1]), cached[2]
        response = self._request("GET", "/contents/" + quote(path, safe="/"), params={"ref": self.branch})
        if response.status_code == 404:
            return None, None
        if response.status_code != 200:
            self._error(response.status_code)
        try:
            obj = response.json()
            sha = obj["sha"]
            if obj.get("encoding") == "base64" and obj.get("content"):
                raw = base64.b64decode(obj["content"])
            else:
                blob = self._request("GET", "/git/blobs/" + quote(sha, safe=""))
                if blob.status_code != 200:
                    self._error(blob.status_code)
                raw = base64.b64decode(blob.json()["content"])
            envelope = json.loads(self._cipher.decrypt(raw))
            if envelope["path"] != path or envelope["record"]["schema_version"] != 1:
                raise ValueError()
            with self._cache_lock:
                self._record_cache[path] = (time.monotonic(), copy.deepcopy(envelope["record"]), sha)
            return envelope["record"], sha
        except (InvalidToken, ValueError, KeyError, TypeError, binascii.Error):
            raise StorageError("암호화 기록을 읽을 수 없습니다. 처음 사용한 암호화 키와 백업을 확인하세요. 기존 기록은 변경하지 않았습니다.") from None

    def get(self, namespace, record_id, fresh=False):
        record, _ = self._read_path(_location(namespace, record_id), fresh=fresh)
        return record

    def invalidate(self):
        with self._cache_lock:
            self._record_cache.clear()
            self._tree_cache = None

    def list(self, namespace, fresh=False):
        _location(namespace, "validation")
        # Pin the tree to the configured branch. A truncated list must never be
        # presented as a complete set of courses or submissions.
        with self._cache_lock:
            cached = self._tree_cache
        if not fresh and cached and time.monotonic() - cached[0] < 15:
            tree = cached[1]
        else:
            response = self._request("GET", "/git/trees/" + quote(self.branch, safe=""), params={"recursive": "1"})
            if response.status_code != 200:
                self._error(response.status_code)
            tree = response.json()
            with self._cache_lock:
                self._tree_cache = (time.monotonic(), tree)
        if tree.get("truncated"):
            raise StorageError("GitHub 목록 크기 제한으로 전체 기록을 확인하지 못했습니다. 관리자에게 분할 조회 설정을 요청하세요.")
        prefix = f"data/classroom/v1/{namespace}/"
        records = []
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            # Exact namespace only; nested namespaces are independent shards.
            suffix = path[len(prefix):] if path.startswith(prefix) else ""
            if entry.get("type") == "blob" and re.fullmatch(r"[a-f0-9]{2}/[a-f0-9]{64}\.json\.enc", suffix):
                record, _ = self._read_path(path, fresh=fresh)
                if record is not None:
                    records.append(record)
        return records

    def put(self, namespace, record_id, record, expected_version=None):
        # Repository visibility can change while a cached app process is alive.
        self._check_private()
        path = _location(namespace, record_id)
        wanted = _record(record, (expected_version or 0) + 1)
        # Reuse the exact ciphertext for all retries and ambiguous network
        # outcomes; checking the record avoids duplicate version increments.
        raw = self._cipher.encrypt(json.dumps({"path": path, "record": wanted}, ensure_ascii=False).encode())
        attempted = False
        for _ in range(self.MAX_ATTEMPTS):
            current, sha = self._read_path(path, fresh=True)
            if attempted and current == wanted:
                with self._cache_lock:
                    self._tree_cache = None
                return current
            actual = current["version"] if current else None
            if actual != expected_version:
                raise ConflictError("다른 창에서 기록이 변경되었습니다. 새로 불러온 뒤 다시 저장해 주세요.")
            body = {"message": "Save classroom record", "content": base64.b64encode(raw).decode(), "branch": self.branch}
            if sha:
                body["sha"] = sha
            attempted = True
            try:
                response = self._request("PUT", "/contents/" + quote(path, safe="/"), json=body)
            except StorageError:
                continue
            if response.status_code in (200, 201):
                with self._cache_lock:
                    self._record_cache.pop(path, None)
                    self._tree_cache = None
                return copy.deepcopy(wanted)
            if response.status_code not in (409, 422, 500, 502, 503, 504):
                self._error(response.status_code)
        # Last request may have committed despite a lost response.
        current, _ = self._read_path(path, fresh=True)
        if current == wanted:
            with self._cache_lock:
                self._tree_cache = None
            return current
        raise StorageError("GitHub 저장을 확인하지 못했습니다. 제출 완료로 처리하지 않았습니다. 새로 불러오고 다시 시도해 주세요.")


def store_from_secrets(secrets):
    """Use the dashboard's explicit existing target; never infer a new repo."""
    github = dict(secrets.get("github", {}))
    classroom = dict(secrets.get("classroom", {}))
    missing = [field for field in ("repo", "branch", "token") if not str(github.get(field, "")).strip()]
    if missing:
        raise ConfigurationError("기존 [github] 설정의 " + ", ".join(missing) + " 항목을 배포 Secrets에 설정하세요. 비밀값을 채팅으로 보내지 마세요.")
    # New classroom installations use their own Secrets setting. The final
    # fallback only preserves access to classroom records encrypted by older
    # versions; it never initializes or connects the separate learning tool.
    key = (classroom.get("encryption_key") or secrets.get("CLASSROOM_ENCRYPTION_KEY")
           or secrets.get("ENCRYPTION_KEY") or dict(secrets.get("snorkl", {})).get("encryption_key"))
    if not key:
        raise ConfigurationError("클래스룸 암호화 설정이 필요합니다. 배포 Secrets의 [classroom] encryption_key를 설정하세요. 기존 클래스룸 기록이 있으면 처음 사용한 키를 그대로 사용하세요. 키 원문은 채팅에 보내지 마세요.")
    return GitHubStore(github["repo"], github["branch"], github["token"], key)


def get_store():
    import streamlit as st
    # Resource construction is cached, record reads and permissions are not.
    @st.cache_resource(show_spinner=False)
    def configured_store():
        try:
            secrets = dict(st.secrets)
        except Exception:
            raise ConfigurationError("배포 Secrets에 기존 [github] 연결과 [classroom] 암호화 설정을 확인하세요.") from None
        return store_from_secrets(secrets)
    return configured_store()
