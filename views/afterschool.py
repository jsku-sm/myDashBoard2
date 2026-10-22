"""과목별 방과후 게시판과 교사전용 기수 관리. 기존 기록은 공통수학2로 호환."""
from __future__ import annotations

import html
import uuid
from datetime import date,datetime,time

import pandas as pd
import streamlit as st
from config import CLASSES, TZ
from afterschool_core import service as svc
from afterschool_core import presentation as design


def _token(key):
    return st.session_state.setdefault('_as_op_'+key,uuid.uuid4().hex)


def _action(fn,message,token_key=None,clear_keys=()):
    try:
        result=fn()
    except svc.SavePendingError as exc:
        st.session_state['_as_pending']={'id':exc.record_id,'token_key':token_key,'message':message,'clear_keys':list(clear_keys)}
        st.rerun()
    except (ValueError,PermissionError) as exc:
        st.error(str(exc)); return False
    except Exception:
        st.error('처리하지 못했어요. 연결 상태를 확인해 주세요. 입력 내용은 유지됩니다.'); return False
    if token_key:
        st.session_state.pop('_as_op_'+token_key,None)
    st.session_state['_as_clear_keys']=list(clear_keys)
    st.session_state['_as_flash']=message+(f' · 기록번호 {result[:8]}' if isinstance(result,str) and result else '')
    st.rerun()


def _notice(user):
    # Apply input resets before their widgets are created on the next run.
    for key in st.session_state.pop('_as_clear_keys',[]):
        # Deleting an existing widget key can restore its old frontend value.
        # Assign explicit defaults before the widget is rendered instead.
        if key.startswith('as_member_input_'):
            st.session_state[key]=''
        elif key.startswith('as_bulk_ids_'):
            st.session_state[key]=[]
        else:
            st.session_state.pop(key,None)
    flash=st.session_state.pop('_as_flash',None)
    if flash: st.success(flash)
    pending=st.session_state.get('_as_pending')
    if pending:
        st.warning('서버에 반영됐지만 영구 저장 확인이 필요해요. 재등록하지 말고 저장을 다시 확인하세요. 자동 재시도도 진행됩니다.')
        if st.button('저장 다시 확인',key='as_retry'):
            try: svc.retry_save(user)
            except Exception: st.error('아직 저장을 확인하지 못했어요. GitHub 설정과 연결을 확인해 주세요.')
            else:
                if pending.get('token_key'): st.session_state.pop('_as_op_'+pending['token_key'],None)
                st.session_state['_as_clear_keys']=pending.get('clear_keys',[])
                st.session_state.pop('_as_pending',None)
                st.session_state['_as_flash']=pending.get('message','저장을 확인했어요.')
                st.rerun()
        return True
    return False


def _pick(rows,key,label='기수 선택'):
    byid={c['id']:c for c in rows}
    if st.session_state.get(key) not in byid: st.session_state[key]=next(iter(byid))
    selected=st.radio(label,list(byid),format_func=lambda cid:f'{byid[cid]["subject"]} · {byid[cid]["year"]} · {byid[cid]["name"]}',
                      horizontal=True,key=key)
    return byid[selected]


def _header(c,teacher=False):
    st.markdown(design.hero(c,svc.STATES[c['state']],teacher),unsafe_allow_html=True)
    if c['state']=='archived':
        st.info('종료한 기수입니다. 자료·질문·본인의 제출/피드백을 읽고 내려받을 수 있지만 새 글·댓글·과제 제출은 할 수 없어요.')
    elif c['state'] in ('draft','closed'):
        st.caption('이 기수는 학생에게 보이지 않습니다. 설정에서 운영 중으로 바꾸면 배정 학생에게 공개됩니다.')


def _files(user,record,kind,prefix):
    if not record.get('attachments'): return
    from afterschool_core.downloads import render
    for i,f in enumerate(record.get('attachments',[])):
        render(user,kind,record['id'],i,f['name'],prefix=prefix)


