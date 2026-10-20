"""수업도구 → 4. 퀴즈 and teacher/student dashboard entry points."""
from __future__ import annotations
import hashlib
import json
import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS
from snorkl_navigation import ACTIVE_TOOL, clear_link
from quiz_core import bank, service as svc
from quiz_core.presentation import dashboard_html, STATE

ERRORS=(svc.QuizError, svc.PendingSave, PermissionError, ValueError)


def _notice(message, success=True):
    st.session_state['_quiz_notice']=(message,success)


def _show_notice():
    note=st.session_state.pop('_quiz_notice',None)
    if note: (st.success if note[1] else st.warning)(note[0])


def _navigate(quiz_id=None):
    clear_link(st.session_state, st.query_params)
    st.session_state['nav']='tools'; st.session_state[ACTIVE_TOOL]='tool_quiz'
    st.session_state['_quiz_full_rerun']=True
    if quiz_id:
        st.session_state['_quiz_open_id']=quiz_id
        user=st.session_state.get('user') or {}
        if user.get('role')=='student':
            st.session_state[f'qstudent_{user["id"]}']=quiz_id


def _pending_line(user, qid):
    status=svc.save_state(user,qid)
    if status['local']:
        st.warning('로컬 시험 저장입니다. 실제 학생 기록을 보관하려면 기존 GitHub 저장 설정을 사용하세요.')
    elif status['durable']:
        st.caption('✓ GitHub 영구 저장 확인 · 학생별 개인 파일에 누적됩니다.')
    else:
        st.warning('응답은 서버에 반영되었습니다. GitHub 일괄 저장 대기 중입니다. 저장 확인 전 앱을 종료하지 마세요.')
    if status['error']: st.warning('마지막 GitHub 저장 시도가 실패했습니다. 입력은 대기 중이며 연결을 확인해야 합니다.')


def _make(user,subject,unit,bank_unit):
    try:
        qid=svc.create_draft(user,subject,unit,bank_unit=bank_unit)
        st.session_state['_quiz_draft']=qid
        st.session_state['q_draft_selector']=qid
        _notice('10문항 초안을 만들었어요. 발문·보기·정답을 검토한 뒤 배포하세요.')
    except ERRORS as e: _notice(str(e),False)


def _followup(user,parent,student_ids,concepts):
    try:
        if not student_ids: raise svc.QuizError('추가 퀴즈를 받을 학생을 선택하세요.')
        q=svc.teacher_paper(user,parent)
        qid=svc.create_draft(user,q['subject'],q['unit'],bank_unit=q['bank_unit'],parent_id=parent,focus=concepts)
        st.session_state['_quiz_next_draft']=(qid,list(student_ids))
        _navigate()
    except ERRORS as e: _notice(str(e),False)


def _reset_editor(qid):
    for key in list(st.session_state):
        if key == f'qedit_revision_{qid}' or key == f'qtitle_{qid}' or any(
            key.startswith(f'{prefix}_{qid}_') for prefix in ('qp','qo','qa','qe')
        ):
            st.session_state.pop(key,None)


def _editor(user,paper):
    qid=paper['id']
    expected_key=f'qedit_revision_{qid}'
    st.session_state.setdefault(expected_key,paper['revision'])
    with st.expander('✏️ 문항·보기·정답 수정',expanded=False):
        st.caption('4지선다 10문항입니다. 한 문항당 10점이며 배포 후에는 문제를 바꿀 수 없습니다.')
        st.button('작성 중인 수정 취소 · 최신 초안 불러오기',on_click=_reset_editor,args=(qid,),key=f'qreset_{qid}')
        with st.form(f'qedit_{qid}'):
            title=st.text_input('퀴즈 제목',value=paper['title'],max_chars=200,key=f'qtitle_{qid}')
            edited=[]
            for i,q in enumerate(paper['questions'],1):
                st.markdown(f'**{i}번 · {q["concept"]}**')
                prompt=st.text_area(f'{i}번 문제',value=q['prompt'],key=f'qp_{qid}_{i}',height=90)
                cols=st.columns(2); options=[]
                for j,option in enumerate(q['options']):
                    options.append(cols[j%2].text_input(f'{i}번 보기 {j+1}',value=option,key=f'qo_{qid}_{i}_{j}'))
                answer=st.radio(f'{i}번 정답',[0,1,2,3],index=q['answer'],format_func=lambda x:f'{x+1}번',
                                horizontal=True,key=f'qa_{qid}_{i}')
                explanation=st.text_area(f'{i}번 해설',value=q['explanation'],height=70,key=f'qe_{qid}_{i}')
                edited.append(dict(q,prompt=prompt,options=options,answer=answer,explanation=explanation))
            if st.form_submit_button('초안 수정 저장',type='primary'):
                try:
                    svc.edit_draft(user,qid,title,edited,st.session_state[expected_key])
                    st.session_state.pop(expected_key,None)
                    _notice('초안 수정을 저장했습니다.'); st.rerun()
                except ERRORS as e: st.error(str(e))


