"""Offline workflow and mocked GitHub CAS tests; no operational writes."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from cryptography.fernet import Fernet

from classroom_core import (ArchivedError, ClassroomService, ConflictError, GitHubStore,
                            MemoryStore, PermissionDenied, StorageError, ValidationError)
from classroom_core.work import WorkService, prepare_attachments


def _response(status, payload=None):
    return SimpleNamespace(status_code=status, json=lambda: payload or {})


class MockGitHub:
    """Locked SHA storage with injected transient/lost responses and no network."""
    def __init__(self):
        self.headers, self.files, self.messages = {}, {}, []
        self.lock = threading.RLock()
        self.fail = False
        self.conflict_once = set()
        self.ambiguous_once = False

    def request(self, method, url, timeout, **kwargs):
        with self.lock:
            if "/git/trees/" in url:
                return _response(200, {"tree": [dict(type="blob", path=p) for p in self.files]})
            if "/contents/" not in url:
                return _response(200, {"private": True})
            path = unquote(url.split("/contents/", 1)[1])
            existing = self.files.get(path)
            sha = hashlib.sha256(existing).hexdigest() if existing else None
            if method == "GET":
                if existing is None:
                    return _response(404)
                return _response(200, dict(sha=sha, encoding="base64", content=base64.b64encode(existing).decode()))
            if self.fail:
                return _response(503)
            if path in self.conflict_once:
                self.conflict_once.remove(path)
                return _response(409)
            body = kwargs["json"]
            if body.get("sha") != sha:
                return _response(409)
            self.files[path] = base64.b64decode(body["content"])
            self.messages.append(body["message"])
            if self.ambiguous_once:
                self.ambiguous_once = False
                raise OSError("response lost after remote commit")
            return _response(201)


def environment(store=None, legacy=None, count=3):
    store = store or MemoryStore()
    users = {"teacher": dict(id="teacher", role="teacher"), "shared": dict(id="shared", role="teacher"),
             "stranger": dict(id="stranger", role="teacher")}
    users.update({f"s{i}": dict(id=f"s{i}", role="student", name=f"학생{i}", **{"class": "1-1"}) for i in range(count)})
    def service(uid):
        return ClassroomService(store, users[uid], users.get, lock_checker=lambda _: False)
    teacher = service("teacher")
    course = teacher.create_course("수학", "2026-2", "수학", teacher_ids=["shared"], student_ids=[f"s{i}" for i in range(count)])
    def work(uid):
        return WorkService(service(uid), legacy=legacy)
    return store, users, teacher, course["id"], work


def assignment(work, cid, **kwargs):
    return work.save_assignment(cid, "탐구", "풀이 과정을 설명하세요.", published=True, **kwargs)


def test_25_concurrent_mock_github_submissions_duplicate_clicks_restart_and_encryption():
    remote, key = MockGitHub(), Fernet.generate_key().decode()
    store = GitHubStore("school/mydashboard", "existing-data", "test-token", key, session=remote)
    store, users, teacher, cid, work = environment(store, count=25)
    task = assignment(work("teacher"), cid, methods=["text", "file"], resubmit_policy="always")
    barrier = threading.Barrier(25)
    def submit(i):
        barrier.wait(timeout=20)
        return work(f"s{i}").submit(cid, task["id"], "request-001", text=f"민감한 답안 {i}",
                                      files=[dict(filename="답안.txt", data=f"첨부 {i}".encode())])
    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(submit, range(25)))
    assert len({r["submission_id"] for r in results}) == 25
    assert all(r["number"] == 1 and r["permanent"] for r in results)
    with ThreadPoolExecutor(max_workers=25) as pool:
        duplicates = list(pool.map(lambda i: work(f"s{i}").submit(cid, task["id"], "request-001", text=f"민감한 답안 {i}",
            files=[dict(filename="답안.txt", data=f"첨부 {i}".encode())]), range(25)))
    assert duplicates == results
    # Two simultaneous identical clicks for one student collapse to one version.
    with ThreadPoolExecutor(max_workers=2) as pool:
        repeated = list(pool.map(lambda _: work("s0").submit(cid, task["id"], "request-002", text="수정 답안"), range(2)))
    assert repeated[0] == repeated[1] and repeated[0]["number"] == 2
    restored = GitHubStore("school/mydashboard", "existing-data", "test-token", key, session=remote)
    restored_teacher = WorkService(ClassroomService(restored, users["teacher"], users.get, lock_checker=lambda _: False))
    for i in range(25):
        record = restored_teacher.submission(cid, task["id"], f"s{i}")
        assert record["versions"][0] == results[i]
        assert len(record["versions"]) == (2 if i == 0 else 1)
        assert len([a for a in restored.get("submissions", record["id"])["audit"] if a["action"] == "submission.submit"]) == len(record["versions"])
    submission_paths = [p for p in remote.files if "/submissions/" in p]
    assert len(submission_paths) == 25
    assert all("민감한".encode() not in raw and "답안.txt".encode() not in raw for raw in remote.files.values())
    assert all("학생" not in path and "s0" not in path.split("/") for path in submission_paths)
    assert set(remote.messages) == {"Save classroom record"}


def test_failed_permanent_save_returns_no_receipt_and_no_partial_audit_then_retry_same_request():
    remote = MockGitHub()
    store = GitHubStore("school/mydashboard", "existing-data", "test-token", Fernet.generate_key().decode(), session=remote)
    _, _, _, cid, work = environment(store)
    task = assignment(work("teacher"), cid)
    remote.fail = True
    with pytest.raises(StorageError):
        work("s0").submit(cid, task["id"], "same-request", "학생 답안")
    assert not any("/submissions/" in p for p in remote.files)
    assert work("s0").submission(cid, task["id"])["status"] == "미제출"
    remote.fail = False
    remote.ambiguous_once = True
    receipt = work("s0").submit(cid, task["id"], "same-request", "학생 답안")
    assert receipt["number"] == 1
    assert work("s0").submit(cid, task["id"], "same-request", "학생 답안") == receipt


def test_immutable_versions_review_draft_publication_request_and_snapshot():
    _, _, _, cid, work = environment()
    teacher, student = work("teacher"), work("s0")
    task = assignment(teacher, cid, max_points=10, rubric=[dict(label="근거", max_points=10)])
    first = student.submit(cid, task["id"], "first", "최초 답안")
    with pytest.raises(ValidationError, match="수정 요청"):
        student.submit(cid, task["id"], "second", "수정 답안")
    teacher.save_review(cid, task["id"], "s0", 1, feedback="미공개 민감 초안", score=5,
                        rubric_scores=[dict(score=5, level="발전", feedback="근거를 더 제시")],
                        review_status="reviewed", score_status="final")
    assert student.submission(cid, task["id"])["reviews"] == {}
    assert not any(n["kind"] == "feedback" for n in student.notifications(cid))
    teacher.publish_review(cid, task["id"], "s0", 1)
    assert student.submission(cid, task["id"])["reviews"]["1"]["score"] == 5
    assert any(n["kind"] == "feedback" for n in student.notifications(cid))
    teacher.request_revision(cid, task["id"], "s0", "이유를 보완하세요.")
    assert student.submission(cid, task["id"])["status"] == "수정 요청"
    teacher.save_assignment(cid, "바뀐 제목", "새 안내", assignment_id=task["id"], max_points=20,
                            rubric=[dict(label="새 기준", max_points=20)], published=True)
    second = student.submit(cid, task["id"], "second", "수정 답안")
    assert second["number"] == 2
    record = student.submission(cid, task["id"])
    assert record["versions"][0] == first
    assert record["versions"][0]["assignment_snapshot"]["max_points"] == 10
    assert record["versions"][1]["assignment_snapshot"]["max_points"] == 20
    assert "2" not in record["reviews"]
    # Reviewing the first answer continues to use the original ten-point rubric.
    with pytest.raises(ValidationError):
        teacher.save_review(cid, task["id"], "s0", 1, score=15)
    teacher.save_review(cid, task["id"], "s0", 2, feedback="두 번째 미공개 초안")
    assert "두 번째 미공개 초안" not in str(student.submission(cid, task["id"]))


def test_other_students_other_classes_unassigned_teacher_revoked_identity_and_files_denied():
    store, users, teacher, cid, work = environment()
    task = assignment(work("teacher"), cid, methods=["text", "file"], target_student_ids=["s0"])
    assert "target_student_ids" not in work("s0").assignment(cid, task["id"])
    work("s0").submit(cid, task["id"], "first", "답안", [dict(filename="private.txt", data=b"private")])
    for call in (lambda: work("s1").assignment(cid, task["id"]),
                 lambda: work("s1").submission(cid, task["id"], "s0"),
                 lambda: work("s1").download_submission(cid, task["id"], "s0", 1, 0),
                 lambda: work("stranger").submission(cid, task["id"], "s0"),
                 lambda: work("s0").save_review(cid, task["id"], "s0", 1)):
        with pytest.raises(PermissionDenied):
            call()
    saved = work("teacher").download_submission(cid, task["id"], "s0", 1, 0)
    assert saved["data"] == b"private"
    fresh = teacher.get_course(cid)
    fresh["student_ids"].remove("s0")
    teacher._write("courses", cid, fresh, fresh["version"], "membership.revoke")
    with pytest.raises(PermissionDenied):
        work("s0").submission(cid, task["id"])
    users["teacher"]["role"] = "student"
    with pytest.raises(PermissionDenied):
        work("teacher").assignment(cid, task["id"])


def test_public_private_questions_and_teacher_personal_observations():
    _, _, _, cid, work = environment()
    student, other = work("s0"), work("s1")
    private = student.save_question(cid, "비공개 질문", visibility="private")
    public = student.save_question(cid, "공개 질문", visibility="course")
    assert {q["id"] for q in other.questions(cid)} == {public["id"]}
    assert len(work("teacher").questions(cid)) == 2
    work("teacher").answer_question(cid, private["id"], "비공개 답변", resolved=True)
    assert "비공개 답변" not in str(other.questions(cid))
    own = work("teacher").save_observation(cid, "s0", "개인 관찰")
    assert work("shared").observations(cid) == []
    with pytest.raises(PermissionDenied):
        student.observations(cid)
    work("teacher").save_observation(cid, "s0", "공유 관찰", observation_id=own["id"], shared_teacher_ids=["shared"])
    assert len(work("shared").observations(cid)) == 1
    with pytest.raises(PermissionDenied):
        work("shared").save_observation(cid, "s0", "타인 기록 수정", observation_id=own["id"])


def test_late_policy_draft_cas_archived_writes_and_files_validation():
    _, _, teacher, cid, work = environment()
    task = assignment(work("teacher"), cid, due_at="2020-01-01T00:00:00+09:00", allow_late=False)
    draft = work("s0").save_draft(cid, task["id"], "임시 답안", expected_revision=0)
    assert draft["permanent"] and draft["revision"] == 1
    with pytest.raises(ConflictError):
        work("s0").save_draft(cid, task["id"], "다른 창", expected_revision=0)
    with pytest.raises(ValidationError, match="마감"):
        work("s0").submit(cid, task["id"], "first", "늦은 답안")
    work("teacher").save_assignment(cid, "탐구", "안내", assignment_id=task["id"], published=True,
                                     due_at="2020-01-01T00:00:00+09:00", allow_late=True)
    assert work("s0").submit(cid, task["id"], "first", "늦은 답안")["late"]
    teacher.archive_course(cid, teacher.get_course(cid)["version"])
    assert work("s0").submission(cid, task["id"])["versions"]
    for call in (lambda: work("s0").save_draft(cid, task["id"], "수정"),
                 lambda: work("teacher").save_post(cid, "공지", "보관 후 작성"),
                 lambda: work("teacher").save_review(cid, task["id"], "s0", 1)):
        with pytest.raises(ArchivedError):
            call()
    for files in ([dict(filename="../secret.txt", data=b"x")],
                  [dict(filename="x.pdf", data=b"not a PDF")],
                  [dict(filename="x.txt", data=b"x" * (2 * 1024 * 1024 + 1))]):
        with pytest.raises(ValidationError):
            prepare_attachments(files)


def test_new_classroom_work_accepts_only_text_file_without_external_provider():
    # Deliberately no activity methods on this adapter: classroom paths must
    # never load an external activity store or require its encryption key.
    store, _, _, cid, work = environment(legacy=SimpleNamespace())
    teacher = work("teacher")
    for fields in (dict(methods=["snorkl"]), dict(activity_id="old-activity"),
                   dict(methods=["file", "snorkl"])):
        with pytest.raises(ValidationError):
            assignment(teacher, cid, **fields)
    with pytest.raises(ValidationError, match="제거"):
        teacher.save_material(cid, "자료", activity_id="old-activity")
    task = assignment(teacher, cid, methods=["text", "file"])
    material = teacher.save_material(cid, "자료", body="설명", published=True)
    assert "activity_id" not in task and "activity_id" not in material
    assert work("s0").submit(cid, task["id"], "new", "직접 답안")["number"] == 1
    assert len(store.list("assignments")) == len(store.list("materials")) == 1


@pytest.mark.parametrize("link", [dict(activity_id="old-activity", methods=["snorkl"]),
                                    dict(methods=["snorkl"]),
                                    dict(activity_id="old-activity", methods=["text"])])
def test_existing_external_assignments_are_disabled_read_only_without_callbacks(link):
    store, _, _, cid, work = environment(legacy=SimpleNamespace())
    teacher = work("teacher")
    task = assignment(teacher, cid)
    original = store.put("assignments", task["id"], dict(task, **link), task["version"])
    visible = work("s0").assignment(cid, task["id"])
    assert visible["disabled"] and "비활성화" in visible["disabled_reason"]
    result = teacher.submission(cid, task["id"], "s0")
    assert result["source"] == "disabled" and result["status"] == "연결 비활성화"
    assert result["versions"] == [] and result["reviews"] == {}
    assert "native" not in result
    for action in (lambda: work("s0").save_draft(cid, task["id"], "답안"),
                   lambda: work("s0").submit(cid, task["id"], "new", "답안"),
                   lambda: teacher.save_assignment(cid, "바꾼 과제", "설명", assignment_id=task["id"]),
                   lambda: teacher.save_review(cid, task["id"], "s0", 1),
                   lambda: teacher.publish_review(cid, task["id"], "s0", 1),
                   lambda: teacher.request_revision(cid, task["id"], "s0", "수정"),
                   lambda: teacher.clone_assignment(cid, task["id"], cid)):
        with pytest.raises(ValidationError, match="비활성화"):
            action()
    with pytest.raises(PermissionDenied):
        work("s1").submission(cid, task["id"], "s0")
    assert teacher.export_assignment(cid, task["id"]) == []
    assert work("s0").notifications(cid) == []
    assert store.get("assignments", task["id"]) == original
    assert store.list("submissions") == []


def test_existing_external_materials_are_disabled_without_conversion_or_new_links():
    store, _, _, cid, work = environment(legacy=SimpleNamespace())
    teacher = work("teacher")
    material = teacher.save_material(cid, "기존 자료", body="보존할 설명", published=True)
    original = store.put("materials", material["id"], dict(material, activity_id="old-activity"), material["version"])
    assert work("s0").materials(cid)[0]["disabled"]
    with pytest.raises(ValidationError, match="비활성화"):
        teacher.save_material(cid, "변경 시도", body="다른 설명", material_id=material["id"])
    with pytest.raises(ValidationError, match="비활성화"):
        assignment(teacher, cid, material_ids=[material["id"]])
    assert store.get("materials", material["id"]) == original
    assert store.list("assignments") == []


def test_legacy_csv_observation_cannot_be_retagged():
    legacy = SimpleNamespace(validate_reference=lambda *args: dict(student_id="s0"))
    _, _, _, cid, work = environment(legacy=legacy)
    with pytest.raises(PermissionDenied, match="일치"):
        work("teacher").save_observation(cid, "s1", "", legacy_ref="existing-observation")


def test_atomic_new_term_copy_templates_no_students_scores_or_published_content():
    store, users, teacher, cid, work = environment()
    material = work("teacher").save_material(cid, "자료", files=[dict(filename="original.txt", data=b"original")], published=True)
    task = assignment(work("teacher"), cid, material_ids=[material["id"]], max_points=10,
                      rubric=[dict(label="설명", max_points=10)])
    work("s0").submit(cid, task["id"], "first", "이전 학생 답안")
    work("teacher").save_review(cid, task["id"], "s0", 1, score=7, feedback="이전 개인 평가")
    copied = teacher.copy_course(cid, "새 학기", "2027-1")
    copied_work = work("teacher")
    materials = copied_work.materials(copied["id"])
    tasks = copied_work.assignments(copied["id"])
    assert len(materials) == len(tasks) == 1
    assert materials[0]["id"] != material["id"] and tasks[0]["id"] != task["id"]
    assert tasks[0]["material_ids"] == [materials[0]["id"]]
    assert not tasks[0]["published"] and tasks[0]["due_at"] is None
    assert copied["student_ids"] == [] and copied["lesson_records"] == {}
    assert "이전 학생 답안" not in str(copied) and "이전 개인 평가" not in str(copied)
    # First edit creates the copied definition's CAS shard and takes precedence.
    edited = copied_work.save_assignment(copied["id"], "수정한 양식", "새 안내", assignment_id=tasks[0]["id"], published=True)
    assert copied_work.assignments(copied["id"])[0]["title"] == edited["title"]
    assert len(copied_work.assignments(copied["id"])) == 1
    assert work("teacher").assignment(cid, task["id"])["title"] == "탐구"


def test_no_automatic_progress_on_material_or_submission_and_draft_feedback():
    store, _, teacher, cid, work = environment()
    task = assignment(work("teacher"), cid)
    before = teacher.get_course(cid)
    work("s0").assignment(cid, task["id"])
    work("s0").submit(cid, task["id"], "first", "답안")
    work("teacher").save_review(cid, task["id"], "s0", 1, feedback="AI 없이 수동 평가", review_status="reviewed")
    assert teacher.get_course(cid) == before
    with pytest.raises(ValidationError, match="다릅니다"):
        work("s0").submit(cid, task["id"], "first", "같은 요청의 다른 답안")


def test_ui_attachment_reruns_deduplicate_raw_upload_and_restored_file():
    from views.classroom_work import _dedup_files
    raw = dict(filename="풀이.txt", data=b"same answer")
    restored = prepare_attachments([raw])[0]
    assert _dedup_files([raw, restored, raw]) == [raw]
    assert len(_dedup_files([raw, dict(filename="풀이.txt", data=b"changed answer")])) == 2


def test_invisible_scoped_lesson_resources_never_fall_back_to_external_links(monkeypatch):
    import views.classroom_work as view
    links, captions = [], []
    fake = SimpleNamespace(materials=lambda cid: [], assignments=lambda cid: [],
                           service=SimpleNamespace(actor=lambda: dict(id="s0", role="student")))
    monkeypatch.setattr(view, "_work", lambda service: fake)
    monkeypatch.setattr(view, "st", SimpleNamespace(caption=captions.append, link_button=lambda *a, **k: links.append(a)))
    lesson = dict(id="lesson", resources=[
        dict(kind="material", id="not-targeted", activity_id="hidden-native", url="https://private.example/file"),
        dict(kind="assignment", id="not-published", activity_id="hidden-native", url="https://private.example/file"),
    ])
    view.render_lesson_resources(fake, dict(id="course"), lesson)
    assert links == []
    assert len(captions) == 2


APP_SOURCE = '''
import streamlit as st
from types import SimpleNamespace
from classroom_core import ClassroomService, MemoryStore
from classroom_core.work import WorkService
from views.classroom_work import render_assignments
if "fixture" not in st.session_state:
    users = {"t": {"id": "t", "role": "teacher", "name": "교사"},
             "s": {"id": "s", "role": "student", "name": "학생", "class": "1-1"},
             "other": {"id": "other", "role": "student", "name": "다른학생", "class": "1-1"}}
    store = MemoryStore()
    svc = ClassroomService(store, users["t"], users.get, lock_checker=lambda _: False)
    course = svc.create_course("수학", "2026-2", "수학", student_ids=["s", "other"])
    work = WorkService(svc)
    task = work.save_assignment(course["id"], "탐구", "설명", max_points=10, published=True)
    st.session_state.fixture = (store, users, course["id"], task["id"])
store, users, cid, aid = st.session_state.fixture
actor = st.session_state.get("actor", "s")
svc = ClassroomService(store, users[actor], users.get, lock_checker=lambda _: False)
work = WorkService(svc, legacy=SimpleNamespace())
render_assignments(work, svc.get_course(cid))
'''


def test_streamlit_submit_receipt_repeat_click_and_identity_scoped_draft():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(APP_SOURCE).run(timeout=30)
    assert not app.exception
    next(w for w in app.text_area if w.label == "내 답안").set_value("나의 풀이").run()
    next(w for w in app.button if w.label == "제출 요청").click().run()
    assert not app.exception
    assert any("제출 완료" in message.value and "제출번호" in message.value for message in app.success)
    next(w for w in app.button if w.label == "제출 요청").click().run()
    assert not app.exception
    store, users, cid, aid = app.session_state["fixture"]
    service = ClassroomService(store, users["s"], users.get, lock_checker=lambda _: False)
    assert len(WorkService(service).submission(cid, aid)["versions"]) == 1
    app.session_state["actor"] = "other"
    app.run(timeout=30)
    assert not app.exception
    assert next(w for w in app.text_area if w.label == "내 답안").value == ""
    assert "나의 풀이" not in str([w.value for w in app.markdown])


def test_streamlit_teacher_draft_stays_private_until_explicit_result_publication():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(APP_SOURCE).run(timeout=30)
    next(w for w in app.text_area if w.label == "내 답안").set_value("학생 답안").run()
    next(w for w in app.button if w.label == "제출 요청").click().run()
    app.session_state["actor"] = "t"
    app.run(timeout=30)
    assert not app.exception
    next(w for w in app.text_area if w.label == "교사 피드백 초안").set_value("검토된 피드백").run()
    next(w for w in app.checkbox if w.label == "교사 검토 완료").check().run()
    next(w for w in app.button if w.label == "평가 초안 저장").click().run()
    assert not app.exception
    app.session_state["actor"] = "s"
    app.run(timeout=30)
    assert "검토된 피드백" not in str([w.value for w in app.markdown])
    app.session_state["actor"] = "t"
    app.run(timeout=30)
    next(w for w in app.checkbox if w.label == "저장한 평가 초안을 학생에게 공개하는 데 동의합니다").check().run()
    next(w for w in app.button if w.label == "결과 공개").click().run()
    assert not app.exception
    app.session_state["actor"] = "s"
    app.run(timeout=30)
    assert not app.exception
    assert "검토된 피드백" in str([w.value for w in app.markdown])