def _cohort_fields(c,prefix):
    a,b=st.columns([1,2])
    year=a.number_input('학년도',min_value=2000,max_value=2100,value=int(c.get('year',datetime.now(TZ).year)),step=1,key=prefix+'year')
    name=b.text_input('기수명',value=c.get('name',''),placeholder='예: 1기, 2기, 겨울방학반',max_chars=80,key=prefix+'name')
    subject=st.selectbox('운영 과목 (한 기수에 한 과목)',list(svc.SUBJECTS),
                         index=list(svc.SUBJECTS).index(c.get('subject',svc.LEGACY_SUBJECT)),key=prefix+'subject')
    st.caption('배정 학생의 해당 과목에만 방과후 탭이 표시됩니다. 과목을 바꾸면 기존 명단·자료·제출물 전체가 새 과목에서 열립니다.')
    desc=st.text_area('기수 안내',value=c.get('description',''),key=prefix+'desc',height=90)
    x,y=st.columns(2)
    start=x.date_input('시작일 (선택)',value=date.fromisoformat(c['start_date']) if c.get('start_date') else None,key=prefix+'start')
    end=y.date_input('종료일 (선택)',value=date.fromisoformat(c['end_date']) if c.get('end_date') else None,key=prefix+'end')
    state=st.selectbox('운영 상태',list(svc.STATES),index=list(svc.STATES).index(c.get('state','draft')),
                       format_func=lambda v:svc.STATES[v],key=prefix+'state')
    st.caption('종료일은 안내용입니다. 종료 시 직접 ‘종료 · 읽기 전용’으로 변경하세요. ‘학생 접근 종료’는 자료 열람도 막습니다.')
    return dict(year=year,name=name,subject=subject,description=desc,start_date=start,end_date=end,state=state)


def teacher_page(user):
    st.markdown(design.styles(),unsafe_allow_html=True)
    with st.container(key='as_admin_shell'):
        _teacher_page(user)


def _teacher_page(user):
    try:
        svc.require_teacher(user)
        if _notice(user): return
        st.subheader('🌙 방과후 관리')
        st.caption('과목과 기수를 정하고 학생을 배정하세요. 자료·과제·질문·제출까지 이곳에서 관리합니다.')
        rows=svc.list_cohorts(user)
        with st.expander('＋ 새 기수 만들기',expanded=not rows):
            opkey='create_cohort'; op=_token(opkey)
            with st.form('as_new_'+op,enter_to_submit=False):
                payload=_cohort_fields({},'as_new_'+op)
                ok=st.form_submit_button('기수 추가',type='primary')
            if ok: _action(lambda:svc.create_cohort(user,payload,op),'새 기수를 만들었어요.',opkey)
        if not rows:
            st.info('아직 기수가 없어요. 필요한 기수를 하나씩 만들어 주세요.'); return
        c=_pick(rows,'as_manage_cohort')
        _header(c,True)
        menu=st.radio('관리 메뉴',['기수 설정','참여 학생','자료·과제','질문·댓글','제출 확인'],horizontal=True,key='as_manage_menu')
        if menu=='기수 설정': _settings(user,c)
        elif menu=='참여 학생': _members(user,c)
        elif menu=='자료·과제': _materials(user,c)
        elif menu=='질문·댓글': _post_list(user,c,'question','manage_questions',manage=True)
        else: _teacher_submissions(user,c)
    except (PermissionError,ValueError) as exc: st.error(str(exc))
    except Exception: st.error('방과후 정보를 불러오지 못했어요. 저장소 연결 상태를 확인해 주세요.')


def _settings(user,c):
    with st.form('as_settings_'+c['id']+'_'+c['revision'],enter_to_submit=False):
        payload=_cohort_fields(c,'as_edit_'+c['id']+'_'+c['revision'])
        confirm=st.checkbox('설정과 학생 접근 범위 변경을 확인했습니다.')
        ok=st.form_submit_button('기수 설정 저장',type='primary')
    if ok:
        if not confirm: st.warning('접근 범위 변경을 확인해 주세요.')
        else: _action(lambda:svc.update_cohort(user,c['id'],payload,c['revision']),'기수 설정을 저장했어요.')
    st.caption('기수 삭제 대신 준비 중/접근 종료 상태로 보관합니다. 학생 명단과 기존 제출물을 초기화하지 않습니다.')