def _preview(paper):
    with st.expander('문제·정답·해설 미리보기 (교사 전용)',expanded=True):
        for i,q in enumerate(paper['questions'],1):
            st.markdown(f'**{i}. {q["prompt"]}**')
            for j,option in enumerate(q['options'],1): st.write(f'{j}. {option}')
            st.caption(f'정답 {q["answer"]+1}번 · {q["explanation"]}')
        st.info('이 미리보기는 교사 전용입니다. 학생에게는 결과 공개 전까지 정답·해설을 전송하지 않습니다.')


def _create_view(user):
    st.subheader('단원별 개념확인 퀴즈 만들기')
    st.caption('기본 문항 틀의 수치·보기를 바꾸어 4지선다 10문항을 생성합니다. AI나 새 API 키가 필요하지 않습니다.')
    cols=st.columns(2)
    subject=cols[0].selectbox('과목 선택',SUBJECTS,key='qgen_subject')
    choices=svc.units(subject)
    unit=cols[1].selectbox('단원 선택',choices,key=f'qgen_unit_{subject}')
    bank_unit=unit
    if unit not in bank.units(subject):
        st.info('사용자 정의 단원입니다. 출제 내용에 맞는 기본 단원을 연결하세요.')
        bank_unit=st.selectbox('기본 출제 단원',bank.units(subject),key=f'qgen_base_{subject}')
    st.button('＋ 개념확인 10문항 만들기',type='primary',on_click=_make,args=(user,subject,unit,bank_unit))
    drafts=[q for q in svc.list_quizzes(user) if q['state']=='draft']
    if not drafts:
        st.info('과목과 단원을 선택한 뒤 10문항 만들기를 눌러 주세요.'); return
    ids=[q['id'] for q in drafts]; labels={q['id']:q['title'] for q in drafts}
    active=st.session_state.get('_quiz_draft')
    if active not in ids: active=ids[0]
    # Selectbox callback keeps a separate durable selection across page switches.
    selected=st.selectbox('검토할 초안',ids,index=ids.index(active),format_func=labels.get,key='q_draft_selector')
    st.session_state['_quiz_draft']=selected
    paper=svc.teacher_paper(user,selected)
    st.markdown(f'### {paper["title"]}')
    _preview(paper); _editor(user,paper)
    st.markdown('#### 배포 대상')
    roster=svc.roster(user)
    preselected=st.session_state.get('_quiz_draft_targets',{}).get(selected,[])
    default_classes=sorted({s['class'] for s in roster if s['id'] in preselected}) if preselected else []
    classes=st.multiselect('배포할 학급 (1-1~1-7)',CLASSES,default=default_classes,
                           format_func=lambda x:f'{x}반',key=f'qclasses_{selected}')
    targets=[s for s in roster if s['class'] in classes]
    labels={s['id']:f'{s["class"]}반 · {s["name"]} ({s["id"]})' for s in targets}
    scope=st.radio('배포 방식',['선택한 반 전체','학생 선택'],index=1 if preselected else 0,
                   horizontal=True,key=f'qscope_{selected}')
    student_ids=None
    if scope=='학생 선택':
        student_ids=st.multiselect('배포할 학생',list(labels),default=[s for s in preselected if s in labels],
                                   format_func=labels.get,key=f'qtargets_{selected}')
    count=len(targets) if student_ids is None else len(student_ids)
    st.caption(f'등록된 대상 {count}명 · 반별/학생별로 배포합니다. 배포 후 등록되는 새 학생은 자동 추가되지 않습니다.')
    reviewed=st.checkbox('문제·보기·정답을 검토했으며 선택한 학생에게 배포합니다.',key=f'qreview_{selected}')
    if st.button('검토한 퀴즈 배포',type='primary',key=f'qpublish_{selected}',disabled=not reviewed or not count):
        try:
            svc.publish(user,selected,classes,student_ids,reviewed=reviewed)
            st.session_state['_quiz_open_id']=selected
            st.session_state['_quiz_go_monitor']=True
            _notice('배포를 저장했습니다. 학생은 수업도구 → 4. 퀴즈에서 참여합니다.'); st.rerun()
        except ERRORS as e: st.error(str(e))
    if st.button('초안 저장 확인·재시도',key=f'qflush_draft_{selected}'):
        try: svc.flush(user,selected); st.success('저장을 확인했습니다.')
        except ERRORS as e: st.warning(str(e))
    _pending_line(user,selected)


