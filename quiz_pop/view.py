"""Streamlit component host for the attached QuizPop app."""
import json
from pathlib import Path
import re
import streamlit as st
from . import api, service

_component=None


def page(user):
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        _component=components.declare_component('goodmath_quizpop',path=str(Path(__file__).with_name('frontend')))
    try:
        data=service.snapshot(user)
        try: cfg=api.config(st.secrets.to_dict())
        except (FileNotFoundError, KeyError, st.errors.StreamlitSecretNotFoundError): cfg=api.config({})
        if data['preview']:
            with st.expander('퀴즈 AI 연결 설정', expanded=not cfg['enabled']):
                st.text('API 키 위치: '+(cfg.get('key_source') or '설정 없음'))
                st.text('출제 모델: '+cfg['model'])
                if cfg['enabled']:
                    st.caption('서버의 API 설정을 읽었습니다. 실제 사용 가능 여부는 퀴즈 생성 응답으로 확인합니다.')
                else:
                    st.warning(cfg.get('reason') or '퀴즈용 OpenAI API 키를 설정해 주세요.')
                st.caption('기존 [openai], [school_record_ai], [snorkl] 또는 OPENAI_API_KEY 설정을 읽습니다. 별도 지정은 Streamlit 앱의 Settings → Secrets에서 아래 구역을 설정하세요. 기존 [quiz_ai] 구역이 있으면 그 안의 값을 수정하세요.')
                st.code('[quiz_ai]\napi_key = "본인의 OpenAI API 키"\nmodel = "gpt-6-luna"\nenabled = true', language='toml')
        key='_quizpop_replies_'+user['id']
        replies=st.session_state.setdefault(key,{})
        event=_component(data=data,enabled=cfg['enabled'],model=cfg['model'],
                         unavailableMessage=(cfg.get('reason','') if data['preview'] else 'AI 퀴즈 연결이 준비되지 않았어요. 선생님에게 알려 주세요. [QUIZ_NOT_READY]'),
                         reply=next(reversed(replies.values()),None) if replies else None,
                         key='quizpop_'+user['id'],default=None)
        if isinstance(event,dict) and isinstance(event.get('id'),str) and re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',event['id']):
            eid=event['id']
            if eid not in replies:
                # Cache terminal replies to avoid another paid request on ordinary reruns.
                result={'id':eid,'ok':False,'error':'퀴즈 요청 처리 중 오류가 발생했습니다. 새로고침 후 다시 시도해 주세요. [QUIZ_INTERNAL]'}
                try:
                    service.authorize(user,write=True)
                    if len(json.dumps(event,ensure_ascii=False,allow_nan=False))>400000: raise ValueError('요청 내용이 너무 큽니다.')
                    action=event.get('action')
                    if action=='save': value=service.save(user,event.get('payload'),event.get('revision'))
                    elif action in ('generate','guide'):
                        with st.spinner('퀴즈팝이 학습 내용을 준비하고 있어요…'):
                            value=api.call(action,event.get('payload'),cfg)
                    else: raise ValueError('지원하지 않는 퀴즈 요청입니다.')
                    result={'id':eid,'ok':True,'value':value}
                except (ValueError,PermissionError) as error: result['error']=str(error)
                except Exception: pass  # Never send provider bodies, credentials or tracebacks to the iframe.
                replies[eid]=result
                while len(replies)>40: replies.pop(next(iter(replies)))
                st.rerun()
        last_reply=next(reversed(replies.values()),None) if replies else None
        if last_reply and not last_reply['ok']:
            st.error(last_reply['error'])
        if data['preview']:
            st.caption('교사 체험 · 학생 기록에 영향을 주지 않습니다.')
            target=service.storage_info(user)
            if target['ready']:
                st.caption('학생 퀴즈 기록 저장소: '+target['expected'])
            else:
                st.warning('학생 학습을 시작하려면 jsku-sm/class-dashboard-data 저장 연결이 필요합니다. Streamlit Secrets의 [app] storage 및 [github] 설정을 확인해 주세요.')
        else:
            from game_core import service as games
            status=games.save_status(user)
            if status['local']: st.caption('현재 로컬 시험 저장입니다. 실제 수업에서는 기존 GitHub 저장 설정을 사용하세요.')
            elif status['pending']: st.caption('학습 기록이 서버에 반영되었습니다. GitHub 저장 대기 중입니다.')
            else: st.caption('jsku-sm/class-dashboard-data · GitHub 저장 대기 변경 없음')
            if status['error']: st.warning('저장소 연결을 확인하고 기록 저장을 다시 시도해 주세요.')
            if st.button('퀴즈 기록 GitHub 저장 확인',key='quizpop_flush'):
                games.flush(user);st.success('저장 대기 없이 반영되었습니다.')
    except (ValueError,PermissionError) as error:
        st.error(str(error))
