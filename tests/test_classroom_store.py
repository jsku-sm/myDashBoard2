import base64
import copy
import hashlib
import json
import sys
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


def json_cloud(session=None):
    return GitHubStore("jsku-sm/class-dashboard-data", "main", "test-secret-token", session=session or FakeGitHub())


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


@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_compare_and_swap_prevents_lost_update_and_create_overwrite(constructor):
    store = constructor()
    first = store.put("progress", "one", {"id": "one", "count": 1})
    with pytest.raises(ConflictError):
        store.put("progress", "one", {"id": "one", "count": 2})
    second = store.put("progress", "one", {"id": "one", "count": 2}, first["version"])
    with pytest.raises(ConflictError):
        store.put("progress", "one", {"id": "one", "count": 3}, first["version"])
    assert store.get("progress", "one", fresh=True) == second


@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_bounded_retry_and_ambiguous_commit_recovery(constructor):
    remote = FakeGitHub()
    remote.fail_put = 100
    store = constructor(remote)
    with pytest.raises(StorageError):
        store.put("submissions", "one", {"id": "one"})
    assert len([call for call in remote.calls if call[0] == "PUT"]) == store.MAX_ATTEMPTS
    remote.fail_put = 0
    remote.ambiguous_put = True
    saved = store.put("submissions", "one", {"id": "one"})
    assert saved["version"] == 1 and len(remote.files) == 1


@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_public_repository_refused_before_any_write_and_safe_error(constructor):
    remote = FakeGitHub(private=False)
    with pytest.raises(ConfigurationError, match="공개") as exc:
        constructor(remote)
    assert "test-secret-token" not in str(exc.value)
    assert not any(call[0] == "PUT" for call in remote.calls)


@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_visibility_flip_blocks_cached_store_before_new_write(constructor):
    remote = FakeGitHub()
    store = constructor(remote)
    store.put("courses", "one", {"id": "one"})
    puts_before = len([call for call in remote.calls if call[0] == "PUT"])
    remote.private = False
    with pytest.raises(ConfigurationError, match="공개"):
        store.put("courses", "two", {"id": "two"})
    assert len([call for call in remote.calls if call[0] == "PUT"]) == puts_before


def test_missing_config_does_not_guess_or_generate_key(monkeypatch):
    with pytest.raises(ConfigurationError, match="repo, branch, token"):
        store_from_secrets({})
    with pytest.raises(ConfigurationError, match="branch"):
        store_from_secrets({"github": {"repo": "owner/mydashboard", "token": "secret"}})
    import classroom_core.store as module
    remote = FakeGitHub()
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: GitHubStore(repo, branch, token, key, session=remote))
    store = store_from_secrets({"github": {"repo": "jsku-sm/class-dashboard-data", "branch": "main", "token": "secret"}})
    assert store.storage_format == "json" and store._cipher is None


def test_classroom_key_works_without_any_snorkl_settings(monkeypatch):
    import classroom_core.store as module
    key = Fernet.generate_key().decode()
    remote = FakeGitHub()
    constructor = GitHubStore
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: constructor(repo, branch, token, key, session=remote))
    secrets = {"github": {"repo": "school/class-dashboard-data", "branch": "main", "token": "test"},
               "classroom": {"storage_format": "encrypted", "encryption_key": key}}
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
    original = store_from_secrets({"github": connection, "classroom": {"storage_format": "encrypted"}, "snorkl": {"encryption_key": key}})
    saved = original.put("courses", "old", {"id": "old", "title": "기존 기록"})
    independent = store_from_secrets({"github": connection, "classroom": {"storage_format": "encrypted", "encryption_key": key}})
    assert independent.get("courses", "old") == saved
    with pytest.raises(StorageError):
        store_from_secrets({"github": connection, "classroom": {"storage_format": "encrypted", "encryption_key": Fernet.generate_key().decode()}}).get("courses", "old")
    assert independent.get("courses", "old", fresh=True) == saved


@pytest.mark.parametrize("constructor,branch", [(cloud, "data/current"), (json_cloud, "main")])
def test_large_contents_blob_fallback_cache_invalidation_and_branch(constructor, branch):
    remote = FakeGitHub()
    store = constructor(remote)
    store.put("courses", "one", {"id": "one"})
    remote.large_response = True
    assert store.get("courses", "one")["version"] == 1
    assert any("/git/blobs/" in call[1] for call in remote.calls)
    store.list("courses")
    store.put("courses", "two", {"id": "two"})
    assert len(store.list("courses")) == 2
    assert all(call[2]["params"]["ref"] == branch for call in remote.calls if call[0] == "GET" and "/contents/" in call[1])


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