def _grade_action(user,qid,ids,incomplete):
    try:
        result=svc.grade(user,qid,ids,include_incomplete=incomplete)
        _notice(f'채점 {result["graded"]}명 · 이미 채점 {result["already"]}명 · 아직 풀이 중 {result["skipped"]}명')
    except ERRORS as e: _notice(str(e),False)


def _release_action(user,qid,ids,confirmed):
    try:
        if not confirmed: raise svc.QuizError('공개 확인란을 선택하세요.')
        n=svc.release(user,qid,ids); _notice(f'{n}명의 채점 결과와 정답·해설을 공개했습니다.')
    except ERRORS as e: _notice(str(e),False)


def _close_action(user,qid):
    try: svc.close(user,qid); _notice('퀴즈를 종료했습니다. 저장된 답은 남아 있으며 교사가 채점할 수 있습니다.')
    except ERRORS as e: _notice(str(e),False)


def _flush_action(user,qid):
    try: svc.flush(user,qid); _notice('영구 저장을 확인했습니다.')
    except ERRORS as e: _notice(str(e),False)


def _monitor_body(user,prefix):
    _show_notice()
    quizzes=[q for q in svc.list_quizzes(user) if q['state'] in ('open','closed')]
    if not quizzes:
        st.info('배포된 퀴즈가 없습니다. 먼저 10문항을 만들고 학생에게 배포하세요.'); return
    ids=[q['id'] for q in quizzes]; labels={q['id']:q['title'] for q in quizzes}
    active=st.session_state.get('_quiz_open_id')
    key=f'{prefix}_quiz'
    if key not in st.session_state or st.session_state[key] not in ids:
        st.session_state[key]=active if active in ids else ids[0]
    qid=st.selectbox('현황을 볼 퀴즈',ids,format_func=labels.get,key=key)
    paper=svc.teacher_paper(user,qid)
    cls=st.selectbox('대시보드 학급',['전체']+paper['classes'],key=f'{prefix}_cls_{qid}')
    board=svc.dashboard(user,qid,cls)
    st.html(dashboard_html(board))
    st.caption('현재 화면을 열어 둔 동안 약 2초 간격으로 같은 앱 서버의 응답을 확인합니다. GitHub 영구 저장 대기와 구분해서 표시합니다.')
    _pending_line(user,qid)
    student_labels={s['id']:f'{s["class"]}반 {s["name"]} ({s["id"]}) · {s["count"]}/10' for s in board['students']}
    if not student_labels: return
    selected=st.selectbox('개별 채점할 학생',list(student_labels),format_func=student_labels.get,key=f'{prefix}_sid_{qid}')
    incomplete=st.checkbox('풀이 중·미응답 학생도 현재 답으로 채점합니다. 미응답은 X(0점)이며 채점 후 수정할 수 없습니다.',
                           key=f'{prefix}_incomplete_{qid}')
    cols=st.columns(3)
    cols[0].button('개별 채점',on_click=_grade_action,args=(user,qid,[selected],incomplete),key=f'{prefix}_grade_one_{qid}',width='stretch')
    cols[1].button(f'일괄 채점 · 현재 대상 {len(student_labels)}명',type='primary',on_click=_grade_action,
                   args=(user,qid,list(student_labels),incomplete),key=f'{prefix}_grade_all_{qid}',width='stretch')
    cols[2].button('저장 확인·재시도',on_click=_flush_action,args=(user,qid),key=f'{prefix}_flush_{qid}',width='stretch')
    st.caption('기본 채점 대상은 제출한 학생 또는 10문항을 모두 선택한 학생입니다. 채점한 답안은 잠기며, 정답은 아직 학생에게 공개되지 않습니다.')
    with st.expander('학생에게 결과 공개 · 수업 종료'):
        confirm=st.checkbox('선택 범위의 채점된 학생에게 점수·O/X·정답·해설을 공개합니다.',key=f'{prefix}_confirm_release_{qid}')
        scope=st.radio('결과 공개 범위',['현재 반 전체','선택한 학생 1명'],horizontal=True,key=f'{prefix}_release_scope_{qid}')
        st.button('학생에게 결과 공개',disabled=not confirm,on_click=_release_action,
                  args=(user,qid,list(student_labels) if scope=='현재 반 전체' else [selected],confirm),key=f'{prefix}_release_{qid}')
        end=st.checkbox('퀴즈를 종료하여 아직 채점하지 않은 학생도 답을 더 이상 바꾸지 못하게 합니다.',key=f'{prefix}_end_confirm_{qid}')
        st.button('퀴즈 종료',disabled=not end or paper['state']=='closed',on_click=_close_action,args=(user,qid),key=f'{prefix}_close_{qid}')
    with st.expander('학생 상세 답안 · 개인 기록'):
        row=next(s for s in board['students'] if s['id']==selected)
        st.write(f'{row["name"]} · {row["class"]}반 · 최근 응답 {row["updated_at"][:19] or "아직 없음"}')
        table=[]
        for i,q in enumerate(board['questions'],1):
            choice=row['answers'].get(q['id'])
            table.append({'문항':i,'개념':q['concept'],'선택':'미응답' if choice is None else str(choice+1),
                          '결과':('O' if row['marks'][q['id']] else 'X') if row['state']=='graded' else '채점 전'})
        st.dataframe(table,hide_index=True,width='stretch')
        _history(user,selected,prefix+qid)
    st.download_button('이 퀴즈 전체 응답·채점표 CSV',svc.export_dashboard(user,qid),
                       file_name=f'quiz_{qid[:8]}_results.csv',mime='text/csv',key=f'{prefix}_csv_{qid}')
    with st.expander('추가 10문항 만들기 · 보충 퀴즈 배포'):
        threshold=st.slider('보충 대상 추천 점수 (미만)',0,100,60,10,key=f'{prefix}_threshold_{qid}')
        recommended,concepts=svc.recommend(user,qid,threshold)
        mode=st.radio('추가 퀴즈 대상',['기준 점수 미만','직접 학생 선택','현재 반 전체'],horizontal=True,key=f'{prefix}_extra_mode_{qid}')
        eligible={s['id']:student_labels[s['id']] for s in board['students']}
        if mode=='기준 점수 미만':
            targets=[sid for sid in recommended if sid in eligible]
            st.caption(f'채점된 학생 중 {threshold}점 미만 {len(targets)}명. 미채점 학생은 점수로 추정하지 않습니다.')
        elif mode=='직접 학생 선택':
            targets=st.multiselect('추가 배포 학생',list(eligible),format_func=eligible.get,key=f'{prefix}_extra_ids_{qid}')
        else: targets=list(eligible)
        tags=list(dict.fromkeys(q['concept'] for q in paper['questions']))
        focus=st.multiselect('우선 복습할 개념',tags,default=[x for x in concepts if x in tags],key=f'{prefix}_focus_{qid}')
        st.caption('기존 문제와 동일한 발문을 피하고, 선택한 개념을 우선 포함합니다. 생성 후 문제 검토·배포 화면으로 이동합니다. 기존 점수는 그대로 남습니다.')
        st.button('추가 10문항 생성',on_click=_followup,args=(user,qid,targets,focus),disabled=not targets,
                  key=f'{prefix}_extra_{qid}',type='primary')


