"""Cohort-selection regression and per-cohort enrollment scenarios (fake accounts)."""
from copy import deepcopy
import json
import pytest
from test_afterschool import env, Rerun, Upload


def manage(env, cid, menu='참여 학생'):
    env.actor(env.t)
    env.st.session_state['as_manage_cohort'] = cid
    env.st.session_state['as_manage_menu'] = menu
    env.view.teacher_page(env.t)


def selected_ids(env, cid):
    env.actor(env.t)
    return {r['id'] for r in env.svc.roster(env.t, cid) if r['selected']}


def create_via_form(env, name='5기'):
    op = env.st.session_state['_as_op_create_cohort']
    prefix = 'as_new_' + op
    env.st.session_state[prefix + 'name'] = name
    env.st.session_state[prefix + 'subject'] = '공통수학2'
    env.st.events.add(prefix + ':기수 추가')
    with pytest.raises(Rerun):
        env.view.teacher_page(env.t)
    return next(r['id'] for r in env.svc.list_cohorts(env.t) if r['name'] == name)


def test_new_fifth_cohort_is_selected_for_enrollment_not_previous_first(env):
    first = env.cohort('1기', env.s[:2])
    manage(env, first, '기수 설정')
    fifth = create_via_form(env)
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth
    assert env.st.session_state['as_manage_menu'] == '참여 학생'
    assert selected_ids(env, first) == {r['id'] for r in env.s[:2]}
    assert selected_ids(env, fifth) == set()


def test_selection_survives_hidden_widget_cleanup(env):
    env.cohort('1기', env.s[:2])
    fifth = env.cohort('5기', env.s[2:16])
    manage(env, fifth)
    # Simulate leaving the screen: Streamlit deletes unrendered widget keys.
    env.st.session_state.pop('as_manage_cohort', None)
    env.st.session_state.pop('as_manage_menu', None)
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth
    assert env.st.session_state['as_manage_menu'] == '참여 학생'


def test_14_students_are_in_fifth_only_and_only_they_can_open_material(env):
    first = env.cohort('1기', env.s[14:20])
    manage(env, first)
    fifth = create_via_form(env)
    env.view.teacher_page(env.t)
    c = env.svc.get_cohort(env.t, fifth)
    key = 'as_bulk_ids_' + fifth + '_' + c['revision'] + '_전체'
    env.st.session_state[key] = [u['id'] for u in env.s[:14]]
    env.st.events.add('as_bulk_add_' + fifth)
    with pytest.raises(Rerun):
        env.view.teacher_page(env.t)
    env.st.outputs = []
    env.view.teacher_page(env.t)
    assert selected_ids(env, fifth) == {u['id'] for u in env.s[:14]}
    assert selected_ids(env, first) == {u['id'] for u in env.s[14:20]}
    html = '\n'.join(str(o[1]) for o in env.st.outputs if o[0] == 'markdown')
    assert '5기 · 현재 배정 명단' in html and '총 14명' in html
    assert '이 기수 배정 14명' in html
    table = next(o[1] for o in env.st.outputs if o[0] == 'dataframe')
    assert dict(zip(table['기수'], table['배정 인원'])) == {'1기': '6명', '5기': '14명'}
    # Create from the teacher's actual material UI, not a detached post fixture.
    env.st.session_state['as_manage_menu'] = '자료·과제'
    env.view.teacher_page(env.t)
    token = env.st.session_state['_as_op_newpost_' + fifth + 'material']
    prefix = 'as_post_' + token
    env.st.session_state[prefix + 'title'] = '5기 전용 수업자료'
    env.st.session_state[prefix + 'body'] = '가상 학습 내용'
    env.st.session_state[prefix + 'files'] = [Upload()]
    env.st.events.add(prefix + ':등록하고 학생에게 공개')
    with pytest.raises(Rerun):
        env.view.teacher_page(env.t)
    posts = env.b.read('as_posts')
    assert len(posts) == 1 and posts[0]['cohort_id'] == fifth
    pid = posts[0]['id']
    for student in env.s[:14]:
        env.actor(student)
        assert {c['id'] for c in env.svc.list_cohorts(student, '공통수학2')} == {fifth}
        assert env.svc.get_post(student, pid)['title'] == '5기 전용 수업자료'
        assert env.svc.download_attachment(student, 'post', pid, 0)[0] == Upload().getvalue()
    for student in env.s[14:]:
        env.actor(student)
        with pytest.raises(PermissionError):
            env.svc.get_post(student, pid)
        with pytest.raises(PermissionError):
            env.svc.download_attachment(student, 'post', pid, 0)


