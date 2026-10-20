"""Local storage + simulated Streamlit control-flow tests (not a browser UI test).

A fixture-local test double substitutes Streamlit only for these tests; it is
not packaged as runtime streamlit.py and never contacts an external repository.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import html
import importlib.util
from pathlib import Path
import sys
import threading
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Rerun(Exception):
    pass


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__('streamlit')
        self.session_state = {}
        self.events = set()
        self.rendered = []

    def cache_resource(self, *args, **kwargs):
        return lambda fn: fn

    cache_data = cache_resource

    def container(self, **kw): return nullcontext()
    def expander(self, *args, **kw): return nullcontext()
    def spinner(self, *args, **kw): return nullcontext()
    def form(self, *args, **kw): return nullcontext()
    def columns(self, widths): return [nullcontext() for _ in widths]

    def _display(self, kind, body): self.rendered.append((kind, body))
    def markdown(self, body, **kw): self._display('markdown', body)
    def caption(self, body, **kw): self._display('caption', body)
    def html(self, body, **kw): self._display('html', body)
    def warning(self, body, **kw): self._display('warning', body)
    def info(self, body, **kw): self._display('info', body)
    def error(self, body, **kw): self._display('error', body)
    def success(self, body, **kw): self._display('success', body)

    def button(self, label, *, key=None, disabled=False, **kwargs):
        self.rendered.append(('button', label, key, disabled))
        hit = key in self.events
        self.events.discard(key)
        return hit and not disabled

    form_submit_button = button

    def text_input(self, label, *, value='', key=None, **kwargs):
        self.rendered.append(('input', label, key))
        self.session_state.setdefault(key, value)
        return self.session_state[key]

    text_area = text_input

    def checkbox(self, label, *, key, **kwargs):
        self.rendered.append(('checkbox', label, key))
        return self.session_state.get(key, False)

    def rerun(self): raise Rerun()


def load_module(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(monkeypatch, tmp_path):
    st = FakeStreamlit()
    monkeypatch.setitem(sys.modules, 'streamlit', st)
    db = load_module('storage', ROOT / 'storage.py', monkeypatch)
    backend = db.LocalBackend(str(tmp_path / 'data'))
    monkeypatch.setattr(db, 'get_backend', lambda: backend)
    cache = {'data': {}, 'lock': threading.Lock()}
    monkeypatch.setattr(db, '_cache', lambda: cache)
    service = load_module('evaluation_plan_service', ROOT / 'evaluation_plan_service.py', monkeypatch)
    teacher = {'id': 'teacher_test', 'role': 'teacher', 'must_change': '0', 'name': '시험교사'}
    student = {'id': 'student_test', 'role': 'student', 'must_change': '0', 'name': '가상학생'}
    backend.append('users', teacher)
    backend.append('users', student)
    st.session_state['user'] = dict(teacher)
    plan = db._norm({'id': 'plan-test', 'subject': '공통수학2', 'category': '평가계획',
                    'title': '원래 평가계획', 'description': '성적 반영 비율 지필평가 40% 수행평가 60%',
                    'uploaded_at': '2026-10-02 09:00:00', 'file_id': 'test-file',
                    'file_name': '첨부.pdf', 'file_url': '', 'mime': 'application/pdf'}, 'materials')
    backend.append('materials', plan)
    ui = types.ModuleType('ui')
    ui.esc = lambda value: html.escape(str(value), quote=True)
    ui.file_widget = lambda row, key: st.rendered.append(('file', row['file_id'], key))
    monkeypatch.setitem(sys.modules, 'ui', ui)
    view = load_module('views.evaluation_plans', ROOT / 'views/evaluation_plans.py', monkeypatch)
    return types.SimpleNamespace(st=st, db=db, backend=backend, svc=service, view=view,
                                 teacher=teacher, student=student, plan=plan)


def edit(env, **kwargs):
    return env.svc.update_plan_text(env.teacher, env.plan['id'], kwargs.get('title', '수정 평가계획'),
        kwargs.get('description', '수정한 원문\n두 번째 줄'), kwargs.get('revision', env.svc.revision_of(env.plan)))


def latest(env):
    return next(r for r in env.backend.read('materials') if r['id'] == env.plan['id'])


def test_edit_text_persist_and_preserve_every_other_field(env):
    saved = edit(env)
    assert saved['title'] == '수정 평가계획' and saved['description'] == '수정한 원문\n두 번째 줄'
    for key, value in env.plan.items():
        if key not in ['title', 'description']: assert saved[key] == value
    reopened = env.db.LocalBackend(env.backend.root)
    assert reopened.read('materials')[0] == saved


def test_blank_description_allowed_and_original_date_unchanged(env):
    saved = edit(env, description='')
    assert saved['description'] == ''
    assert saved['uploaded_at'] == env.plan['uploaded_at']


@pytest.mark.parametrize('field,value', [('title', ''), ('title', '  '), ('title', 'a' * 201),
                                        ('description', 'x' * 30001), ('description', None)], ids=['empty_title','space_title','long_title','long_description','not_string'])
def test_invalid_inputs_do_not_write(env, field, value):
    with pytest.raises(ValueError): edit(env, **{field: value})
    assert latest(env) == env.plan


@pytest.mark.parametrize('scenario', ['student', 'forged_role', 'no_session', 'other_id', 'revoked', 'must_change'])
def test_mutations_recheck_teacher_identity(env, scenario):
    user = env.teacher
    if scenario in ['student', 'forged_role']:
        env.st.session_state['user'] = dict(env.student)
        user = dict(env.student, role='teacher') if scenario == 'forged_role' else env.student
    elif scenario == 'no_session': env.st.session_state.clear()
    elif scenario == 'other_id': env.st.session_state['user'] = dict(env.teacher, id='unrelated')
    elif scenario == 'revoked': env.backend.update('users', env.teacher['id'], {'role': 'student'})
    elif scenario == 'must_change': env.backend.update('users', env.teacher['id'], {'must_change': '1'})
    with pytest.raises(PermissionError):
        env.svc.update_plan_text(user, env.plan['id'], '수정', '내용', env.svc.revision_of(env.plan))
    assert latest(env) == env.plan


@pytest.mark.parametrize('field,value', [('subject', '공통수학1'), ('category', '학습지')])
def test_other_subject_and_material_category_are_not_editable(env, field, value):
    env.backend.update('materials', env.plan['id'], {field: value})
    with pytest.raises(PermissionError): edit(env)


def test_stale_form_does_not_overwrite_newer_edit(env):
    env.backend.update('materials', env.plan['id'], {'description': '다른 창에서 수정'})
    with pytest.raises(env.svc.PlanConflictError): edit(env)
    assert latest(env)['description'] == '다른 창에서 수정'


def test_stale_attachment_is_also_conflict(env):
    env.backend.update('materials', env.plan['id'], {'file_id': 'replacement'})
    with pytest.raises(env.svc.PlanConflictError): edit(env)


def test_deleted_plan_is_not_recreated(env):
    env.backend.delete('materials', env.plan['id'])
    with pytest.raises(env.svc.PlanConflictError): edit(env)
    assert not env.backend.read('materials')


def test_pending_github_flush_is_not_reported_as_success(env, monkeypatch):
    def fail(): raise RuntimeError('secret-value-must-not-leak')
    monkeypatch.setattr(env.db, 'flush_now', fail)
    with pytest.raises(env.svc.PlanSavePendingError) as result: edit(env)
    assert result.value.revision == env.svc.revision_of(latest(env))
    assert 'secret-value' not in str(result.value)
    monkeypatch.setattr(env.db, 'flush_now', lambda: None)
    assert edit(env, revision=result.value.revision)['title'] == '수정 평가계획'


def test_cache_invalidated_after_text_save(env):
    assert env.db.read('materials')[0]['title'] == '원래 평가계획'
    edit(env)
    assert env.db.read('materials')[0]['title'] == '수정 평가계획'


def test_flush_runs_after_releasing_backend_lock(env, monkeypatch):
    observed = []
    monkeypatch.setattr(env.db, 'flush_now', lambda: observed.append(env.backend.lock._is_owned()))
    edit(env)
    assert observed == [False]


def test_teacher_only_edit_button_and_student_read_only(env):
    env.view.render_evaluation_plan_card(env.teacher, env.plan)
    assert any(r[:2] == ('button', '✏️ 수정') for r in env.st.rendered)
    env.st.rendered.clear()
    env.st.session_state['user'] = env.student
    env.view.render_evaluation_plan_card(env.student, env.plan)
    assert not any(r[0] in ['button', 'input', 'checkbox'] for r in env.st.rendered)
    assert any(r[0] == 'html' and 'ep-composition' in r[1] for r in env.st.rendered)
    assert any(r[0] == 'file' for r in env.st.rendered)


def start_editor(env):
    env.st.events.add('eval_plan_edit_' + env.plan['id'])
    with pytest.raises(Rerun): env.view.render_evaluation_plan_card(env.teacher, env.plan)
    state = env.st.session_state[env.view._slot(env.plan['id'], env.teacher['id'])]
    env.view.render_evaluation_plan_card(env.teacher, latest(env))
    return state


def test_form_prefilled_and_save_persists(env):
    state = start_editor(env)
    prefix = state['token']
    assert env.st.session_state[prefix + '_title'] == env.plan['title']
    assert env.st.session_state[prefix + '_description'] == env.plan['description']
    env.st.session_state[prefix + '_title'] = '새 제목'
    env.st.session_state[prefix + '_description'] = '지필평가 50% 수행평가 50%'
    env.st.events.add(prefix + '_save')
    with pytest.raises(Rerun): env.view.render_evaluation_plan_card(env.teacher, latest(env))
    assert latest(env)['title'] == '새 제목'
    assert env.view._slot(env.plan['id'], env.teacher['id']) not in env.st.session_state


def test_preview_does_not_save(env):
    state = start_editor(env)
    env.st.session_state[state['token'] + '_description'] = '지필평가 50% 수행평가 50%'
    env.st.events.add(state['token'] + '_preview')
    env.view.render_evaluation_plan_card(env.teacher, latest(env))
    assert latest(env) == env.plan
    assert state['preview']['description'] == '지필평가 50% 수행평가 50%'


def test_cancel_keeps_original_and_reopen_loads_latest(env):
    state = start_editor(env)
    env.st.session_state[state['token'] + '_description'] = '저장하지 않은 내용'
    env.st.events.add(state['token'] + '_cancel')
    with pytest.raises(Rerun): env.view.render_evaluation_plan_card(env.teacher, latest(env))
    assert latest(env) == env.plan
    next_state = start_editor(env)
    assert next_state['token'] != state['token']
    assert next_state['description'] == env.plan['description']


def test_save_failure_keeps_typed_text_and_expected_revision(env, monkeypatch):
    state = start_editor(env)
    env.st.session_state[state['token'] + '_description'] = '변경 내용'
    env.st.events.add(state['token'] + '_save')
    monkeypatch.setattr(env.db, 'flush_now', lambda: (_ for _ in ()).throw(RuntimeError('no network')))
    env.view.render_evaluation_plan_card(env.teacher, latest(env))
    assert env.st.session_state[state['token'] + '_description'] == '변경 내용'
    assert state['pending']
    assert state['revision'] == env.svc.revision_of(latest(env))
    assert not any(r[0] == 'success' for r in env.st.rendered)


def test_student_cannot_reuse_teacher_editor_state(env):
    state = start_editor(env)
    env.st.session_state['user'] = env.student
    env.st.events.add(state['token'] + '_save')
    env.st.rendered.clear()
    env.view.render_evaluation_plan_card(env.student, latest(env))
    assert not any(r[0] == 'input' for r in env.st.rendered)
    assert latest(env) == env.plan


def test_delete_requires_permission_and_keeps_shared_attachment(env, monkeypatch):
    env.backend.append('materials', dict(env.plan, id='other'))
    deleted = []
    monkeypatch.setattr(env.backend, 'delete_file', lambda fid: deleted.append(fid))
    env.svc.delete_plan(env.teacher, env.plan['id'], env.svc.revision_of(env.plan))
    assert deleted == []
    assert len(env.backend.read('materials')) == 1


def test_only_math2_evaluation_cards_route_to_new_view():
    import ast
    tree = ast.parse((ROOT / 'views/math_class.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_material_card')
    assert isinstance(node.body[0], ast.If)
    condition = ast.unparse(node.body[0].test)
    assert "'공통수학2'" in condition and "'평가계획'" in condition
