"""Teacher updates reach the correct student home and its existing navigation."""
from datetime import timedelta
import io

from pypdf import PdfWriter
import pytest
from streamlit.testing.v1 import AppTest

import storage as db
from config import TZ
from snorkl_navigation import ACTIVE_TOOL, LINK_SEEN, REQUESTED_COURSE
from think_app.classroom import Classroom
from think_app.courses import CourseManager
from think_app.storage import AppError, MemoryStore
from views import announcements, math_class
from views import student_home_updates as updates


USER = dict(id="10101", name="학생", role="student", **{"class": "1-1"})
TEACHER = dict(id="teacher", name="선생님", role="teacher")


@pytest.fixture
def home_ui(tmp_path, monkeypatch):
    backend = db.LocalBackend(str(tmp_path))
    db._cache.clear()
    db.load_file_cached.clear()
    monkeypatch.setattr(db, "get_backend", lambda: backend)
    clock = {"instant": db.now()}
    monkeypatch.setattr(db, "now_str", lambda: clock["instant"].strftime("%Y-%m-%d %H:%M:%S"))
    db.append("users", TEACHER)
    db.append("users", USER)
    store = MemoryStore()
    room = Classroom(store)
    manager = CourseManager(store)
    cid = manager.create("우리 반 수행평가", "#123456", ["1-1"])
    aid = room.save_activity(cid, "설명하는 풀이", "PRIVATE_QUESTION", "PRIVATE_MODEL_ANSWER", ["PRIVATE_CRITERIA"],
                             2, db.today_str(), db.today_str())
    room.distribute_activity(aid)
    mine = room.submit(aid, USER["id"], USER["name"], USER["class"], "PRIVATE_STUDENT_WORK", [], False, "a" * 32)
    room.comment(mine, "수행평가의 풀이 근거가 좋아요.")
    store.transaction(lambda state: state["course_attempts"][mine].update(feedback={
        "praise": "답안의 식을 바르게 정리했어요.", "hint": "각 단계의 이유도 설명해 보세요.",
        "teacher_notes": "PRIVATE_TEACHER_ONLY_ANALYSIS", "expected_answer": "PRIVATE_ANSWER_KEY",
    }))
    other = room.submit(aid, "10102", "다른 학생", "1-1", "PRIVATE_OTHER_WORK", [], False, "b" * 32)
    room.comment(other, "PRIVATE_OTHER_ASSESSMENT_FEEDBACK")
    hidden = room.save_activity(cid, "PRIVATE_UNPUBLISHED", "숨긴 문제", "숨긴 답안", ["기준"],
                                2, db.today_str(), db.today_str())
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    raw = io.BytesIO()
    writer.write(raw)
    fid, _ = backend.save_file(raw.getvalue(), "활동지.pdf", "application/pdf", True)
    db.append("materials", dict(id="document", subject="공통수학1", category="학습지", title="교사가 배포한 문서",
                                description="수업 전에 읽어 보세요.", file_id=fid, file_name="활동지.pdf",
                                mime="application/pdf", uploaded_at=db.now_str()))
    db.append("submissions", dict(id="submission", student_id=USER["id"], name=USER["name"], **{"class": USER["class"]},
                                  subject="공통수학1", title="나의 게시판 풀이", created_at=db.now_str(),
                                  teacher_comment_at=db.now_str(), teacher_comment="게시판의 설명을 잘 썼어요.",
                                  feedback="기존 최근 피드백", content="PRIVATE_BOARD_WORK"))
    db.append("submissions", dict(id="other", student_id="10102", **{"class": "1-1"}, subject="공통수학1",
                                  teacher_comment="PRIVATE_OTHER_COMMENT", feedback="PRIVATE_OTHER_AUTOMATIC"))
    db.append("questions", dict(id="question", student_id=USER["id"], subject="공통수학2", title="나의 질문",
                                answered_at=db.now_str(), answer="질문의 식을 먼저 정리해 보세요."))
    own_notice = announcements.save_announcement(TEACHER, "우리 반 준비물 공지", "교과서와 필기도구를 챙기세요.", ["1-1"])
    announcements.save_announcement(TEACHER, "PRIVATE_OTHER_CLASS_NOTICE", "다른 반 안내", ["1-2"])
    announcements.save_announcement(TEACHER, "PRIVATE_DRAFT_NOTICE", "아직 공개하지 않은 안내", ["1-1"], False)
    db.append("points", dict(student_id=USER["id"], kind="상점", score="3"))
    monkeypatch.setattr(updates, "_assessment_state", store.read)
    def app():
        result = AppTest.from_string(
            "import streamlit as st\n"
            "import auth\n"
            "from views import home\n"
            "from snorkl_navigation import sync_shared_link\n"
            "user=auth.get_user(st.session_state['user']['id'])\n"
            "st.session_state['user']=user\n"
            "sync_shared_link(st.session_state,st.query_params)\n"
            "home.apply_pending_navigation(user)\n"
            "st.radio('메뉴',['home','tools','math1','math2'],key='nav')\n"
            "if st.session_state['nav']=='home':\n"
            "    home.page(user)\n"
            "else:\n"
            "    st.write('선택한 메뉴: '+st.session_state['nav'])\n")
        result.session_state["user"] = dict(USER)
        return result.run(timeout=10)
    try:
        yield backend, room, cid, aid, own_notice, clock, app
    finally:
        db._cache.clear()
        db.load_file_cached.clear()


