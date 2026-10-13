"""Assessment state and original attachments survive process-store restarts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import io
import stat
import threading
from types import SimpleNamespace
import wave
import zipfile

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app.ai import normalized_image
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager, now
from think_app.persistence import local_encryption_key, open_local_store, migrate_memory_store
from think_app.question_files import QuestionFiles
from think_app.storage import AppError, GitHubStore, LocalStore, MemoryStore
from think_app.uploads import UploadedFiles


def source_assessment():
    source = MemoryStore()
    cid = CourseManager(source).create("영속 수행평가", "#123456", ["1반"])
    problem = QuestionFiles(source).save(cid, "2+2를 계산하세요.".encode(), "문제.txt")
    room = Classroom(source)
    aid = room.save_activity(cid, "문제 평가", "", "4", ["풀이를 설명한다."], 2, now()[:10], None,
                             question_files=[problem])
    room.distribute_activity(aid)
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    files = UploadedFiles(source)
    document = files.save(aid, "1001", "학생", "1반", "풀이.pdf", pdf.getvalue())
    picture = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(picture, "PNG")
    files.save(aid, "1001", "학생", "1반", "사진.png", picture.getvalue())
    audio = io.BytesIO()
    with wave.open(audio, "wb") as recording:
        recording.setnchannels(1); recording.setsampwidth(2); recording.setframerate(16000)
        recording.writeframes(b"\x00" * 3200)
    request = room.submit(aid, "1001", "학생", "1반", "답은 4입니다.", [normalized_image(picture.getvalue())],
                          False, "a" * 32, audio=audio.getvalue(), upload_ids=[document["id"]])
    room.comment(request, "풀이 근거가 좋습니다.")
    source.transaction(lambda state: state["course_attempts"][request].update(feedback={"correctness": "correct"}))
    return source, cid, aid, request, document, pdf.getvalue()


def test_automatic_key_is_owner_only_reused_and_state_survives_restart(tmp_path):
    settings = Settings(mode="local", data_dir=str(tmp_path))
    first = open_local_store(settings)
    cid = CourseManager(first).create("재실행 후 남는 수업", "#123456", ["1반"])
    key_path = tmp_path / ".encryption.key"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    original_key_file = key_path.read_bytes()
    restarted = open_local_store(settings)
    assert CourseManager(restarted).get(cid)["title"] == "재실행 후 남는 수업"
    assert key_path.read_bytes() == original_key_file
    assert "재실행".encode() not in (tmp_path / "state.enc").read_bytes()


def test_concurrent_initializers_publish_one_complete_key_and_remove_temporary_files(tmp_path):
    with ThreadPoolExecutor(max_workers=12) as executor:
        keys = list(executor.map(lambda _: local_encryption_key(tmp_path), range(36)))
    assert len(set(keys)) == 1
    assert stat.S_IMODE((tmp_path / ".encryption.key").stat().st_mode) == 0o600
    assert [path.name for path in tmp_path.iterdir()] == [".encryption.key"]


def test_explicit_key_is_not_replaced_or_written_to_an_automatic_key_file(tmp_path):
    key = Fernet.generate_key().decode()
    settings = Settings(mode="local", data_dir=str(tmp_path), encryption_key=key)
    store = open_local_store(settings)
    cid = CourseManager(store).create("명시적 키 사용", "#123456", ["1반"])
    assert not (tmp_path / ".encryption.key").exists()
    assert CourseManager(open_local_store(settings)).get(cid)["title"] == "명시적 키 사용"


def test_existing_state_without_a_key_never_creates_a_replacement_key(tmp_path):
    store = LocalStore(tmp_path, Fernet.generate_key().decode())
    CourseManager(store).create("기존 암호화 자료", "#123456", ["1반"])
    before = (tmp_path / "state.enc").read_bytes()
    with pytest.raises(AppError, match="기존 평가 자료|기존.*키"):
        local_encryption_key(tmp_path)
    assert not (tmp_path / ".encryption.key").exists()
    assert (tmp_path / "state.enc").read_bytes() == before


def test_corrupt_key_is_preserved_and_wrong_explicit_key_cannot_write_existing_state(tmp_path):
    settings = Settings(mode="local", data_dir=str(tmp_path))
    store = open_local_store(settings)
    CourseManager(store).create("기존 자료", "#123456", ["1반"])
    before = (tmp_path / "state.enc").read_bytes()
    wrong = Settings(mode="local", data_dir=str(tmp_path), encryption_key=Fernet.generate_key().decode())
    with pytest.raises(AppError, match="기존 암호화키"):
        open_local_store(wrong)
    (tmp_path / ".encryption.key").write_bytes(b"corrupt")
    with pytest.raises(AppError, match="기존 키 파일"):
        open_local_store(settings)
    assert (tmp_path / ".encryption.key").read_bytes() == b"corrupt"
    assert (tmp_path / "state.enc").read_bytes() == before


def test_memory_migration_preserves_current_feedback_original_bundles_and_all_attachments(tmp_path):
    source, cid, aid, request, document, raw = source_assessment()
    original_state = source.read()
    original_bundles = copy.deepcopy(source.submissions)
    settings = Settings(mode="local", data_dir=str(tmp_path))
    target = open_local_store(settings)
    result = migrate_memory_store(source, target)
    assert result["records"] > 0 and result["blobs"] == len(source.blobs)
    assert result["uploads"] == len(source.uploads) and result["submissions"] == len(source.submissions)
    assert source.read() == original_state and target.read() == original_state
    restarted = open_local_store(settings)
    attempt = restarted.read()["course_attempts"][request]
    assert attempt["teacher_comment"] == "풀이 근거가 좋습니다." and attempt["feedback"]["correctness"] == "correct"
    assert restarted.get_student_submission(attempt) == original_bundles[attempt["submission_file"]]
    assert restarted.get_student_submission(attempt)["submission"]["feedback"] is None
    assert base64.b64decode(restarted.get_student_submission(attempt)["assets"][document["blob_ref"]]["base64"]) == raw
    for name, contents in source.blobs.items():
        assert restarted.get_blob(name) == contents
    for upload in source.read()["course_uploads"].values():
        assert restarted.get_uploaded_file(upload) == upload
    with zipfile.ZipFile(io.BytesIO(Classroom(restarted).export(cid, aid))) as archive:
        assert archive.read(f"답안/{request}/첨부-1-풀이.pdf") == raw


def test_success_marker_skips_stale_source_after_destination_edits_and_store_reconstruction(tmp_path):
    source, cid, *_ = source_assessment()
    settings = Settings(mode="local", data_dir=str(tmp_path))
    target = open_local_store(settings)
    migrate_memory_store(source, target)
    target.transaction(lambda state: state["courses"][cid].update(title="영구 저장소에서 수정"))
    result = migrate_memory_store(source, open_local_store(settings))
    assert result["already_migrated"] and result["records"] == result["blobs"] == 0
    assert target.read()["courses"][cid]["title"] == "영구 저장소에서 수정"


def test_first_migration_state_conflict_preserves_existing_data_and_source(tmp_path):
    source, cid, *_ = source_assessment()
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    target.transaction(lambda state: state["courses"].update({cid: {"id": cid, "title": "기존 수업"}}))
    before = target.read()
    files = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(AppError, match="기존 평가 자료가 다릅니다"):
        migrate_memory_store(source, target)
    assert target.read() == before
    assert {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == files
    assert source.read()["courses"][cid]["title"] == "영속 수행평가"


def test_first_migration_blob_conflict_does_not_overwrite_any_existing_file(tmp_path):
    source, *_ = source_assessment()
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    name = next(iter(source.blobs))
    target.put_blob(name, b"existing attachment")
    before = (tmp_path / (name + ".enc")).read_bytes()
    with pytest.raises(AppError, match="기존 첨부.*내용이 다릅니다"):
        migrate_memory_store(source, target)
    assert target.get_blob(name) == b"existing attachment"
    assert (tmp_path / (name + ".enc")).read_bytes() == before
    assert not (tmp_path / "state.enc").exists()


def test_blank_memory_store_is_a_noop_and_marks_the_durable_destination_for_forwarding(tmp_path):
    source = MemoryStore()
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    assert migrate_memory_store(source, target)["records"] == 0
    assert not (tmp_path / "state.enc").exists()
    assert source._persistence_target is target
    cid = CourseManager(target).create("나중에 생긴 자료", "#123456", ["1반"])
    assert migrate_memory_store(source, target)["already_migrated"]
    assert CourseManager(target).get(cid)["title"] == "나중에 생긴 자료"


def test_forwarded_memory_source_cannot_silently_migrate_stale_assets_to_a_different_store(tmp_path):
    source = MemoryStore()
    first = open_local_store(Settings(mode="local", data_dir=str(tmp_path / "first")))
    second = open_local_store(Settings(mode="local", data_dir=str(tmp_path / "second")))
    migrate_memory_store(source, first)
    with pytest.raises(AppError, match="다른 저장소"):
        migrate_memory_store(source, second)
    assert source._persistence_target is first
    assert not (tmp_path / "second" / "state.enc").exists()


class FakePrivateGitHub(GitHubStore):
    """Run the real GitHub store's state/CAS contract entirely in memory."""
    def __init__(self):
        key = Fernet.generate_key()
        self.fernet = Fernet(key)
        self.signing_key = key
        self.repo, self.branch = "test/private", "main"
        self._read_lock = threading.RLock()
        self._cached_state, self._cache_until = None, 0
        self.files = {}

    def _check_private(self): pass

    def _get(self, relative):
        raw = self.files.get(relative)
        return raw, hashlib.sha256(raw).hexdigest() if raw is not None else None

    def _put(self, relative, raw, sha=None):
        existing, current_sha = self._get(relative)
        if current_sha != sha:
            return SimpleNamespace(status_code=409)
        self.files[relative] = raw
        return SimpleNamespace(status_code=201 if existing is None else 200)


