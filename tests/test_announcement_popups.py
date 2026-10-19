"""Announcement dialogs persist each student's acknowledgement of visible revisions."""
import copy
from pathlib import Path
import threading

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import storage as db
from views import announcements
from views import student_announcements as popups


TEACHER = dict(id="teacher", name="공지 선생님", role="teacher", **{"class": ""})
STUDENT = dict(id="10101", name="첫 학생", role="student", **{"class": "1-1"})
CLASSMATE = dict(id="10102", name="다음 학생", role="student", **{"class": "1-1"})
OTHER_CLASS = dict(id="10201", name="다른 반 학생", role="student", **{"class": "1-2"})


@pytest.fixture
def popup_store(tmp_path, monkeypatch):
    connection = {"backend": db.LocalBackend(str(tmp_path))}
    cache = {"data": {}, "lock": threading.Lock()}
    clock = {"now": "2026-10-19 09:00:00"}
    monkeypatch.setattr(db, "get_backend", lambda: connection["backend"])
    monkeypatch.setattr(db, "_cache", lambda: cache)
    monkeypatch.setattr(db, "now_str", lambda: clock["now"])
    for user in (TEACHER, STUDENT, CLASSMATE, OTHER_CLASS):
        db.append("users", dict(user, must_change="0"))
    return connection, cache, clock, tmp_path


def notice(title="준비물 안내", content="교과서와 필기도구를 챙기세요.", classes=None, active=True, aid=None):
    return announcements.save_announcement(TEACHER, title, content, ["1-1"] if classes is None else classes,
                                          active, announcement_id=aid)


def displayed(app):
    return "\n".join(str(item.value) for elements in (app.title, app.subheader, app.markdown, app.caption,
                                                    app.info, app.warning) for item in elements)


def popup_app(user=STUDENT, menu="home"):
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from views import student_announcements as popups\n"
        "st.radio('메뉴', ['home', 'tools'], key='nav')\n"
        "st.write('현재 메뉴: ' + st.session_state['nav'])\n"
        "popups.show_announcement_popup(st.session_state['user'])\n"
    )
    app.session_state["user"] = dict(user)
    app.session_state["nav"] = menu
    return app.run()


def test_pending_includes_only_published_own_class_notices_and_full_bodies(popup_store):
    first = notice(content="첫째 줄\n둘째 줄\n" + "상세 안내입니다. " * 100)
    second = notice("평가 안내", "내일 수행평가를 진행합니다.")
    notice("PRIVATE_OTHER_CLASS", classes=["1-2"])
    notice("PRIVATE_DRAFT", active=False)
    pending = popups.pending_announcements(STUDENT)
    assert {item["id"] for item in pending} == {first, second}
    assert all(set(item) == {"id", "title", "content", "created_at", "updated_at", "author_name"}
               for item in pending)
    assert next(item["content"] for item in pending if item["id"] == first).endswith("상세 안내입니다.")
    assert all(item["author_name"] == TEACHER["name"] for item in pending)
    assert "PRIVATE" not in str(pending)


def test_pending_uses_current_registered_class_over_stale_session_profile(popup_store):
    own = notice()
    other = notice("다른 반 안내", classes=["1-2"])
    stale_profile = dict(STUDENT, **{"class": "1-2"})
    assert [item["id"] for item in popups.pending_announcements(stale_profile)] == [own]
    db.update("users", STUDENT["id"], {"class": "1-2"})
    assert [item["id"] for item in popups.pending_announcements(STUDENT)] == [other]


@pytest.mark.parametrize("user", [None, {}, TEACHER, dict(STUDENT, role="teacher"),
                                 dict(TEACHER, role="student"), dict(STUDENT, id="missing"),
                                 dict(STUDENT, id="")])
def test_unregistered_and_nonstudent_accounts_cannot_read_or_acknowledge(popup_store, user):
    notice()
    pending = popups.pending_announcements(STUDENT)
    assert popups.pending_announcements(user) == []
    popups.acknowledge_announcements(user, pending)
    assert db.read("announcement_reads") == []


@pytest.mark.parametrize("changes", [{"role": "teacher"}, {"must_change": "1"}, {"class": ""}])
def test_current_account_is_rechecked_before_reading_and_acknowledging(popup_store, changes):
    notice()
    pending = popups.pending_announcements(STUDENT)
    db.update("users", STUDENT["id"], changes)
    assert popups.pending_announcements(STUDENT) == []
    popups.acknowledge_announcements(STUDENT, pending)
    assert db.read("announcement_reads") == []