def test_all_management_tabs_preserve_same_cohort_id(env):
    env.cohort('1기', env.s[:2])
    fifth = env.cohort('5기', env.s[2:16])
    manage(env, fifth)
    before = deepcopy(env.b.read('as_cohorts'))
    for menu in ('기수 설정', '참여 학생', '자료·과제', '질문·댓글', '제출 확인', '참여 학생'):
        env.st.session_state['as_manage_menu'] = menu
        env.st.outputs = []
        env.view.teacher_page(env.t)
        assert env.st.session_state['as_manage_cohort'] == fifth
        assert not [o for o in env.st.outputs if o[0] == 'error']
        assert any('5기' in str(o[1]) and '현재 관리 중인 기수' in str(o[1])
                   for o in env.st.outputs if o[0] == 'markdown')
    assert env.b.read('as_cohorts') == before


def test_overview_button_opens_exact_cohort_and_enrollment_menu(env):
    first = env.cohort('1기', env.s[:2])
    fifth = env.cohort('5기', env.s[2:16])
    manage(env, first, '기수 설정')
    env.st.events.add('as_open_members_' + fifth)
    with pytest.raises(Rerun):
        env.view.teacher_page(env.t)
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth
    assert env.st.session_state['as_manage_menu'] == '참여 학생'
    assert len(selected_ids(env, fifth)) == 14


def test_same_name_in_other_year_or_subject_is_never_same_roster(env):
    fifth = env.cohort('5기', env.s[:14])
    second = env.svc.create_cohort(env.t, {'year': 2026, 'subject':'공통수학1', 'name':'5기'}, 'different-subject')
    third = env.svc.create_cohort(env.t, {'year': 2027, 'subject':'공통수학2', 'name':'5기'}, 'different-year')
    env.svc.add_member(env.t, second, env.s[-1]['id'], '1')
    env.svc.add_member(env.t, third, env.s[-2]['id'], '1')
    assert len({fifth, second, third}) == 3
    assert len(selected_ids(env, fifth)) == 14
    assert selected_ids(env, second) == {env.s[-1]['id']}
    assert selected_ids(env, third) == {env.s[-2]['id']}


def test_one_student_in_two_cohorts_removal_changes_only_one(env):
    first = env.cohort('1기', env.s[:2])
    fifth = env.cohort('5기', env.s[:14])
    aid = env.post(fifth, 'assignment')
    env.actor(env.s[0])
    rid = env.svc.submit(env.s[0], aid, '보존할 답안', [], 'retain-submission')
    manage(env, fifth)
    env.st.events.add('as_remove_' + fifth + '_' + env.s[0]['id'])
    with pytest.raises(Rerun): env.view.teacher_page(env.t)
    env.st.outputs = []
    env.view.teacher_page(env.t)
    assert any('5기에서' in str(o[1]) for o in env.st.outputs if o[0]=='warning')
    env.st.events.add('as_remove_confirm_' + fifth)
    with pytest.raises(Rerun): env.view.teacher_page(env.t)
    assert len(selected_ids(env, fifth)) == 13
    assert selected_ids(env, first) == {u['id'] for u in env.s[:2]}
    assert env.svc.submissions(env.t, aid)[0]['id'] == rid
    env.actor(env.s[0])
    assert {c['id'] for c in env.svc.list_cohorts(env.s[0])} == {first}
    with pytest.raises(PermissionError): env.svc.get_post(env.s[0], aid)


