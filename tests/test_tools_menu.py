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


def app_names(app):
    return [button.label for button in app.button
            if button.key and button.key.startswith("tool_app_open_")]


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
            assert not buttons(app) and not table_links(app) and not app_names(app)
            assert not app.text_area
            assert menu_app.calls[-1][0] == dict(app.session_state["user"])
        elif key == "tool_apps":
            assert app_names(app) == [name for name, _ in parse_links(SETTINGS[key])]
            assert not buttons(app) and not table_links(app)
        else:
            assert buttons(app) == parse_links(SETTINGS[key])
            assert not table_links(app) and not app_names(app)
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
    if key == "tool_apps":
        assert app_names(app) == [name for name, _ in parse_links(updated)]
        assert not table_links(app) and not buttons(app)
    else:
        assert buttons(app) == parse_links(updated)

    other = "tool_quiz" if key != "tool_quiz" else "tool_activity"
    app.radio[0].set_value(other).run()
    assert app.text_area[0].value == SETTINGS[other]
    app.radio[0].set_value(key).run()
    assert not app.exception
    assert app.text_area[0].value == updated
    if key == "tool_apps":
        assert app_names(app) == [name for name, _ in parse_links(updated)]
        assert not table_links(app) and not buttons(app)
    else:
        assert buttons(app) == parse_links(updated)


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
    assert app_names(app) == [name for name, _ in parse_links(DEFAULT_SETTINGS["tool_apps"])]
    gallery = "".join(element.value for element in app.markdown)
    for number in ("01", "02", "03", "04", "05", "06"):
        assert f'<span class="app-card-number">{number}</span>' in gallery
    assert not table_links(app) and not buttons(app)


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_open_app_embeds_inside_dashboard_and_return_keeps_session(menu_app, role):
    query = {"embed": "true", "lesson": "keep-me"}
    app = menu_app.make(role, query=query, active="tool_apps")
    user = dict(app.session_state["user"])
    app.session_state["dashboard_navigation"] = {"menu": "tools", "class": "1-1"}
    name, url = parse_links(SETTINGS["tool_apps"])[0]

    app.button(key="tool_app_open_1").click().run()
    assert not app.exception
    assert app.radio[0].value == "tool_apps"
    assert app.session_state[tools.ACTIVE_APP] == (name, url)
    assert dict(app.session_state["user"]) == user
    assert app.session_state["dashboard_navigation"] == {"menu": "tools", "class": "1-1"}
    assert dict(app.query_params) == query
    assert not app_names(app) and not buttons(app) and not table_links(app)
    assert app.button(key="tool_apps_back").label == "← 앱 목록으로 돌아가기"
    assert [frame.proto.src for frame in app.get("iframe")] == [url]

    app.run()
    assert not app.exception
    assert [frame.proto.src for frame in app.get("iframe")] == [url]
    assert dict(app.session_state["user"]) == user

    app.button(key="tool_apps_back").click().run()
    assert not app.exception
    assert app.radio[0].value == "tool_apps"
    assert app_names(app) == [name for name, _ in parse_links(SETTINGS["tool_apps"])]
    assert not app.get("iframe")
    assert tools.ACTIVE_APP not in app.session_state
    assert dict(app.session_state["user"]) == user
    assert app.session_state["dashboard_navigation"] == {"menu": "tools", "class": "1-1"}
    assert dict(app.query_params) == query


def test_selected_app_survives_other_tool_menu_selection(menu_app):
    app = menu_app.make("student", active="tool_apps")
    app.button(key="tool_app_open_2").click().run()
    selected = parse_links(SETTINGS["tool_apps"])[1]

    app.radio[0].set_value("tool_quiz").run()
    assert not app.exception
    assert buttons(app) == parse_links(SETTINGS["tool_quiz"])
    assert not app.get("iframe")
    assert app.session_state[tools.ACTIVE_APP] == selected

    app.radio[0].set_value("tool_apps").run()
    assert not app.exception
    assert [frame.proto.src for frame in app.get("iframe")] == [selected[1]]
    assert app.button(key="tool_apps_back").label == "← 앱 목록으로 돌아가기"


@pytest.mark.parametrize("index", range(1, 11))
def test_each_default_app_opens_its_exact_url_inside_dashboard(menu_app, index):
    menu_app.settings["tool_apps"] = ""
    links = parse_links(DEFAULT_SETTINGS["tool_apps"])
    assert len(links) == 10
    assert links[6] == ("점과 도형의 평행이동", "https://jsku-sm.github.io/Moving/")
    app = menu_app.make("student", active="tool_apps")
    name, url = links[index - 1]

    app.button(key=f"tool_app_open_{index}").click().run()
    assert not app.exception
    assert app.session_state[tools.ACTIVE_APP] == (name, url)
    assert [frame.proto.src for frame in app.get("iframe")] == [url]
    assert not buttons(app) and not table_links(app)
    app.button(key="tool_apps_back").click().run()
    assert not app.exception
    assert app_names(app) == [name for name, _ in links]


def test_editing_apps_links_recovers_from_a_removed_selection(menu_app):
    app = menu_app.make(active="tool_apps")
    app.button(key="tool_app_open_1").click().run()
    updated = "새 수업 앱|https://lesson.example.com/updated"

    app.text_area[0].set_value(updated)
    app.button(key="save_tool_apps").click().run()
    assert not app.exception
    assert menu_app.writes == [("tool_apps", updated)]
    assert app_names(app) == ["새 수업 앱"]
    assert not app.get("iframe")

    app.button(key="tool_app_open_1").click().run()
    assert not app.exception
    assert [frame.proto.src for frame in app.get("iframe")] == [
        "https://lesson.example.com/updated"
    ]


@pytest.mark.parametrize("selected", [
    ("삭제된 앱", "https://apps.example.com/removed"),
    ("함수 & 그래프", "https://apps.example.com/outdated"),
    "https://apps.example.com/graph?x=1&y=2",
    None,
])
def test_invalid_saved_app_selection_shows_the_app_list(menu_app, selected):
    app = menu_app.make("student", active="tool_apps")
    app.session_state[tools.ACTIVE_APP] = selected
    app.run()
    assert not app.exception
    assert app_names(app) == [name for name, _ in parse_links(SETTINGS["tool_apps"])]
    assert not app.get("iframe")


def test_app_names_with_html_characters_stay_in_native_widgets(menu_app):
    name = '함수 & <img src=x onerror="alert(1)">'
    url = "https://apps.example.com/special?x=1&y=2"
    menu_app.settings["tool_apps"] = f"{name}|{url}"
    app = menu_app.make("student", active="tool_apps")
    assert app_names(app) == [name]
    assert not table_links(app)

    app.button(key="tool_app_open_1").click().run()
    assert not app.exception
    assert [frame.proto.src for frame in app.get("iframe")] == [url]
    assert not table_links(app)
    assert not any(element.proto.allow_html and name in element.value
                   for element in app.markdown)


def test_missing_links_show_preparation_message_and_stale_selection_recovers(menu_app):
    menu_app.settings["tool_desmos"] = ""
    app = menu_app.make("student", active="obsolete_tool")
    assert app.radio[0].value == "tool_desmos"
    assert headings(app) == ["#### 1. 데스모스"]
    assert "선생님이 링크를 준비 중이에요." in [element.value for element in app.caption]
    assert not buttons(app) and not app.get("iframe")