def _members(user,c):
    """Enter only submits this form; blur/filter changes never assign a student."""
    cid=c['id']
    roster=svc.roster(user,cid)
    selected=[r for r in roster if r['selected']]
    candidates=[r for r in roster if not r.get('unavailable')]
    allby={r['id']:r for r in roster}
    st.markdown(design.stats([('현재 배정 인원',f'{len(selected)}명'),
                             ('운영 과목',c['subject']),('기수 상태',svc.STATES[c['state']])]),unsafe_allow_html=True)
    input_key='as_member_input_'+cid
    search_key='as_member_search_'+cid
    remove_key='as_remove_pending_'+cid

    with st.container(key='as_add_panel_'+cid):
        st.markdown('#### 학번으로 바로 배정')
        st.caption('정확한 학번 + Enter → 배정 저장. 이름은 검색 결과에서 확인한 뒤 선택하세요.')
        with st.form('as_quick_add_'+cid,enter_to_submit=True):
            query=st.text_input('학번·이름 검색',placeholder='학번 입력 후 Enter / 이름 입력 후 Enter로 검색',
                                key=input_key,max_chars=100).strip()
            entered=st.form_submit_button('배정 / 검색 ↵',type='primary')
        if entered:
            if not query:
                st.warning('학번 또는 이름을 입력해 주세요.')
            elif query in allby and not allby[query].get('unavailable'):
                if allby[query]['selected']:
                    st.info(f'{allby[query]["name"]} ({query}) 학생은 이미 배정되어 있어요. 인원은 늘어나지 않습니다.')
                    st.session_state[search_key]=''
                else:
                    _action(lambda:svc.add_member(user,cid,query,c['revision']),
                            f'{allby[query]["name"]} ({query}) 학생을 배정했어요.',
                            clear_keys=(input_key,search_key))
            else:
                st.session_state[search_key]=query
        # Name/partial-id entry must not auto-assign even a single result.
        search=st.session_state.get(search_key,'')
        if search:
            matches=[r for r in candidates if search.casefold() in r['id'].casefold() or search.casefold() in r['name'].casefold()]
            if not matches:
                st.warning('일치하는 가입 학생이 없어요. 정확한 학번을 확인하세요. 새 학생 계정은 자동으로 만들지 않습니다.')
            else:
                st.caption(f'검색 결과 {len(matches)}명 · 이름만 입력한 경우 아래에서 배정할 학생을 확인하세요.')
                for r in matches:
                    left,right=st.columns([4,1])
                    left.markdown(design.person(r),unsafe_allow_html=True)
                    if right.button('이미 배정됨' if r['selected'] else '이 학생 배정',
                                    key='as_add_candidate_'+cid+'_'+r['id'],disabled=r['selected']):
                        _action(lambda sid=r['id']:svc.add_member(user,cid,sid,c['revision']),
                                f'{r["name"]} 학생을 배정했어요.',clear_keys=(input_key,search_key))
        with st.expander('여러 학생을 한 번에 추가하기'):
            cls=st.selectbox('추가할 학생의 학급',['전체']+CLASSES,key='as_bulk_class_'+cid)
            visible=[r for r in candidates if not r['selected'] and (cls=='전체' or r['class']==cls)]
            choice_key='as_bulk_ids_'+cid+'_'+c['revision']+'_'+cls
            choices=st.multiselect('추가할 학생 (여러 명 선택)',[r['id'] for r in visible],
                                  format_func=lambda sid:f'{allby[sid]["class"]} · {sid} {allby[sid]["name"]}',
                                  key=choice_key,placeholder='이름이나 학번으로 선택하세요')
            st.caption('현재 명단에서 선택을 해제하는 방식이 아닙니다. 선택한 학생만 추가하고 다른 배정은 그대로 유지합니다.')
            if st.button('선택 학생 추가',key='as_bulk_add_'+cid,disabled=not choices):
                _action(lambda:svc.add_members(user,cid,choices,c['revision']),
                        f'{len(choices)}명의 학생을 추가했어요.',clear_keys=(choice_key,input_key,search_key))

    with st.container(key='as_roster_panel_'+cid):
        a,b=st.columns(2)
        cls=a.selectbox('배정 명단 학급',['전체']+CLASSES,key='as_list_class_'+cid)
        query=b.text_input('배정 명단에서 찾기',key='as_list_search_'+cid,placeholder='학번 또는 이름 (목록 필터)').strip()
        shown=[r for r in selected if (cls=='전체' or r['class']==cls) and
               (not query or query.casefold() in r['id'].casefold() or query.casefold() in r['name'].casefold())]
        st.markdown(design.roster_heading(len(selected),len(shown)),unsafe_allow_html=True)
        st.caption('배정 취소는 이 기수에서만 제외합니다. 학생 계정·다른 기수·기존 제출 기록은 삭제하지 않습니다.')
        pending=st.session_state.get(remove_key)
        if pending:
            target=allby.get(pending['id'])
            if not target or not target['selected']:
                st.session_state.pop(remove_key,None)
            else:
                with st.container(border=True):
                    st.warning(f'{target["class"]} · {target["id"]} {target["name"]} 학생의 배정을 취소할까요?')
                    yes,no=st.columns(2)
                    if yes.button('배정 취소 확정',key='as_remove_confirm_'+cid,type='primary'):
                        _action(lambda:svc.remove_member(user,cid,target['id'],pending['revision']),
                                f'{target["name"]} 학생을 이 기수에서 제외했어요.',clear_keys=(remove_key,))
                    if no.button('유지하기',key='as_remove_keep_'+cid):
                        st.session_state.pop(remove_key,None);st.rerun()
                    if pending['revision'] != c['revision']:
                        st.caption('명단이나 설정이 변경되었습니다. 유지하기를 누른 뒤 최신 명단에서 다시 선택하세요.')
        if not selected:
            st.info('아직 배정한 학생이 없어요. 위에서 학번을 입력하고 Enter를 눌러 보세요.')
        elif not shown:
            st.info('검색 조건에 맞는 배정 학생이 없어요. 전체 배정 인원은 그대로 유지됩니다.')
        for r in shown:
            with st.container(key='as_member_row_'+cid+'_'+r['id']):
                left,right=st.columns([4,1])
                left.markdown(design.person(r),unsafe_allow_html=True)
                if right.button('배정 취소',key='as_remove_'+cid+'_'+r['id'],help='이 기수에서만 제외합니다.'):
                    st.session_state[remove_key]={'id':r['id'],'revision':c['revision']};st.rerun()
        if selected:
            st.download_button('배정 명단 CSV',svc.export_roster(user,cid),
                               file_name=f'방과후_{c["year"]}_{c["subject"]}_{c["name"]}_명단.csv',
                               mime='text/csv',key='as_roster_dl_'+cid)


