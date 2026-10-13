"""Offline Cloud persistence through a private GitHub repository and stable key."""
import base64
import copy
import hashlib
import io
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
from PIL import Image
from pypdf import PdfWriter
import pytest

from think_app import classroom as classroom_module
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.question_files import QuestionFiles
from think_app.reference_images import ReferenceImages
from think_app.storage import AppError, GitHubStore, blank
from think_app.uploads import UploadedFiles


PREFIX = "think-learning-v1/"
KEY_PATH = PREFIX + ".encryption.key"
STATE_PATH = PREFIX + "state.enc"


class FakePrivateRepository:
    """Emulate only the GitHub requests used by the encrypted assessment store."""
    def __init__(self, private=True):
        self.private = private
        self.files = {}
        self.headers = {}
        self.calls = []
        self.key_put_status = None
        self.key_conflict_status = None
        self.conflict_winner = None

    @staticmethod
    def response(status, body=None):
        return SimpleNamespace(status_code=status, json=lambda: body or {})

    def request(self, method, url, timeout, **kwargs):
        self.calls.append((method, url, copy.deepcopy(kwargs)))
        if url == "https://api.github.com/repos/owner/private-data":
            return self.response(200, {"private": self.private})
        if "/git/blobs/" in url and method == "GET":
            sha = url.rsplit("/", 1)[-1]
            raw = next((value for value in self.files.values() if hashlib.sha256(value).hexdigest() == sha), None)
            if raw is None:
                return self.response(404)
            return self.response(200, {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        if "/contents/" not in url:
            raise AssertionError("Unexpected fake GitHub request")
        path = url.split("/contents/", 1)[1]
        if method == "GET":
            raw = self.files.get(path)
            if raw is None:
                return self.response(404)
            sha = hashlib.sha256(raw).hexdigest()
            if len(raw) > 1_000_000:
                return self.response(200, {"encoding": "none", "sha": sha})
            return self.response(200, {"content": base64.b64encode(raw).decode(), "encoding": "base64", "sha": sha})
        if method == "PUT":
            body = kwargs["json"]
            assert body["branch"] == "main"
            if path == KEY_PATH:
                if self.key_put_status is not None:
                    return self.response(self.key_put_status)
                if self.key_conflict_status is not None:
                    assert path not in self.files and "sha" not in body
                    self.files[path] = self.conflict_winner
                    status, self.key_conflict_status = self.key_conflict_status, None
                    return self.response(status)
            old = self.files.get(path)
            if old is None and "sha" in body:
                return self.response(409)
            if old is not None and body.get("sha") != hashlib.sha256(old).hexdigest():
                return self.response(409)
            self.files[path] = base64.b64decode(body["content"])
            return self.response(201 if old is None else 200)
        raise AssertionError("Unexpected fake GitHub method")


def cloud_store(repository, key=""):
    return GitHubStore("owner/private-data", "main", "fake-test-token", key, session=repository)


def key_requests(repository, method):
    return [call for call in repository.calls if call[0] == method and call[1].endswith("/" + KEY_PATH)]


def image_bytes(color="blue"):
    output = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(output, "PNG")
    return output.getvalue()


def pdf_bytes(large=False):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if large:
        writer.add_metadata({"/Comment": "x" * 1_100_000})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("key", ["", None])
def test_private_repository_creates_one_stable_key_before_any_assessment_state(key):
    repository = FakePrivateRepository()
    store = cloud_store(repository, key)
    assert len(repository.files[KEY_PATH]) == 44
    assert store.signing_key == repository.files[KEY_PATH]
    assert list(repository.files) == [KEY_PATH]
    assert len(key_requests(repository, "PUT")) == 1
    assert repository.calls[0][1] == "https://api.github.com/repos/owner/private-data"
    assert "sha" not in key_requests(repository, "PUT")[0][2]["json"]
    assert store.read() == blank()


def test_new_store_instance_reuses_key_without_rewriting_or_losing_saved_state():
    repository = FakePrivateRepository()
    first = cloud_store(repository)
    cid = CourseManager(first).create("재시작 보관 수업", "#123456", ["1반"])
    before = copy.deepcopy(repository.files)
    restarted = cloud_store(repository)
    assert restarted.signing_key == first.signing_key
    assert CourseManager(restarted).get(cid)["title"] == "재시작 보관 수업"
    assert repository.files == before
    assert len(key_requests(repository, "PUT")) == 1


@pytest.mark.parametrize("status", [409, 422])
def test_concurrent_initial_key_creation_reads_the_winning_key(status):
    repository = FakePrivateRepository()
    repository.key_conflict_status = status
    repository.conflict_winner = Fernet.generate_key()
    store = cloud_store(repository)
    assert store.signing_key == repository.conflict_winner == repository.files[KEY_PATH]
    assert len(key_requests(repository, "PUT")) == 1
    assert len(key_requests(repository, "GET")) == 2


def test_public_repository_is_rejected_before_any_key_read_or_write():
    repository = FakePrivateRepository(private=False)
    with pytest.raises(AppError, match="비공개"):
        cloud_store(repository)
    assert repository.files == {}
    assert not key_requests(repository, "GET") and not key_requests(repository, "PUT")


@pytest.mark.parametrize("status", [403, 500])
def test_failed_key_creation_does_not_fall_back_to_ephemeral_key(status):
    repository = FakePrivateRepository()
    repository.key_put_status = status
    with pytest.raises(AppError, match="저장하지 못했습니다"):
        cloud_store(repository)
    assert repository.files == {} and len(key_requests(repository, "PUT")) == 1


def test_repeated_key_creation_conflicts_stop_without_creating_a_new_local_key():
    repository = FakePrivateRepository()
    repository.key_put_status = 409
    with pytest.raises(AppError, match="지연되었습니다"):
        cloud_store(repository)
    assert len(key_requests(repository, "PUT")) == 6 and repository.files == {}


@pytest.mark.parametrize("raw", [b"", b"not-a-fernet-key", b"\xff\xff"])
def test_invalid_saved_key_is_never_replaced(raw):
    repository = FakePrivateRepository()
    repository.files[KEY_PATH] = raw
    with pytest.raises(AppError, match="키 파일을 지우거나 새 키로 바꾸지"):
        cloud_store(repository)
    assert repository.files == {KEY_PATH: raw} and not key_requests(repository, "PUT")


def test_existing_encrypted_state_without_automatic_key_requires_its_original_key():
    repository = FakePrivateRepository()
    key = Fernet.generate_key()
    repository.files[STATE_PATH] = Fernet(key).encrypt(json.dumps(blank()).encode())
    before = copy.deepcopy(repository.files)
    with pytest.raises(AppError, match="처음 저장할 때 사용한 encryption_key"):
        cloud_store(repository)
    assert repository.files == before and not key_requests(repository, "PUT")


def test_explicit_existing_key_reads_older_state_without_auto_key_requests():
    repository = FakePrivateRepository()
    key = Fernet.generate_key().decode()
    first = cloud_store(repository, key)
    cid = CourseManager(first).create("기존 설정 수업", "#123456", ["1반"])
    assert KEY_PATH not in repository.files
    restarted = cloud_store(repository, key)
    assert CourseManager(restarted).get(cid)["title"] == "기존 설정 수업"
    assert not key_requests(repository, "GET") and not key_requests(repository, "PUT")


def test_explicit_key_takes_priority_over_unrelated_saved_auto_key():
    repository = FakePrivateRepository()
    key = Fernet.generate_key().decode()
    repository.files[KEY_PATH] = b"unrelated-key-file"
    state = dict(blank(), marker="원래 키로 저장한 자료")
    repository.files[STATE_PATH] = Fernet(key.encode()).encrypt(json.dumps(state).encode())
    assert cloud_store(repository, key).read() == state
    assert not key_requests(repository, "GET") and not key_requests(repository, "PUT")


@pytest.mark.parametrize("large_pdf", [False, True])
def test_restarted_cloud_store_preserves_questions_model_images_and_student_pdf_image_files(monkeypatch, large_pdf):
    monkeypatch.setattr(classroom_module, "now", lambda: "2026-10-14T09:00:00+09:00")
    repository = FakePrivateRepository()
    first = cloud_store(repository)
    manager, room = CourseManager(first), Classroom(first)
    cid = manager.create("첨부까지 보관되는 수업", "#123456", ["1반"])
    question_raw, reference_raw = image_bytes(), image_bytes("green")
    question = QuestionFiles(first).save(cid, question_raw, "문제.png")
    reference = ReferenceImages(first).save(cid, reference_raw, "모범답안.png")
    aid = room.save_activity(cid, "첨부 수행평가", "문제 파일을 읽고 풀어보세요.", "교사의 모범풀이",
                             ["근거를 설명한다."], 2, "2026-10-14", None,
                             question_files=[question], expected_images=[reference])
    room.distribute_activity(aid)
    uploads = UploadedFiles(first)
    raw_pdf, raw_image = pdf_bytes(large_pdf), image_bytes("red")
    document = uploads.save(aid, "1001", "학생", "1반", "풀이.pdf", raw_pdf)
    picture = uploads.save(aid, "1001", "학생", "1반", "풀이.png", raw_image)
    request = room.submit(aid, "1001", "학생", "1반", "첨부한 풀이를 보세요.", [], False, "a" * 32,
                          upload_ids=[document["id"], picture["id"]])
    snapshot = first.read()
    restarted = cloud_store(repository)
    assert restarted.signing_key == first.signing_key
    assert restarted.read() == snapshot
    assert Classroom(restarted).activity(aid)["expected"] == "교사의 모범풀이"
    assert QuestionFiles(restarted).read(question, cid, original=True) == question_raw
    assert ReferenceImages(restarted).read(reference, cid) == first.get_blob(reference["blob_ref"])
    assert restarted.get_blob(reference["original_ref"]) == reference_raw
    files = UploadedFiles(restarted)
    assert files.read(document, aid, "1001", "1반", original=True) == raw_pdf
    assert files.read(picture, aid, "1001", "1반", original=True) == raw_image
    assert restarted.get_uploaded_file(document) == document
    attempt = snapshot["course_attempts"][request]
    bundle = restarted.get_student_submission(attempt)
    assert bundle["submission"] == attempt
    assert base64.b64decode(bundle["assets"][document["original_ref"]]["base64"]) == raw_pdf
    assert bundle["assets"][document["original_ref"]]["mime_type"] == "application/pdf"
    assert repository.files[STATE_PATH].startswith(b"gAAAA")
    if large_pdf:
        assert any("/git/blobs/" in url for _, url, _ in repository.calls)
