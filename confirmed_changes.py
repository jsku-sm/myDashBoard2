# GOOD_RECORDS_1.1_FINAL5
"""Critical UI changes report success only after the backend confirms storage.

Retries flush the queued change; they never repeat an account mutation. No
password, callback or credential is retained in the retry receipt.
"""
from copy import deepcopy
import streamlit as st
import storage as db

PENDING = '_critical_change_pending'


def begin_change(backend_api, state, actor_id, label, mutation):
    if not actor_id:
        raise ValueError('로그인 상태를 확인하세요.')
    if state.get(PENDING):
        raise ValueError('이전 변경의 저장을 먼저 확인하세요.')
    result = mutation()
    state[PENDING] = {'actor_id': actor_id, 'label': label, 'result': deepcopy(result)}
    return finish_change(backend_api, state, actor_id)


def finish_change(backend_api, state, actor_id):
    pending = state.get(PENDING)
    if not pending or pending['actor_id'] != actor_id:
        raise ValueError('현재 계정의 저장 요청이 아닙니다.')
    backend_api.flush_now()
    state.pop(PENDING)
    return pending['result']


def pending_controls(key='_critical_change_retry'):
    """Return True while an earlier critical change still needs confirmation."""
    pending = st.session_state.get(PENDING)
    if not pending:
        return False
    actor_id = (st.session_state.get('user') or {}).get('id')
    if actor_id != pending['actor_id']:
        st.error('저장 요청의 계정이 다릅니다. 원래 계정으로 다시 접속하세요.')
        return True
    st.warning(pending['label'] + ' 변경은 접수됐지만 저장 완료를 아직 확인하지 못했습니다.')
    st.caption('같은 작업을 다시 실행하지 않고, 접수한 변경의 저장만 확인합니다.')
    if st.button('저장 확인 다시 시도', key=key, type='primary'):
        try:
            finish_change(db, st.session_state, actor_id)
        except Exception:
            st.error('저장소 연결을 확인하고 다시 시도해 주세요. 저장 요청은 유지됩니다.')
        else:
            st.session_state['_critical_change_saved'] = pending['label']
            st.rerun()
    return True


def perform(label, mutation):
    """UI wrapper returning (confirmed, result), preserving pending on failure."""
    try:
        result = begin_change(db, st.session_state,
                              (st.session_state.get('user') or {}).get('id'), label, mutation)
    except Exception:
        if st.session_state.get(PENDING):
            st.rerun()
        else:
            st.error(label + ' 변경을 완료하지 못했습니다. 입력 내용을 확인해 주세요.')
        return False, None
    return True, result
