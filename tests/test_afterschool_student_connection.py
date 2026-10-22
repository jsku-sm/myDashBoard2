"""Student 10101 / cohort 5 scenario plus publication and live-permission tests.

Uses real service/storage code with a LOCAL temporary store and Streamlit UI
stand-ins. Does not connect to a school account, GitHub or live deployment.
"""
from copy import deepcopy
from types import ModuleType
import json
import sys

import pytest
from test_afterschool import env, Rerun, Upload, ROOT, load


def make_student(env, sid='10101'):
    s=dict(env.s[0], id=sid, name='시험학생 '+sid)
    env.b.append('users',s)
    return s


def make_cohort(env, members=(), name='5기', subject='공통수학2', state=None):
    env.actor(env.t)
    data={'year':2026,'subject':subject,'name':name}
    if state is not None: data['state']=state
    cid=env.svc.create_cohort(env.t,data,'scenario-'+str(len(env.b.read('as_cohorts'))).zfill(8))
    if members:
        env.svc.add_members(env.t,cid,[s['id'] for s in members],env.svc.get_cohort(env.t,cid)['revision'])
    return cid


def manage(env,cid,menu='자료·과제'):
    env.actor(env.t)
    env.st.session_state['as_manage_cohort']=cid
    env.st.session_state['as_manage_menu']=menu
    env.view.teacher_page(env.t)


def connect(env,cid,pids=(),open_board=False):
    env.actor(env.t)
    versions={pid:env.svc.get_post(env.t,pid)['revision'] for pid in pids}
    return env.svc.publish_to_students(env.t,cid,versions,env.svc.get_cohort(env.t,cid)['revision'],open_board=open_board)


def output(env):
    return '\n'.join(str(v) for _,v,*_ in env.st.outputs)


def test_10101_5th_cohort_teacher_posts_student_reads_comments_and_submits(env):
    s=make_student(env)
    cid=make_cohort(env,[s]); assert env.svc.get_cohort(env.t,cid)['state']=='active'
    pid=env.post(cid,files=[Upload('5기학습지.txt')],title='5기 함수 수업자료')
    aid=env.post(cid,'assignment',request='5th-assignment',title='5기 과제')
    env.actor(s)
    assert [c['name'] for c in env.svc.list_cohorts(s,'공통수학2')]==['5기']
    assert env.svc.list_cohorts(s,'공통수학1')==[]
    assert {p['id'] for p in env.svc.list_posts(s,cid)}=={pid,aid}
    assert env.svc.download_attachment(s,'post',pid,0)[0]==Upload().getvalue()
    env.view._files=lambda *a,**kw:None  # standalone component has browser-only runtime
    env.view.student_board(s,'공통수학2')
    nav=[o for o in env.st.outputs if o[0]=='radio' and o[1]=='게시판'][0]
    assert nav[2]['options']==['자료·과제','질문·댓글','내 과제 제출']
    rid=env.svc.submit(s,aid,'함수의 뜻 설명',[],'my-first-attempt')
    env.svc.add_comment(s,pid,'자료를 확인했습니다.','my-first-comment')
    env.actor(env.t)
    assert env.svc.submissions(env.t,aid)[0]['id']==rid
    assert env.svc.comments(env.t,pid)[0]['body']=='자료를 확인했습니다.'
    assert env.svc.publication_status(env.t,cid)['path']=='공통수학2 → 방과후 게시판 → 5기'


def test_no_automatic_disclosure_of_existing_draft_cohort_and_posts(env):
    s=make_student(env);cid=make_cohort(env,[s],state='draft')
    pid=env.post(cid,published=False)
    before=deepcopy(env.b.read('as_cohorts')+env.b.read('as_posts'))
    manage(env,cid)
    assert '현재 준비 중' in output(env)
    assert env.b.read('as_cohorts')+env.b.read('as_posts')==before
    env.actor(s)
    assert not env.svc.has_access(s,'공통수학2')
    with pytest.raises(PermissionError):env.svc.get_post(s,pid)


