"""Persistent local keys and non-destructive migration of process-memory data."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from cryptography.fernet import Fernet, InvalidToken

from .storage import (AppError, GitHubStore, LocalStore, MemoryStore, make_cipher,
                      student_submission_path, uploaded_file_path, _submission_bundle)


KEY_FILENAME = ".encryption.key"


def _publish_new_file(path, raw):
    """Publish a fully written private file atomically without replacing one."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _read_local_key(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid():
            raise AppError("자동 암호화 키 파일의 소유자와 형식을 확인하세요.")
        os.fchmod(descriptor, 0o600)
        raw = os.read(descriptor, 128)
    finally:
        os.close(descriptor)
    try:
        key = raw.decode("ascii").strip()
        make_cipher(key)
    except (UnicodeDecodeError, AppError):
        raise AppError("자동 암호화 키 파일을 읽지 못했습니다. 기존 키 파일을 복원하세요. 새 키로 바꾸지 마세요.") from None
    return key


def local_encryption_key(data_dir, encryption_key=""):
    """Reuse an explicit key or atomically create one for a new local store."""
    if encryption_key:
        make_cipher(encryption_key)
        return encryption_key
    root = Path(data_dir).expanduser()
    path = root / KEY_FILENAME
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            return _read_local_key(path)
        except FileNotFoundError:
            pass
        if (root / "state.enc").exists():
            raise AppError("기존 평가 자료가 있지만 암호화 키가 없습니다. 기존 .encryption.key를 복원하거나 원래 encryption_key를 설정하세요. 새 키를 만들지 않았습니다.")
        key = Fernet.generate_key()
        # Another new-store initializer may publish its own complete key first.
        _publish_new_file(path, key + b"\n")
        return _read_local_key(path)
    except AppError:
        raise
    except OSError:
        raise AppError("로컬 암호화 키를 저장하거나 읽지 못했습니다. 데이터 폴더의 쓰기 권한을 확인하세요.") from None


def open_local_store(settings):
    store = LocalStore(settings.data_dir, local_encryption_key(settings.data_dir, settings.encryption_key))
    store.read()  # Fail before any writes if an explicitly configured key is wrong.
    return store


def _target_identity(target):
    fingerprint = hashlib.sha256(target.signing_key).hexdigest()
    if isinstance(target, LocalStore):
        return ("local", str(target.root.resolve()), fingerprint)
    if isinstance(target, GitHubStore):
        return ("github", target.repo.casefold(), target.branch, target.PREFIX, fingerprint)
    raise AppError("자료를 이전할 영구 저장소를 확인하세요.")


def _merge_state(current, incoming):
    added = 0
    for collection, value in incoming.items():
        if isinstance(value, dict):
            if collection in current and not isinstance(current[collection], dict):
                raise AppError("기존 저장 자료와 메모리 자료의 형식이 다릅니다. 기존 자료를 덮어쓰지 않았습니다.")
            destination = current.setdefault(collection, {})
            for identity, record in value.items():
                if identity in destination and destination[identity] != record:
                    raise AppError("같은 식별자의 기존 평가 자료가 다릅니다. 기존 자료를 덮어쓰지 않았습니다.")
                if identity not in destination:
                    destination[identity] = copy.deepcopy(record)
                    added += 1
        elif collection in current and current[collection] != value:
            raise AppError("기존 저장 자료와 메모리 자료의 설정이 다릅니다. 기존 자료를 덮어쓰지 않았습니다.")
        else:
            current.setdefault(collection, copy.deepcopy(value))
    return added


def _plaintext(target, relative):
    if isinstance(target, LocalStore):
        path = target.root / relative
        if not os.path.lexists(path):
            return None
        raw = path.read_bytes()
    else:
        raw, _ = target._get(relative)
        if raw is None:
            return None
    try:
        return target.fernet.decrypt(raw)
    except InvalidToken:
        raise AppError("기존 저장 파일의 암호화 키가 일치하지 않습니다. 기존 파일을 덮어쓰지 않았습니다.") from None


def _same_plaintext(existing, incoming, is_json):
    if is_json:
        try:
            return json.loads(existing) == json.loads(incoming)
        except (ValueError, UnicodeDecodeError):
            return False
    return existing == incoming


def _preserve_file(target, relative, incoming, is_json=False):
    """Copy one missing file; concurrent creators never replace existing bytes."""
    for _ in range(6):
        existing = _plaintext(target, relative)
        if existing is not None:
            if not _same_plaintext(existing, incoming, is_json):
                raise AppError("같은 식별자의 기존 첨부·제출 파일 내용이 다릅니다. 기존 파일을 덮어쓰지 않았습니다.")
            return False
        encrypted = target.fernet.encrypt(incoming)
        if isinstance(target, LocalStore):
            if _publish_new_file(target.root / relative, encrypted):
                return True
        else:
            target._check_private()
            response = target._put(relative, encrypted)
            if response.status_code in (200, 201):
                return True
            if response.status_code not in (409, 422):
                raise AppError("평가 파일 이전을 저장하지 못했습니다. 메모리 자료는 유지됩니다.")
    raise AppError("동시 파일 저장으로 자료 이전이 지연되었습니다. 메모리 자료는 유지됩니다.")