def test_acknowledgements_are_idempotent_persist_after_restart_and_are_per_account(popup_store):
    connection, cache, _, path = popup_store
    aid = notice()
    pending = popups.pending_announcements(STUDENT)
    popups.acknowledge_announcements(STUDENT, pending)
    popups.acknowledge_announcements(STUDENT, pending)
    reads = db.read("announcement_reads")
    assert len(reads) == 1 and reads[0]["student_id"] == STUDENT["id"]
    assert reads[0]["announcement_id"] == aid and reads[0]["revision"] and reads[0]["read_at"]
    assert popups.pending_announcements(STUDENT) == []
    assert [item["id"] for item in popups.pending_announcements(CLASSMATE)] == [aid]
    popups.acknowledge_announcements(CLASSMATE, pending)
    reads = db.read("announcement_reads")
    assert len(reads) == 2 and len({item["id"] for item in reads}) == 2
    connection["backend"] = db.LocalBackend(str(path))
    cache["data"].clear()
    assert popups.pending_announcements(STUDENT) == []
    assert popups.pending_announcements(CLASSMATE) == []
    assert connection["backend"].read("announcement_reads") == reads


@pytest.mark.parametrize("field", ["title", "content", "updated_at"])
def test_edited_notice_reappears_and_reuses_its_read_record_even_in_the_same_second(popup_store, field):
    aid = notice()
    old = popups.pending_announcements(STUDENT)
    popups.acknowledge_announcements(STUDENT, old)
    previous = db.read("announcement_reads")[0]
    changed = {"title": "변경한 제목", "content": "변경한 안내 내용", "updated_at": "2026-10-19 09:00:01"}[field]
    db.update("announcements", aid, {field: changed})
    pending = popups.pending_announcements(STUDENT)
    assert len(pending) == 1 and pending[0][field] == changed
    popups.acknowledge_announcements(STUDENT, pending)
    current = db.read("announcement_reads")
    assert len(current) == 1 and current[0]["id"] == previous["id"]
    assert current[0]["revision"] != previous["revision"]
    assert popups.pending_announcements(STUDENT) == []


@pytest.mark.parametrize("change", ["title", "content", "hidden", "reassigned", "deleted", "student_moved"])
def test_stale_dialog_does_not_acknowledge_changed_or_no_longer_visible_notices(popup_store, change):
    aid = notice()
    pending = popups.pending_announcements(STUDENT)
    if change in ("title", "content"):
        db.update("announcements", aid, {change: "학생이 아직 읽지 않은 새 내용"})
    elif change == "hidden":
        db.update("announcements", aid, {"active": "0"})
    elif change == "reassigned":
        db.update("announcements", aid, {"classes": '["1-2"]'})
    elif change == "deleted":
        db.delete("announcements", aid)
    else:
        db.update("users", STUDENT["id"], {"class": "1-2"})
    popups.acknowledge_announcements(STUDENT, pending)
    assert db.read("announcement_reads") == []
    assert bool(popups.pending_announcements(STUDENT)) == (change in ("title", "content"))


def test_acknowledging_multiple_notices_skips_stale_and_forged_items(popup_store):
    kept = notice("그대로인 공지")
    changed = notice("수정될 공지")
    pending = popups.pending_announcements(STUDENT)
    forged = copy.deepcopy(next(item for item in pending if item["id"] == kept))
    forged["content"] = "서버에 없는 본문"
    db.update("announcements", changed, {"content": "새로 고친 본문"})
    popups.acknowledge_announcements(STUDENT, [forged, None, {}, *pending])
    assert [item["announcement_id"] for item in db.read("announcement_reads")] == [kept]
    assert [item["id"] for item in popups.pending_announcements(STUDENT)] == [changed]


def test_polling_refreshes_only_when_an_existing_pending_signature_changes(popup_store, monkeypatch):
    reruns = []
    monkeypatch.setattr(popups.st, "session_state", {})
    monkeypatch.setattr(popups.st, "rerun", lambda **kwargs: reruns.append(kwargs))
    popups.poll_announcements(STUDENT)
    popups.poll_announcements(STUDENT)
    assert reruns == []
    aid = notice()
    popups.poll_announcements(STUDENT)
    assert reruns == [{"scope": "app"}]
    popups.poll_announcements(STUDENT)
    assert len(reruns) == 1
    db.update("announcements", aid, {"content": "같은 초에 변경한 공지"})
    popups.poll_announcements(STUDENT)
    assert reruns == [{"scope": "app"}, {"scope": "app"}]
    popups.acknowledge_announcements(STUDENT, popups.pending_announcements(STUDENT))
    popups.poll_announcements(STUDENT)
    popups.poll_announcements(STUDENT)
    assert reruns == [{"scope": "app"}] * 3


