"""Class announcements enforce teacher access and persist through CSV restarts."""
import csv
import io
import json
import threading
import time
from types import FunctionType, SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import storage as db
from config import CLASSES
from views import announcements, teacher


TEACHER = {"id": "teacher", "name": "공지 선생님", "class": "", "role": "teacher"}
STUDENT = {"id": "10101", "name": "시험학생", "class": "1-1", "role": "student"}


@pytest.fixture
def announcement_store(monkeypatch, tmp_path):
    backend = db.LocalBackend(str(tmp_path))
    clock = {"now": "2026-10-14 09:00:00"}
    cache = {"data": {}, "lock": threading.Lock()}
    monkeypatch.setattr(db, "get_backend", lambda: backend)
    monkeypatch.setattr(db, "_cache", lambda: cache)
    monkeypatch.setattr(db, "now_str", lambda: clock["now"])
    db.append("users", TEACHER)
    db.append("users", STUDENT)
    return backend, clock, tmp_path


def announcement_app(user=TEACHER):
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from views import announcements\n"
        "announcements.tab_announcements(st.session_state['user'])\n"
    )
    app.session_state["user"] = dict(user)
    return app.run()


def test_creation_uses_real_teacher_identity_and_survives_backend_restart(announcement_store):
    _, _, path = announcement_store
    forged_profile = dict(TEACHER, name="세션에서 바꾼 이름")
    aid = announcements.save_announcement(forged_profile, "  준비물 안내  ", "교과서와 필기도구\n챙겨 오세요.", ["1-7", "1-1"])
    rows = db.LocalBackend(str(path)).read("announcements")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == aid and row["title"] == "준비물 안내"
    assert row["content"] == "교과서와 필기도구\n챙겨 오세요."
    assert json.loads(row["classes"]) == ["1-1", "1-7"]
    assert row["active"] == "1" and row["author_id"] == TEACHER["id"]
    assert row["author_name"] == TEACHER["name"]
    assert row["created_at"] == row["updated_at"] == "2026-10-14 09:00:00"


def test_editing_keeps_creation_and_author_but_updates_targets_publication_and_order(announcement_store):
    _, clock, _ = announcement_store
    first = announcements.save_announcement(TEACHER, "첫 공지", "내용", ["1-1"])
    clock["now"] = "2026-10-14 09:10:00"
    second = announcements.save_announcement(TEACHER, "다음 공지", "내용", ["1-1"])
    assert [row["id"] for row in announcements.list_announcements()] == [second, first]
    colleague = dict(TEACHER, id="teacher2", name="다른 선생님")
    db.append("users", colleague)
    clock["now"] = "2026-10-14 09:20:00"
    announcements.save_announcement(colleague, "첫 공지 수정", "수정한 내용", ["1-2"], False, first)
    rows = announcements.list_announcements()
    assert [row["id"] for row in rows] == [first, second]
    assert rows[0]["created_at"] == "2026-10-14 09:00:00"
    assert rows[0]["updated_at"] == "2026-10-14 09:20:00"
    assert rows[0]["author_id"] == TEACHER["id"]
    assert rows[0]["author_name"] == TEACHER["name"]
    assert json.loads(rows[0]["classes"]) == ["1-2"] and rows[0]["active"] == "0"


@pytest.mark.parametrize("changes", [
    {"title": ""}, {"title": " "}, {"title": "a" * 121}, {"title": None},
    {"content": ""}, {"content": "\n"}, {"content": "a" * 10_001}, {"content": None},
    {"classes": []}, {"classes": "1-1"}, {"classes": ["2-1"]}, {"classes": [None]},
    {"classes": ["1-1", "1-1"]}, {"active": "1"}, {"active": None},
])
def test_invalid_announcements_do_not_write_or_replace_existing_records(announcement_store, changes):
    aid = announcements.save_announcement(TEACHER, "기존 공지", "기존 내용", ["1-1"])
    previous = db.read("announcements")
    values = dict(title="새 제목", content="새 내용", classes=["1-1"], active=True)
    values.update(changes)
    for editing in (None, aid):
        with pytest.raises(ValueError):
            announcements.save_announcement(TEACHER, announcement_id=editing, **values)
        assert db.read("announcements") == previous


@pytest.mark.parametrize("user", [STUDENT, {}, None, dict(STUDENT, role="teacher"),
                                 dict(TEACHER, id="missing"), dict(TEACHER, role="student")])
