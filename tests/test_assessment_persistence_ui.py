"""Saved assessments remain visible in new teacher and student sessions."""
import pytest
from streamlit.testing.v1 import AppTest

from snorkl_navigation import REQUESTED_COURSE
from think_app import embedded
from think_app.classroom import Classroom
from think_app.config import Settings
from think_app.courses import CourseManager
from think_app.integration import resolve_settings
from think_app.storage import GitHubStore, LocalStore, MemoryStore
from think_app.persistence import open_local_store


@pytest.mark.parametrize("mode", ["local", "demo", "cloud"])
def test_create_distribute_submit_and_restore_after_caches_and_sessions_are_lost(tmp_path, monkeypatch, mode):
    repository = None
    if mode == "cloud":
        from test_assessment_cloud_persistence import FakePrivateRepository, KEY_PATH
        repository = FakePrivateRepository()
        settings = resolve_settings({"github": {"repo": "owner/private-data", "token": "fake-test-token"},
                                     "snorkl": {"data_dir": str(tmp_path)}}, {})
        assert settings.mode == "github" and not settings.encryption_key
        monkeypatch.setattr(embedded, "GitHubStore",
                            lambda repo, branch, token, key: GitHubStore(repo, branch, token, key, session=repository))
    else:
        settings = Settings(mode=mode, data_dir=str(tmp_path))
    monkeypatch.setattr(embedded, "load_embedded_settings", lambda: settings)
    embedded.persistent_store.clear()
    embedded.memory_store.clear()
    try:
        teacher_source = "from think_app import embedded\nembedded.render({'role':'teacher','id':'teacher'})\n"
        teacher = AppTest.from_string(teacher_source).run()
        assert not teacher.exception and not teacher.error
        teacher.button(key="create_assessment").click().run()
        next(item for item in teacher.text_input if item.label == "수행평가 이름").set_value("재시작 후에도 남는 평가")
        next(button for button in teacher.button if button.label == "수행평가 만들기").click().run()
        assert not teacher.exception and not teacher.error
        store = embedded.get_store(settings)
        manager = CourseManager(store)
        course = manager.list_courses()[0]
        cid = course["id"]
        teacher.button(key="open_course_" + cid).click().run()
        next(button for button in teacher.button if button.label == "＋ 활동 추가하기").click().run()
        prefix = "activity_form_" + cid
        teacher.text_input(key=prefix + "_title").set_value("보관된 세부 활동")
        teacher.text_area(key=prefix + "_prompt").set_value("2+2의 값을 설명하세요.")
        teacher.text_area(key=prefix + "_expected").set_value("4입니다.")
        teacher.text_area(key=prefix + "_criteria").set_value("덧셈의 근거를 설명한다.")
        teacher.number_input(key=prefix + "_duration").set_value(10)
        teacher.button(key=prefix + "_save").click().run()
        assert not teacher.exception and not teacher.error
        room = Classroom(store)
        aid = room.activities(cid)[0]["id"]
        teacher.button(key="distribute_activity_" + aid).click().run()
        student_source = ("from think_app import embedded\n"
                          "embedded.render({'role':'student','id':'10101','name':'학생','class':'1-1'})\n")
        student = AppTest.from_string(student_source)
        student.session_state[REQUESTED_COURSE] = cid
        student.run()
        student.text_area(key=f"student_{aid}_1-1_10101_0_text").set_value("2와 2를 더하면 4입니다.")
        next(button for button in student.button if button.label == "답안 제출").click().run()
        assert not student.exception and not student.error
        attempt = room.attempts(aid)[0]
        room.comment(attempt["id"], "설명을 잘 썼어요.")
        teacher.button(key="timer_end_" + aid).click().run()
        saved = store.read()
        original_key = repository.files[KEY_PATH] if repository else (tmp_path / ".encryption.key").read_bytes()

        embedded.persistent_store.clear()
        embedded.memory_store.clear()
        restarted_teacher = AppTest.from_string(teacher_source).run()
        assert not restarted_teacher.exception and not restarted_teacher.error
        assert restarted_teacher.button(key="open_course_" + cid).label == "재시작 후에도 남는 평가"
        restarted_teacher.button(key="open_course_" + cid).click().run()
        assert not restarted_teacher.exception and not restarted_teacher.error
        assert restarted_teacher.button(key="activity_" + aid).label == "보관된 세부 활동"
        assert restarted_teacher.button(key="timer_resume_" + aid).label == "평가 재개"
        restored = embedded.get_store(settings)
        assert restored.read() == saved
        restored_key = repository.files[KEY_PATH] if repository else (tmp_path / ".encryption.key").read_bytes()
        assert restored_key == original_key
        if repository:
            assert not list(tmp_path.iterdir()), "Cloud records must be restored without any local data files."
        resumed_student = AppTest.from_string(student_source)
        resumed_student.session_state[REQUESTED_COURSE] = cid
        resumed_student.run()
        assert not resumed_student.exception and not resumed_student.error
        assert "선생님이 평가를 종료했습니다." in [item.value for item in resumed_student.info]
        assert restored.get_student_submission(Classroom(restored).attempts(aid)[0])["submission"]["text"] == "2와 2를 더하면 4입니다."
    finally:
        embedded.persistent_store.clear()
        embedded.memory_store.clear()


def test_hot_reload_keeps_the_cached_local_store_and_its_existing_writer_lock(tmp_path, monkeypatch):
    settings = Settings(mode="local", data_dir=str(tmp_path))
    store = open_local_store(settings)
    manager = CourseManager(store)
    cid = manager.create("업데이트 전 평가", "#123456", ["1-1"])
    original_lock = store.lock
    old_class = type("LocalStore", (), {key: value for key, value in LocalStore.__dict__.items()
                                        if key not in ("__dict__", "__weakref__")})
    store.__class__ = old_class
    assert not isinstance(store, LocalStore)
    monkeypatch.setattr(embedded, "persistent_store", lambda *args: store)
    monkeypatch.setattr(embedded, "memory_store", lambda: MemoryStore())
    restored = embedded.get_store(settings)
    assert restored is store and isinstance(restored, LocalStore)
    assert restored.lock is original_lock
    assert CourseManager(restored).get(cid)["title"] == "업데이트 전 평가"
    after = manager.create("기존 화면에서 추가한 평가", "#123456", ["1-1"])
    assert CourseManager(open_local_store(settings)).get(after)["title"] == "기존 화면에서 추가한 평가"
