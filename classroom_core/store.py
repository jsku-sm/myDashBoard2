"""Isolated synchronous classroom records with optimistic concurrency.

New records are JSON in a private repository. Explicit legacy-key construction
keeps the original encrypted format; neither format migrates the other.
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


def _location(namespace, record_id, schema_version=1):
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*(?:/[A-Za-z0-9_-]+)*", namespace):
        raise StorageError("올바르지 않은 저장 구분입니다.")
    if not isinstance(record_id, str) or not record_id or len(record_id) > 300:
        raise StorageError("올바르지 않은 기록 ID입니다.")
    digest = hashlib.sha256(record_id.encode()).hexdigest()
    suffix = ".json.enc" if schema_version == 1 else ".json"
    return f"data/classroom/v{schema_version}/{namespace}/{digest[:2]}/{digest}{suffix}"


def _record(record, version, schema_version=1):
    result = copy.deepcopy(record)
    result["version"] = version
    result["schema_version"] = schema_version
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
    """One CAS record per resource/student; success means remote commit.

    Contents API SHA is read on every write. A competing update of the same
    record fails visibly; unrelated branch commits retry at most three times.
    """
    durable = True
    MAX_ATTEMPTS = 3

    def __init__(self, repo, branch, token, key=None, session=None):
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo))
                or str(repo).split("/")[0] == "내깃허브아이디"
                or not str(branch).strip() or not str(token).strip()):
            raise ConfigurationError("배포 Secrets의 기존 [github] repo, branch, token을 확인하세요. 저장소 경로와 브랜치는 추측하지 않습니다.")
        self.storage_format = "json" if key is None else "encrypted"
        self.schema_version = 2 if key is None else 1
        self._cipher = None
        if key is not None:
            try:
                self._cipher = Fernet(key if isinstance(key, bytes) else str(key).encode())
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
        try:
            metadata = response.json()
            if not isinstance(metadata, dict) or not isinstance(metadata.get("private"), bool):
                raise ValueError()
        except (ValueError, TypeError):
            raise StorageError("GitHub 저장소의 비공개 상태를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
        if metadata["private"] is not True:
            raise ConfigurationError("운영 데이터 저장소가 공개 상태입니다. 비공개 저장소로 설정하기 전에는 학생 자료를 조회·저장할 수 없습니다.")

    def _location(self, namespace, record_id):
        return _location(namespace, record_id, self.schema_version)

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
            if not isinstance(obj, dict):
                raise ValueError()
            sha = obj["sha"]
            if not isinstance(sha, str) or not sha:
                raise ValueError()
            if obj.get("encoding") == "base64" and obj.get("content"):
                raw = base64.b64decode(obj["content"])
            else:
                blob = self._request("GET", "/git/blobs/" + quote(sha, safe=""))
                if blob.status_code != 200:
                    self._error(blob.status_code)
                blob_data = blob.json()
                if not isinstance(blob_data, dict):
                    raise ValueError()
                raw = base64.b64decode(blob_data["content"])
            envelope = json.loads(self._cipher.decrypt(raw) if self._cipher else raw)
            if not isinstance(envelope, dict) or envelope.get("path") != path:
                raise ValueError()
            record = envelope.get("record")
            if (not isinstance(record, dict)
                    or type(record.get("schema_version")) is not int
                    or record["schema_version"] != self.schema_version
                    or type(record.get("version")) is not int or record["version"] < 1):
                raise ValueError()
            with self._cache_lock:
                self._record_cache[path] = (time.monotonic(), copy.deepcopy(record), sha)
            return record, sha
        except (InvalidToken, ValueError, KeyError, TypeError, binascii.Error):
            if self._cipher:
                message = "암호화 기록을 읽을 수 없습니다. 처음 사용한 암호화 키와 백업을 확인하세요. 기존 기록은 변경하지 않았습니다."
            else:
                message = "클래스룸 JSON 기록의 형식·저장 경로·버전을 확인할 수 없습니다. 백업을 확인하세요. 기존 기록은 변경하지 않았습니다."
            raise StorageError(message) from None

    def get(self, namespace, record_id, fresh=False):
        path = self._location(namespace, record_id)
        # Recheck even when the record itself can be returned from cache.
        self._check_private()
        record, _ = self._read_path(path, fresh=fresh)
        return record

    def invalidate(self):
        with self._cache_lock:
            self._record_cache.clear()
            self._tree_cache = None

    def list(self, namespace, fresh=False):
        self._location(namespace, "validation")
        self._check_private()
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
            try:
                tree = response.json()
                if (not isinstance(tree, dict) or not isinstance(tree.get("tree"), list)
                        or any(not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                               for entry in tree["tree"])):
                    raise ValueError()
            except (ValueError, TypeError):
                raise StorageError("GitHub의 전체 클래스룸 목록을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
            with self._cache_lock:
                self._tree_cache = (time.monotonic(), tree)
        if tree.get("truncated"):
            raise StorageError("GitHub 목록 크기 제한으로 전체 기록을 확인하지 못했습니다. 관리자에게 분할 조회 설정을 요청하세요.")
        prefix = f"data/classroom/v{self.schema_version}/{namespace}/"
        pattern = r"[a-f0-9]{2}/[a-f0-9]{64}\.json" + (r"\.enc" if self._cipher else "")
        records = []
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            # Exact namespace only; nested namespaces are independent shards.
            suffix = path[len(prefix):] if path.startswith(prefix) else ""
            if entry.get("type") == "blob" and re.fullmatch(pattern, suffix):
                record, _ = self._read_path(path, fresh=fresh)
                if record is not None:
                    records.append(record)
        return records

    def legacy_data_present(self):
        """Report old files from the last complete list, without extra requests.

        None means no complete tree has been loaded yet. This detects file
        presence only; it does not decrypt, import, or modify legacy records.
        """
        with self._cache_lock:
            cached = self._tree_cache
        if not cached or cached[1].get("truncated"):
            return None
        return any(entry.get("type") == "blob"
                   and isinstance(entry.get("path"), str)
                   and entry["path"].startswith("data/classroom/v1/")
                   and entry["path"].endswith(".json.enc")
                   for entry in cached[1].get("tree", []))

    def put(self, namespace, record_id, record, expected_version=None):
        # Repository visibility can change while a cached app process is alive.
        self._check_private()
        path = self._location(namespace, record_id)
        wanted = _record(record, (expected_version or 0) + 1, self.schema_version)
        # Reuse the exact bytes for all retries and ambiguous network
        # outcomes; checking the record avoids duplicate version increments.
        raw = json.dumps({"path": path, "record": wanted}, ensure_ascii=False).encode()
        if self._cipher:
            raw = self._cipher.encrypt(raw)
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


def _settings(secrets):
    """Normalize only settings used by the selected format, never make a key."""
    github = secrets.get("github", {})
    classroom = secrets.get("classroom", {})
    if not hasattr(github, "get") or not hasattr(classroom, "get"):
        raise ConfigurationError("배포 Secrets의 [github] 및 [classroom] 설정 형식을 확인하세요.")
    missing = [field for field in ("repo", "branch", "token") if not str(github.get(field, "")).strip()]
    if missing:
        raise ConfigurationError("기존 [github] 설정의 " + ", ".join(missing) + " 항목을 배포 Secrets에 설정하세요. 비밀값을 채팅으로 보내지 마세요.")
    storage_format = str(classroom.get("storage_format", "json")).strip().lower()
    if storage_format not in ("json", "encrypted"):
        raise ConfigurationError('[classroom] storage_format은 "json" 또는 "encrypted"로 설정하세요.')
    key = None
    if storage_format == "encrypted":
        # Old key locations are consulted only for an explicit legacy-format
        # request. The default JSON path never even reads unrelated keys.
        key = (classroom.get("encryption_key") or secrets.get("CLASSROOM_ENCRYPTION_KEY")
               or secrets.get("ENCRYPTION_KEY"))
        if not key:
            legacy = secrets.get("snorkl", {})
            key = legacy.get("encryption_key") if hasattr(legacy, "get") else None
        if not key:
            raise ConfigurationError("기존 암호화 클래스룸 기록을 읽으려면 [classroom] encryption_key에 처음 사용한 키가 필요합니다. 새 키를 만들지 마세요. 기본 JSON 저장에는 키가 필요하지 않습니다. 키 원문은 채팅에 보내지 마세요.")
    return github["repo"], github["branch"], github["token"], key


def store_from_secrets(secrets):
    """Default to key-free private JSON; encrypted v1 requires an explicit opt-in."""
    return GitHubStore(*_settings(secrets))


def get_store():
    import streamlit as st
    try:
        # Read active settings outside the cache so changing Secrets or storage
        # mode cannot return a previously configured encrypted resource.
        settings = _settings(st.secrets)
    except ClassroomError:
        raise
    except Exception:
        raise ConfigurationError("배포 Secrets에 기존 [github] repo, branch, token 연결 설정을 확인하세요. 기본 JSON 저장에는 추가 암호화 키가 필요하지 않습니다.") from None

    # All effective credentials and the storage revision participate in the
    # cache hash. Streamlit hashes these inputs; they are never logged here.
    @st.cache_resource(show_spinner=False)
    def configured_store(repo, branch, token, key, storage_revision):
        return GitHubStore(repo, branch, token, key)
    return configured_store(*settings, storage_revision="classroom-json-v2")