def test_only_registered_teachers_can_create_edit_or_delete(announcement_store, user):
    aid = announcements.save_announcement(TEACHER, "기존 공지", "내용", ["1-1"])
    previous = db.read("announcements")
    with pytest.raises(PermissionError):
        announcements.save_announcement(user, "공지", "내용", ["1-1"])
    with pytest.raises(PermissionError):
        announcements.save_announcement(user, "공지", "내용", ["1-1"], announcement_id=aid)
    with pytest.raises(PermissionError):
        announcements.delete_announcement(user, aid)
    assert db.read("announcements") == previous


def test_teacher_role_is_rechecked_after_the_account_changes(announcement_store):
    aid = announcements.save_announcement(TEACHER, "기존 공지", "내용", ["1-1"])
    db.update("users", TEACHER["id"], {"role": "student"})
    with pytest.raises(PermissionError):
        announcements.save_announcement(TEACHER, "수정", "내용", ["1-1"], announcement_id=aid)
    assert db.read("announcements")[0]["title"] == "기존 공지"


def test_deleted_and_missing_announcements_are_not_silently_recreated(announcement_store):
    first = announcements.save_announcement(TEACHER, "지울 공지", "내용", ["1-1"])
    second = announcements.save_announcement(TEACHER, "남길 공지", "내용", ["1-2"])
    announcements.delete_announcement(TEACHER, first)
    assert [row["id"] for row in db.read("announcements")] == [second]
    with pytest.raises(ValueError, match="찾을 수"):
        announcements.save_announcement(TEACHER, "수정", "내용", ["1-1"], announcement_id=first)
    with pytest.raises(ValueError, match="찾을 수"):
        announcements.delete_announcement(TEACHER, first)
    assert [row["id"] for row in db.read("announcements")] == [second]


@pytest.mark.parametrize("targets", ["broken", "{}", "null", '["2-1"]', '["1-1","1-1"]', '[["1-1"]]'])
def test_class_picker_does_not_accept_malformed_stored_targets(targets):
    assert announcements.announcement_classes({"classes": targets}) == []


def test_older_submission_csv_rows_receive_an_empty_teacher_comment_timestamp(announcement_store):
    _, _, path = announcement_store
    (path / "submissions.csv").write_text("id,teacher_comment\nold,좋은 풀이예요\n", encoding="utf-8")
    row = db.LocalBackend(str(path)).read("submissions")[0]
    assert row["teacher_comment"] == "좋은 풀이예요" and row["teacher_comment_at"] == ""


def test_teacher_form_creates_edits_unpublishes_and_deletes_an_announcement(announcement_store):
    _, clock, _ = announcement_store
    app = announcement_app()
    assert not app.exception and not app.error
    assert app.checkbox(key="announcement_new_active").value is True
    assert app.multiselect(key="announcement_new_classes").value == CLASSES
    app.text_input(key="announcement_new_title").set_value("준비물")
    app.text_area(key="announcement_new_content").set_value("필기도구를 챙기세요.")
    app.multiselect(key="announcement_new_classes").set_value(["1-1", "1-2"])
    app.button(key="announcement_create_save").click().run()
    assert not app.exception and not app.error
    row = db.read("announcements")[0]
    assert row["title"] == "준비물" and row["active"] == "1"
    assert app.text_input(key="announcement_new_title").value == ""
    prefix = "announcement_edit_" + row["id"]
    clock["now"] = "2026-10-14 10:00:00"
    app.text_input(key=prefix + "_title").set_value("준비물 수정")
    app.text_area(key=prefix + "_content").set_value("계산기도 챙기세요.")
    app.multiselect(key=prefix + "_classes").set_value(["1-2"])
    app.checkbox(key=prefix + "_active").uncheck()
    app.button(key=prefix + "_save").click().run()
    assert not app.exception and not app.error
    updated = db.read("announcements")[0]
    assert updated["title"] == "준비물 수정" and updated["active"] == "0"
    assert json.loads(updated["classes"]) == ["1-2"]
    app.button(key=prefix + "_delete").click().run()
    assert not app.exception and not app.error
    assert db.read("announcements") == []


def test_teacher_form_keeps_draft_input_when_no_target_class_is_selected(announcement_store):
    app = announcement_app()
    app.text_input(key="announcement_new_title").set_value("작성 중인 공지")
    app.text_area(key="announcement_new_content").set_value("작성 중인 내용")
    app.multiselect(key="announcement_new_classes").set_value([])
    app.button(key="announcement_create_save").click().run()
    assert not app.exception and app.error
    assert app.text_input(key="announcement_new_title").value == "작성 중인 공지"
    assert app.text_area(key="announcement_new_content").value == "작성 중인 내용"
    assert db.read("announcements") == []


def test_students_cannot_open_the_announcement_editor(announcement_store):
    app = announcement_app(STUDENT)
    assert not app.exception and app.error
    assert not app.text_input and not app.text_area and not app.button