def test_memory_to_private_github_migration_copies_assets_without_external_calls():
    source, cid, _, request, _, _ = source_assessment()
    original = source.read()
    bundle = source.get_student_submission(original["course_attempts"][request])
    target = FakePrivateGitHub()
    result = migrate_memory_store(source, target)
    assert result["blobs"] == len(source.blobs) and target.read() == original
    attempt = target.read()["course_attempts"][request]
    assert target.get_student_submission(attempt) == bundle
    assert all(target.get_blob(name) == raw for name, raw in source.blobs.items())
    target.transaction(lambda state: state["courses"][cid].update(title="원격 수정"))
    assert migrate_memory_store(source, target)["already_migrated"]
    assert target.read()["courses"][cid]["title"] == "원격 수정"


def test_migration_merges_unrelated_existing_courses_without_changing_their_records(tmp_path):
    source, cid, *_ = source_assessment()
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    existing = CourseManager(target).create("이미 저장된 수업", "#654321", ["2반"])
    before = target.read()["courses"][existing]
    migrate_memory_store(source, target)
    assert target.read()["courses"][existing] == before
    assert target.read()["courses"][cid]["title"] == "영속 수행평가"
    assert len(target.read()["courses"]) == 2


def test_interrupted_final_state_write_keeps_source_and_can_retry_completed_files(tmp_path):
    class FailingLocalStore(LocalStore):
        fail_once = True

        def transaction(self, change):
            if self.fail_once:
                self.fail_once = False
                raise AppError("모의 저장 중단")
            return super().transaction(change)

    source, cid, *_ = source_assessment()
    target = FailingLocalStore(tmp_path, local_encryption_key(tmp_path))
    with pytest.raises(AppError, match="모의 저장 중단"):
        migrate_memory_store(source, target)
    assert getattr(source, "_persistence_target", None) is None
    assert not (tmp_path / "state.enc").exists()
    assert source.read()["courses"][cid]["title"] == "영속 수행평가"
    result = migrate_memory_store(source, target)
    assert result["records"] > 0 and result["blobs"] == result["uploads"] == result["submissions"] == 0
    assert source._persistence_target is target
    assert target.read()["courses"][cid]["title"] == "영속 수행평가"