def _post_fields(kind,prefix,p=None,edit=False):
    p=p or {}
    title=st.text_input('제목',value=p.get('title',''),max_chars=160,key=prefix+'title')
    body=st.text_area('내용',value=p.get('body',''),height=160,key=prefix+'body')
    lesson=st.date_input('수업일 (선택)',value=date.fromisoformat(p['lesson_date']) if p.get('lesson_date') else None,key=prefix+'lesson')
    links=st.text_area('자료 링크 (선택 · 한 줄에 하나)',value='\n'.join(p.get('links',[])),height=75,key=prefix+'links')
    st.caption('링크는 외부 사이트 자체의 권한이 적용됩니다. 명단 제한이 필요한 파일은 아래 첨부를 사용하세요.')
    files=[] if edit else st.file_uploader('첨부파일 (최대 3개 · 합계 10 MiB)',type=list(svc.EXTENSIONS),accept_multiple_files=True,key=prefix+'files')
    due=''; late=False
    if kind=='assignment':
        x,y=st.columns(2)
        parsed=datetime.strptime(p['due_at'],'%Y-%m-%d %H:%M:%S') if p.get('due_at') else None
        d=x.date_input('마감일 (없으면 기한 없음)',value=parsed.date() if parsed else None,key=prefix+'due_date')
        t=y.time_input('마감 시간 (한국 시간)',value=parsed.time() if parsed else time(23,59),key=prefix+'due_time')
        due=datetime.combine(d,t) if d else ''
        late=st.checkbox('마감 후 제출 허용',value=p.get('allow_late')=='1',key=prefix+'late')
    x,y,z=st.columns(3)
    published=x.checkbox('학생에게 공개',value=p.get('published')=='1',key=prefix+'pub')
    pinned=y.checkbox('상단 고정',value=p.get('pinned')=='1',key=prefix+'pin')
    comments=z.checkbox('댓글 허용',value=p.get('comments_enabled','1')=='1',key=prefix+'comments')
    return dict(kind=kind,title=title,body=body,lesson_date=lesson,links=links,published=published,pinned=pinned,
                comments_enabled=comments,due_at=due,allow_late=late,visibility='cohort'),files


