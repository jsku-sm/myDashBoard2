"""Performance-assessment persistence across question and curriculum revisions."""
import copy
import io
import zipfile

from PIL import Image
import pytest

from think_app.classroom import Classroom
from think_app.courses import CourseManager, now
from think_app.curriculum import criteria_text, selection_metadata, standards_for, subject_names, unit_names
from think_app.question_files import QuestionFiles
from think_app.storage import AppError, MemoryStore


def image_bytes(color="blue"):
    output = io.BytesIO()
    Image.new("RGB", (50, 40), color).save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def assessment():
    store = MemoryStore()
    manager = CourseManager(store)
    cid = manager.create("첨부 문제 수행평가", "#123456", ["1반"])
    return store, manager, Classroom(store), QuestionFiles(store), cid


def save_task(room, course_id, **changes):
    values = dict(title="문제 평가", prompt="2+2의 값을 구하세요.", expected="4",
                  criteria=["풀이를 근거와 함께 설명한다."], max_attempts=2,
                  start=now()[:10], end=None)
    values.update(changes)
    return room.save_activity(course_id, **values)


def curriculum_selection():
    subject = subject_names()[0]
    unit = unit_names(subject)[0]
    codes = [record["code"] for record in standards_for(subject, unit)[:2]]
    return selection_metadata(subject, unit, codes), criteria_text(subject, unit, codes)


def test_file_only_question_is_saved_but_a_question_without_text_or_files_is_rejected(assessment):
    store, _, room, files, cid = assessment
    question = files.save(cid, image_bytes(), "문제.png")
    aid = save_task(room, cid, prompt=" \n ", question_files=[question["id"]])
    assert room.activity(aid)["prompt"] == ""
    assert room.activity(aid)["question_files"] == [question]
    for selected in (None, []):
        with pytest.raises(AppError, match="문제를 입력하거나 문제 파일"):
            save_task(room, cid, prompt="", question_files=selected)
    assert list(store.read()["course_activities"]) == [aid]


def test_activity_save_rejects_cross_course_and_tampered_question_metadata(assessment):
    store, manager, room, files, cid = assessment
    question = files.save(cid, image_bytes(), "문제.png")
    other = manager.create("다른 평가", "#123456", ["1반"])
    with pytest.raises(AppError, match="다른 수업"):
        save_task(room, other, prompt="", question_files=[question])
    with pytest.raises(AppError, match="저장 내용과 다릅니다"):
        save_task(room, cid, question_files=[dict(question, original_ref="f" * 32)])
    assert not store.read().get("course_activities")


@pytest.mark.parametrize("blob_field", ["original_ref", "blob_ref"])
def test_activity_save_refuses_corrupt_original_or_preview_before_publishing(assessment, blob_field):
    store, _, room, files, cid = assessment
    question = files.save(cid, image_bytes(), "문제.png")
    store.put_blob(question[blob_field], b"corrupt")
    with pytest.raises(AppError, match="저장된 문제 파일"):
        save_task(room, cid, question_files=[question])
    assert not store.read().get("course_activities")


def test_activity_saves_canonical_curriculum_metadata_and_selected_criterion_text(assessment):
    _, _, room, _, cid = assessment
    metadata, official = curriculum_selection()
    incoming = dict(metadata, source_url="https://untrusted.example/curriculum")
    aid = save_task(room, cid, curriculum=incoming, criteria=official + ["풀이를 설명한다."])
    task = room.activity(aid)
    assert task["curriculum"] == metadata
    assert task["criteria"] == official + ["풀이를 설명한다."]
    # Both omitted optional arguments retain existing saved metadata on edit.
    save_task(room, cid, aid=aid, criteria=task["criteria"])
    assert room.activity(aid)["curriculum"] == metadata