def render_monitor(user,prefix='quiz_tools'):
    auto=st.toggle('응답 현황 자동 새로고침 (2초)',value=True,key=f'{prefix}_auto')
    try:
        st.fragment(_monitor_guarded,run_every=2 if auto else None)(user,prefix)
    except ERRORS as e: st.error(str(e))


def _monitor_guarded(user,prefix):
    if st.session_state.pop('_quiz_full_rerun',False):
        st.rerun()  # Outside callback: promote fragment interaction to app navigation.
    try: _monitor_body(user,prefix)
    except ERRORS as e: st.error(str(e))
    except Exception:
        st.error('퀴즈 현황을 불러오지 못했습니다. 저장소 연결을 확인한 뒤 새로고침하세요.')


def _history(user,sid,prefix):
    records=svc.history(user,sid)
    if not records: st.caption('아직 저장된 퀴즈 응답이 없습니다.'); return
    st.dataframe([{'날짜':r['updated_at'][:10],'과목':r['subject'],'단원':r['unit'], '회차':r['round'],
                   '퀴즈':r['title'],'상태':STATE.get(r['attempt_state'],r['attempt_state']),
                   '점수':f'{r["score"]}점' if r.get('score') is not None else '공개 전/미채점'} for r in records],
                  hide_index=True,width='stretch')
    if records[0].get('storage_path'): st.caption('개인 파일: '+records[0]['storage_path'])
    digest=hashlib.sha256(sid.encode()).hexdigest()[:12]
    st.download_button('개인 퀴즈 기록 JSON',json.dumps(records,ensure_ascii=False,indent=2).encode(),
                       file_name=f'quiz_student_{digest}.json',mime='application/json',key=f'{prefix}_personal_json_{digest}')