def test_explicit_old_cohort_repair_selects_only_intended_drafts(env):
    s=make_student(env);cid=make_cohort(env,[s],state='draft')
    public=env.post(cid,title='공개할 것',published=False,files=[Upload()])
    secret=env.post(cid,title='비공개 유지',published=False,request='secret-draft')
    source=deepcopy(env.svc.get_post(env.t,public))
    connect(env,cid,[public],True)
    env.actor(s)
    assert env.svc.has_access(s,'공통수학2')
    row=env.svc.get_post(s,public)
    assert row['id']==source['id'] and row['attachments']==source['attachments']
    assert env.svc.download_attachment(s,'post',public,0)[0]==Upload().getvalue()
    with pytest.raises(PermissionError):env.svc.get_post(s,secret)
    assert len(env.b.read('as_posts'))==2


@pytest.mark.parametrize('state',['draft','closed'])
def test_open_requires_explicit_authorized_confirmation(env,state):
    s=make_student(env);cid=make_cohort(env,[s],state=state)
    with pytest.raises(ValueError):connect(env,cid,[],False)
    connect(env,cid,[],True)
    env.actor(s);assert env.svc.has_access(s,'공통수학2')


def test_readonly_cohort_cannot_be_reopened_by_publication_shortcut(env):
    s=make_student(env);cid=make_cohort(env,[s],state='archived')
    with pytest.raises(PermissionError):connect(env,cid,[],True)
    assert env.svc.get_cohort(env.t,cid)['state']=='archived'


@pytest.mark.parametrize('actor',['student','other_teacher'])
def test_publication_and_diagnostics_are_owner_only(env,actor):
    cid=make_cohort(env,[env.s[0]])
    pid=env.post(cid,published=False)
    c=env.svc.get_cohort(env.t,cid)
    who=env.s[0] if actor=='student' else env.other;env.actor(who)
    with pytest.raises(PermissionError):env.svc.publication_status(who,cid)
    with pytest.raises(PermissionError):env.svc.publish_to_students(who,cid,{pid:'1'},c['revision'])


def test_publish_rejects_other_cohort_and_rolls_back_prevalidation(env):
    a=make_cohort(env,[env.s[0]]); p1=env.post(a,published=False)
    b=make_cohort(env,[env.s[1]],name='6기');p2=env.post(b,published=False,request='other-post')
    with pytest.raises(PermissionError):connect(env,a,[p1,p2])
    assert env.svc.get_post(env.t,p1)['published']=='0'


def test_publish_checks_all_revisions_before_mutating(env):
    cid=make_cohort(env,[env.s[0]],state='draft')
    p1=env.post(cid,published=False);p2=env.post(cid,published=False,request='second-post')
    c=env.svc.get_cohort(env.t,cid)
    with pytest.raises(env.svc.ConflictError):
        env.svc.publish_to_students(env.t,cid,{p1:'1',p2:'not-current'},c['revision'],open_board=True)
    assert env.svc.get_post(env.t,p1)['published']=='0'
    assert env.svc.get_cohort(env.t,cid)['state']=='draft'


def test_publish_rejects_empty_members_no_fake_success(env):
    cid=make_cohort(env)
    with pytest.raises(ValueError):connect(env,cid,[],True)


def test_publish_cannot_disclose_private_student_questions(env):
    cid=make_cohort(env,[env.s[0]])
    env.actor(env.s[0]);qid=env.svc.create_post(env.s[0],cid,{'kind':'question','title':'private','body':'sensitive'},[],'private-question')
    with pytest.raises(PermissionError):connect(env,cid,[qid])
    assert env.svc.get_post(env.t,qid)['visibility']=='private'


