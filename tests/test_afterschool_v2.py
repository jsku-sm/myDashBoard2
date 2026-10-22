"""Subject isolation, additive enrollment, confirmation/removal, and UI doubles.

No production accounts, secrets, network or live deployment are used.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
import csv
import io
import json
import threading
from pathlib import Path

import pytest
from test_afterschool import env, Rerun, Upload, ROOT, load
from afterschool_core import presentation


def cohort(env,subject,name='1기',members=()):
    env.actor(env.t)
    cid=env.svc.create_cohort(env.t,{'year':2026,'subject':subject,'name':name,'state':'active'},
                              f'create-subject-{len(env.b.read("as_cohorts")):08}')
    if members:
        env.svc.add_members(env.t,cid,[r['id'] for r in members],env.svc.get_cohort(env.t,cid)['revision'])
    return cid


def member_ids(env,cid):
    return {r['id'] for r in env.svc.roster(env.t,cid) if r['selected']}


def open_members(env,cid):
    env.actor(env.t)
    env.st.session_state['as_manage_cohort']=cid
    env.st.session_state['as_manage_menu']='참여 학생'
    env.view.teacher_page(env.t)


def submit_query(env,cid,query):
    env.st.session_state['as_member_input_'+cid]=query
    env.st.events.add('as_quick_add_'+cid+':배정 / 검색 ↵')
    env.view.teacher_page(env.t)


@pytest.mark.parametrize('subject',['공통수학1','공통수학2'])
def test_one_subject_cohort_assignment_and_hidden_other_course(env,subject):
    cid=cohort(env,subject,members=[env.s[0]])
    env.actor(env.s[0])
    assert env.svc.list_cohorts(env.s[0],subject)[0]['id']==cid
    other='공통수학2' if subject=='공통수학1' else '공통수학1'
    assert env.svc.has_access(env.s[0],subject)
    assert not env.svc.has_access(env.s[0],other)
    with pytest.raises(PermissionError):env.svc.get_cohort(env.s[0],cid,subject=other)
    env.actor(env.s[1]);assert not env.svc.has_access(env.s[1],subject)


def test_same_year_and_name_in_two_subjects_allowed_but_exact_duplicate_denied(env):
    a=cohort(env,'공통수학1');b=cohort(env,'공통수학2')
    assert a!=b and len(env.svc.list_cohorts(env.t))==2
    with pytest.raises(ValueError):cohort(env,'공통수학1')


@pytest.mark.parametrize('subject',['',None,'공통수학3',['공통수학1','공통수학2'],False])
def test_invalid_or_multi_subject_value_rejected(env,subject):
    with pytest.raises((ValueError,TypeError)):cohort(env,subject)
    assert not env.b.read('as_cohorts')


def test_legacy_csv_without_subject_reads_as_math2_and_is_not_rewritten(env):
    cid=env.cohort(members=[env.s[0]])
    path=Path(env.b.root)/'as_cohorts.csv'
    rows=env.b.read('as_cohorts');fields=[f for f in env.db.SCHEMAS['as_cohorts'] if f!='subject']
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        w.writerows({k:r[k] for k in fields} for r in rows)
    before=path.read_bytes()
    env.actor(env.s[0]);assert env.svc.list_cohorts(env.s[0],'공통수학2')[0]['id']==cid
    assert not env.svc.has_access(env.s[0],'공통수학1')
    assert path.read_bytes()==before
    env.actor(env.t);c=env.svc.get_cohort(env.t,cid)
    env.svc.update_cohort(env.t,cid,dict(c,description='설명만 수정'),c['revision'])
    assert env.svc.get_cohort(env.t,cid)['subject']=='공통수학2'
    assert 'subject' in path.read_text().splitlines()[0]
    assert member_ids(env,cid)=={env.s[0]['id']}


def test_subject_change_preserves_post_comment_submission_and_moves_tab(env):
    cid=cohort(env,'공통수학2',members=[env.s[0]])
    pid=env.post(cid,'assignment');env.actor(env.s[0])
    rid=env.svc.submit(env.s[0],pid,'나의 풀이',[],'subject-change-submit')
    env.svc.add_comment(env.s[0],pid,'질문', 'subject-comment-01')
    posts=deepcopy(env.b.read('as_posts'));attempts=deepcopy(env.b.read('as_submissions'))
    env.actor(env.t);c=env.svc.get_cohort(env.t,cid)
    env.svc.update_cohort(env.t,cid,dict(c,subject='공통수학1'),c['revision'])
    assert posts==env.b.read('as_posts') and attempts==env.b.read('as_submissions')
    env.actor(env.s[0]);assert env.svc.has_access(env.s[0],'공통수학1')
    assert not env.svc.has_access(env.s[0],'공통수학2')
    assert env.svc.submissions(env.s[0],pid)[0]['id']==rid
    env.actor(env.t)
    h=json.loads(env.b.read('as_cohorts')[0]['history_json'])[-1]
    assert h['previous_subject']=='공통수학2' and h['subject']=='공통수학1'


def test_omitted_subject_in_update_preserves_existing_math1(env):
    cid=cohort(env,'공통수학1');c=env.svc.get_cohort(env.t,cid)
    payload=dict(c,name='2기');payload.pop('subject')
    env.svc.update_cohort(env.t,cid,payload,c['revision'])
    assert env.svc.get_cohort(env.t,cid)['subject']=='공통수학1'


def test_multiple_cohort_memberships_independent_and_student_summary_private(env):
    a=cohort(env,'공통수학1',members=env.s[:2]);b=cohort(env,'공통수학2',members=env.s[:1])
    env.svc.remove_member(env.t,a,env.s[0]['id'],env.svc.get_cohort(env.t,a)['revision'])
    assert member_ids(env,b)=={env.s[0]['id']}
    env.actor(env.s[0]);rows=env.svc.list_cohorts(env.s[0])
    assert len(rows)==1 and rows[0]['id']==b
    assert 'member_count' not in rows[0] and 'members_json' not in rows[0]


def test_enter_exact_id_assigns_clears_input_and_automatically_counts(env):
    cid=cohort(env,'공통수학1');open_members(env,cid)
    with pytest.raises(Rerun):submit_query(env,cid,env.s[0]['id'])
    assert member_ids(env,cid)=={env.s[0]['id']}
    env.st.outputs=[];env.view.teacher_page(env.t)
    assert env.st.session_state.get('as_member_input_'+cid)=='',env.st.session_state.data
    assert any('총 1명' in str(v) for k,v,*_ in env.st.outputs if k=='markdown')
    assert any('배정했어요' in str(v) for k,v,*_ in env.st.outputs if k=='success')


def test_text_change_or_blur_without_submit_never_enrolls(env):
    cid=cohort(env,'공통수학2');open_members(env,cid)
    env.st.session_state['as_member_input_'+cid]=env.s[0]['id']
    env.view.teacher_page(env.t)
    assert member_ids(env,cid)==set()
    source=(ROOT/'views/afterschool.py').read_text()
    assert "with st.form('as_quick_add_'+cid,enter_to_submit=True)" in source


def test_duplicate_id_has_no_duplicate_revision_or_count(env):
    cid=cohort(env,'공통수학2',members=[env.s[0]]);open_members(env,cid)
    before=env.svc.get_cohort(env.t,cid)['revision']
    submit_query(env,cid,env.s[0]['id'])
    assert env.svc.get_cohort(env.t,cid)['revision']==before
    assert env.svc.get_cohort(env.t,cid)['member_count']==1
    assert any('이미 배정' in str(v) for k,v,*_ in env.st.outputs if k=='info')


@pytest.mark.parametrize('query',['99999','','100','가상학생1'])
def test_non_exact_id_or_name_does_not_auto_assign(env,query):
    cid=cohort(env,'공통수학1');open_members(env,cid)
    submit_query(env,cid,query)
    assert member_ids(env,cid)==set()
    assert len(env.b.read('users'))==27


def test_name_candidate_can_be_confirmed_and_assigned(env):
    cid=cohort(env,'공통수학1');open_members(env,cid)
    submit_query(env,cid,'가상학생25')
    assert not member_ids(env,cid)
    env.st.events.add('as_add_candidate_'+cid+'_'+env.s[-1]['id'])
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert member_ids(env,cid)=={env.s[-1]['id']}


def test_leading_zeros_are_preserved(env):
    user=dict(env.s[0],id='00123');env.b.append('users',user)
    cid=cohort(env,'공통수학2');open_members(env,cid)
    with pytest.raises(Rerun):submit_query(env,cid,' 00123 ')
    assert member_ids(env,cid)=={'00123'}


def test_removal_requires_confirmation_decrements_count_but_preserves_everything_else(env):
    a=cohort(env,'공통수학1',members=env.s[:2]);b=cohort(env,'공통수학2',members=env.s[:1])
    pid=env.post(a,'assignment');env.actor(env.s[0]);env.svc.submit(env.s[0],pid,'유지될 답',[],'keep-attempt-01')
    users=deepcopy(env.b.read('users'));submissions=deepcopy(env.b.read('as_submissions'))
    open_members(env,a);env.st.events.add('as_remove_'+a+'_'+env.s[0]['id'])
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert len(member_ids(env,a))==2
    env.st.events.add('as_remove_confirm_'+a)
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert member_ids(env,a)=={env.s[1]['id']} and member_ids(env,b)=={env.s[0]['id']}
    assert users==env.b.read('users') and submissions==env.b.read('as_submissions')
    env.st.outputs=[];env.view.teacher_page(env.t)
    assert any('총 1명' in str(v) for k,v,*_ in env.st.outputs if k=='markdown')
    assert not env.st.session_state.get('as_remove_pending_'+a)
    env.actor(env.s[0]);assert not env.svc.has_access(env.s[0],'공통수학1')


def test_cancel_removal_keeps_members(env):
    cid=cohort(env,'공통수학1',members=env.s[:1]);open_members(env,cid)
    env.st.events.add('as_remove_'+cid+'_'+env.s[0]['id'])
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    env.st.events.add('as_remove_keep_'+cid)
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert member_ids(env,cid)=={env.s[0]['id']}


def test_filtered_roster_shows_total_separately(env):
    cid=cohort(env,'공통수학2',members=env.s[:7]);open_members(env,cid)
    env.st.session_state['as_list_class_'+cid]='1-1'
    env.st.outputs=[];env.view.teacher_page(env.t)
    text='\n'.join(str(v) for k,v,*_ in env.st.outputs if k=='markdown')
    assert '총 7명' in text and '검색 결과 1명' in text
    assert len(member_ids(env,cid))==7


def test_missing_account_can_be_removed_from_retained_roster(env):
    cid=cohort(env,'공통수학2',members=env.s[:1]);env.b.delete('users',env.s[0]['id'])
    row=next(r for r in env.svc.roster(env.t,cid) if r['id']==env.s[0]['id'])
    assert row['unavailable'] and row['selected']
    open_members(env,cid)
    assert env.svc.get_cohort(env.t,cid)['member_count']==1
    env.svc.remove_member(env.t,cid,env.s[0]['id'],env.svc.get_cohort(env.t,cid)['revision'])
    assert env.svc.get_cohort(env.t,cid)['member_count']==0


@pytest.mark.parametrize('action',['add','remove'])
@pytest.mark.parametrize('who',['student','other_teacher'])
def test_membership_delta_needs_current_owner_permission(env,action,who):
    cid=cohort(env,'공통수학1',members=env.s[:1]);c=env.svc.get_cohort(env.t,cid)
    u=env.s[0] if who=='student' else env.other;env.actor(u)
    fn=env.svc.add_member if action=='add' else env.svc.remove_member
    with pytest.raises(PermissionError):fn(u,cid,env.s[0]['id'],c['revision'])


def test_revision_conflict_cannot_overwrite_concurrent_addition(env):
    cid=cohort(env,'공통수학1');c=env.svc.get_cohort(env.t,cid)
    env.svc.add_member(env.t,cid,env.s[0]['id'],c['revision'])
    with pytest.raises(env.svc.ConflictError):env.svc.add_member(env.t,cid,env.s[1]['id'],c['revision'])
    env.svc.add_member(env.t,cid,env.s[1]['id'],env.svc.get_cohort(env.t,cid)['revision'])
    assert member_ids(env,cid)=={u['id'] for u in env.s[:2]}


def test_save_failure_does_not_show_success_or_increased_count_until_confirmed(env):
    cid=cohort(env,'공통수학1');open_members(env,cid)
    env.mp.setattr(env.db,'flush_now',lambda:(_ for _ in ()).throw(IOError('offline')))
    with pytest.raises(Rerun):submit_query(env,cid,env.s[0]['id'])
    env.st.outputs=[];env.view.teacher_page(env.t)
    assert not any(k=='success' for k,*_ in env.st.outputs)
    assert not any('총 1명' in str(v) for k,v,*_ in env.st.outputs if k=='markdown')
    assert env.st.session_state['as_member_input_'+cid]==env.s[0]['id']
    env.mp.setattr(env.db,'flush_now',lambda:None);env.st.events.add('as_retry')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    env.view.teacher_page(env.t)
    assert env.st.session_state['as_member_input_'+cid]==''
    assert env.svc.get_cohort(env.t,cid)['member_count']==1


def test_own_submissions_panel_no_roster_and_no_other_answers_or_teacher_controls(env):
    cid=cohort(env,'공통수학1',members=env.s[:2]);pid=env.post(cid,'assignment')
    for student,body in zip(env.s[:2],['MY-ANSWER','OTHER-SECRET-ANSWER']):
        env.actor(student);env.svc.submit(student,pid,body,[],'answer-'+student['id'])
    env.actor(env.s[0]);env.st.session_state['as_board_section_math1_'+cid]='내 제출 확인'
    env.mp.setattr(env.svc,'roster',lambda *a:(_ for _ in ()).throw(AssertionError('no roster for students')))
    env.st.outputs=[];env.view.student_board(env.s[0],'공통수학1')
    text='\n'.join(str(v) for _,v,*_ in env.st.outputs)
    assert 'MY-ANSWER' in text and 'OTHER-SECRET-ANSWER' not in text
    assert not [o for o in env.st.outputs if o[0]=='error']
    buttons=[v for k,v,*_ in env.st.outputs if k=='button']
    assert not set(buttons)&{'기수 추가','학생 배정 저장','배정 취소','과제 제출','피드백 저장 · 학생에게 공개'}


def test_two_subject_student_menus_and_selected_cohort_cannot_leak_across_subject(env):
    a=cohort(env,'공통수학1',members=env.s[:1]);b=cohort(env,'공통수학2',members=env.s[:1])
    env.post(a,title='MATH1-ONLY');env.post(b,title='MATH2-ONLY',request='math2-post')
    env.actor(env.s[0]);env.st.session_state['as_student_cohort_math1']=b
    env.view.student_board(env.s[0],'공통수학1')
    text='\n'.join(str(v) for _,v,*_ in env.st.outputs)
    assert 'MATH1-ONLY' in text and 'MATH2-ONLY' not in text
    assert env.st.session_state['as_student_cohort_math1']==a


@pytest.mark.parametrize('subject',['공통수학1','공통수학2'])
@pytest.mark.parametrize('state,visible',[('draft',False),('active',True),('archived',True),('closed',False)])
def test_subject_state_visibility_and_readonly_submission_controls(env,subject,state,visible):
    cid=cohort(env,subject,members=env.s[:1]);pid=env.post(cid,'assignment')
    env.state(cid,state);env.actor(env.s[0])
    assert env.svc.has_access(env.s[0],subject)==visible
    env.view.student_board(env.s[0],subject)
    buttons=[v for k,v,*_ in env.st.outputs if k=='button']
    if state!='active':assert '과제 제출' not in buttons and '댓글 등록' not in buttons
    if state=='archived':assert env.svc.get_post(env.s[0],pid)


def test_course_ui_tabs_both_subjects_and_unassigned_hidden(env):
    fakeui=ModuleType('ui');fakeui.page_title=lambda *a:None
    env.mp.setitem(__import__('sys').modules,'ui',fakeui)
    env.mp.setitem(__import__('sys').modules,'auth',ModuleType('auth'))
    math=load('views.math_class',ROOT/'views/math_class.py',env.mp)
    for fn in ('tab_plan','tab_sheets','tab_board','tab_questions'):env.mp.setattr(math,fn,lambda *a:None)
    board=ModuleType('views.afterschool');board.student_board=lambda u,s:env.st._out('subject_called',s)
    env.mp.setitem(__import__('sys').modules,'views.afterschool',board)
    cohort(env,'공통수학1',members=env.s[:1]);cohort(env,'공통수학2',members=env.s[:1])
    for user,visible in [(env.s[0],True),(env.s[1],False)]:
        for subject in ('공통수학1','공통수학2'):
            env.actor(user);env.st.outputs=[];math.page(user,subject)
            labels=next(v for k,v,*_ in env.st.outputs if k=='tabs')
            assert ('🌙 방과후 게시판' in labels)==visible
            assert any(k=='subject_called' and v==subject for k,v,*_ in env.st.outputs)==visible


def test_visual_helpers_escape_strings_and_css_is_local():
    value='<img src=x onerror=alert(1)>'
    out=presentation.person({'id':value,'name':value,'class':value})
    assert '<img' not in out and '&lt;img' in out
    assert '.st-key-as_admin_shell' in presentation.styles()
    assert 'body{' not in presentation.styles() and 'body {' not in presentation.styles()
    assert '총 7명' in presentation.roster_heading(7,2)
    assert '검색 결과 2명' in presentation.roster_heading(7,2)


def test_create_and_edit_subject_through_teacher_form(env):
    env.view.teacher_page(env.t)
    op=env.st.session_state['_as_op_create_cohort'];prefix='as_new_'+op
    env.st.session_state[prefix+'name']='방과후 1기'
    env.st.session_state[prefix+'subject']='공통수학1'
    env.st.session_state[prefix+'state']='active'
    env.st.events.add(prefix+':기수 추가')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    c=env.svc.list_cohorts(env.t)[0];assert c['subject']=='공통수학1'
    env.view.teacher_page(env.t)  # creation now opens the new cohort's enrollment page
    env.st.session_state['as_manage_menu']='기수 설정'
    env.view.teacher_page(env.t)
    env.st.session_state['as_edit_'+c['id']+'_'+c['revision']+'subject']='공통수학2'
    # Confirmation is cohort/revision-scoped, never shared with another cohort.
    env.st.session_state['as_settings_confirm_'+c['id']+'_'+c['revision']]=True
    env.st.events.add('as_settings_'+c['id']+'_'+c['revision']+':기수 설정 저장')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert env.svc.get_cohort(env.t,c['id'])['subject']=='공통수학2'


def test_blank_subject_from_old_memory_store_stays_math2(env):
    cid=env.cohort(members=env.s[:1]);env.b.update('as_cohorts',cid,{'subject':''})
    env.actor(env.s[0])
    assert len(env.svc.list_cohorts(env.s[0],'공통수학2'))==1
    assert env.svc.list_cohorts(env.s[0],'공통수학1')==[]


def test_new_member_delta_noop_never_duplicates_history(env):
    cid=cohort(env,'공통수학1',members=env.s[:1]);c=env.svc.get_cohort(env.t,cid)
    before=deepcopy(env.b.read('as_cohorts'))
    env.svc.add_member(env.t,cid,env.s[0]['id'],c['revision'])
    assert env.b.read('as_cohorts')==before


def test_teacher_id_and_unknown_cannot_be_added_as_students(env):
    cid=cohort(env,'공통수학2');c=env.svc.get_cohort(env.t,cid)
    for sid in [env.t['id'],'unknown-student']:
        with pytest.raises(ValueError):env.svc.add_member(env.t,cid,sid,c['revision'])
    assert not member_ids(env,cid)


def test_after_success_input_reset_sets_value_instead_of_deleting_widget_key(env):
    # Real Streamlit reconnects to the browser's old value if a widget key is
    # just deleted. Explicit blank before rendering is required.
    key='as_member_input_example';env.st.session_state[key]='10001'
    env.st.session_state['_as_clear_keys']=[key]
    env.view._notice(env.t)
    assert key in env.st.session_state and env.st.session_state[key]==''
