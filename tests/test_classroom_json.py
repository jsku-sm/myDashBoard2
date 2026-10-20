"""Key-free private JSON workflows against a mock remote, never live GitHub."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest
from cryptography.fernet import Fernet

import auth
import classroom_core
from classroom_core import ClassroomService, GitHubStore, PermissionDenied, StorageError
from classroom_core.work import WorkService
from test_classroom_work import MockGitHub, environment, assignment


def json_cloud(remote):
    return GitHubStore("jsku-sm/class-dashboard-data", "main", "synthetic-test-token", session=remote)


def test_json_25_concurrent_students_duplicate_receipts_and_restart():
    remote = MockGitHub()
    store, users, teacher, cid, work = environment(json_cloud(remote), count=25)
    task = assignment(work("teacher"), cid, methods=["text", "file"], resubmit_policy="always")
    barrier = threading.Barrier(25)
    def submit(index):
        barrier.wait(timeout=20)
        return work(f"s{index}").submit(cid, task["id"], "same-operation", f"답안 {index}",
                                       [dict(filename="work.txt", data=f"file {index}".encode())])
    with ThreadPoolExecutor(max_workers=25) as pool:
        receipts = list(pool.map(submit, range(25)))
    assert len({r["submission_id"] for r in receipts}) == 25
    for index in range(25):
        assert work(f"s{index}").submit(cid, task["id"], "same-operation", f"답안 {index}",
                                         [dict(filename="work.txt", data=f"file {index}".encode())]) == receipts[index]
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicate = list(pool.map(lambda _: work("s0").submit(cid, task["id"], "second-operation", "수정 답안"), range(2)))
    assert duplicate[0] == duplicate[1] and duplicate[0]["number"] == 2
    restarted = WorkService(ClassroomService(json_cloud(remote), users["teacher"], users.get, lock_checker=lambda _: False))
    for index in range(25):
        record = restarted.submission(cid, task["id"], f"s{index}")
        assert record["versions"][0] == receipts[index]
        assert len(record["versions"]) == (2 if index == 0 else 1)
    paths = [p for p in remote.files if "/submissions/" in p]
    assert len(paths) == 25
    assert all(p.startswith("data/classroom/v2/") and p.endswith(".json") for p in remote.files)
    assert all(json.loads(raw)["record"]["schema_version"] == 2 for raw in remote.files.values())
    assert any("답안 0" in raw.decode() for raw in remote.files.values())
    assert set(remote.messages) == {"Save classroom record"}


def test_json_failure_has_no_success_receipt_and_retry_preserves_one_version():
    remote = MockGitHub()
    store, users, teacher, cid, work = environment(json_cloud(remote))
    task = assignment(work("teacher"), cid)
    remote.fail = True
    with pytest.raises(StorageError):
        work("s0").submit(cid, task["id"], "retry-id", "작성 중이던 답안")
    assert not any("/submissions/" in p for p in remote.files)
    assert work("s0").submission(cid, task["id"])["status"] == "미제출"
    remote.fail = False
    remote.ambiguous_once = True
    receipt = work("s0").submit(cid, task["id"], "retry-id", "작성 중이던 답안")
    assert work("s0").submit(cid, task["id"], "retry-id", "작성 중이던 답안") == receipt
    assert receipt["number"] == 1


def test_json_storage_retains_server_access_checks_and_unpublished_feedback():
    store, users, teacher, cid, work = environment(json_cloud(MockGitHub()))
    task = assignment(work("teacher"), cid, methods=["text", "file"], max_points=10)
    work("s0").submit(cid, task["id"], "first", "내 답안", [dict(filename="work.txt", data=b"own")])
    work("teacher").save_review(cid, task["id"], "s0", 1, feedback="미공개 초안", score=8, review_status="reviewed", score_status="final")
    assert work("s0").submission(cid, task["id"])["reviews"] == {}
    for action in (lambda: work("s1").submission(cid, task["id"], "s0"),
                   lambda: work("s1").download_submission(cid, task["id"], "s0", 1, 0),
                   lambda: work("stranger").assignment(cid, task["id"])):
        with pytest.raises(PermissionDenied):
            action()
    work("teacher").publish_review(cid, task["id"], "s0", 1)
    assert work("s0").submission(cid, task["id"])["reviews"]["1"]["score"] == 8


def test_json_same_id_never_replaces_or_reads_original_ciphertext():
    remote = MockGitHub()
    key = Fernet.generate_key().decode()
    original = GitHubStore("jsku-sm/class-dashboard-data", "main", "test", key, session=remote)
    saved = original.put("courses", "same-id", {"id": "same-id", "title": "암호화 원본"})
    before = copy.deepcopy(remote.files)
    current = json_cloud(remote)
    assert current.get("courses", "same-id") is None
    assert current.list("courses") == []
    assert current.legacy_data_present() is True
    current.put("courses", "same-id", {"id": "same-id", "title": "새 JSON 기록"})
    assert all(remote.files[path] == raw for path, raw in before.items())
    assert original.get("courses", "same-id", fresh=True) == saved
    assert current.get("courses", "same-id")["title"] == "새 JSON 기록"


def test_real_classroom_page_opens_without_key_and_notes_preserved_legacy_data(monkeypatch):
    from streamlit.testing.v1 import AppTest
    remote = MockGitHub()
    encrypted = GitHubStore("jsku-sm/class-dashboard-data", "main", "test", Fernet.generate_key().decode(), session=remote)
    encrypted.put("courses", "old", {"id": "old", "title": "이전 수업"})
    store = json_cloud(remote)
    user = {"id": "teacher", "role": "teacher", "name": "교사", "must_change": "0"}
    monkeypatch.setattr(classroom_core, "get_store", lambda: store)
    monkeypatch.setattr(auth, "get_user", lambda uid: user if uid == "teacher" else None)
    app = AppTest.from_string("from views.classroom import page\npage({'id':'teacher','role':'teacher','name':'교사'})\n").run()
    assert not app.exception and not app.error
    assert any("내용 암호화 없음" in message.value for message in app.caption)
    assert any("이전 암호화 기록" in message.value for message in app.info)
    assert any("전체 학급 진도" in message.value for message in app.markdown)
