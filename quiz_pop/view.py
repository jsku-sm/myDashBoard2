"""Teacher-only creation and code-based student participation."""
import html
import json
from pathlib import Path
import re
import streamlit as st
from config import CLASSES
from . import api, service, classroom

_component = None


def config():
    try: return api.config(st.secrets.to_dict())
    except (FileNotFoundError, KeyError, st.errors.StreamlitSecretNotFoundError): return api.config({})


def dispatch(user, event, cfg, code=None):
    """Every RPC uses the stored login role and server-selected classroom."""
    actor = service.authorize(user, write=True)
    if len(json.dumps(event, ensure_ascii=False, allow_nan=False)) > 400000: raise ValueError('요청 내용이 너무 큽니다.')
    action = event.get('action')
    if action == 'generate':
        service.authorize(user, role='teacher', write=True)
        return api.call(action, event.get('payload'), cfg)
    if action == 'save':
        if actor['role'] == 'teacher':
            result=service.save(user, event.get('payload'), event.get('revision'))
            result['publication']=classroom.publish_current(user)
            return result
        if not code: raise PermissionError('참여코드로 입장한 학생만 풀이를 저장할 수 있어요.')
        return classroom.save(user, code, event.get('payload'), event.get('revision'))
    if action == 'guide':
        payload = event.get('payload')
        if actor['role'] == 'student':
            if not code: raise PermissionError('참여코드로 입장한 뒤 질문해 주세요.')
            payload = classroom.guide_payload(user, code, payload)
        return api.call(action, payload, cfg)
    if action == 'publish':
        service.authorize(user, role='teacher', write=True)
        return {'publication':classroom.publish_current(user,retry=True)}
    raise ValueError('지원하지 않는 퀴즈 요청입니다.')


def _component_renderer():
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        _component = components.declare_component('goodmath_quizpop', path=str(Path(__file__).with_name('frontend')))
    return _component


def component(user, data, cfg, code=None):
    render = _component_renderer()
    scope = user['id']+'_'+(code or 'teacher')
    replies = st.session_state.setdefault('_quizpop_replies_'+scope, {})
    event = render(data=data, enabled=cfg['enabled'], model=cfg['model'],
                       unavailableMessage=cfg.get('reason','') if data['preview'] else '생각 길잡이 AI 연결을 선생님께 확인해 주세요.',
                       reply=next(reversed(replies.values()),None) if replies else None,
                       key='quizpop_'+scope, default=None)
    if isinstance(event,dict) and isinstance(event.get('id'),str) and re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',event['id']):
        eid = event['id']
        if eid not in replies:
            result = {'id':eid,'ok':False,'error':'퀴즈 요청 처리 중 오류가 발생했습니다. 다시 시도해 주세요. [QUIZ_INTERNAL]'}
            try:
                value = dispatch(user,event,cfg,code)
                result = {'id':eid,'ok':True,'value':value}
            except (ValueError,PermissionError) as error: result['error']=str(error)
            except Exception: pass  # Never send raw provider errors or credentials.
            replies[eid]=result
            while len(replies)>40: replies.pop(next(iter(replies)))
            st.rerun()
    reply=next(reversed(replies.values()),None) if replies else None
    if reply and not reply['ok']: st.error(reply['error'])


def teacher_paper(user, code=None):
    """A separate, read-only component never sends practice saves or AI requests."""
    service.authorize(user, role='teacher')
    if code:
        paper = classroom.teacher_paper(user, code)
    else:
        saved = service.snapshot(user).get('saved')
        session = saved.get('session') if saved else None
        if not session or not session.get('questions'):
            return
        paper = {k: session[k] for k in ('title', 'stage', 'settings', 'questions')}
    with st.expander('생성한 문제 전체 확인 · 정답·해설', expanded=False):
        _component_renderer()(data=dict(userId=user['id'], role='teacher', preview=True, teacherPaper=paper),
                              key='quizpop_paper_'+user['id']+'_'+(code or 'current'), default=None)


def _settings(cfg):
    with st.expander('퀴즈 AI 연결 설정', expanded=not cfg['enabled']):
        st.text('API 키 위치: '+(cfg.get('key_source') or '설정 없음'))
        st.text('출제 모델: '+cfg['model'])
        if not cfg['enabled']: st.warning(cfg.get('reason') or '퀴즈용 OpenAI API 키를 설정해 주세요.')
        st.caption('기존 [openai], [school_record_ai], [snorkl] 또는 OPENAI_API_KEY 설정을 읽습니다. 별도 지정은 Streamlit Settings → Secrets의 [quiz_ai] 구역을 사용하세요.')
        st.code('[quiz_ai]\napi_key = "본인의 OpenAI API 키"\nmodel = "gpt-6-luna"\nenabled = true',language='toml')


def _save_status(user, code):
    status=classroom.save_status(user,code)
    st.caption('jsku-sm/class-dashboard-data · '+('GitHub 저장 대기 중' if status['pending'] else '저장 대기 변경 없음'))
    if status['error']: st.warning('저장소 연결을 확인하고 저장 확인을 다시 눌러 주세요.')
    if st.button('퀴즈 기록 GitHub 저장 확인',key='quizpop_flush_'+code):
        classroom.flush(user,code);st.success('저장 대기 없이 반영되었습니다.')


