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
    }, reviewed=(clock["instant"] - timedelta(minutes=1)).isoformat()))
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


def selector(app, label):
    return next(item for item in app.selectbox if item.label == label)


def choose(app, label, value):
    selector(app, label).set_value(value).run(timeout=10)
    assert not app.exception and not app.error
    return app


def popover_labels(app):
    return [item.proto.popover.label for item in app.get("popover")]


def student_surface(app):
    return "\n".join([displayed(app), *popover_labels(app),
                      *(option for item in app.selectbox for option in item.options),
                      *(item.label for item in app.button),
                      *(item.label for item in app.get("download_button"))])


def test_home_shows_all_four_update_types_before_recent_feedback_and_keeps_existing_sections(home_ui):
    _, _, _, _, _, _, make = home_ui
    app = make()
    assert not app.exception and not app.error
    text = displayed(app)
    for value in ("배포 문서", "선생님 피드백", "수행평가 배포 현황", "공지글",
                  "게시판의 설명을 잘 썼어요.",
                  "기존 최근 피드백"):
        assert value in text
    assert "우리 반 준비물 공지" in student_surface(app) and "설명하는 풀이" in student_surface(app)
    assert [item.value for item in app.markdown if item.value.startswith("##### ")] == [
        "##### 📄 배포 문서", "##### 💬 선생님 피드백", "##### 📝 수행평가 배포 현황", "##### 📢 공지글"]
    assert {item.label for item in app.selectbox} == {
        "배포 문서 선택", "선생님 피드백 선택", "수행평가 선택", "공지글 선택", "게시판 피드백 선택"}
    assert "최근에 받은 피드백 · 1건" in popover_labels(app)
    assert "PRIVATE" not in student_surface(app)
    assert "오늘의 기분" in text and "상점" in text and "벌점" in text and "3점" in text
    assert not app.metric
    assert any(item.label == "활동지.pdf" for item in app.get("download_button"))
    assert "교사가 배포한 문서" not in text and "수업 전에 읽어 보세요." not in text
    assert len(selector(app, "선생님 피드백 선택").options) == 3
    choose(app, "선생님 피드백 선택", "question:question")
    assert "질문의 식을 먼저 정리해 보세요." in displayed(app)
    choose(app, "선생님 피드백 선택", "assessment:" + "a" * 32)
    for value in ("수행평가의 풀이 근거가 좋아요.", "답안의 식을 바르게 정리했어요.", "각 단계의 이유도 설명해 보세요."):
        assert value in displayed(app)
    assert "PRIVATE" not in student_surface(app)


@pytest.mark.parametrize("is_local", [True, False])
def test_document_dropdown_keeps_all_files_but_loads_and_downloads_only_the_selected_file(home_ui, monkeypatch, is_local):
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
    downloads, loads = [], []
    original_load = backend.load_file
    def load(file_id):
        loads.append(file_id)
        return original_load(file_id)
    monkeypatch.setattr(backend, "load_file", load)
    original_download = updates.st.download_button
    def download(label, **kwargs):
        downloads.append((label, kwargs["data"], kwargs["file_name"], kwargs["mime"]))
        return original_download(label, **kwargs)
    monkeypatch.setattr(updates.st, "download_button", download)

    app = make()

    assert not app.exception and not app.error
    expected = ["학습지_7.pdf"]
    buttons = app.get("download_button")
    assert [item.label for item in buttons] == expected
    assert all(not item.disabled and item.proto.url for item in buttons)
    assert downloads == [(name, files[name], name, "application/pdf") for name in expected]
    assert len(loads) == 1
    assert len(selector(app, "배포 문서 선택").options) == 8
    assert all(any(f"학습지_{index}.pdf" in option for option in selector(app, "배포 문서 선택").options)
               for index in range(1, 8))
    text = displayed(app)
    assert "단원 제목" not in text and "표시하지 않을 설명" not in text
    assert not any("열기" in item.label and "학습지" in item.label for item in app.button)
    choose(app, "배포 문서 선택", "document-1")
    assert [item.label for item in app.get("download_button")] == ["학습지_1.pdf"]
    assert downloads[-1] == ("학습지_1.pdf", files["학습지_1.pdf"], "학습지_1.pdf", "application/pdf")
    assert len(loads) == 2 and len(set(loads)) == 2
    app.run(timeout=10)
    assert not app.exception and not app.error and len(loads) == 2
    assert app.session_state["nav"] == "home" and REQUESTED_COURSE not in app.session_state


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
    assert "새로 배포한 공지" in student_surface(student)
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
    choose(app, "선생님 피드백 선택", "assessment:" + "a" * 32)
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
    assert selector(app, "수행평가 선택").disabled
    assert any(item.label == "활동지.pdf" for item in app.get("download_button"))
    assert "우리 반 준비물 공지" in student_surface(app)
    assert "게시판의 설명을 잘 썼어요." in text and "PRIVATE" not in text