def displayed(app):
    return "\n".join(str(item.value) for kind in (app.markdown, app.caption, app.info, app.warning)
                     for item in kind)


def test_home_shows_all_four_update_types_before_recent_feedback_and_keeps_existing_sections(home_ui):
    _, _, _, _, _, _, make = home_ui
    app = make()
    assert not app.exception and not app.error
    text = displayed(app)
    for value in ("배포 문서", "선생님 피드백", "수행평가 배포 현황", "공지글",
                  "게시판의 설명을 잘 썼어요.", "질문의 식을 먼저 정리해 보세요.", "수행평가의 풀이 근거가 좋아요.",
                  "답안의 식을 바르게 정리했어요.", "각 단계의 이유도 설명해 보세요.",
                  "우리 반 준비물 공지", "설명하는 풀이", "기존 최근 피드백"):
        assert value in text
    for heading in ("##### 📄 배포 문서", "##### 💬 선생님 피드백", "##### 📝 수행평가 배포 현황", "##### 📢 공지글"):
        assert text.index(heading) < text.index("#### 최근에 받은 피드백")
    assert "PRIVATE" not in text
    assert "#### 오늘의 기분" in text and "#### 나의 상점·벌점" in text
    assert any(item.value == "3점" for item in app.metric)
    assert any(item.label == "활동지.pdf" for item in app.get("download_button"))
    assert "교사가 배포한 문서" not in text and "수업 전에 읽어 보세요." not in text


@pytest.mark.parametrize("is_local", [True, False])
def test_documents_show_only_five_latest_filenames_as_direct_downloads(home_ui, monkeypatch, is_local):
    backend, _, _, _, _, clock, make = home_ui
    monkeypatch.setattr(backend, "is_local", is_local)
    files = {}
    for index in (3, 7, 1, 5, 2, 6, 4):
        filename = f"학습지_{index}.pdf"
        raw = f"worksheet {index}".encode()
        fid, _ = backend.save_file(raw, filename, "application/pdf", True)
        files[filename] = raw
        db.append("materials", dict(id=f"document-{index}", subject="공통수학2", category="학습지",
                                    title=f"단원 제목 {index}", description="표시하지 않을 설명", file_id=fid,
                                    file_name=filename, mime="application/pdf",
                                    uploaded_at=(clock["instant"] + timedelta(minutes=index)).isoformat()))
    downloads = []
    original_download = updates.st.download_button
    def download(label, **kwargs):
        downloads.append((label, kwargs["data"], kwargs["file_name"], kwargs["mime"]))
        return original_download(label, **kwargs)
    monkeypatch.setattr(updates.st, "download_button", download)

    app = make()

    assert not app.exception and not app.error
    expected = [f"학습지_{index}.pdf" for index in (7, 6, 5, 4, 3)]
    buttons = app.get("download_button")
    assert [item.label for item in buttons] == expected
    assert all(not item.disabled and item.proto.url for item in buttons)
    assert downloads == [(name, files[name], name, "application/pdf") for name in expected]
    assert not app.columns[0].expander
    text = displayed(app)
    assert "단원 제목" not in text and "표시하지 않을 설명" not in text
    assert not any("열기" in item.label and "학습지" in item.label for item in app.button)