def _materials(user,c):
    if c['state'] in ('draft','active'):
        with st.expander('＋ 수업자료 또는 과제 등록',expanded=False):
            kind=st.radio('등록 유형',['material','assignment'],format_func=lambda k:svc.KINDS[k],horizontal=True,key='as_kind_'+c['id'])
            opkey='newpost_'+c['id']+kind; op=_token(opkey)
            with st.form('as_post_'+op,enter_to_submit=False):
                payload,files=_post_fields(kind,'as_post_'+op)
                preview=st.form_submit_button('내용 미리보기')
                ok=st.form_submit_button('자료·과제 저장',type='primary')
            if preview:
                st.markdown('##### 학생에게 보일 내용 미리보기'); st.text(payload['title']);st.text(payload['body'])
                st.caption('공개 체크를 켜도 기수가 준비 중이면 학생은 접근할 수 없어요.')
            if ok: _action(lambda:svc.create_post(user,c['id'],payload,files,op),'자료·과제를 저장했어요.',opkey)
    else: st.info('이 기수는 읽기 전용입니다. 새 자료를 등록하려면 기수 상태를 운영 중으로 바꾸세요.')
    _post_list(user,c,None,'manage_materials',manage=True,exclude_questions=True)


def student_board(user,subject='공통수학2'):
    """Subject-filtered student workspace. Teacher controls never appear here."""
    if subject not in svc.SUBJECTS:
        st.warning('지원하는 과목을 선택해 주세요.');return
    st.markdown(design.styles(),unsafe_allow_html=True)
    shell='as_student_math1' if subject=='공통수학1' else 'as_student_math2'
    with st.container(key=shell):
        _student_board(user,subject)