def test_publish_save_failure_is_reported_not_success(env):
    cid=make_cohort(env,[env.s[0]],state='draft');pid=env.post(cid,published=False)
    env.mp.setattr(env.db,'flush_now',lambda:(_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(env.svc.SavePendingError):connect(env,cid,[pid],True)
    env.mp.setattr(env.db,'flush_now',lambda:None)
    env.svc.retry_save(env.t)
    env.actor(env.s[0]);assert env.svc.get_post(env.s[0],pid)['published']=='1'


def test_new_teacher_form_defaults_to_active(env):
    env.view.teacher_page(env.t)
    op=env.st.session_state['_as_op_create_cohort'];key='as_new_'+op
    assert env.st.session_state[key+'state']=='active'
    env.st.session_state[key+'name']='5기'
    env.st.events.add(key+':기수 추가')
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    assert env.svc.list_cohorts(env.t)[0]['state']=='active'


@pytest.mark.parametrize('public',[True,False])
def test_new_post_buttons_explicitly_public_or_draft(env,public):
    s=make_student(env);cid=make_cohort(env,[s]);manage(env,cid)
    op=env.st.session_state['_as_op_newpost_'+cid+'material'];key='as_post_'+op
    env.st.session_state[key+'title']='교사가 등록한 자료'
    env.st.session_state[key+'body']='동일 본문'
    button='등록하고 학생에게 공개' if public else '초안으로 저장'
    env.st.events.add(key+':'+button)
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    env.actor(s)
    posts=env.svc.list_posts(s,cid)
    assert bool(posts)==public
    if public:assert posts[0]['body']=='동일 본문'


def test_preview_never_posts_or_opens_board(env):
    cid=make_cohort(env,[env.s[0]],state='draft');manage(env,cid)
    op=env.st.session_state['_as_op_newpost_'+cid+'material'];key='as_post_'+op
    env.st.session_state[key+'title']='미리보기';env.st.session_state[key+'body']='private preview'
    env.st.events.add(key+':내용 미리보기');env.view.teacher_page(env.t)
    assert not env.b.read('as_posts') and env.svc.get_cohort(env.t,cid)['state']=='draft'


def test_existing_repair_ui_needs_confirm_and_does_not_publish_all(env):
    s=make_student(env);cid=make_cohort(env,[s],state='draft');pid=env.post(cid,published=False)
    rev=env.svc.get_cohort(env.t,cid)['revision'];manage(env,cid)
    env.st.session_state['as_publish_posts_'+cid+'_'+rev]=[pid]
    env.st.session_state['as_publish_open_'+cid+'_'+rev]=True
    event='as_publish_'+cid+'_'+rev+':배정 학생에게 연결 · 선택 글 공개'
    env.st.events.add(event);env.view.teacher_page(env.t)
    assert env.svc.get_cohort(env.t,cid)['state']=='draft'
    env.st.session_state['as_publish_confirm_'+cid+'_'+rev]=True
    env.st.events.add(event)
    with pytest.raises(Rerun):env.view.teacher_page(env.t)
    env.actor(s);assert env.svc.get_post(s,pid)['published']=='1'


def test_my_assignment_tab_can_submit_and_only_sees_own_records(env):
    s=make_student(env);other=env.s[0];cid=make_cohort(env,[s,other]);aid=env.post(cid,'assignment')
    env.actor(other);env.svc.submit(other,aid,'HIDDEN_OTHER_ANSWER',[],'other-answer')
    env.actor(s);env.st.session_state['as_board_section_math2_'+cid]='내 과제 제출'
    env.view.student_board(s,'공통수학2')
    assert 'HIDDEN_OTHER_ANSWER' not in output(env)
    op=env.st.session_state['_as_op_submit_'+aid]
    env.st.session_state['as_answer_'+op]='MY_ANSWER_10101'
    env.st.events.add('as_submit_'+op+':과제 제출')
    with pytest.raises(Rerun):env.view.student_board(s,'공통수학2')
    assert env.svc.submissions(s,aid)[0]['body']=='MY_ANSWER_10101'


def test_legacy_my_receipts_selection_migrates_to_new_menu(env):
    s=make_student(env);cid=make_cohort(env,[s]);env.post(cid,'assignment')
    env.actor(s);key='as_board_section_math2_'+cid
    env.st.session_state[key]='내 제출 확인';env.view.student_board(s,'공통수학2')
    assert env.st.session_state[key]=='내 과제 제출'
    assert '과제 제출' in [v for k,v,*_ in env.st.outputs if k=='button']


def test_snapshots_exclude_other_cohort_private_questions_and_answers(env):
    s=make_student(env);cid=make_cohort(env,[s,env.s[0]])
    aid=env.post(cid,'assignment');env.actor(s);base=env.svc.student_snapshot(s,'공통수학2')
    env.actor(env.s[0]);env.svc.create_post(env.s[0],cid,{'kind':'question','title':'SECRET_PRIVATE','body':'secret'},[],'other-private')
    env.svc.submit(env.s[0],aid,'OTHER_ANSWER',[],'other-answers')
    env.actor(s);assert env.svc.student_snapshot(s,'공통수학2')==base
    env.actor(env.t);env.post(cid,published=False,request='unpublished-secret',title='SECRET_DRAFT')
    env.actor(s);assert env.svc.student_snapshot(s,'공통수학2')==base
    cid2=make_cohort(env,[env.s[1]],name='6기');env.post(cid2,request='other-cohort-material')
    env.actor(s);assert env.svc.student_snapshot(s,'공통수학2')==base


def test_snapshots_change_on_visible_content_not_other_member_assignment(env):
    s=make_student(env);cid=make_cohort(env,[s]);env.actor(s);base=env.svc.student_snapshot(s,'공통수학2')
    env.actor(env.t);env.svc.add_member(env.t,cid,env.s[0]['id'],env.svc.get_cohort(env.t,cid)['revision'])
    env.actor(s);assert env.svc.student_snapshot(s,'공통수학2')==base
    env.post(cid);env.actor(s);after=env.svc.student_snapshot(s,'공통수학2')
    assert base['access']==after['access'] and base['content']!=after['content']


def test_snapshot_reacts_to_subject_change_removal_and_archive(env):
    s=make_student(env);cid=make_cohort(env,[s]);env.actor(s);base=env.svc.student_snapshot(s,'공통수학2')
    env.state(cid,'archived');env.actor(s);assert env.svc.student_snapshot(s,'공통수학2')['access']!=base['access']
    env.actor(env.t);c=env.svc.get_cohort(env.t,cid)
    env.svc.update_cohort(env.t,cid,dict(c,subject='공통수학1'),c['revision'])
    env.actor(s);assert not env.svc.student_snapshot(s,'공통수학2')['access']
    assert env.svc.student_snapshot(s,'공통수학1')['access']
    env.actor(env.t);env.svc.remove_member(env.t,cid,s['id'],env.svc.get_cohort(env.t,cid)['revision'])
    env.actor(s);assert not env.svc.student_snapshot(s,'공통수학1')['access']


def sync_module(env):
    return load('afterschool_core.student_sync',ROOT/'afterschool_core/student_sync.py',env.mp)


def test_live_watcher_reruns_on_new_membership_without_relogin(env):
    s=make_student(env);cid=make_cohort(env);mod=sync_module(env)
    env.actor(s);mod.watch(s,'공통수학2');key='_as_page_snapshot_10101_공통수학2'
    env.actor(env.t);env.svc.add_member(env.t,cid,s['id'],env.svc.get_cohort(env.t,cid)['revision'])
    env.actor(s)
    with pytest.raises(Rerun):mod._poll(s,'공통수학2',key)
    mod.watch(s,'공통수학2')  # full rerun baseline, must not loop


def test_live_watcher_does_not_rerun_on_new_content_until_requested(env):
    s=make_student(env);cid=make_cohort(env,[s]);mod=sync_module(env)
    env.actor(s);mod.watch(s,'공통수학2');key='_as_page_snapshot_10101_공통수학2'
    env.st.session_state['as_answer_unsubmitted']='UNSENT_DRAFT'
    env.post(cid);env.actor(s)
    mod._poll(s,'공통수학2',key)
    assert env.st.session_state['as_answer_unsubmitted']=='UNSENT_DRAFT'
    assert '새 자료·과제' in output(env)
    env.st.events.add(key+'_refresh')
    with pytest.raises(Rerun):mod._poll(s,'공통수학2',key)


def test_live_watcher_revocation_reruns_and_service_blocks_access(env):
    s=make_student(env);cid=make_cohort(env,[s]);pid=env.post(cid);mod=sync_module(env)
    env.actor(s);mod.watch(s,'공통수학2');key='_as_page_snapshot_10101_공통수학2'
    env.actor(env.t);env.svc.remove_member(env.t,cid,s['id'],env.svc.get_cohort(env.t,cid)['revision'])
    env.actor(s)
    with pytest.raises(Rerun):mod._poll(s,'공통수학2',key)
    with pytest.raises(PermissionError):env.svc.get_post(s,pid)


def test_live_watcher_connection_error_is_visible_and_does_not_mutate_permissions(env):
    s=make_student(env);mod=sync_module(env);env.actor(s)
    env.mp.setattr(env.svc,'student_snapshot',lambda *a:(_ for _ in ()).throw(OSError('no connection')))
    mod.watch(s,'공통수학2')
    assert any(k=='warning' and '확인하지 못' in str(v) for k,v,*_ in env.st.outputs)


def test_board_and_access_remain_after_backend_reload(env):
    s=make_student(env);cid=make_cohort(env,[s],state='draft');pid=env.post(cid,published=False)
    connect(env,cid,[pid],True)
    reloaded=env.db.LocalBackend(str(env.b.root));env.mp.setattr(env.db,'get_backend',lambda:reloaded)
    env.actor(s)
    assert env.svc.has_access(s,'공통수학2') and env.svc.get_post(s,pid)['published']=='1'


def test_student_course_tab_created_only_for_assigned_subject_and_not_other_students(env):
    s=make_student(env);make_cohort(env,[s])
    fakeui=ModuleType('ui');fakeui.page_title=lambda *a:None
    env.mp.setitem(sys.modules,'ui',fakeui);env.mp.setitem(sys.modules,'auth',ModuleType('auth'))
    sync_module(env)
    math=load('views.math_class',ROOT/'views/math_class.py',env.mp)
    for name in ('tab_plan','tab_sheets','tab_board','tab_questions'):env.mp.setattr(math,name,lambda *a:None)
    env.mp.setattr(env.view,'_files',lambda *a,**kw:None)
    for student,subject,expected in [(s,'공통수학2',True),(s,'공통수학1',False),(env.s[0],'공통수학2',False)]:
        env.actor(student);env.st.outputs=[];math.page(student,subject)
        labels=next(v for k,v,*_ in env.st.outputs if k=='tabs')
        assert ('🌙 방과후 게시판' in labels)==expected


def test_archived_own_submission_menu_readonly(env):
    s=make_student(env);cid=make_cohort(env,[s]);aid=env.post(cid,'assignment')
    env.actor(s);env.svc.submit(s,aid,'기존 답안',[],'original-answer')
    env.state(cid,'archived');env.actor(s)
    env.st.session_state['as_board_section_math2_'+cid]='내 과제 제출';env.st.outputs=[]
    env.view.student_board(s,'공통수학2')
    assert '기존 답안' in output(env)
    assert not any(k=='button' and v in ('과제 제출','새 차수로 재제출') for k,v,*_ in env.st.outputs)


def test_partial_settings_update_preserves_closed_or_draft_state(env):
    for i,state in enumerate(['draft','closed','archived']):
        cid=make_cohort(env,[env.s[0]],state=state,name=f'{i+1}기')
        c=env.svc.get_cohort(env.t,cid)
        env.svc.update_cohort(env.t,cid,{'year':2026,'name':c['name'],'description':'안내만 수정'},c['revision'])
        assert env.svc.get_cohort(env.t,cid)['state']==state