def test_teacher_page_includes_the_announcement_tab_without_changing_other_tools(announcement_store, monkeypatch):
    for name in ("tab_lock", "tab_observe", "tab_points", "tab_record", "tab_roster", "tab_settings"):
        monkeypatch.setattr(teacher, name, lambda: st.caption("기존 교사 기능"))
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from views import teacher\n"
        "teacher.page(st.session_state['user'])\n"
    )
    app.session_state["user"] = dict(TEACHER)
    app.run()
    assert not app.exception and not app.error
    assert [tab.label for tab in app.tabs] == ["🔒 화면 잠금", "📢 공지사항", "📒 관찰기록", "⭐ 상점·벌점",
                                             "📝 생기부 생성기", "👥 학생 명단", "⚙️ 설정"]
    assert app.checkbox(key="announcement_new_active").value is True


def previous_backend_class(current):
    """Keep the old module's schema globals, as a cached pre-update class does."""
    namespace = dict(db.__dict__)
    namespace["SCHEMAS"] = {name: list(columns) for name, columns in db.SCHEMAS.items()
                            if name != "announcements"}
    namespace["SCHEMAS"]["submissions"].remove("teacher_comment_at")
    namespace["_norm"] = FunctionType(db._norm.__code__, namespace)
    methods = {"__module__": db.__name__, "__qualname__": current.__qualname__}
    for name, member in current.__dict__.items():
        if isinstance(member, FunctionType):
            methods[name] = FunctionType(member.__code__, namespace, name, member.__defaults__, member.__closure__)
            methods[name].__kwdefaults__ = member.__kwdefaults__
        elif isinstance(member, staticmethod):
            methods[name] = member
    if current is db.GitHubBackend:
        exec("def old_csv(self, path):\n"
             "    table = path[5:-4].split('/')[0]\n"
             "    rows = [row for row in self.rows[table] if self._path(table, row) == path]\n"
             "    output = io.StringIO()\n"
             "    writer = csv.DictWriter(output, fieldnames=SCHEMAS[table])\n"
             "    writer.writeheader()\n"
             "    writer.writerows(rows)\n"
             "    return output.getvalue()\n", namespace)
        methods["_csv"] = namespace["old_csv"]
    return type(current.__name__, (), methods)


def stored_notice(announcement_id="persisted"):
    return {"id": announcement_id, "title": "기존 원격 공지", "content": "기존 본문", "classes": '["1-1"]',
            "author_id": TEACHER["id"], "author_name": TEACHER["name"], "active": "1",
            "created_at": "2026-10-14 09:00:00", "updated_at": "2026-10-14 09:00:00"}


@pytest.mark.parametrize("operation", ["read", "append", "append_many", "update", "delete"])
def test_every_table_facade_upgrades_old_local_backend_and_persists_new_schema(announcement_store, monkeypatch, operation):
    _, _, path = announcement_store
    db.LocalBackend(str(path)).append("announcements", stored_notice())
    previous = previous_backend_class(db.LocalBackend)(str(path))
    previous.append("submissions", {"id": "old-answer", "teacher_comment": "기존 피드백"})
    lock = previous.lock
    monkeypatch.setattr(db, "get_backend", lambda: previous)
    with pytest.raises(KeyError):
        previous.read("announcements")
    if operation == "read":
        assert db.read("announcements")[0]["id"] == "persisted"
    elif operation == "append":
        db.append("announcements", stored_notice("new"))
    elif operation == "append_many":
        db.append_many("announcements", [stored_notice("new"), stored_notice("new2")])
    elif operation == "update":
        assert db.update("announcements", "persisted", {"title": "수정한 공지"})
    else:
        db.delete("announcements", "persisted")
    assert type(previous) is db.LocalBackend and previous.lock is lock
    persisted = db.LocalBackend(str(path)).read("announcements")
    expected_ids = {"read": ["persisted"], "append": ["persisted", "new"],
                    "append_many": ["persisted", "new", "new2"], "update": ["persisted"], "delete": []}
    assert [row["id"] for row in persisted] == expected_ids[operation]
    if operation == "update":
        assert persisted[0]["title"] == "수정한 공지"
    assert db.update("submissions", "old-answer", {"teacher_comment": "새 피드백", "teacher_comment_at": "2026-10-14 11:00:00"})
    answer = db.LocalBackend(str(path)).read("submissions")[0]
    assert answer["teacher_comment"] == "새 피드백" and answer["teacher_comment_at"] == "2026-10-14 11:00:00"