def _history_view(user):
    roster=svc.roster(user)
    if not roster: st.info('등록된 학생이 없습니다.'); return
    labels={s['id']:f'{s["class"]}반 · {s["name"]} ({s["id"]})' for s in roster}
    sid=st.selectbox('개인 기록을 볼 학생',list(labels),format_func=labels.get,key='quiz_history_student')
    _history(user,sid,'quiz_history')


def _mark(user,qid,item,key,rev):
    try:
        svc.save_answer(user,qid,item,st.session_state.get(key),rev)
    except ERRORS as e: _notice(str(e),False)
    except Exception: _notice('선택한 답을 저장하지 못했어요. 저장된 답을 확인하고 다시 선택해 주세요.',False)


def _student_body(user):
    _show_notice()
    quizzes=svc.list_quizzes(user)
    if not quizzes: st.info('아직 배포받은 퀴즈가 없습니다. 선생님이 배포하면 여기에 나타납니다.'); return
    ids=[q['id'] for q in quizzes]; labels={q['id']:q['title'] for q in quizzes}
    key=f'qstudent_{user["id"]}'
    if key not in st.session_state or st.session_state[key] not in ids:
        active=st.session_state.get('_quiz_open_id'); st.session_state[key]=active if active in ids else ids[0]
    qid=st.selectbox('배포된 퀴즈',ids,format_func=labels.get,key=key)
    paper=svc.student_paper(user,qid)
    st.markdown(f'### {paper["title"]}')
    st.progress(len(paper['answers'])/10,text=f'답 선택 {len(paper["answers"])}/10')
    _pending_line(user,qid)
    if paper['released']:
        st.success(f'채점 결과 {paper["score"]}점 / 100점')
    elif paper['attempt_state']=='graded': st.info('선생님이 채점했습니다. 결과가 공개되면 점수와 해설을 볼 수 있어요.')
    else: st.info('선택한 답은 선생님 화면에 전달됩니다. 정답과 점수는 선생님이 채점하고 공개한 뒤 확인해요.')
    import realtime
    locked=realtime.is_locked(svc.current_actor(user).get('class',''))
    if locked: st.warning('지금은 선생님 설명 시간입니다. 답은 보존되며 수정은 잠시 멈춥니다.')
    solutions={s['id']:s for s in paper.get('solutions',[])}
    for i,q in enumerate(paper['questions'],1):
        with st.container(border=True):
            st.markdown(f'**{i}. {q["prompt"]}**')
            wkey=f'qm_{user["id"]}_{qid}_{q["id"]}'
            # The store is authoritative after conflicts, grading or reconnects.
            st.session_state[wkey]=paper['answers'].get(q['id'])
            st.radio(f'{i}번 답 선택',list(range(4)),index=None,
                     format_func=lambda v,opts=q['options']:f'{v+1}. {opts[v]}',
                     key=wkey,on_change=_mark,args=(user,qid,q['id'],wkey,paper['revision']),
                     disabled=not paper['editable'] or locked,label_visibility='collapsed')
            if paper['released']:
                sol=solutions[q['id']]
                (st.success if paper['marks'][q['id']] else st.warning)('O 정답' if paper['marks'][q['id']] else 'X 다시 확인해요')
                st.write(f'정답: {sol["answer"]+1}번 · {q["options"][sol["answer"]]}')
                st.caption(sol['explanation'])
    if paper['editable'] and not locked:
        allow_blank=False
        if len(paper['answers'])<10:
            allow_blank=st.checkbox('미응답 문항이 있는 상태로 제출합니다. 미응답은 채점 시 0점입니다.',key=f'qblank_{qid}_{user["id"]}')
        if st.button('최종 제출 · 저장 확인',type='primary',key=f'qsubmit_{qid}_{user["id"]}',
                     disabled=len(paper['answers'])<10 and not allow_blank):
            try:
                svc.submit(user,qid,allow_blank=allow_blank)
                _notice('최종 제출과 저장을 확인했습니다. 정답은 아직 공개되지 않습니다.'); st.rerun(scope='fragment')
            except ERRORS as e: st.error(str(e))
    else:
        st.caption('제출·채점·종료 후에는 기존 답안을 수정하지 않습니다. 추가 연습은 새 퀴즈에서 이어갑니다.')
    if st.button('저장 확인·재시도',key=f'qstudent_flush_{qid}_{user["id"]}'):
        try: svc.flush(user,qid); st.success('현재 답안의 저장을 확인했습니다.')
        except ERRORS as e: st.warning(str(e))
    with st.expander('나의 퀴즈 기록'):
        _history(user,user['id'],f'q_student_hist_{qid}')