def test_activity_rejects_curriculum_criterion_mismatch_without_partial_save(assessment):
    store, _, room, _, cid = assessment
    metadata, official = curriculum_selection()
    with pytest.raises(AppError, match="평가 기준에 포함"):
        save_task(room, cid, curriculum=metadata, criteria=official[:-1])
    invalid = dict(metadata, standard_codes=["unrecognized-standard"])
    with pytest.raises(AppError, match="과목과 단원에 속한"):
        save_task(room, cid, curriculum=invalid, criteria=official)
    assert not store.read().get("course_activities")


def test_submission_snapshot_is_immutable_and_export_keeps_historical_and_current_questions(assessment):
    store, _, room, files, cid = assessment
    original = image_bytes()
    first = files.save(cid, original, "첫문제.png")
    metadata, official = curriculum_selection()
    aid = save_task(room, cid, prompt="", question_files=[first], curriculum=metadata, criteria=official)
    room.distribute_activity(aid)
    request = room.submit(aid, "1001", "학생", "1반", "답은 4입니다.", [], False, "a" * 32)
    snapshot = copy.deepcopy(store.read()["course_attempts"][request]["activity_snapshot"])
    second = files.save(cid, b"2+2?", "next.txt")
    save_task(room, cid, aid=aid, prompt="", title="변경한 문제", question_files=[second], criteria=official)
    assert store.read()["course_attempts"][request]["activity_snapshot"] == snapshot
    assert snapshot["question_files"] == [first]
    assert snapshot["curriculum"] == metadata
    assert room.activity(aid)["question_files"] == [second]
    bundle = store.get_student_submission(store.read()["course_attempts"][request])
    assert bundle["submission"]["activity_snapshot"] == snapshot
    with zipfile.ZipFile(io.BytesIO(room.export(cid, aid))) as archive:
        assert archive.read(f"문제/{first['id']}/첫문제.png") == original
        assert archive.read(f"문제/{second['id']}/next.txt") == b"2+2?"
        assert len([name for name in archive.namelist() if name.startswith("문제/")]) == 2


def test_question_revision_during_submission_is_rejected(assessment, monkeypatch):
    store, _, room, files, cid = assessment
    first = files.save(cid, image_bytes(), "첫문제.png")
    second = files.save(cid, image_bytes("green"), "새문제.png")
    aid = save_task(room, cid, prompt="", question_files=[first])
    room.distribute_activity(aid)
    put_blob = store.put_blob
    changed = False

    def edit_question_while_saving_answer(name, raw):
        nonlocal changed
        put_blob(name, raw)
        if not changed:
            changed = True
            # Simulate another teacher session editing the task between the
            # submission's initial read and its final transaction.
            store.transaction(lambda state: state["course_activities"][aid].update(question_files=[second]))

    monkeypatch.setattr(store, "put_blob", edit_question_while_saving_answer)
    with pytest.raises(AppError, match="활동 내용이 변경"):
        room.submit(aid, "1001", "학생", "1반", "풀이 설명", [files.read(first, cid)], False, "b" * 32)
    assert changed
    assert not store.read().get("course_attempts")
    assert room.activity(aid)["question_files"] == [second]


def test_new_desmos_default_has_two_attempts_and_existing_limit_is_preserved(assessment):
    _, manager, room, _, _ = assessment
    cid = manager.create("Desmos 그래프 수업", "#123456", ["1반"])
    course = manager.get(cid)
    aid = room.ensure_desmos_activity(course)
    assert room.activity(aid)["max_attempts"] == 2
    save_task(room, cid, aid=aid, title="기존 Desmos 활동", mode="graph", max_attempts=5)
    assert room.ensure_desmos_activity(course) == aid
    assert room.activity(aid)["max_attempts"] == 5
    legacy = manager.create("데스모스 기존 수업", "#123456", ["1반"])
    legacy_aid = save_task(room, legacy, title="기존 데스모스 활동", max_attempts=7)
    assert room.ensure_desmos_activity(manager.get(legacy)) == legacy_aid
    assert room.activity(legacy_aid)["max_attempts"] == 7