def _student_board(user,subject):
    try:
        if _notice(user): return
        rows=svc.list_cohorts(user,subject)
        if not rows:
            if user['role']=='teacher':
                st.info('이 과목의 기수가 없어요. 교사전용 → 방과후 관리에서 기수를 추가하세요.')
            return
        suffix='math1' if subject=='공통수학1' else 'math2'
        st.subheader('🌙 방과후 게시판')
        if st.button('게시판 새로고침',key='as_board_refresh_'+suffix): st.rerun()
        if user['role']=='teacher':
            st.caption('열람 화면입니다. 기수·학생·자료 설정과 답변/피드백은 교사전용 → 방과후 관리에서 합니다.')
        selected=_pick(rows,'as_student_cohort_'+suffix)
        c=svc.get_cohort(user,selected['id'],subject=subject)
        _header(c,user['role']=='teacher')
        menu=st.radio('게시판',['자료·과제','질문·댓글','내 제출 확인'],horizontal=True,
                      key='as_board_section_'+suffix+'_'+c['id'])
        if menu=='내 제출 확인':
            if user['role']=='teacher':
                st.info('학생은 이곳에서 본인 기록만 확인합니다. 전체 제출 현황과 피드백 관리는 교사전용 → 방과후 관리 → 제출 확인에서 합니다.')
            else:
                _student_receipts(user,c,'board_receipts_'+suffix)
            return
        if menu=='질문·댓글' and c['writable'] and user['role']=='student':
            with st.expander('✋ 질문 작성'):
                opkey='question_'+c['id']; op=_token(opkey)
                with st.form('as_q_'+op,enter_to_submit=False):
                    title=st.text_input('질문 제목',key='as_q_title_'+op,max_chars=160)
                    body=st.text_area('질문 내용',key='as_q_body_'+op)
                    scope=st.radio('질문 공개 범위',['private','cohort'],format_func=lambda v:'선생님과 나만' if v=='private' else '이 기수 참여 학생',horizontal=True,key='as_q_scope_'+op)
                    files=st.file_uploader('질문 첨부 (선택 · 합계 10 MiB)',type=list(svc.EXTENSIONS),accept_multiple_files=True,key='as_q_files_'+op)
                    ok=st.form_submit_button('질문 올리기',type='primary')
                if ok:
                    _action(lambda:svc.create_post(user,c['id'],{'kind':'question','title':title,'body':body,'visibility':scope},files,op),'질문을 올렸어요.',opkey)
        kind='question' if menu=='질문·댓글' else None
        _post_list(user,c,kind,'board_'+suffix+'_'+str(kind),manage=False,exclude_questions=kind is None)
    except (ValueError,PermissionError) as exc: st.warning(str(exc))
    except Exception: st.error('방과후 게시판을 불러오지 못했어요. 연결 상태를 확인해 주세요.')


def _student_receipts(user,c,prefix):
    """No all-student roster or answers are requested by this view."""
    assignments=svc.list_posts(user,c['id'],'assignment')
    if not assignments:
        st.info('공개된 과제가 없어요.');return
    summaries=[];records_by={}
    for p in assignments:
        records=svc.submissions(user,p['id'])  # service returns only caller's own attempts
        records_by[p['id']]=records
        latest=records[0] if records else None
        summaries.append({'과제':p['title'],'상태':'제출 완료' if latest else '미제출',
                          '최근 제출':latest['created_at'] if latest else '—',
                          '제출 차수':str(latest['attempt'])+'차' if latest else '—',
                          '피드백':'도착' if latest and latest['feedback'] else '—'})
    submitted=sum(bool(records_by[p['id']]) for p in assignments)
    st.markdown(design.stats([('전체 과제',f'{len(assignments)}개'),('제출 완료',f'{submitted}개'),
                             ('미제출',f'{len(assignments)-submitted}개')]),unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(summaries),hide_index=True,width='stretch')
    byid={p['id']:p for p in assignments};key='as_receipt_assignment_'+c['id']
    if st.session_state.get(key) not in byid:st.session_state.pop(key,None)
    pid=st.selectbox('내 제출 상세 확인',list(byid),format_func=lambda i:byid[i]['title'],key=key)
    st.caption('본인의 제출 이력과 공개된 피드백만 표시됩니다. 답안 작성·재제출은 자료·과제에서 합니다.')
    _student_submission(user,c,byid[pid],prefix,allow_write=False)