def test_popup_shows_all_full_notices_on_another_menu_and_does_not_repeat_after_confirmation(popup_store):
    long_body = "공지 본문의 첫 부분\n" + "자세한 안내를 확인하세요. " * 100 + "\n공지 본문의 마지막 부분"
    aid = notice(content=long_body)
    notice("두 번째 공개 공지", "함께 확인해야 할 다른 안내")
    notice("PRIVATE_OTHER_CLASS", classes=["1-2"])
    notice("PRIVATE_DRAFT", active=False)
    app = popup_app(menu="tools")
    assert not app.exception and not app.error
    text = displayed(app)
    assert "현재 메뉴: tools" in text and long_body in text
    assert "두 번째 공개 공지" in text and "함께 확인해야 할 다른 안내" in text
    assert "PRIVATE" not in text
    app.button(key="acknowledge_announcements").click().run()
    assert not app.exception and not app.error
    assert len(db.read("announcement_reads")) == 2
    assert not any(item.key == "acknowledge_announcements" for item in app.button)
    app.run()
    restarted = popup_app(menu="tools")
    assert not restarted.exception and not restarted.error
    assert not any(item.key == "acknowledge_announcements" for item in restarted.button)
    notice("같은 초에 수정한 공지", "다시 읽어야 할 새 안내", aid=aid)
    restarted.run()
    assert not restarted.exception and not restarted.error
    assert "다시 읽어야 할 새 안내" in displayed(restarted)
    assert restarted.button(key="acknowledge_announcements").label == "확인했어요"


def test_popup_confirmation_does_not_mark_a_revision_edited_after_dialog_open_as_read(popup_store):
    aid = notice()
    app = popup_app()
    assert "교과서와 필기도구를 챙기세요." in displayed(app)
    notice(content="확인 버튼을 누르기 전에 교사가 수정한 공지", aid=aid)
    app.button(key="acknowledge_announcements").click().run()
    assert not app.exception and not app.error
    assert db.read("announcement_reads") == []
    assert "확인 버튼을 누르기 전에 교사가 수정한 공지" in displayed(app)
    app.button(key="acknowledge_announcements").click().run()
    assert not app.exception and not app.error
    assert popups.pending_announcements(STUDENT) == []


@pytest.fixture
def main_app(popup_store, monkeypatch):
    import auth
    import realtime as rt
    import ui
    from views import emotion, home, tools

    monkeypatch.setattr(auth, "ensure_teacher", lambda: None)
    monkeypatch.setattr(ui, "inject_css", lambda: None)
    monkeypatch.setattr(ui, "sidebar_header", lambda *args: None)
    monkeypatch.setattr(rt, "touch", lambda *args: None)
    monkeypatch.setattr(rt, "is_locked", lambda *args: False)
    monkeypatch.setattr(rt, "has_pending", lambda *args: False)
    monkeypatch.setattr(emotion, "done_today", lambda *args: True)
    monkeypatch.setattr(home, "apply_pending_navigation", lambda *args: None)
    monkeypatch.setattr(home, "page", lambda *args: st.write("APP_HOME_CONTENT"))
    monkeypatch.setattr(tools, "page", lambda *args: st.write("APP_TOOLS_CONTENT"))

    def make(penalties=None):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.session_state["user"] = dict(STUDENT)
        app.session_state["nav"] = "tools"
        if penalties:
            app.session_state["_popups"] = penalties
        return app.run()

    return make


def test_main_app_polls_for_notices_and_opens_popup_while_student_uses_tools(main_app):
    app = main_app()
    assert not app.exception and not app.error
    assert "APP_TOOLS_CONTENT" in displayed(app)
    assert not any(item.key == "acknowledge_announcements" for item in app.button)
    notice("수업도구에서 확인할 공지", "다른 메뉴에서도 새 공지가 표시됩니다.")
    app.run()
    assert not app.exception and not app.error
    assert "APP_TOOLS_CONTENT" in displayed(app)
    assert "다른 메뉴에서도 새 공지가 표시됩니다." in displayed(app)
    app.button(key="acknowledge_announcements").click().run()
    assert not app.exception and not app.error
    assert "APP_TOOLS_CONTENT" in displayed(app)
    assert not any(item.key == "acknowledge_announcements" for item in app.button)


def test_main_app_shows_penalty_and_announcement_dialogs_in_separate_reruns(main_app):
    notice("벌점 확인 뒤의 공지", "두 팝업이 서로 가리지 않아야 합니다.")
    app = main_app([dict(kind="벌점", score="1", reason="준비물 미지참")])
    assert not app.exception and not app.error
    assert "준비물 미지참" in displayed(app)
    assert not any(item.key == "acknowledge_announcements" for item in app.button)
    next(item for item in app.button if item.label == "확인했어요").click().run()
    assert not app.exception and not app.error
    assert "두 팝업이 서로 가리지 않아야 합니다." in displayed(app)
    app.button(key="acknowledge_announcements").click().run()
    assert not app.exception and not app.error
    assert not any(item.key == "acknowledge_announcements" for item in app.button)