def test_other_class_and_unpublished_notices_disappear_after_teacher_changes_targets(home_ui):
    _, _, _, _, notice_id, _, make = home_ui
    app = make()
    announcements.save_announcement(TEACHER, "우리 반 준비물 공지", "내용", ["1-2"], announcement_id=notice_id)
    app.run()
    assert not app.exception and not app.error
    assert "우리 반 준비물 공지" not in student_surface(app)
    assert "PRIVATE_OTHER_CLASS_NOTICE" not in student_surface(app)
    assert "PRIVATE_DRAFT_NOTICE" not in student_surface(app)


def test_home_updates_recheck_enrollment_before_refreshing_a_stale_student_fragment(home_ui, monkeypatch):
    db.update("users", USER["id"], {"class": "1-2"})
    reruns = []
    monkeypatch.setattr(updates.st, "rerun", lambda **kwargs: reruns.append(kwargs))
    monkeypatch.setattr(updates, "_assessment_state", lambda: pytest.fail("Stale enrollment must be rechecked first."))
    updates.render_student_updates.__wrapped__(USER)
    assert reruns == [{"scope": "app"}]


def test_many_long_updates_keep_all_dropdown_choices_and_render_only_selected_details(home_ui):
    _, room, cid, _, _, clock, make = home_ui
    assessment_ids = []
    for index in range(1, 9):
        timestamp = (clock["instant"] + timedelta(minutes=10 + index)).isoformat()
        db.append("submissions", dict(id=f"long-submission-{index}", student_id=USER["id"], subject="공통수학1",
            title=f"긴 게시판 글 {index}", created_at=timestamp, teacher_comment_at=timestamp,
            feedback=("자동 격려의 내용 " * 100) + f"AUTO_END_{index}",
            teacher_comment=("풀이에 대한 선생님 의견 " * 100) + f"TEACHER_END_{index}"))
        db.append("questions", dict(id=f"long-question-{index}", student_id=USER["id"], subject="공통수학2",
            title=f"긴 질문 {index}", answered_at=timestamp,
            answer=("질문에 대한 상세한 설명 " * 100) + f"QUESTION_END_{index}"))
        db.append("announcements", dict(id=f"long-notice-{index}", title=f"긴 공지 {index}", classes='["1-1"]', active="1",
            created_at=timestamp, updated_at=timestamp, author_name="선생님",
            content=("공지의 상세한 안내 " * 100) + f"NOTICE_END_{index}"))
        aid = room.save_activity(cid, f"추가 수행평가 {index}", "PRIVATE_QUESTION", "PRIVATE_MODEL_ANSWER", ["PRIVATE_CRITERIA"],
                                 2, db.today_str(), db.today_str())
        room.distribute_activity(aid)
        room.store.transaction(lambda state: state["course_activities"][aid].update(updated=timestamp))
        assessment_ids.append(aid)

    app = make()

    assert not app.exception and not app.error
    assert len(selector(app, "선생님 피드백 선택").options) == 19
    assert len(selector(app, "공지글 선택").options) == 9
    assert len(selector(app, "수행평가 선택").options) == 9
    assert len(selector(app, "게시판 피드백 선택").options) == 9
    assert "최근에 받은 피드백 · 9건" in popover_labels(app)
    assert len([item for item in app.button if (item.key or "").startswith("home_assessment_")]) == 1
    assert not app.metric and not app.expander
    choose(app, "선생님 피드백 선택", "question:long-question-1")
    assert "QUESTION_END_1" in displayed(app) and "QUESTION_END_2" not in displayed(app)
    choose(app, "공지글 선택", "long-notice-1")
    assert "NOTICE_END_1" in displayed(app) and "NOTICE_END_2" not in displayed(app)
    choose(app, "게시판 피드백 선택", "long-submission-1")
    assert "AUTO_END_1" in displayed(app) and "TEACHER_END_1" in displayed(app)
    assert "AUTO_END_8" not in displayed(app) and "TEACHER_END_8" not in displayed(app)
    choose(app, "수행평가 선택", assessment_ids[0])
    assert app.button(key="home_assessment_" + assessment_ids[0]).label == "수행평가 열기"
    assert len([item for item in app.button if (item.key or "").startswith("home_assessment_")]) == 1
    assert "PRIVATE" not in student_surface(app)
    assert app.session_state["nav"] == "home"
    assert REQUESTED_COURSE not in app.session_state and updates.PENDING_NAVIGATION not in app.session_state
    assert {key: app.session_state["user"][key] for key in USER} == USER