def test_teacher_new_notice_and_edited_feedback_appear_on_the_student_home(home_ui):
    _, _, _, _, _, clock, make = home_ui
    student = make()
    clock["instant"] += timedelta(minutes=2)
    teacher = AppTest.from_string(
        "import streamlit as st\nfrom views import announcements\n"
        "announcements.tab_announcements(st.session_state['user'])\n")
    teacher.session_state["user"] = dict(TEACHER)
    teacher.run()
    teacher.text_input(key="announcement_new_title").set_value("새로 배포한 공지")
    teacher.text_area(key="announcement_new_content").set_value("내일 평가 준비물을 확인하세요.")
    teacher.multiselect(key="announcement_new_classes").set_value(["1-1"])
    teacher.button(key="announcement_create_save").click().run()
    assert not teacher.exception and not teacher.error
    feedback = AppTest.from_string("from views import math_class\nmath_class._board_teacher('공통수학1')\n").run()
    feedback.text_input(key="cm_submission").set_value("새로 고친 선생님의 피드백")
    feedback.button(key="cms_submission").click().run()
    assert not feedback.exception and not feedback.error
    assert db.read("submissions")[0]["teacher_comment_at"] == db.now_str()
    student.run()
    assert not student.exception and not student.error
    assert "새로 배포한 공지" in displayed(student)
    assert "새로 고친 선생님의 피드백" in displayed(student)


def test_assessment_shortcut_changes_the_instantiated_sidebar_without_widget_errors(home_ui):
    _, _, cid, aid, _, _, make = home_ui
    app = make()
    app.query_params.update({"tool": "snorkl", "course_id": "c" * 32})
    app.session_state[LINK_SEEN] = ("snorkl", "c" * 32)
    app.button(key="home_assessment_" + aid).click().run()
    assert not app.exception and not app.error
    assert app.session_state["nav"] == "tools"
    assert app.session_state[ACTIVE_TOOL] == "snorkl"
    assert app.session_state[REQUESTED_COURSE] == cid
    assert app.session_state["snorkl_student_activity_" + cid] == aid
    assert {key: app.session_state["user"][key] for key in USER} == USER
    assert "course_id" not in app.query_params and "tool" not in app.query_params
    assert updates.PENDING_NAVIGATION not in app.session_state


def test_closed_assessment_overview_stays_visible_and_feedback_is_kept(home_ui):
    _, room, _, aid, _, _, make = home_ui
    room.start_timer(aid, 10)
    room.end_timer(aid)
    app = make()
    assert not app.exception and not app.error
    assert "평가 종료" in displayed(app) and "선생님이 평가를 종료했습니다." in displayed(app)
    assert "수행평가의 풀이 근거가 좋아요." in displayed(app)
    assert app.button(key="home_assessment_" + aid).disabled


def test_assessment_connection_error_does_not_hide_documents_feedback_or_notices(home_ui, monkeypatch):
    *_, make = home_ui
    def unavailable():
        raise AppError("PRIVATE_CONNECTION_DETAIL")
    monkeypatch.setattr(updates, "_assessment_state", unavailable)
    app = make()
    assert not app.exception and not app.error
    text = displayed(app)
    assert "수행평가 소식을 불러오지 못했어요." in text
    assert any(item.label == "활동지.pdf" for item in app.get("download_button"))
    assert "우리 반 준비물 공지" in text
    assert "게시판의 설명을 잘 썼어요." in text and "PRIVATE" not in text


def test_other_class_and_unpublished_notices_disappear_after_teacher_changes_targets(home_ui):
    _, _, _, _, notice_id, _, make = home_ui
    app = make()
    announcements.save_announcement(TEACHER, "우리 반 준비물 공지", "내용", ["1-2"], announcement_id=notice_id)
    app.run()
    assert not app.exception and not app.error
    assert "우리 반 준비물 공지" not in displayed(app)
    assert "PRIVATE_OTHER_CLASS_NOTICE" not in displayed(app)
    assert "PRIVATE_DRAFT_NOTICE" not in displayed(app)


def test_home_updates_recheck_enrollment_before_refreshing_a_stale_student_fragment(home_ui, monkeypatch):
    db.update("users", USER["id"], {"class": "1-2"})
    reruns = []
    monkeypatch.setattr(updates.st, "rerun", lambda **kwargs: reruns.append(kwargs))
    monkeypatch.setattr(updates, "_assessment_state", lambda: pytest.fail("Stale enrollment must be rechecked first."))
    updates.render_student_updates.__wrapped__(USER)
    assert reruns == [{"scope": "app"}]