def _post_list(user,c,kind,prefix,manage=False,exclude_questions=False):
    posts=svc.list_posts(user,c['id'],kind)
    if exclude_questions: posts=[p for p in posts if p['kind']!='question']
    if not manage and user['role']=='teacher': posts=[p for p in posts if p['published']=='1']
    if not posts: st.info('표시할 게시글이 없어요.');return
    byid={p['id']:p for p in posts};key=f'as_select_{prefix}_{c["id"]}'
    if st.session_state.get(key) not in byid: st.session_state.pop(key,None)
    pid=st.selectbox('게시글 선택',list(byid),format_func=lambda i:('📌 ' if byid[i]['pinned']=='1' else '')+
                     ('[초안] ' if byid[i]['published']!='1' else '')+byid[i]['title'],key=key)
    p=svc.get_post(user,pid)
    with st.container(border=True):
        st.markdown('#### '+html.escape(p['title']))
        st.caption(f'{svc.KINDS[p["kind"]]} · {p["created_at"][:16]} · '+('선생님과 작성자만' if p['visibility']=='private' else '기수 공개'))
        if p['lesson_date']: st.caption('수업일: '+p['lesson_date'])
        if p['kind']=='assignment':st.caption('마감: '+(p['due_at'] or '기한 없음')+(' · 기한 후 제출 허용' if p['allow_late']=='1' else ''))
        if p['kind']=='question':st.caption('✅ 해결됨' if p['resolved']=='1' else '질문 · 답변 확인 중')
        st.text(p['body'])
        _files(user,p,'post',prefix)
        for i,url in enumerate(p['links']): st.link_button(f'자료 링크 {i+1} ↗',url)
    if manage and p['kind']!='question' and c['state'] in ('draft','active'):
        with st.expander('✏️ 선택 자료·과제 수정'):
            with st.form('as_editpost_'+pid+'_'+p['revision'],enter_to_submit=False):
                payload,_=_post_fields(p['kind'],'as_editpost_'+pid+'_'+p['revision'],p,edit=True)
                st.caption('기존 첨부파일은 유지합니다. 첨부 교체는 새 자료를 등록해 주세요.')
                ok=st.form_submit_button('수정 저장')
            if ok: _action(lambda:svc.update_post(user,pid,payload,p['revision']),'자료·과제를 수정했어요.')
    if p['kind']=='assignment' and user['role']=='student': _student_submission(user,c,p,prefix)
    can_comment=c['writable'] and (user['role']=='student' or manage)
    st.markdown('##### 질문·댓글' if p['kind']!='question' else '##### 답변·댓글')
    for r in svc.comments(user,pid):
        st.caption(f'{r["author_name"]} · {r["created_at"][:16]}'); st.text(r['body'])
        if can_comment and (user['role']=='teacher' or r['author_id']==user['id']):
            if st.button('댓글 삭제',key=prefix+'_delcomment_'+r['id']):
                _action(lambda r=r:svc.delete_comment(user,r['id'],r['revision']),'댓글을 삭제했어요.')
    if can_comment and p['comments_enabled']=='1':
        opkey='comment_'+pid;op=_token(opkey)
        with st.form(prefix+'_comment_'+pid+'_'+op,enter_to_submit=False):
            body=st.text_area('댓글 / 답변',key=prefix+'_comment_body_'+op,height=80)
            ok=st.form_submit_button('댓글 등록')
        if ok:_action(lambda:svc.add_comment(user,pid,body,op),'댓글을 등록했어요.',opkey)
    elif p['comments_enabled']!='1': st.caption('댓글이 닫혀 있습니다.')
    if manage and p['kind']=='question' and c['writable']:
        if st.button('미해결로 변경' if p['resolved']=='1' else '해결 표시',key=prefix+'_resolve_'+pid):
            _action(lambda:svc.resolve_question(user,pid,p['resolved']!='1',p['revision']),'질문 상태를 변경했어요.')
    may_delete=(manage and c['state'] in ('draft','active')) or (user['role']=='student' and p['kind']=='question' and p['author_id']==user['id'] and c['writable'])
    if may_delete:
        with st.expander('게시글 삭제'):
            confirm=st.checkbox('이 글을 게시판에서 숨깁니다. 제출물이 있는 과제는 삭제할 수 없습니다.',key=prefix+'_delcheck_'+pid)
            if st.button('게시글 삭제',key=prefix+'_delete_'+pid,disabled=not confirm):
                _action(lambda:svc.delete_post(user,pid,p['revision']),'게시글을 숨겼어요. 원본 파일은 보존합니다.')