def test_quick_add_after_hidden_selector_cleanup_still_targets_fifth(env):
    first = env.cohort('1기', env.s[:2])
    fifth = env.cohort('5기', [])
    manage(env, fifth)
    env.st.session_state.pop('as_manage_cohort')
    env.st.session_state.pop('as_manage_menu')
    env.view.teacher_page(env.t)
    env.st.session_state['as_member_input_' + fifth] = env.s[3]['id']
    env.st.events.add('as_quick_add_' + fifth + ':배정 / 검색 ↵')
    with pytest.raises(Rerun): env.view.teacher_page(env.t)
    assert selected_ids(env, fifth) == {env.s[3]['id']}
    assert selected_ids(env, first) == {u['id'] for u in env.s[:2]}
    assert '5기에 배정했어요' in env.st.session_state['_as_flash']


def test_cohort_setting_edit_keeps_same_members(env):
    first = env.cohort('1기', env.s[14:16])
    fifth = env.cohort('5기', env.s[:14])
    manage(env, fifth, '기수 설정')
    c = env.svc.get_cohort(env.t, fifth)
    prefix = 'as_edit_' + fifth + '_' + c['revision']
    env.st.session_state[prefix + 'desc'] = '설명만 변경'
    env.st.session_state['as_settings_confirm_' + fifth + '_' + c['revision']] = True
    env.st.events.add('as_settings_' + fifth + '_' + c['revision'] + ':기수 설정 저장')
    with pytest.raises(Rerun): env.view.teacher_page(env.t)
    assert len(selected_ids(env, fifth)) == 14 and len(selected_ids(env, first)) == 2
    assert env.svc.get_cohort(env.t, fifth)['description'] == '설명만 변경'
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth


def test_confirmation_checkbox_is_not_reused_for_another_cohort(env):
    first = env.cohort('1기'); fifth = env.cohort('5기')
    manage(env, first, '기수 설정')
    env.st.session_state['as_settings_confirm_' + first + '_1'] = True
    manage(env, fifth, '기수 설정')
    assert not env.st.session_state['as_settings_confirm_' + fifth + '_1']


def test_creation_pending_save_opens_new_cohort_only_after_confirmation(env):
    first = env.cohort('1기', env.s[:2]); manage(env, first)
    env.mp.setattr(env.db, 'flush_now', lambda: (_ for _ in ()).throw(OSError('offline')))
    fifth = create_via_form(env)
    assert env.st.session_state['_as_pending']['id'] == fifth
    assert not env.st.session_state.get('_as_manager_open_target')
    env.st.session_state.pop('as_manage_cohort', None)
    env.st.session_state.pop('as_manage_menu', None)
    env.mp.setattr(env.db, 'flush_now', lambda: None)
    env.st.events.add('as_retry')
    with pytest.raises(Rerun): env.view.teacher_page(env.t)
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth
    assert env.st.session_state['as_manage_menu'] == '참여 학생'
    assert len(env.svc.list_cohorts(env.t)) == 2


def test_failed_validation_does_not_navigate_or_change_members(env):
    first = env.cohort('1기', env.s[:14]); manage(env, first)
    before = deepcopy(env.b.read('as_cohorts'))
    op = env.st.session_state['_as_op_create_cohort']
    env.st.session_state['as_new_' + op + 'name'] = ''
    env.st.events.add('as_new_' + op + ':기수 추가')
    env.view.teacher_page(env.t)
    assert env.b.read('as_cohorts') == before
    assert env.st.session_state['as_manage_cohort'] == first
    assert not env.st.session_state.get('_as_manager_open_target')


