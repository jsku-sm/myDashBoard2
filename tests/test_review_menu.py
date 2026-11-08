"""The new quiz submenu is teacher-only, including stale session values."""
from test_tools_menu import menu_app
from review_core import view


def test_teacher_review_submenu(menu_app,monkeypatch):
    monkeypatch.setattr(view,'teacher_page',lambda user:view.st.write('전시학습 교사 설정 확인'))
    app=menu_app.make(active='tool_quiz')
    picker=next(r for r in app.radio if r.label=='퀴즈 하위 메뉴')
    assert picker.options==['개념 확인 퀴즈','전시학습 확인']
    picker.set_value('전시학습 확인').run()
    assert not app.exception
    assert any('전시학습 교사 설정 확인' in str(x.value) for x in app.markdown)


def test_student_has_no_review_submenu_even_with_stale_value(menu_app):
    app=menu_app.make(role='student',active='tool_quiz')
    app.session_state['_quiz_review_sub']='전시학습 확인'
    app.run()
    assert not app.exception
    assert all(r.label!='퀴즈 하위 메뉴' for r in app.radio)
    assert all('전시학습 교사 설정 확인' not in str(x.value) for x in app.markdown)
