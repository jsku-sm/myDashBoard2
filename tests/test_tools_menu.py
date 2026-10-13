"""Streamlit menu regressions with in-memory settings and a guarded-page stand-in.

AppTest exercises callbacks and reruns without opening external sites or touching
the dashboard database. The real embedded-tool access checks are covered by
test_snorkl_integration.py.
"""
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from config import DEFAULT_SETTINGS
from snorkl_navigation import ACTIVE_TOOL, LINK_SEEN, REQUESTED_COURSE
from ui import parse_links
from views import snorkl, tools


MENU = [
    ("tool_desmos", "1. 데스모스"),
    ("tool_activity", "2. 데스모스 액티비티"),
    ("snorkl", "3. 수행평가"),
    ("tool_quiz", "4. 퀴즈"),
    ("tool_apps", "5. 앱 (by Good쌤)"),
]
SETTINGS = {
    "tool_desmos": "그래프 계산기|https://www.desmos.com/calculator\n"
                   "공학용 계산기|https://www.desmos.com/scientific",
    "tool_activity": "액티비티 입장|https://student.desmos.com/",
    "tool_quiz": "수학 퀴즈|https://quiz.example.com/",
    "tool_apps": "함수 & 그래프|https://apps.example.com/graph?x=1&y=2\n"
                 "도형 앱|https://apps.example.com/shapes",
}
SENTINEL = "수행평가 연동 확인"


@pytest.fixture
def menu_app(monkeypatch):
    settings = dict(SETTINGS)
    writes, calls = [], []

    def save_setting(key, value):
        settings[key] = value
        writes.append((key, value))

    def embedded_page(user):
        # Mirror consumption of the course request, while avoiding the real
        # course store, account database and external providers.
        requested = st.session_state.pop(REQUESTED_COURSE, None)
        calls.append((dict(user), requested))
        st.markdown(SENTINEL)

    monkeypatch.setattr(tools.db, "get_setting", lambda key: settings.get(key, ""))
    monkeypatch.setattr(tools.db, "set_setting", save_setting)
    monkeypatch.setattr(snorkl, "page", embedded_page)

    def make(role="teacher", query=None, active=None):
        app = AppTest.from_string(
            "import streamlit as st\n"
            "from snorkl_navigation import sync_shared_link\n"
            "from views import tools\n"
            "sync_shared_link(st.session_state, st.query_params)\n"
            "tools.page(st.session_state['user'])\n"
        )
        app.session_state["user"] = {
            "id": "teacher" if role == "teacher" else "10101",
            "name": "시험계정", "class": "1-1", "role": role,
        }
        if query:
            app.query_params.update(query)
        if active is not None:
            app.session_state[ACTIVE_TOOL] = active
        app.run()
        assert not app.exception
        return app

    return SimpleNamespace(make=make, settings=settings, writes=writes, calls=calls)


def headings(app):
    return [element.value for element in app.markdown
            if element.value.startswith("#### ")]


def buttons(app):
    return [(element.proto.label, element.proto.url)
            for element in app.get("link_button")]


class TableLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.label = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.href is not None:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append(("".join(self.label), self.href))
            self.href = None


def table_links(app):
    parser = TableLinks()
    for element in app.markdown:
        parser.feed(element.value)
    return parser.links


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_menu_order_and_only_selected_content_is_rendered(menu_app, role):
    app = menu_app.make(role)
    assert app.radio[0].options == [label for _, label in MENU]
    assert app.radio[0].value == "tool_desmos"

    for key, label in MENU:
        app.radio[0].set_value(key).run()
        assert not app.exception
        assert headings(app) == [f"#### {label}"]
        assert app.radio[0].value == key
        assert (SENTINEL in [element.value for element in app.markdown]) == (key == "snorkl")
        if key == "snorkl":
            assert not buttons(app) and not table_links(app)
            assert not app.text_area
            assert menu_app.calls[-1][0] == dict(app.session_state["user"])
        elif key == "tool_apps":
            assert table_links(app) == parse_links(SETTINGS[key])
            assert not buttons(app)
        else:
            assert buttons(app) == parse_links(SETTINGS[key])
            assert not table_links(app)
        if key == "tool_desmos":
            assert [frame.proto.src for frame in app.get("iframe")] == [
                "https://www.desmos.com/calculator"
            ]
        else:
            assert not app.get("iframe")
        if role == "student":
            assert not app.text_area
            assert not any(button.label == "저장" for button in app.button)


@pytest.mark.parametrize("key", ["tool_desmos", "tool_activity", "tool_quiz", "tool_apps"])
def test_teacher_can_save_selected_links_and_return_to_saved_values(menu_app, key):
    app = menu_app.make()
    app.radio[0].set_value(key).run()
    assert len(app.text_area) == 1
    assert app.text_area[0].value == SETTINGS[key]
    updated = "새 수업 링크|https://lesson.example.com/updated"
    app.text_area[0].set_value(updated)
    app.button(key=f"save_{key}").click().run()
    assert not app.exception
    assert menu_app.writes == [(key, updated)]
    assert app.radio[0].value == key
    assert (table_links(app) if key == "tool_apps" else buttons(app)) == parse_links(updated)

    other = "tool_quiz" if key != "tool_quiz" else "tool_activity"
    app.radio[0].set_value(other).run()
    assert app.text_area[0].value == SETTINGS[other]
    app.radio[0].set_value(key).run()
    assert not app.exception
    assert app.text_area[0].value == updated
    assert (table_links(app) if key == "tool_apps" else buttons(app)) == parse_links(updated)


@pytest.mark.parametrize("role", ["teacher", "student"])
@pytest.mark.parametrize("query", [
    {"tool": "snorkl", "course_id": "c" * 32, "embed": "true"},
    {"course_id": "c" * 32, "embed": "true"},
    {"tool": "snorkl", "embed": "true"},
])
def test_shared_link_selects_assessment_and_user_selection_clears_link(menu_app, role, query):
    app = menu_app.make(role, query=query)
    assert app.radio[0].value == "snorkl"
    assert headings(app) == ["#### 3. 수행평가"]
    assert menu_app.calls == [(dict(app.session_state["user"]), query.get("course_id"))]
    assert LINK_SEEN in app.session_state
    assert REQUESTED_COURSE not in app.session_state

    app.radio[0].set_value("tool_quiz").run()
    assert not app.exception
    assert app.radio[0].value == "tool_quiz"
    assert headings(app) == ["#### 4. 퀴즈"]
    assert "tool" not in app.query_params and "course_id" not in app.query_params
    assert app.query_params["embed"] == query["embed"]
    assert LINK_SEEN not in app.session_state
    assert REQUESTED_COURSE not in app.session_state
    app.run()
    assert not app.exception
    assert app.radio[0].value == "tool_quiz"
    assert len(menu_app.calls) == 1


def test_empty_apps_setting_uses_default_links(menu_app):
    menu_app.settings["tool_apps"] = "  \n "
    app = menu_app.make("student", active="tool_apps")
    assert headings(app) == ["#### 5. 앱 (by Good쌤)"]
    assert table_links(app) == parse_links(DEFAULT_SETTINGS["tool_apps"])


def test_missing_links_show_preparation_message_and_stale_selection_recovers(menu_app):
    menu_app.settings["tool_desmos"] = ""
    app = menu_app.make("student", active="obsolete_tool")
    assert app.radio[0].value == "tool_desmos"
    assert headings(app) == ["#### 1. 데스모스"]
    assert "선생님이 링크를 준비 중이에요." in [element.value for element in app.caption]
    assert not buttons(app) and not app.get("iframe")