def _student_guarded(user):
    try: _student_body(user)
    except ERRORS as e: st.warning(str(e))
    except Exception: st.error('퀴즈를 불러오지 못했습니다. 연결을 확인하고 다시 열어 주세요.')


def page(user):
    st.session_state.pop('_quiz_full_rerun',None)
    actor=svc.current_actor(user)
    pending=st.session_state.pop('_quiz_next_draft',None)
    if pending and actor['role']=='teacher':
        qid,ids=pending
        st.session_state['_quiz_draft']=qid
        st.session_state['q_draft_selector']=qid
        st.session_state.setdefault('_quiz_draft_targets',{})[qid]=ids
        st.session_state['quiz_teacher_section']='퀴즈 만들기'
    if st.session_state.pop('_quiz_go_monitor',False):
        st.session_state['quiz_teacher_section']='응답·채점 대시보드'
        st.session_state['quiz_tools_quiz']=st.session_state.get('_quiz_open_id')
    if actor['role']=='teacher':
        _show_notice()
        section=st.radio('퀴즈 관리',['퀴즈 만들기','응답·채점 대시보드','학생 개인 기록'],
                         horizontal=True,key='quiz_teacher_section')
        try:
            if section=='퀴즈 만들기': _create_view(user)
            elif section=='응답·채점 대시보드': render_monitor(user)
            else: _history_view(user)
        except ERRORS as e: st.error(str(e))
    else:
        st.fragment(_student_guarded,run_every=3)(user)


def teacher_dashboard(user):
    try:
        if not svc.list_quizzes(user):
            st.info('수업도구 → 4. 퀴즈에서 개념확인 문제를 만들고 배포할 수 있습니다.')
            st.button('퀴즈 만들러 가기',on_click=_navigate,key='dashboard_quiz_start')
            return
        st.subheader('개념퀴즈 · 학생별 응답과 채점')
        st.button('퀴즈 만들기·개인 기록 메뉴 열기',on_click=_navigate,key='dashboard_quiz_open')
        render_monitor(user,'quiz_dashboard')
    except ERRORS as e: st.warning(str(e))


def _home_body(user):
    if st.session_state.pop('_quiz_full_rerun',False):
        st.rerun()
    try:
        quizzes=svc.list_quizzes(user)
        if not quizzes: return
        with st.container(border=True):
            st.markdown('### 나의 개념퀴즈')
            st.caption(f'배포받은 퀴즈 {len(quizzes)}개 · 공개된 결과는 내 개인 기록에서 확인해요.')
            labels={q['id']:q['title'] for q in quizzes}
            qid=st.selectbox('참여할 퀴즈',list(labels),format_func=labels.get,key='home_quiz_select')
            st.button('퀴즈 참여·결과 확인',on_click=_navigate,args=(qid,),key='home_quiz_open',type='primary')
    except ERRORS as e: st.caption(str(e))


def student_home(user):
    st.fragment(_home_body,run_every=5)(user)