@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_network_read_and_cached_read_never_share_mutable_objects(constructor):
    store = constructor()
    store.put("courses", "one", {"id": "one", "lessons": [{"title": "원래 차시"}]})
    first = store.get("courses", "one", fresh=True)
    first["lessons"][0]["title"] = "저장되지 않은 입력"
    assert store.get("courses", "one")["lessons"][0]["title"] == "원래 차시"
    second = store.get("courses", "one")
    second["lessons"].clear()
    assert len(store.get("courses", "one")["lessons"]) == 1
    store.invalidate()
    assert store.get("courses", "one")["lessons"][0]["title"] == "원래 차시"


def test_key_free_json_restart_backup_and_opaque_path():
    remote = FakeGitHub()
    store = json_cloud(remote)
    saved = store.put("submissions", "student-001", {"id": "student-001", "answer": "학생의 답안"})
    path, raw = next(iter(remote.files.items()))
    assert path.startswith("data/classroom/v2/submissions/") and path.endswith(".json")
    assert "student-001" not in path and "학생의 답안".encode() in raw
    assert json.loads(raw) == {"path": path, "record": saved}
    assert saved["schema_version"] == 2 and saved["version"] == 1
    restored = FakeGitHub()
    restored.files = copy.deepcopy(remote.files)
    assert json_cloud(restored).get("submissions", "student-001") == saved
    assert restored.files == remote.files


def test_json_and_encrypted_files_are_disjoint_and_legacy_is_preserved():
    remote, key = FakeGitHub(), Fernet.generate_key().decode()
    encrypted = cloud(remote, key)
    old = encrypted.put("courses", "same-id", {"id": "same-id", "title": "기존 기록"})
    backup = copy.deepcopy(remote.files)
    plain = json_cloud(remote)
    assert plain.legacy_data_present() is None
    assert plain.get("courses", "same-id") is None
    assert plain.list("courses") == []
    before = len(remote.calls)
    assert plain.legacy_data_present() is True
    assert len(remote.calls) == before  # No extra tree request or key request.
    saved = plain.put("courses", "same-id", {"id": "same-id", "title": "새 JSON 기록"})
    assert len(remote.files) == 2
    assert all(remote.files[path] == raw for path, raw in backup.items())
    assert plain.list("courses") == [saved]
    assert encrypted.list("courses", fresh=True) == [old]
    assert cloud(remote, key).get("courses", "same-id") == old


@pytest.mark.parametrize("operation", ["get", "list"])
@pytest.mark.parametrize("constructor", [cloud, json_cloud])
def test_visibility_flip_blocks_cached_reads(operation, constructor):
    remote = FakeGitHub()
    store = constructor(remote)
    store.put("courses", "one", {"id": "one"})
    store.get("courses", "one")
    store.list("courses")
    remote.private = False
    before = len(remote.calls)
    with pytest.raises(ConfigurationError, match="공개"):
        getattr(store, operation)("courses", "one") if operation == "get" else store.list("courses")
    assert len(remote.calls) == before + 1
    assert "/contents/" not in remote.calls[-1][1] and "/git/trees/" not in remote.calls[-1][1]


@pytest.mark.parametrize("bad", [b"not JSON", b"[]", b"null", b'{"path":"wrong","record":{}}',
                               b'{"record": {}}'])
def test_invalid_json_never_overwrites_existing_file(bad):
    remote = FakeGitHub()
    store = json_cloud(remote)
    store.put("courses", "one", {"id": "one"})
    path = next(iter(remote.files))
    remote.files[path] = bad
    before = copy.deepcopy(remote.files)
    with pytest.raises(StorageError, match="JSON"):
        store.get("courses", "one", fresh=True)
    with pytest.raises(StorageError, match="JSON"):
        store.put("courses", "one", {"id": "one"}, 1)
    assert remote.files == before


@pytest.mark.parametrize("field,value", [("schema_version", 1), ("schema_version", True),
                                        ("schema_version", "2"), ("version", 0),
                                        ("version", True), ("version", "1")])
def test_json_schema_and_version_are_validated_before_read_or_cas(field, value):
    remote = FakeGitHub()
    store = json_cloud(remote)
    store.put("courses", "one", {"id": "one"})
    path = next(iter(remote.files))
    envelope = json.loads(remote.files[path])
    envelope["record"][field] = value
    remote.files[path] = json.dumps(envelope).encode()
    with pytest.raises(StorageError, match="JSON"):
        store.get("courses", "one", fresh=True)
    with pytest.raises(StorageError, match="JSON"):
        store.put("courses", "one", {"id": "one"}, 1)


