"""Student subject-page refresh, scoped to live server state and authorization.

Access changes refresh tabs automatically. Content changes only show a reload
button, to avoid destroying an unsubmitted question/answer being typed.
"""
from __future__ import annotations
import logging
import streamlit as st
from afterschool_core import service as svc

_LOG = logging.getLogger(__name__)


def watch(user, subject):
    if user.get('role') != 'student':
        return
    key = '_as_page_snapshot_' + str(user['id']) + '_' + subject
    try:
        snapshot = svc.student_snapshot(user, subject)
    except PermissionError:
        snapshot = {'access': (), 'content': 'denied'}
    except Exception:
        _LOG.warning('Afterschool snapshot unavailable (no record content logged).')
        st.warning('방과후 배정 정보를 확인하지 못했어요. 화면을 새로고침해 주세요.')
        return
    st.session_state[key] = snapshot
    _poll(user, subject, key)


@st.fragment(run_every=5)
def _poll(user, subject, key):
    try:
        current = svc.student_snapshot(user, subject)
    except PermissionError:
        current = {'access': (), 'content': 'denied'}
    except Exception:
        st.caption('방과후 변경 확인이 지연되고 있어요.')
        return
    previous = st.session_state.get(key, current)
    if previous['access'] != current['access']:
        st.session_state[key] = current
        # Full app rerun is required: the outer subject tab itself may not exist.
        st.rerun(scope='app')
    elif previous['content'] != current['content']:
        st.info('방과후에 새 자료·과제 또는 답변이 있어요. 작성 중인 내용은 제출한 뒤 새로 불러오세요.')
        if st.button('방과후 새 내용 불러오기', key=key + '_refresh'):
            st.rerun(scope='app')
