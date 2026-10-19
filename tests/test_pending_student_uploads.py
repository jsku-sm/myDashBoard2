"""Teachers can find saved answer files before the student submits the answer."""
import io

from cryptography.fernet import Fernet
from pypdf import PdfWriter
import pytest

from think_app import classroom as classroom_module
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.storage import LocalStore, MemoryStore
from think_app.uploads import UploadedFiles


def pdf_bytes(subject="학생 풀이"):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Subject": subject})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def clock(monkeypatch):
    instant = ["2026-10-19T09:00:00+09:00"]
    monkeypatch.setattr(classroom_module, "now", lambda: instant[0])
    return instant


def assessment(store):
    room = Classroom(store)
    cid = CourseManager(store).create("수행평가", "#123456", ["1-1", "1-2"])
    aid = room.save_activity(cid, "풀이 설명", "문제를 풀고 파일을 올리세요.", "모범 풀이", ["풀이 근거"],
                             2, "2026-10-19", "2026-10-19")
    room.distribute_activity(aid)
    return room, UploadedFiles(store), cid, aid


def save_pdf(files, aid, subject="학생 풀이", **changes):
    values = dict(aid=aid, student_id="10101", name="학생", class_id="1-1",
                  filename="풀이.pdf", raw=pdf_bytes(subject))
    values.update(changes)
    return files.save(**values)


def test_upload_only_file_is_visible_without_creating_a_submission(clock):
    store = MemoryStore()
    room, files, _, aid = assessment(store)
    record = save_pdf(files, aid)

    pending = files.pending_for_activity(aid)

    assert pending == [record]
    assert not room.attempts(aid)
    assert files.read(pending[0], aid, "10101", "1-1", original=True) == pdf_bytes()
    pending[0]["name"] = "변경"
    assert files.pending_for_activity(aid)[0]["name"] == "학생"


def test_files_used_in_any_previous_submission_stay_out_of_pending_uploads(clock):
    store = MemoryStore()
    room, files, _, aid = assessment(store)
    submitted = save_pdf(files, aid, "첫 풀이")
    room.submit(aid, "10101", "학생", "1-1", "", [], False, "a" * 32,
                upload_ids=[submitted["id"]])
    revised = save_pdf(files, aid, "수정 풀이")
    room.submit(aid, "10101", "학생", "1-1", "두 번째 글 답안", [], False, "b" * 32)

    assert files.pending_for_activity(aid) == [revised]
    assert len(room.attempts(aid)) == 2
    assert files.for_student(aid, "10101", "1-1") == [submitted, revised]


def test_pending_uploads_use_exact_activity_course_class_and_real_student_scope(clock):
    store = MemoryStore()
    room, files, cid, aid = assessment(store)
    own = save_pdf(files, aid)
    other_class = save_pdf(files, aid, class_id="1-2")
    save_pdf(files, aid, preview=True)
    other_activity = room.save_activity(cid, "다른 평가", "문제", "답", ["기준"], 2,
                                        "2026-10-19", "2026-10-19")
    room.distribute_activity(other_activity)
    save_pdf(files, other_activity)
    _, _, other_course, other_aid = assessment(store)
    save_pdf(files, other_aid)

    def add_ineligible_metadata(state):
        state["course_uploads"]["c" * 32] = dict(own, id="c" * 32, course_id=other_course)
        state["course_uploads"]["d" * 32] = dict(own, id="d" * 32, saved=False)

    store.transaction(add_ineligible_metadata)

    assert {item["id"] for item in files.pending_for_activity(aid)} == {own["id"], other_class["id"]}
    assert files.pending_for_activity(aid, "1-1") == [own]
    assert files.pending_for_activity(aid, "1-2") == [other_class]
    assert files.pending_for_activity(aid, "1반") == []
    assert files.pending_for_activity("missing") == []


def test_teacher_can_find_pending_upload_after_assessment_ends(clock):
    store = MemoryStore()
    _, files, _, aid = assessment(store)
    record = save_pdf(files, aid)
    clock[0] = "2026-10-20T09:00:00+09:00"

    assert files.pending_for_activity(aid) == [record]
    assert files.read(record, aid, "10101", "1-1", original=True) == pdf_bytes()


def test_pending_uploads_survive_encrypted_restart_and_disappear_after_submission(tmp_path, clock):
    key = Fernet.generate_key().decode()
    room, files, _, aid = assessment(LocalStore(tmp_path, key))
    record = save_pdf(files, aid)
    restarted = LocalStore(tmp_path, key)
    restored_files = UploadedFiles(restarted)

    assert restored_files.pending_for_activity(aid, "1-1") == [record]
    assert restored_files.read(record, aid, "10101", "1-1", original=True) == pdf_bytes()

    Classroom(restarted).submit(aid, "10101", "학생", "1-1", "", [], False, "a" * 32,
                                upload_ids=[record["id"]])

    assert UploadedFiles(LocalStore(tmp_path, key)).pending_for_activity(aid) == []
