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
        try: cfg=api.config(st.secrets)
        except (FileNotFoundError, KeyError): cfg=api.config({})
        key='_quizpop_replies_'+user['id']
        replies=st.session_state.setdefault(key,{})
        event=_component(data=data,enabled=cfg['enabled'],model=cfg['model'],
                         reply=next(reversed(replies.values()),None) if replies else None,
                         key='quizpop_'+user['id'],default=None)
        if isinstance(event,dict) and isinstance(event.get('id'),str) and re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',event['id']):
            eid=event['id']
            if eid not in replies:
                # Cache terminal replies to avoid another paid request on ordinary reruns.
                result={'id':eid,'ok':False,'error':'요청을 처리하지 못했어요. 다시 시도해 주세요.'}
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
        if data['preview']:
            st.caption('교사 체험 · 학생 기록에 영향을 주지 않습니다.')
        else:
            from game_core import service as games
            status=games.save_status(user)
            if status['local']: st.caption('현재 로컬 시험 저장입니다. 실제 수업에서는 기존 GitHub 저장 설정을 사용하세요.')
            elif status['pending']: st.caption('학습 기록이 서버에 반영되었습니다. GitHub 저장 대기 중입니다.')
            else: st.caption('GitHub 저장 대기 변경 없음 · 퀴즈팝은 연습용 학습 기록이며 공식 평가 점수가 아닙니다.')
            if status['error']: st.warning('저장소 연결을 확인하고 기록 저장을 다시 시도해 주세요.')
            if st.button('퀴즈 기록 GitHub 저장 확인',key='quizpop_flush'):
                games.flush(user);st.success('저장 대기 없이 반영되었습니다.')
        if not cfg['enabled'] and data['preview']:
            st.info('AI 퀴즈는 기존 Streamlit Secrets의 [openai] api_key를 사용합니다. 별도 설정은 [quiz_ai] api_key와 model을 사용할 수 있습니다. 키 없이도 예시 퀴즈를 체험할 수 있습니다.')
    except (ValueError,PermissionError) as error:
        st.error(str(error))