@st.fragment(run_every=5)
def teacher_room(user, code):
    try:
        report=classroom.report(user,code)
        st.markdown('<div style="background:#e8dfff;border:3px solid #25233d;border-radius:24px;padding:24px;box-shadow:6px 6px #c9ff59;text-align:center">'
                    '<b>학생에게 아래 참여코드를 알려 주세요</b>'
                    f'<div style="font-size:clamp(38px,8vw,76px);font-weight:900;letter-spacing:.15em;color:#5326c8">{report["code"]}</div>'
                    f'<p>{html.escape(report["title"])} · {report["count"]}문항</p></div>',unsafe_allow_html=True)
        if report['status']=='closed': st.warning('참여가 종료되었습니다. 기존 학생 기록은 보존됩니다.')
        else: st.info('학생: 왼쪽 참여코드 입력 또는 수학 플레이 → 퀴즈에서 입장할 수 있어요.')
        teacher_paper(user, code)
        a,b,c=st.columns(3)
        a.metric('참여 학생',report['joined']);b.metric('완료 학생',report['completed']);c.metric('대상 학생',len(report['results']))
        st.caption('학생 풀이 결과는 5초마다 갱신됩니다. 첫 시도 정답과 힌트를 사용한 풀이를 함께 확인하세요.')
        st.dataframe(report['results'],hide_index=True,width='stretch')
        if report['status']=='open' and st.button('이 퀴즈 참여 종료',key='quizpop_close_'+code):
            classroom.close(user,code);st.rerun()
        _save_status(user,code)
    except (ValueError,PermissionError) as error: st.error(str(error))


def teacher_page(user):
    service.authorize(user,role='teacher')
    selected=st.session_state.get('_quizpop_teacher_room')
    if selected:
        if st.button('← 퀴즈 만들기 · 배포 목록',key='quizpop_builder_back'):
            st.session_state.pop('_quizpop_teacher_room',None);st.rerun()
        teacher_room(user,selected)
        return
    st.markdown('**교사 전용 · 퀴즈 생성 → 참여코드 자동 발급 → 학생 참여**')
    history=classroom.history(user)
    if history:
        with st.expander('배포한 퀴즈 · 문제와 학생 결과 다시 열기'):
            labels={r['code']:f'{r["created_at"]} · {r["title"]} · {"참여 중" if r["status"]=="open" else "종료"}' for r in history}
            code=st.selectbox('배포한 퀴즈',list(labels),format_func=labels.get,key='quizpop_history_code')
            if st.button('문제·참여코드·학생 결과 열기',key='quizpop_open_room'):
                st.session_state['_quizpop_teacher_room']=code;st.rerun()
    st.multiselect('참여 학급',CLASSES,default=CLASSES,key='_quizpop_publish_classes',
                   help='새로 생성할 퀴즈의 참여 학급입니다. 이미 발급된 코드의 대상은 바뀌지 않습니다.')
    data=service.snapshot(user);cfg=config();target=service.storage_info(user)
    saved=data.get('saved');session=saved.get('session') if saved else None
    if session and session.get('questions'):
        publication=classroom.publish_current(user)
        if publication and publication['status']=='ready':
            st.markdown('<div style="background:#e8dfff;border:3px solid #25233d;border-radius:22px;padding:20px;text-align:center">'
                        '<b>학생 참여코드 · 아래 숫자 6자리를 알려 주세요</b>'
                        f'<div style="font-size:clamp(38px,7vw,68px);font-weight:900;letter-spacing:.15em;color:#5326c8">{publication["code"]}</div>'
                        f'<span>{html.escape(publication["title"])} · {publication["count"]}문항</span></div>',unsafe_allow_html=True)
            st.caption('학생: 수학 플레이 → 퀴즈 또는 왼쪽 참여코드 입력 → 위 코드 입력 → 퀴즈 참여')
            if st.button('이 퀴즈 문제·학생 참여·풀이 결과 보기',key='quizpop_current_results'):
                st.session_state['_quizpop_teacher_room']=publication['code'];st.rerun()
        elif publication and publication['status']=='closed':
            st.info('이 퀴즈는 참여가 종료되었습니다. 새 퀴즈를 생성하면 새 참여코드가 표시됩니다.')
        else:
            st.error((publication or {}).get('error') or '참여코드를 준비하고 있습니다.')
            if st.button('참여코드 생성 다시 시도',key='quizpop_retry_publish'):
                classroom.publish_current(user,retry=True);st.rerun()
        data=service.snapshot(user)
        teacher_paper(user)
    else:
        st.info('참여 학급을 선택하고 아래 퀴즈 만들기를 누르세요. 문항 생성 후 6자리 참여코드가 자동으로 표시됩니다.')
    if not target['ready']: st.warning('참여코드를 저장하려면 jsku-sm/class-dashboard-data 저장 연결이 필요합니다.')
    _settings(cfg)
    component(user,data,cfg)
    st.caption('학생은 교사가 생성한 문항을 풉니다. 다음 단계도 교사가 생성하면 새 참여코드가 발급됩니다.')


def student_quiz(user, code):
    data=classroom.snapshot(user,code)
    if data['assignment']['closed']:
        st.info('선생님이 참여를 종료했습니다. 풀이 기록은 저장되어 있습니다. 다른 참여코드로 입장해 주세요.')
        return
    st.caption('선생님이 준비한 퀴즈입니다. 같은 참여코드로 다시 입장하면 이어서 풀 수 있어요.')
    component(user,data,config(),code)
    _save_status(user,code)


def page(user):
    try:
        actor=service.authorize(user)
        if actor['role']=='teacher': teacher_page(user)
        else:
            from .entry import student_entry
            student_entry(user,st.session_state.get('_quizpop_student_code','join'),standalone=False)
    except (ValueError,PermissionError) as error: st.error(str(error))
