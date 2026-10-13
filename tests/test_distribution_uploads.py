"""Student image drafts require distribution and in-period course access."""
import io

from PIL import Image
import pytest

from think_app import classroom as classroom_module
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.storage import AppError, MemoryStore
from think_app.uploads import UploadedFiles


def answer_image():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def upload_assessment(monkeypatch):
    clock = ["2026-10-14T10:00:00+09:00"]
    monkeypatch.setattr(classroom_module, "now", lambda: clock[0])
    store = MemoryStore()
    cid = CourseManager(store).create("수행평가", "#123456", ["1반"])
    room = Classroom(store)
    aid = room.save_activity(cid, "문제", "2+2?", "4", ["풀이 근거 설명"], 2,
                             "2026-10-14", "2026-10-14")
    return store, room, UploadedFiles(store), aid, clock


def save_answer(files, aid):
    return files.save(aid, "1001", "학생", "1반", "답안.png", answer_image())


def test_student_cannot_store_files_before_distribution_or_bypass_with_status(upload_assessment):
    store, room, files, aid, _ = upload_assessment
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는"):
        save_answer(files, aid)
    room.set_status(aid, "진행 중")
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는"):
        save_answer(files, aid)
    assert not store.read().get("course_uploads") and not store.blobs
    room.distribute_activity(aid)
    record = save_answer(files, aid)
    assert record["saved"]
    assert files.get(record["id"], aid, "1001", "1반") == record


@pytest.mark.parametrize("instant", ["2026-10-13T23:59:59+09:00", "2026-10-15T00:00:00+09:00"])
def test_student_image_upload_is_rejected_outside_assessment_dates(upload_assessment, instant):
    store, room, files, aid, clock = upload_assessment
    room.distribute_activity(aid)
    clock[0] = instant
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는"):
        save_answer(files, aid)
    assert not store.read().get("course_uploads") and not store.blobs


@pytest.mark.parametrize("instant", ["2026-10-13T15:00:00+00:00", "2026-10-14T14:59:59+00:00"])
def test_student_upload_includes_both_korean_date_boundaries(upload_assessment, instant):
    _, room, files, aid, clock = upload_assessment
    room.distribute_activity(aid)
    clock[0] = instant
    assert save_answer(files, aid)["saved"]


def test_timer_expiry_keeps_image_draft_but_does_not_allow_submission(upload_assessment):
    _, room, files, aid, clock = upload_assessment
    task = room.activity(aid)
    room.save_activity(task["course_id"], task["title"], task["prompt"], task["expected"],
                       task["criteria"], 2, task["start"], task["end"], aid=aid, duration_minutes=1)
    room.distribute_activity(aid)
    clock[0] = "2026-10-14T10:01:01+09:00"
    assert room.timer_state(room.activity(aid))["phase"] == "expired"
    record = save_answer(files, aid)
    assert record["saved"]
    with pytest.raises(AppError, match="현재 제출할 수 없는"):
        room.submit(aid, "1001", "학생", "1반", "풀이", [], False, "a" * 32,
                    upload_ids=[record["id"]])


@pytest.mark.parametrize("change", ["hidden", "distribution_revoked", "date_boundary", "class_removed"])
def test_upload_rechecks_access_at_metadata_transaction(upload_assessment, monkeypatch, change):
    store, room, files, aid, clock = upload_assessment
    room.distribute_activity(aid)
    put_blob = store.put_blob
    changed = False

    def change_access_during_blob_write(name, raw):
        nonlocal changed
        put_blob(name, raw)
        if changed:
            return
        changed = True
        if change == "date_boundary":
            clock[0] = "2026-10-15T00:00:00+09:00"
        elif change == "class_removed":
            cid = room.activity(aid)["course_id"]
            store.transaction(lambda state: state["courses"][cid].update(classes=["2반"]))
        else:
            values = {"status": "숨김"} if change == "hidden" else {"distributed_at": None}
            store.transaction(lambda state: state["course_activities"][aid].update(values))

    monkeypatch.setattr(store, "put_blob", change_access_during_blob_write)
    with pytest.raises(AppError, match="현재 파일을 저장할 수 없는|참여 대상 학급"):
        save_answer(files, aid)
    assert changed
    assert not store.read().get("course_uploads") and not store.uploads


def test_legacy_published_activity_keeps_upload_access_without_distribution_timestamp(upload_assessment):
    store, _, files, aid, _ = upload_assessment

    def legacy(state):
        task = state["course_activities"][aid]
        task.pop("distribution_required", None)
        task.pop("distributed_at", None)
        task["status"] = "진행 중"

    store.transaction(legacy)
    assert save_answer(files, aid)["saved"]
