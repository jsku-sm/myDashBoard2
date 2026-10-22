"""A session-bound file transfer, not a public Streamlit media/download URL.

Only the active component can ask its own Python view to prepare a file. The
service rechecks the current user, membership and parent record before bytes
are returned through that session. Previously received bytes cannot be recalled.
"""
import base64
import hashlib
import re
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from afterschool_core import service as svc

_component = components.declare_component('afterschool_private_download',path=str(Path(__file__).with_name('download_component')))


def render(user, kind, record_id, index, name, *, prefix='board'):
    # No file ID or server path is accepted from the component's messages.
    binding = hashlib.sha256(f'{user["id"]}:{prefix}:{kind}:{record_id}:{index}'.encode()).hexdigest()
    sk = '_as_download_' + binding
    current = st.session_state.get(sk, {})
    if current.get('at',0) + 65 < time.time():
        current = {}
        st.session_state.pop(sk,None)
    event = _component(binding=binding,label=f'📎 {name}',result=current.get('result'),key='as_file_'+binding,default=None)
    if not isinstance(event,dict): return
    rid=event.get('request_id','')
    if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{8,100}',rid): return
    if event.get('action')=='received' and current.get('result',{}).get('request_id')==rid:
        # Remove bytes from server session after the iframe acknowledges receipt.
        st.session_state[sk]={'at':time.time(),'last':rid}
        st.rerun()
    if event.get('action')!='prepare' or rid==current.get('last'): return
    try:
        data,filename,mime=svc.download_attachment(user,kind,record_id,index)
        result={'request_id':rid,'data':base64.b64encode(data).decode('ascii'),'name':filename,'mime':mime}
    except (PermissionError,ValueError) as exc:
        result={'request_id':rid,'error':str(exc)}
    except Exception:
        result={'request_id':rid,'error':'파일을 불러오지 못했어요. 연결 상태를 확인하고 다시 시도해 주세요.'}
    # Keep only one staged file payload per session.
    for key in list(st.session_state):
        if key.startswith('_as_download_') and key!=sk:
            st.session_state.pop(key,None)
    st.session_state[sk]={'at':time.time(),'last':rid,'result':result}
    st.rerun()
