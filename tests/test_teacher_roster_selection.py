"""Streamlit row-selection events and management actions use one student ID."""
import json
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def roster_ui(monkeypatch):
    import streamlit
    from views import teacher
    students = [
        dict(id='10101', name='같은이름', **{'class': '1-1'}, must_change='0'),
        dict(id='10102', name='같은이름', **{'class': '1-1'}, must_change='1'),
        dict(id='10201', name='다른학생', **{'class': '1-2'}, must_change='0'),
    ]
    resets, deleted = [], []
    monkeypatch.setattr(teacher, 'st', streamlit)
    monkeypatch.setattr(teacher.auth, 'students', lambda cls: [u.copy() for u in students if cls == '전체' or u['class'] == cls])
    monkeypatch.setattr(teacher.auth, 'reset_password', resets.append)
    def delete(table, sid):
        assert table == 'users'
        deleted.append(sid)
        students[:] = [u for u in students if u['id'] != sid]
    monkeypatch.setattr(teacher.db, 'delete', delete)
    app = AppTest.from_string('from views.teacher import tab_roster\ntab_roster()', default_timeout=20)
    app.run()
    assert not app.exception
    return SimpleNamespace(app=app, students=students, resets=resets, deleted=deleted)


def button(app, label):
    return next(b for b in app.button if b.label == label)


def click_row(app, index):
    # Send the same protocol event as a browser row click, exercising the
    # registered callback before the selectbox is instantiated on the rerun.
    states = app._tree.get_widget_states()
    event = states.widgets.add()
    event.id = app.dataframe[0].proto.id
    event.string_value = json.dumps({'selection': {'rows': [index], 'columns': [], 'cells': []}})
    app._run(widget_state=states)
    assert not app.exception


def assert_selected(app, sid):
    assert app.selectbox(key='ro_stu').value == sid
    frame = app.dataframe[0].value
    assert frame.loc[frame['선택'] == '✓', '학번'].tolist() == [sid]


def test_click_row_updates_dropdown_and_password_target_with_duplicate_names(roster_ui):
    u = roster_ui
    assert_selected(u.app, '10101')
    click_row(u.app, 1)
    assert_selected(u.app, '10102')
    button(u.app, '🔑 비밀번호 초기화 (학번으로)').click().run()
    assert not u.app.exception and u.resets == ['10102']
    assert_selected(u.app, '10102')


def test_dropdown_updates_list_then_next_row_click_wins(roster_ui):
    a = roster_ui.app
    click_row(a, 1)
    a.selectbox(key='ro_stu').select('10201').run()
    assert_selected(a, '10201')
    click_row(a, 0)
    assert_selected(a, '10101')


def test_class_filter_keeps_valid_student_and_clears_invalid_or_empty_selection(roster_ui):
    a = roster_ui.app
    click_row(a, 1)
    a.selectbox(key='ro_cls').select('1-1').run()
    assert_selected(a, '10102')
    a.selectbox(key='ro_cls').select('1-2').run()
    assert_selected(a, '10201')
    a.selectbox(key='ro_cls').select('1-3').run()
    assert not a.exception and not a.dataframe
    assert not any(s.key == 'ro_stu' for s in a.selectbox)
    assert not any('학생 삭제' in b.label for b in a.button)
    a.selectbox(key='ro_cls').select('전체').run()
    assert_selected(a, '10101')


@pytest.mark.parametrize('change', ['row', 'dropdown', 'class'])
def test_changing_student_cancels_pending_delete(roster_ui, change):
    a = roster_ui.app
    button(a, '🗑️ 학생 삭제').click().run()
    assert any(b.label == '네, 지울게요' for b in a.button)
    if change == 'row':
        click_row(a, 1)
    elif change == 'dropdown':
        a.selectbox(key='ro_stu').select('10102').run()
    else:
        a.selectbox(key='ro_cls').select('1-2').run()
    assert not any(b.label == '네, 지울게요' for b in a.button)
    assert not roster_ui.deleted
    a.selectbox(key='ro_cls').select('전체').run()
    a.selectbox(key='ro_stu').select('10101').run()
    assert not any(b.label == '네, 지울게요' for b in a.button)


def test_delete_clicked_student_and_choose_surviving_student(roster_ui):
    u = roster_ui
    click_row(u.app, 1)
    button(u.app, '🗑️ 학생 삭제').click().run()
    button(u.app, '네, 지울게요').click().run()
    assert not u.app.exception and u.deleted == ['10102']
    assert_selected(u.app, '10101')
    assert '10102' not in u.app.dataframe[0].value['학번'].tolist()


def test_roster_reordering_and_renaming_preserve_identity(roster_ui):
    u = roster_ui
    click_row(u.app, 1)
    u.students[1]['name'] = '수정이름'
    u.students.reverse()
    u.app.run()
    assert not u.app.exception
    assert_selected(u.app, '10102')
    assert '10102 수정이름' in u.app.selectbox(key='ro_stu').options
    click_row(u.app, 0)
    assert_selected(u.app, '10201')


def test_legacy_dictionary_selection_upgrades_to_student_id(roster_ui):
    u = roster_ui
    app = AppTest.from_string('from views.teacher import tab_roster\ntab_roster()', default_timeout=20)
    app.session_state['ro_stu'] = u.students[1].copy()
    app.run()
    assert not app.exception
    assert_selected(app, '10102')