def test_no_auto_migration_even_if_first_has14_and_fifth_has0(env):
    first = env.cohort('1기', env.s[:14]); fifth = env.cohort('5기', [])
    before = deepcopy(env.b.read('as_cohorts'))
    manage(env, fifth)
    assert len(selected_ids(env, first)) == 14 and not selected_ids(env, fifth)
    assert before == env.b.read('as_cohorts')
    # The teacher explicitly adds the intended 14. Other enrollment is preserved.
    env.svc.add_members(env.t, fifth, [u['id'] for u in env.s[:14]], env.svc.get_cohort(env.t, fifth)['revision'])
    assert len(selected_ids(env, fifth)) == 14 and len(selected_ids(env, first)) == 14


def test_members_persist_in_correct_csv_row_after_backend_reload(env):
    first = env.cohort('1기', env.s[14:16]); fifth = env.cohort('5기', env.s[:14])
    fresh = env.db.LocalBackend(env.b.root)
    byid = {c['id']:c for c in fresh.read('as_cohorts')}
    assert set(json.loads(byid[fifth]['members_json'])) == {s['id'] for s in env.s[:14]}
    assert set(json.loads(byid[first]['members_json'])) == {s['id'] for s in env.s[14:16]}


def test_student_and_other_teacher_cannot_see_overview(env):
    env.cohort('5기', env.s[:14])
    for person in (env.s[0], env.other):
        env.actor(person); env.st.outputs = []
        env.view.teacher_page(person)
        assert not [o for o in env.st.outputs if o[0] == 'dataframe']
        assert not [o for o in env.st.outputs if o[0] == 'button' and '학생 배정 (' in str(o[1])]


def test_management_context_does_not_execute_untrusted_cohort_names():
    from afterschool_core import presentation as p
    c = {'year':'2026','name':'<img src=x onerror=alert(1)>','subject':'공통수학2','member_count':14}
    for text in (p.management_context(c), p.enrollment_target(c), p.roster_heading(14, cohort=c)):
        assert '<img' not in text and '&lt;img' in text


def test_owner_and_authorized_ids_protect_navigation_cache():
    from afterschool_core import admin_navigation as n
    state = {}
    rows = [{'id':'first'}, {'id':'fifth'}]
    n.restore(state, 'teacher-A', rows)
    n.remember(state, 'teacher-A', 'fifth', '참여 학생')
    state.pop(n.COHORT_WIDGET); state.pop(n.MENU_WIDGET)
    n.restore(state, 'teacher-A', rows)
    assert state[n.COHORT_WIDGET] == 'fifth'
    n.request_open(state, 'teacher-A', 'fifth')
    n.restore(state, 'teacher-B', [{'id':'other'}])
    assert state[n.COHORT_WIDGET] == 'other'
    n.restore(state, 'teacher-A', [{'id':'first'}])
    assert state[n.COHORT_WIDGET] == 'first'


def test_stale_queued_target_cannot_select_revoked_cohort():
    from afterschool_core import admin_navigation as n
    state = {}
    n.request_open(state, 'teacher-A', 'removed')
    n.restore(state, 'teacher-A', [{'id':'allowed'}])
    assert state[n.COHORT_WIDGET] == 'allowed'
    assert not state.get('_as_manager_open_target')


def test_manual_switch_is_honored_after_creation_redirect_once(env):
    first = env.cohort('1기'); manage(env, first)
    fifth = create_via_form(env); env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == fifth
    env.st.session_state['as_manage_cohort'] = first
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_manage_cohort'] == first


def test_stale_form_from_another_cohort_cannot_be_consumed(env):
    first = env.cohort('1기'); fifth = env.cohort('5기')
    manage(env, first)
    env.st.session_state['as_member_input_' + first] = env.s[0]['id']
    env.st.events.add('as_quick_add_' + first + ':배정 / 검색 ↵')
    env.st.session_state['as_manage_cohort'] = fifth
    env.view.teacher_page(env.t)
    assert not selected_ids(env, first) and not selected_ids(env, fifth)
