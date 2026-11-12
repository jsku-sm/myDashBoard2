"""QuizPop replaces the old quiz/review submenu for both authenticated roles."""
import pytest
from test_tools_menu import menu_app, QUIZ_SENTINEL


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_new_quiz_replaces_legacy_submenus_even_with_stale_selection(menu_app, role):
    app=menu_app.make(role=role, active="tool_quiz")
    app.session_state["_quiz_review_sub"]="전시학습 확인"
    app.run()
    assert not app.exception
    assert all(r.label!="퀴즈 하위 메뉴" for r in app.radio)
    assert any(QUIZ_SENTINEL in str(x.value) for x in app.markdown)
