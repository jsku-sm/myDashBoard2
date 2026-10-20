import base64
import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from cryptography.fernet import Fernet

from classroom_core.store import (ConfigurationError, ConflictError, GitHubStore,
                                 MemoryStore, StorageError, store_from_secrets)


def response(status, data=None):
    return SimpleNamespace(status_code=status, json=lambda: data or {})


class FakeGitHub:
    """An in-process remote object store; tests never contact GitHub."""
    def __init__(self, private=True):
        self.headers, self.files, self.calls = {}, {}, []
        self.private = private
        self.fail_put = 0
        self.ambiguous_put = False
        self.large_response = False

    def request(self, method, url, timeout, **kwargs):
        self.calls.append((method, url, copy.deepcopy(kwargs)))
        if "/git/trees/" in url:
            return response(200, {"tree": [{"path": path, "type": "blob"} for path in self.files]})
        if "/git/blobs/" in url:
            sha = url.rsplit("/", 1)[-1]
            raw = next(raw for raw in self.files.values() if hashlib.sha256(raw).hexdigest() == sha)
            return response(200, {"content": base64.b64encode(raw).decode()})
        if "/contents/" not in url:
            return response(200, {"private": self.private})
        path = unquote(url.split("/contents/", 1)[1])
        existing = self.files.get(path)
        sha = hashlib.sha256(existing).hexdigest() if existing else None
        if method == "GET":
            if existing is None:
                return response(404)
            return response(200, {"sha": sha, "encoding": "none" if self.large_response else "base64",
                                  "content": "" if self.large_response else base64.b64encode(existing).decode()})
        if self.fail_put:
            self.fail_put -= 1
            return response(503)
        body = kwargs["json"]
        if body.get("sha") != sha:
            return response(409)
        self.files[path] = base64.b64decode(body["content"])
        if self.ambiguous_put:
            self.ambiguous_put = False
            raise OSError("lost response")
        return response(201)


def cloud(session=None, key=None):
    return GitHubStore("owner/mydashboard", "data/current", "test-secret-token", key or Fernet.generate_key().decode(), session=session or FakeGitHub())


def test_encrypted_opaque_paths_restart_and_backup_restore():
    remote, key = FakeGitHub(), Fernet.generate_key().decode()
    store = cloud(remote, key)
    record = store.put("submissions", "student-001-answer", {"id": "student-001-answer", "answer": "민감한 학생 답안"})
    path, raw = next(iter(remote.files.items()))
    assert "student-001" not in path and "민감한".encode() not in raw
    assert all("민감한" not in call[2].get("json", {}).get("message", "") for call in remote.calls)
    restored = FakeGitHub()
    restored.files = copy.deepcopy(remote.files)
    assert cloud(restored, key).get("submissions", "student-001-answer") == record
    with pytest.raises(StorageError, match="암호화"):
        cloud(restored).get("submissions", "student-001-answer")
    assert restored.files == remote.files


def test_compare_and_swap_prevents_lost_update_and_create_overwrite():
    store = cloud()
    first = store.put("progress", "one", {"id": "one", "count": 1})
    with pytest.raises(ConflictError):
        store.put("progress", "one", {"id": "one", "count": 2})
    second = store.put("progress", "one", {"id": "one", "count": 2}, first["version"])
    with pytest.raises(ConflictError):
        store.put("progress", "one", {"id": "one", "count": 3}, first["version"])
    assert store.get("progress", "one", fresh=True) == second


def test_bounded_retry_and_ambiguous_commit_recovery():
    remote = FakeGitHub()
    remote.fail_put = 100
    store = cloud(remote)
    with pytest.raises(StorageError):
        store.put("submissions", "one", {"id": "one"})
    assert len([call for call in remote.calls if call[0] == "PUT"]) == store.MAX_ATTEMPTS
    remote.fail_put = 0
    remote.ambiguous_put = True
    saved = store.put("submissions", "one", {"id": "one"})
    assert saved["version"] == 1 and len(remote.files) == 1


def test_public_repository_refused_before_any_write_and_safe_error():
    remote = FakeGitHub(private=False)
    with pytest.raises(ConfigurationError, match="공개") as exc:
        cloud(remote)
    assert "test-secret-token" not in str(exc.value)
    assert not any(call[0] == "PUT" for call in remote.calls)


def test_visibility_flip_blocks_cached_store_before_new_write():
    remote = FakeGitHub()
    store = cloud(remote)
    store.put("courses", "one", {"id": "one"})
    puts_before = len([call for call in remote.calls if call[0] == "PUT"])
    remote.private = False
    with pytest.raises(ConfigurationError, match="공개"):
        store.put("courses", "two", {"id": "two"})
    assert len([call for call in remote.calls if call[0] == "PUT"]) == puts_before