class _MigrationTransaction:
    """Preserve original submission bundles while importing current feedback."""
    def __init__(self, target, submitted_paths):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_submitted_paths", submitted_paths)

    def __getattribute__(self, name):
        if name in ("_target", "_submitted_paths", "save_student_submission", "__class__"):
            return object.__getattribute__(self, name)
        return getattr(object.__getattribute__(self, "_target"), name)

    def __setattr__(self, name, value):
        setattr(self._target, name, value)

    def save_student_submission(self, attempt):
        path = student_submission_path(attempt)
        if path in self._submitted_paths:
            return path
        return self._target.save_student_submission(attempt)


def _upgrade_memory_store(source):
    """Refresh a pre-reload cached store in place, preserving live references."""
    if isinstance(source, MemoryStore):
        return
    old_class = type(source)
    if (old_class.__module__ != "think_app.storage" or old_class.__name__ != "MemoryStore" or
            any(not isinstance(getattr(source, field, None), dict) for field in
                ("state", "blobs", "uploads", "submissions")) or
            not isinstance(getattr(source, "signing_key", None), bytes) or
            not callable(getattr(getattr(source, "lock", None), "__enter__", None)) or
            not callable(getattr(getattr(source, "lock", None), "__exit__", None))):
        raise AppError("이전할 메모리 저장소를 확인하세요.")
    with source.lock:
        try:
            source.__class__ = MemoryStore
        except TypeError:
            raise AppError("메모리 저장소를 새 저장 방식으로 연결하지 못했습니다. 기존 메모리 자료는 유지됩니다.") from None
        if not hasattr(source, "_persistence_target"):
            source._persistence_target = None


def migrate_memory_store(source, target):
    """Import a running memory store once per durable destination, without loss."""
    _upgrade_memory_store(source)
    identity = _target_identity(target)
    empty = dict(records=0, blobs=0, uploads=0, submissions=0, already_migrated=False)
    with source.lock:
        completed = getattr(source, "_persistent_migrations", set())
        if identity in completed:
            source._persistence_target = target
            source.signing_key = target.signing_key
            return dict(empty, already_migrated=True)
        if getattr(source, "_persistence_target", None) is not None:
            raise AppError("이미 연결된 영구 저장소의 자료를 다른 저장소로 자동 이전할 수 없습니다. 기존 보관 위치를 유지하세요.")
        snapshot = MemoryStore()
        snapshot.state = source.read()
        snapshot.blobs = copy.deepcopy(source.blobs)
        snapshot.uploads = copy.deepcopy(source.uploads)
        snapshot.submissions = copy.deepcopy(source.submissions)
        if not snapshot.blobs and not snapshot.uploads and not snapshot.submissions and not any(
                isinstance(value, dict) and value for value in snapshot.state.values()):
            source._persistent_migrations = set(completed) | {identity}
            source.signing_key = target.signing_key
            source._persistence_target = target
            return empty
        # Reconstruct a missing individual bundle only when state itself exists;
        # original bundles retain the feedback snapshot from their creation time.
        for attempt in snapshot.state.get("course_attempts", {}).values():
            path = student_submission_path(attempt)
            if path not in snapshot.submissions:
                snapshot.submissions[path] = _submission_bundle(snapshot, attempt)
        for upload in snapshot.state.get("course_uploads", {}).values():
            snapshot.uploads.setdefault(uploaded_file_path(upload), {"schema": 1, "upload": copy.deepcopy(upload)})
        files = []
        for name, raw in snapshot.blobs.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-f0-9]{32}", name) or not isinstance(raw, bytes):
                raise AppError("이전할 첨부 파일의 식별자와 내용을 확인하세요.")
            relative = name + ".enc" if isinstance(target, LocalStore) else "images/" + name + ".enc"
            files.append(("blobs", relative, raw, False))
        for kind, packets in (("uploads", snapshot.uploads), ("submissions", snapshot.submissions)):
            for relative, payload in packets.items():
                record = payload.get("upload" if kind == "uploads" else "submission", {})
                expected = uploaded_file_path(record) if kind == "uploads" else student_submission_path(record)
                if relative != expected or payload.get("schema") != 1:
                    raise AppError("이전할 첨부·제출 파일 경로를 확인하세요.")
                files.append((kind, relative, json.dumps(payload, ensure_ascii=False).encode(), True))
        # Preflight every conflict before publishing anything to the destination.
        _merge_state(copy.deepcopy(target.read()), snapshot.state)
        for _, relative, raw, is_json in files:
            existing = _plaintext(target, relative)
            if existing is not None and not _same_plaintext(existing, raw, is_json):
                raise AppError("같은 식별자의 기존 첨부·제출 파일 내용이 다릅니다. 기존 파일을 덮어쓰지 않았습니다.")
        counts = dict(empty)
        for kind, relative, raw, is_json in files:
            counts[kind] += int(_preserve_file(target, relative, raw, is_json))
        adapter_type = type("_AssessmentMigrationStore", (_MigrationTransaction, type(target)), {})
        adapter = adapter_type(target, set(snapshot.submissions))
        counts["records"] = type(target).transaction(adapter, lambda state: _merge_state(state, snapshot.state))
        source._persistent_migrations = set(completed) | {identity}
        source.signing_key = target.signing_key
        source._persistence_target = target
        return counts
