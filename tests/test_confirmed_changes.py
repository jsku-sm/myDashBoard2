from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
from confirmed_changes import PENDING, begin_change, finish_change


def test_failed_commit_never_acknowledges_or_repeats_mutation():
    state, mutations, commits = {}, [], []
    def fail():
        commits.append('failed'); raise RuntimeError('offline')
    api = SimpleNamespace(flush_now=fail)
    def change(): mutations.append('changed'); return (2, 1, 0)
    with pytest.raises(RuntimeError):
        begin_change(api, state, 'teacher', '학생 등록', change)
    assert len(mutations) == 1 and state[PENDING]['result'] == (2, 1, 0)
    with pytest.raises(ValueError):
        begin_change(api, state, 'teacher', '다른 등록', change)
    with pytest.raises(ValueError):
        finish_change(api, state, 'different-teacher')
    api.flush_now = lambda: commits.append('saved')
    assert finish_change(api, state, 'teacher') == (2, 1, 0)
    assert mutations == ['changed'] and commits == ['failed', 'saved'] and PENDING not in state


def test_mutation_validation_failure_has_no_receipt_or_false_success():
    state = {}
    def invalid(): raise ValueError('invalid input')
    with pytest.raises(ValueError):
        begin_change(SimpleNamespace(flush_now=lambda: pytest.fail('must not save')), state, 'teacher', '등록', invalid)
    assert not state


def test_password_ui_failure_retry_does_not_repeat_password_change(monkeypatch):
    import auth
    import storage as db
    from views import account
    import streamlit as st
    monkeypatch.setattr(account, 'st', st)
    changed, saved = [], []
    monkeypatch.setattr(auth, 'change_password', lambda uid, password: changed.append(uid))
    def flush():
        saved.append('try')
        if len(saved) == 1: raise RuntimeError('network error with PRIVATE-TOKEN')
    monkeypatch.setattr(db, 'flush_now', flush)
    app = AppTest.from_string('''
import streamlit as st
from views.account import force_change
from confirmed_changes import pending_controls
st.session_state['user']={'id':'10101','role':'student'}
if pending_controls(): st.stop()
if st.session_state.pop('_critical_change_saved', None):
    st.success('저장 확인 완료'); st.stop()
force_change(st.session_state['user'])
''', default_timeout=20).run()
    app.text_input[0].set_value('new-test-password')
    app.text_input[1].set_value('new-test-password')
    app.button[0].click().run()
    assert not app.exception and not app.success and app.warning
    assert changed == ['10101'] and len(saved) == 1
    assert 'PRIVATE-TOKEN' not in str(app.error)
    assert 'password' not in str(app.session_state[PENDING])
    next(b for b in app.button if b.label == '저장 확인 다시 시도').click().run()
    assert not app.exception and app.success
    assert changed == ['10101'] and len(saved) == 2