def _student_submission(user,c,p,prefix,allow_write=True):
    records=svc.submissions(user,p['id'])
    st.markdown('##### 나의 제출 기록')
    if not records: st.caption('아직 제출하지 않았어요.')
    for r in records:
        with st.expander(f'{r["attempt"]}차 제출 · {r["created_at"]}'+(' · 기한 후' if r['late']=='1' else ''),expanded=r==records[0]):
            st.caption('제출번호: '+r['id']); st.text(r['body']); _files(user,r,'submission',prefix)
            if r['feedback']: st.info('선생님 피드백\n\n'+r['feedback'])
    if c['writable'] and allow_write:
        opkey='submit_'+p['id'];op=_token(opkey)
        with st.form('as_submit_'+op,enter_to_submit=False):
            body=st.text_area('과제 답안',key='as_answer_'+op,height=150)
            files=st.file_uploader('과제 첨부 (선택 · 최대 3개, 합계 10 MiB)',type=list(svc.EXTENSIONS),accept_multiple_files=True,key='as_submit_files_'+op)
            st.caption('재제출하면 이전 답안은 보존하고 새 제출 차수를 만듭니다. 최종 제출 전 임시 자동 저장은 제공하지 않습니다.')
            ok=st.form_submit_button('새 차수로 재제출' if records else '과제 제출',type='primary')
        if ok: _action(lambda:svc.submit(user,p['id'],body,files,op),'과제 제출을 저장했어요.',opkey)


def _teacher_submissions(user,c):
    assignments=svc.list_posts(user,c['id'],'assignment')
    if not assignments: st.info('등록한 과제가 없어요. 자료·과제 메뉴에서 먼저 만드세요.');return
    byid={p['id']:p for p in assignments}
    key='as_grade_assignment_'+c['id']
    if st.session_state.get(key) not in byid:st.session_state.pop(key,None)
    pid=st.selectbox('확인할 과제',list(byid),format_func=lambda i:byid[i]['title'],key=key)
    rows=svc.submissions(user,pid)
    roster=svc.roster(user,c['id']);assigned=[r for r in roster if r['selected']]
    done={r['student_id'] for r in rows};active_ids={r['id'] for r in assigned}
    st.caption(f'현재 배정 {len(assigned)}명 · 제출한 배정 학생 {len(done & active_ids)}명 · 미제출 {len(active_ids-done)}명')
    if active_ids-done: st.write('미제출: '+', '.join(r['name']+' ('+r['id']+')' for r in assigned if r['id'] not in done))
    if done-active_ids: st.caption('명단에서 제외된 학생의 과거 제출물도 교사에게는 보존됩니다.')
    if not rows: st.info('제출된 답안이 없어요.');return
    st.dataframe(pd.DataFrame([{'학생':r['student_name'],'학번':r['student_id'],'제출 차수':int(r['attempt']),
                               '제출 시각':r['created_at'],'기한 후':'예' if r['late']=='1' else '',
                               '피드백':'작성됨' if r['feedback'] else '대기'} for r in rows]),hide_index=True,width='stretch')
    rowmap={r['id']:r for r in rows};rk='as_grade_record_'+pid
    if st.session_state.get(rk) not in rowmap:st.session_state.pop(rk,None)
    rid=st.selectbox('제출물 선택',list(rowmap),format_func=lambda i:f'{rowmap[i]["student_name"]} · {rowmap[i]["attempt"]}차 · {rowmap[i]["created_at"]}',key=rk)
    r=rowmap[rid];st.text(r['body']);_files(user,r,'submission','review')
    if c['writable']:
        with st.form('as_feedback_'+rid+'_'+r['revision'],enter_to_submit=False):
            body=st.text_area('학생에게 보여 줄 피드백',value=r['feedback'],key='as_fb_'+rid+'_'+r['revision'])
            ok=st.form_submit_button('피드백 저장 · 학생에게 공개',type='primary')
        if ok: _action(lambda:svc.feedback(user,rid,body,r['revision']),'피드백을 저장하고 공개했어요.')
    elif r['feedback']: st.info(r['feedback'])
