"""Existing saved app lists receive the update and remain teacher-editable."""
import threading

import pytest
from streamlit.testing.v1 import AppTest

import storage as db
from snorkl_navigation import ACTIVE_TOOL
from ui import parse_links


REQUESTED_APPS = [
    ("라텍스 수식변환기", "https://latexhangultool.streamlit.app/"),
    ("점과 도형의 평행이동", "https://jsku-sm.github.io/Moving/"),
    ("대칭을 이용한 최단거리 찾기 시뮬레이션", "https://jsku-sm.github.io/shortcut/"),
    ("몬티홀 딜레마 탐구", "https://js-math900.my.canva.site/"),
    ("별똥별 잡기 게임", "https://catchikjs.github.io/starcatchinggame/"),
]
LEGACY_APPS = (
    "픽토그램|https://jsku-sm.github.io/pictogram/\n"
    "집합 개념 퀴즈|https://jsku-sm.github.io/math_setQuiz/\n"
    "좌표평면|https://js-math.streamlit.app/?embed=true\n"
    "집합의 연산 · 벤다이어그램|https://jsku-sm.github.io/math_quiz/\n"
    "직선의 방정식 · 퀴즈|https://jsku-sm.github.io/line_mathQuiz/\n"
    "점과 도형의 이동|https://jsku-sm.github.io/Moving/"
)


@pytest.fixture
def catalog_store(tmp_path, monkeypatch):
    backend = db.LocalBackend(str(tmp_path))
    cache = {"data": {}, "lock": threading.Lock()}
    monkeypatch.setattr(db, "get_backend", lambda: backend)
    monkeypatch.setattr(db, "_cache", lambda: cache)
    return backend, tmp_path


def apps_page(role):
    app = AppTest.from_string(
        "import streamlit as st\nfrom views import tools\ntools.page(st.session_state['user'])\n")
    app.session_state["user"] = dict(id="teacher" if role == "teacher" else "10101", role=role,
                                      name="시험계정", **{"class": "1-1"})
    app.session_state[ACTIVE_TOOL] = "tool_apps"
    return app.run()


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_saved_apps_are_upgraded_without_duplicates_and_only_names_appear_in_the_gallery(catalog_store, role):
    backend, path = catalog_store
    custom = "우리 반 탐구|https://teacher.example.com/lesson"
    db.set_setting("tool_apps", LEGACY_APPS + "\n" + custom +
                   "\n이동 중복|https://jsku-sm.github.io/Moving")
    app = apps_page(role)
    assert not app.exception and not app.error
    links = parse_links(db.get_setting("tool_apps"))
    assert len(links) == 11
    assert links[:5] == parse_links(LEGACY_APPS)[:5]
    assert parse_links(custom)[0] in links
    for pair in REQUESTED_APPS:
        assert links.count(pair) == 1
    assert sum(url.rstrip("/") == "https://jsku-sm.github.io/Moving" for _, url in links) == 1
    names = [button.label for button in app.button if button.key.startswith("tool_app_open_")]
    assert names == [name for name, _ in links]
    displayed = "\n".join([element.value for element in app.markdown] +
                            [element.value for element in app.caption] + names)
    assert all(name in displayed for name, _ in REQUESTED_APPS)
    assert "https://" not in displayed and "http://" not in displayed
    for pair in REQUESTED_APPS:
        index = links.index(pair) + 1
        app.button(key=f"tool_app_open_{index}").click().run()
        assert not app.exception and not app.error
        assert [frame.proto.src for frame in app.get("iframe")] == [pair[1]]
        app.button(key="tool_apps_back").click().run()
    # Both the new catalog and its one-time update marker survive a restart.
    restored = {row["id"]: row["value"] for row in db.LocalBackend(str(path)).read("settings")}
    assert restored["tool_apps"] == db.get_setting("tool_apps")
    assert backend.read("settings") == db.LocalBackend(str(path)).read("settings")


def test_teacher_can_remove_or_edit_apps_after_the_one_time_upgrade_and_after_restart(catalog_store, monkeypatch):
    backend, path = catalog_store
    db.set_setting("tool_apps", LEGACY_APPS)
    db.get_setting("tool_apps")
    updated = "선생님이 고친 목록|https://teacher.example.com/updated"
    db.set_setting("tool_apps", updated)
    monkeypatch.setattr(db, "get_backend", lambda: db.LocalBackend(str(path)))
    assert db.get_setting("tool_apps") == updated
    assert backend.read("settings") == db.LocalBackend(str(path)).read("settings")


def test_simultaneous_first_reads_add_each_app_and_marker_only_once(catalog_store):
    from concurrent.futures import ThreadPoolExecutor

    backend, _ = catalog_store
    db.set_setting("tool_apps", LEGACY_APPS)
    with ThreadPoolExecutor(max_workers=4) as pool:
        lists = list(pool.map(lambda _: db.get_setting("tool_apps"), range(8)))
    assert all(value == lists[0] for value in lists)
    assert len(parse_links(lists[0])) == 10
    rows = backend.read("settings")
    assert len(rows) == 2 and len({row["id"] for row in rows}) == 2

