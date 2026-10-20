"""Menu-only regressions; no Streamlit install, secrets, or network required.

The actual MENU, menu_for and sidebar definitions are loaded from app.py using
AST, avoiding app startup and operational storage. This is a logic test, not a
browser/Streamlit UI test.
"""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from snorkl_navigation import sync_shared_link

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_TREE = ast.parse(APP_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def app_menu():
    nodes = [
        node for node in APP_TREE.body
        if (isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == "MENU" for target in node.targets))
        or (isinstance(node, ast.FunctionDef) and node.name in ("menu_for", "sidebar"))
    ]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace


class FakeStreamlit:
    def __init__(self, state):
        self.session_state = state
        self.query_params = {}
        self.sidebar = nullcontext()
        self.labels = []
        self.callbacks = []

    def radio(self, label, options, *, format_func, key, on_change, args, **kwargs):
        self.labels = [format_func(item) for item in options]
        self.callbacks.append((on_change, args))
        assert self.session_state[key] in options
        return self.session_state[key]

    def container(self, **kwargs):
        return nullcontext()

    def button(self, *args, **kwargs):
        return False

    def divider(self):
        pass

    def caption(self, message):
        pass


def render_sidebar(app_menu, role, state):
    fake = FakeStreamlit(state)
    app_menu.update(
        st=fake,
        ui=SimpleNamespace(sidebar_header=lambda *args: None),
        rt=SimpleNamespace(locked_classes=lambda: []),
        db=SimpleNamespace(backend_status=lambda: "memory-only-test"),
        APP_TITLE="메뉴 검사",
        main_menu_changed=lambda *args: None,
    )
    return app_menu["sidebar"]({"id": "test", "role": role}), fake


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_classroom_is_not_a_visible_menu(app_menu, role):
    menu = app_menu["menu_for"](role)
    assert "classroom" not in menu
    assert all("클래스룸" not in label for label in menu.values())
    assert {"intro", "math1", "math2", "sudanote", "tools", "account"} <= menu.keys()
    if role == "teacher":
        assert "dashboard" in menu and "teacher" in menu and "home" not in menu
    else:
        assert "home" in menu and "dashboard" not in menu and "teacher" not in menu


@pytest.mark.parametrize("role", ["teacher", "student"])
@pytest.mark.parametrize("previous", [None, "classroom", "removed-menu"])
def test_old_session_recovers_without_clearing_user_or_drafts(app_menu, role, previous):
    user = {"id": "test", "role": role}
    draft = {"answer": "작성 중 답안"}
    state = {"user": user, "draft": draft, "saved_progress": "keep"}
    if previous is not None:
        state["nav"] = previous
    selected, fake = render_sidebar(app_menu, role, state)
    assert selected == ("dashboard" if role == "teacher" else "home")
    assert state["user"] is user and state["draft"] is draft
    assert state["saved_progress"] == "keep"
    assert not any("클래스룸" in label for label in fake.labels)


@pytest.mark.parametrize("role", ["teacher", "student"])
@pytest.mark.parametrize("selected", ["intro", "math1", "math2", "sudanote", "tools", "account"])
def test_existing_valid_menu_stays_selected(app_menu, role, selected):
    result, _ = render_sidebar(app_menu, role, {"nav": selected})
    assert result == selected


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_other_role_menu_falls_back_safely(app_menu, role):
    selected, _ = render_sidebar(app_menu, role, {"nav": "home" if role == "teacher" else "teacher"})
    assert selected == ("dashboard" if role == "teacher" else "home")


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_numbered_menu_labels_remain_contiguous(app_menu, role):
    labels = app_menu["menu_for"](role).values()
    numbers = [int(label.split(".", 1)[0]) for label in labels if label[:1].isdigit()]
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_available_route_matches_a_menu(app_menu):
    routes = next(node.value for node in APP_TREE.body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "ROUTES" for target in node.targets))
    route_ids = {ast.literal_eval(key) for key in routes.keys}
    menu_ids = {row[0] for row in app_menu["MENU"]}
    assert route_ids == menu_ids
    assert "classroom" not in route_ids


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_snorkl_shared_link_still_opens_tools(app_menu, role):
    user = {"id": "test", "role": role}
    state = {"nav": "classroom", "user": user}
    sync_shared_link(state, {"tool": "snorkl", "course_id": "test-course"})
    selected, _ = render_sidebar(app_menu, role, state)
    assert selected == "tools"
    assert state["_tools_active"] == "snorkl"
    assert state["_snorkl_requested_course"] == "test-course"
    assert state["user"] is user