def old_github_backend(monkeypatch):
    previous = object.__new__(previous_backend_class(db.GitHubBackend))
    previous.repo, previous.branch = "owner/private-data", "main"
    previous.lock, previous.flush_lock = threading.RLock(), threading.Lock()
    previous.rows = {name: [] for name in db.SCHEMAS if name != "announcements"}
    previous.rows["users"] = [dict(TEACHER)]
    previous.rows["submissions"] = [{"id": "pending-answer", "teacher_comment": "未保存 피드백",
                                     "teacher_comment_at": "2026-10-14 10:00:00"}]
    previous.dirty = {"data/submissions.csv": 7}
    previous.pending_files = [("files/2026-10/answer.pdf", "pending-file-sha")]
    previous.ver, previous.last_saved, previous.last_error = 7, "previous-save", "retry pending"
    previous.s, previous.worker = object(), object()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=db.SCHEMAS["announcements"])
    writer.writeheader()
    writer.writerow(stored_notice("remote"))
    raw = output.getvalue().encode()
    calls = []

    def request(method, path, **kwargs):
        assert method == "GET" and path.endswith("/git/trees/existing-head")
        calls.append((method, path))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"tree": [
            {"path": "data/announcements.csv", "type": "blob", "sha": "announcement-sha"},
            {"path": "data/submissions.csv", "type": "blob", "sha": "untouched-submission-sha"},
        ]})

    def blob(sha):
        assert sha == "announcement-sha"
        calls.append(("blob", sha))
        return raw

    previous._head = lambda: "existing-head"
    previous._req, previous._blob = request, blob
    monkeypatch.setattr(db, "get_backend", lambda: previous)
    return previous, calls


def test_old_github_backend_loads_new_remote_announcements_once_without_losing_pending_work(announcement_store, monkeypatch):
    previous, calls = old_github_backend(monkeypatch)
    original = {name: getattr(previous, name) for name in ("rows", "dirty", "pending_files", "lock", "flush_lock", "s", "worker")}
    db._cache()["data"]["announcements"] = (time.time(), [])
    with pytest.raises(ValueError, match="fieldnames"):
        previous._csv("data/submissions.csv")
    rows = db.read("announcements")
    assert [row["id"] for row in rows] == ["remote"]
    assert type(previous) is db.GitHubBackend
    for name, value in original.items():
        assert getattr(previous, name) is value
    assert previous.ver == 7 and previous.last_error == "retry pending" and previous.last_saved == "previous-save"
    assert previous.dirty == {"data/submissions.csv": 7}
    assert previous.rows["submissions"][0]["teacher_comment"] == "未保存 피드백"
    assert db.read("announcements") == rows
    assert [kind for kind, _ in calls] == ["GET", "blob"]
    text = previous._csv("data/submissions.csv")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed[0]["teacher_comment_at"] == "2026-10-14 10:00:00"
    assert next(csv.reader(io.StringIO(text))) == db.SCHEMAS["submissions"]
    announcements.save_announcement(TEACHER, "추가 공지", "새 본문", ["1-1"])
    assert len(previous.rows["announcements"]) == 2 and previous.rows["announcements"][0]["id"] == "remote"
    assert previous.dirty["data/submissions.csv"] == 7 and previous.pending_files is original["pending_files"]
    assert [kind for kind, _ in calls] == ["GET", "blob"]


def test_new_remote_table_load_failure_does_not_publish_empty_data_or_block_a_retry(announcement_store, monkeypatch):
    previous, calls = old_github_backend(monkeypatch)
    successful_blob = previous._blob
    previous._blob = lambda sha: (_ for _ in ()).throw(RuntimeError("temporary read failure"))
    with pytest.raises(RuntimeError, match="temporary"):
        db.read("announcements")
    assert "announcements" not in previous.rows
    assert previous.dirty == {"data/submissions.csv": 7}
    previous._blob = successful_blob
    assert db.read("announcements")[0]["id"] == "remote"
    assert [kind for kind, _ in calls] == ["GET", "GET", "blob"]


def test_read_cache_from_previous_schema_is_normalized_and_still_upgrades_the_backend(announcement_store, monkeypatch):
    _, _, path = announcement_store
    previous = previous_backend_class(db.LocalBackend)(str(path))
    monkeypatch.setattr(db, "get_backend", lambda: previous)
    db._cache()["data"]["submissions"] = (time.time(), [{"id": "cached", "teacher_comment": "기존 피드백"}])
    row = db.read("submissions")[0]
    assert row["teacher_comment_at"] == "" and row["teacher_comment"] == "기존 피드백"
    assert set(row) == set(db.SCHEMAS["submissions"])
    assert type(previous) is db.LocalBackend