def test_missing_config_does_not_guess_or_generate_key():
    with pytest.raises(ConfigurationError, match="repo, branch, token"):
        store_from_secrets({})
    with pytest.raises(ConfigurationError, match="branch"):
        store_from_secrets({"github": {"repo": "owner/mydashboard", "token": "secret"}})
    with pytest.raises(ConfigurationError, match=r"\[classroom\] encryption_key") as error:
        store_from_secrets({"github": {"repo": "owner/mydashboard", "branch": "main", "token": "secret"}})
    assert "[snorkl]" not in str(error.value)


def test_classroom_key_works_without_any_snorkl_settings(monkeypatch):
    import classroom_core.store as module
    key = Fernet.generate_key().decode()
    remote = FakeGitHub()
    constructor = GitHubStore
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: constructor(repo, branch, token, key, session=remote))
    secrets = {"github": {"repo": "school/class-dashboard-data", "branch": "main", "token": "test"},
               "classroom": {"encryption_key": key}}
    first = store_from_secrets(secrets)
    saved = first.put("courses", "one", {"id": "one", "title": "독립 클래스룸"})
    assert store_from_secrets(secrets).get("courses", "one") == saved
    assert "독립 클래스룸".encode() not in next(iter(remote.files.values()))


def test_original_classroom_encryption_key_remains_compatible(monkeypatch):
    import classroom_core.store as module
    key = Fernet.generate_key().decode()
    remote = FakeGitHub()
    constructor = GitHubStore
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: constructor(repo, branch, token, key, session=remote))
    connection = {"repo": "school/class-dashboard-data", "branch": "main", "token": "test"}
    original = store_from_secrets({"github": connection, "snorkl": {"encryption_key": key}})
    saved = original.put("courses", "old", {"id": "old", "title": "기존 기록"})
    independent = store_from_secrets({"github": connection, "classroom": {"encryption_key": key}})
    assert independent.get("courses", "old") == saved
    with pytest.raises(StorageError):
        store_from_secrets({"github": connection, "classroom": {"encryption_key": Fernet.generate_key().decode()}}).get("courses", "old")
    assert independent.get("courses", "old", fresh=True) == saved


def test_large_contents_blob_fallback_cache_invalidation_and_branch():
    remote = FakeGitHub()
    store = cloud(remote)
    store.put("courses", "one", {"id": "one"})
    remote.large_response = True
    assert store.get("courses", "one")["version"] == 1
    assert any("/git/blobs/" in call[1] for call in remote.calls)
    store.list("courses")
    store.put("courses", "two", {"id": "two"})
    assert len(store.list("courses")) == 2
    assert all(call[2]["params"]["ref"] == "data/current" for call in remote.calls if call[0] == "GET" and "/contents/" in call[1])


def test_25_student_shards_and_duplicate_cas_are_independent():
    store = MemoryStore()
    def submit(index):
        return store.put("submissions", f"assignment-{index}", {"id": str(index), "answer": str(index)})
    with ThreadPoolExecutor(max_workers=25) as executor:
        records = list(executor.map(submit, range(25)))
    assert len(records) == len(store.list("submissions")) == 25
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(store.put, "submissions", "same", {"answer": "same"}) for _ in range(2)]
    assert sum(f.exception() is None for f in futures) == 1
    assert sum(isinstance(f.exception(), ConflictError) for f in futures) == 1


def test_ciphertext_cannot_be_moved_between_record_paths():
    remote = FakeGitHub()
    store = cloud(remote)
    store.put("courses", "one", {"id": "one"})
    store.put("courses", "two", {"id": "two"})
    paths = list(remote.files)
    remote.files[paths[1]] = remote.files[paths[0]]
    with pytest.raises(StorageError):
        store.get("courses", "two", fresh=True)


def test_network_read_and_cached_read_never_share_mutable_objects():
    store = cloud()
    store.put("courses", "one", {"id": "one", "lessons": [{"title": "원래 차시"}]})
    first = store.get("courses", "one", fresh=True)
    first["lessons"][0]["title"] = "저장되지 않은 입력"
    assert store.get("courses", "one")["lessons"][0]["title"] == "원래 차시"
    second = store.get("courses", "one")
    second["lessons"].clear()
    assert len(store.get("courses", "one")["lessons"]) == 1
    store.invalidate()
    assert store.get("courses", "one")["lessons"][0]["title"] == "원래 차시"