@pytest.mark.parametrize("same_title", [False, True])
def test_feedback_choices_with_same_record_id_keep_source_identity_and_full_selected_feedback(home_ui, same_title):
    _, _, _, _, _, clock, make = home_ui
    db.append("questions", dict(id="submission", student_id=USER["id"], subject="공통수학2",
        title="나의 게시판 풀이" if same_title else "게시판과 번호가 같은 질문",
        answered_at=(clock["instant"] + timedelta(minutes=1)).isoformat(),
        answer="질문에만 해당하는 답변 SAME_ID_QUESTION"))
    app = make()
    assert len(selector(app, "선생님 피드백 선택").options) == 4
    choose(app, "선생님 피드백 선택", "submission:submission")
    assert selector(app, "선생님 피드백 선택").value == "submission:submission"
    assert "게시판의 설명을 잘 썼어요." in displayed(app)
    assert "SAME_ID_QUESTION" not in displayed(app)
    choose(app, "선생님 피드백 선택", "question:submission")
    assert selector(app, "선생님 피드백 선택").value == "question:submission"
    assert "SAME_ID_QUESTION" in displayed(app)
    choose(app, "선생님 피드백 선택", "assessment:" + "a" * 32)
    for text in ("수행평가의 풀이 근거가 좋아요.", "답안의 식을 바르게 정리했어요.", "각 단계의 이유도 설명해 보세요."):
        assert text in displayed(app)
    assert "SAME_ID_QUESTION" not in displayed(app)
    assert "PRIVATE" not in student_surface(app)


def test_new_latest_document_is_selected_while_explicit_history_selection_is_kept_and_deleted_id_resets(home_ui):
    backend, _, _, _, _, clock, make = home_ui
    app = make()
    assert selector(app, "배포 문서 선택").value == "document"
    def append_document(identity, filename, minutes):
        fid, _ = backend.save_file(filename.encode(), filename, "application/pdf", True)
        db.append("materials", dict(id=identity, subject="공통수학1", category="학습지", title=filename,
            file_id=fid, file_name=filename, mime="application/pdf",
            uploaded_at=(clock["instant"] + timedelta(minutes=minutes)).isoformat()))
    append_document("new-document", "새 활동지.pdf", 1)
    app.run(timeout=10)
    assert not app.exception and not app.error
    assert selector(app, "배포 문서 선택").value == "new-document"
    assert [item.label for item in app.get("download_button")] == ["새 활동지.pdf"]
    choose(app, "배포 문서 선택", "document")
    append_document("newest-document", "최신 활동지.pdf", 2)
    app.run(timeout=10)
    assert not app.exception and not app.error
    assert selector(app, "배포 문서 선택").value == "document"
    assert [item.label for item in app.get("download_button")] == ["활동지.pdf"]
    db.delete("materials", "document")
    app.run(timeout=10)
    assert not app.exception and not app.error
    assert selector(app, "배포 문서 선택").value == "newest-document"
    assert len(selector(app, "배포 문서 선택").options) == 2
    assert [item.label for item in app.get("download_button")] == ["최신 활동지.pdf"]