def test_json_record_cannot_be_moved_to_a_different_path():
    remote = FakeGitHub()
    store = json_cloud(remote)
    store.put("courses", "one", {"id": "one"})
    store.put("courses", "two", {"id": "two"})
    one, two = list(remote.files)
    remote.files[two] = remote.files[one]
    with pytest.raises(StorageError, match="JSON"):
        store.get("courses", "two", fresh=True)


def test_factory_default_never_reads_old_or_unrelated_keys(monkeypatch):
    import classroom_core.store as module

    class GuardedSettings(dict):
        def get(self, name, default=None):
            assert name not in {"encryption_key", "CLASSROOM_ENCRYPTION_KEY", "ENCRYPTION_KEY", "snorkl"}
            return super().get(name, default)

    remote = FakeGitHub()
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: GitHubStore(repo, branch, token, key, session=remote))
    settings = GuardedSettings(github={"repo": "jsku-sm/class-dashboard-data", "branch": "main", "token": "test"},
                               classroom=GuardedSettings(encryption_key="broken"),
                               ENCRYPTION_KEY="broken", snorkl={"encryption_key": "broken"})
    assert store_from_secrets(settings).storage_format == "json"
    settings["classroom"]["storage_format"] = "json"
    assert store_from_secrets(settings).storage_format == "json"


def test_explicit_encrypted_mode_requires_existing_valid_key():
    connection = {"repo": "jsku-sm/class-dashboard-data", "branch": "main", "token": "test"}
    with pytest.raises(ConfigurationError, match="처음 사용한 키"):
        store_from_secrets({"github": connection, "classroom": {"storage_format": "encrypted"}})
    with pytest.raises(ConfigurationError, match="Fernet"):
        store_from_secrets({"github": connection, "classroom": {"storage_format": "encrypted", "encryption_key": "invalid"}})
    with pytest.raises(ConfigurationError, match="storage_format"):
        store_from_secrets({"github": connection, "classroom": {"storage_format": "invalid"}})


def test_resource_cache_changes_when_effective_settings_change(monkeypatch):
    import classroom_core.store as module
    cache, remote = {}, FakeGitHub()
    def cache_resource(**options):
        def decorate(function):
            def cached(*args, **kwargs):
                key = (function.__name__, args, tuple(sorted(kwargs.items())))
                if key not in cache:
                    cache[key] = function(*args, **kwargs)
                return cache[key]
            return cached
        return decorate
    fake_st = SimpleNamespace(cache_resource=cache_resource,
                              secrets={"github": {"repo": "jsku-sm/class-dashboard-data", "branch": "main", "token": "test"}})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setattr(module, "GitHubStore", lambda repo, branch, token, key: GitHubStore(repo, branch, token, key, session=remote))
    plain = module.get_store()
    assert module.get_store() is plain
    fake_st.secrets["ENCRYPTION_KEY"] = "irrelevant-invalid-key"
    assert module.get_store() is plain
    fake_st.secrets["github"]["token"] = "changed-token"
    retargeted = module.get_store()
    assert retargeted is not plain and retargeted.storage_format == "json"
    fake_st.secrets["classroom"] = {"storage_format": "encrypted", "encryption_key": Fernet.generate_key().decode()}
    legacy = module.get_store()
    assert legacy is not retargeted and legacy.storage_format == "encrypted"
    fake_st.secrets["classroom"]["encryption_key"] = Fernet.generate_key().decode()
    assert module.get_store() is not legacy
    fake_st.secrets["classroom"]["storage_format"] = "json"
    assert module.get_store() is retargeted


@pytest.mark.parametrize("bad_tree", [{"tree": None}, {"tree": [None]},
                                    {"tree": [{"type": "blob", "path": 123}]}])
def test_malformed_tree_is_a_safe_failure_and_never_cached(bad_tree):
    class BadTreeGitHub(FakeGitHub):
        def request(self, method, url, timeout, **kwargs):
            if "/git/trees/" in url:
                return response(200, bad_tree)
            return super().request(method, url, timeout, **kwargs)
    store = json_cloud(BadTreeGitHub())
    with pytest.raises(StorageError, match="목록"):
        store.list("courses")
    assert store.legacy_data_present() is None


def test_json_exact_namespace_listing_excludes_independent_shards():
    store = json_cloud()
    parent = store.put("courses", "same", {"id": "same", "title": "전체"})
    child = store.put("courses/group1", "same", {"id": "same", "title": "분할"})
    assert store.list("courses") == [parent]
    assert store.legacy_data_present() is False
    assert store.list("courses/group1") == [child]