def test_pre_reload_cached_memory_store_keeps_identity_data_and_forwards_late_writes(tmp_path):
    source, cid, *_ = source_assessment()
    original_state = source.read()
    original_identity = id(source)
    old_class = type("MemoryStore", (), {"__module__": "think_app.storage"})
    source.__class__ = old_class
    source.__dict__.pop("_persistence_target", None)
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    migrate_memory_store(source, target)
    assert id(source) == original_identity and isinstance(source, MemoryStore)
    assert source.state == original_state and target.read()["courses"][cid] == original_state["courses"][cid]
    assert source._persistence_target is target
    late = CourseManager(source).create("이전 객체에서 늦게 저장한 수업", "#123456", ["1반"])
    source.put_blob("f" * 32, b"late attachment")
    restarted = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    assert CourseManager(restarted).get(late)["title"] == "이전 객체에서 늦게 저장한 수업"
    assert restarted.get_blob("f" * 32) == b"late attachment"
    assert late not in source.state["courses"]


@pytest.mark.parametrize("module,name", [("another.module", "MemoryStore"), ("think_app.storage", "OtherStore")])
def test_unrelated_objects_cannot_be_reclassified_as_a_cached_memory_store(tmp_path, module, name):
    source = type(name, (), {"__module__": module})()
    source.state, source.blobs, source.uploads, source.submissions = {}, {}, {}, {}
    source.lock, source.signing_key = threading.RLock(), b"placeholder"
    original_class = type(source)
    target = open_local_store(Settings(mode="local", data_dir=str(tmp_path)))
    with pytest.raises(AppError, match="메모리 저장소"):
        migrate_memory_store(source, target)
    assert type(source) is original_class and not (tmp_path / "state.enc").exists()