def test_deleted_selected_feedback_and_recent_post_reset_without_old_details_or_other_students(home_ui):
    _, _, _, _, _, clock, make = home_ui
    db.append("submissions", dict(id="older", student_id=USER["id"], subject="공통수학1", title="이전 게시판 풀이",
        created_at=(clock["instant"] - timedelta(minutes=2)).isoformat(),
        teacher_comment_at=(clock["instant"] - timedelta(minutes=2)).isoformat(),
        feedback="OLD_AUTOMATIC_DETAIL", teacher_comment="OLD_TEACHER_DETAIL"))
    app = make()
    choose(app, "선생님 피드백 선택", "submission:older")
    choose(app, "게시판 피드백 선택", "older")
    assert "OLD_AUTOMATIC_DETAIL" in displayed(app) and "OLD_TEACHER_DETAIL" in displayed(app)
    db.delete("submissions", "older")
    app.run(timeout=10)
    assert not app.exception and not app.error
    assert selector(app, "선생님 피드백 선택").value == "submission:submission"
    assert selector(app, "게시판 피드백 선택").value == "submission"
    assert "OLD_AUTOMATIC_DETAIL" not in displayed(app) and "OLD_TEACHER_DETAIL" not in displayed(app)
    assert "PRIVATE" not in student_surface(app)


def test_all_four_compact_category_choosers_remain_visible_when_empty(home_ui):
    _, room, _, aid, notice_id, _, make = home_ui
    db.delete("materials", "document")
    db.delete("submissions", "submission")
    db.delete("questions", "question")
    announcements.save_announcement(TEACHER, "우리 반 준비물 공지", "내용", ["1-2"], announcement_id=notice_id)
    room.store.transaction(lambda state: state["course_activities"][aid].update(status="숨김"))
    app = make()
    assert not app.exception and not app.error
    for label in ("배포 문서 선택", "선생님 피드백 선택", "수행평가 선택", "공지글 선택"):
        assert selector(app, label).disabled
    assert not app.get("download_button")
    assert not any((item.key or "").startswith("home_assessment_") for item in app.button)
    assert "PRIVATE" not in student_surface(app)


def test_duplicate_filenames_and_titles_remain_distinct_selectable_records_in_every_category(home_ui, monkeypatch):
    backend, room, cid, aid, notice_id, clock, make = home_ui
    timestamp = (clock["instant"] + timedelta(minutes=1)).isoformat()
    fid, _ = backend.save_file(b"new document version", "활동지.pdf", "application/pdf", True)
    db.append("materials", dict(id="duplicate-document", subject="공통수학1", category="학습지", file_id=fid,
        file_name="활동지.pdf", mime="application/pdf", uploaded_at=timestamp))
    db.append("submissions", dict(id="duplicate-submission", student_id=USER["id"], subject="공통수학1",
        title="나의 게시판 풀이", created_at=timestamp, teacher_comment_at=timestamp,
        feedback="두 번째 같은 제목 게시판의 피드백", teacher_comment="두 번째 같은 제목 게시판의 교사 의견"))
    db.append("announcements", dict(id="duplicate-notice", title="우리 반 준비물 공지", content="두 번째 같은 제목 공지의 내용",
        classes='["1-1"]', active="1", created_at=timestamp, updated_at=timestamp, author_name="선생님"))
    duplicate_aid = room.save_activity(cid, "설명하는 풀이", "PRIVATE_QUESTION", "PRIVATE_EXPECTED", ["PRIVATE_CRITERIA"],
                                       2, db.today_str(), db.today_str())
    room.distribute_activity(duplicate_aid)
    room.store.transaction(lambda state: state["course_activities"][duplicate_aid].update(updated=timestamp))
    downloads = []
    original_download = updates.st.download_button
    def download(label, **kwargs):
        downloads.append(kwargs["data"])
        return original_download(label, **kwargs)
    monkeypatch.setattr(updates.st, "download_button", download)
    app = make()
    for label in ("배포 문서 선택", "선생님 피드백 선택", "수행평가 선택", "공지글 선택", "게시판 피드백 선택"):
        options = selector(app, label).options
        assert len(options) == len(set(options)), label
    for label, first, second in (("배포 문서 선택", "document", "duplicate-document"),
                                 ("게시판 피드백 선택", "submission", "duplicate-submission"),
                                 ("공지글 선택", notice_id, "duplicate-notice"),
                                 ("수행평가 선택", aid, duplicate_aid)):
        choose(app, label, first)
        assert selector(app, label).value == first
        choose(app, label, second)
        assert selector(app, label).value == second
    assert "두 번째 같은 제목 게시판의 피드백" in displayed(app)
    assert "두 번째 같은 제목 공지의 내용" in displayed(app)
    assert downloads[-1] == b"new document version"
    assert app.button(key="home_assessment_" + duplicate_aid).label == "수행평가 열기"
    assert "PRIVATE" not in student_surface(app)
    assert app.session_state["nav"] == "home" and REQUESTED_COURSE not in app.session_state
