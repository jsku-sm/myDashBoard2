"""Streamlit bridge. The browser supplies intentions, never ownership or auth."""
from pathlib import Path
import hashlib
import logging
import streamlit as st
from . import service as svc
import teaching_progress_service as tp

_component = None


def page(user, mode='progress'):
    global _component
    try:
        data = svc.snapshot(user)
    except PermissionError as exc:
        st.error(str(exc))
        return
    except Exception:
        logging.exception('Teacher planner read failed')
        st.error('교사 기록을 불러오지 못했어요. 저장소 연결을 확인해 주세요.')
        return
    import streamlit.components.v1 as components
    if _component is None:
        _component = components.declare_component('good_teacher_planner', path=str(Path(__file__).with_name('frontend')))
    key = 'planner_' + hashlib.sha256(user['id'].encode()).hexdigest()[:16] + '_' + mode
    state = st.session_state.setdefault(key + '_state', {'seen': [], 'ack': None})
    command = _component(data=data, mode=mode, ack=state['ack'], key=key, default=None)
    if isinstance(command, dict) and command.get('token') not in state['seen']:
        token = command.get('token')
        # Bound retained messages to avoid repeated rerun mutations.
        if isinstance(token, str):
            state['seen'] = (state['seen'] + [token])[-100:]
        try:
            result = svc.dispatch(user, command)
            state['ack'] = dict(token=token, ok=True, result=result)
        except tp.SavePendingError as exc:
            state['ack'] = dict(token=token, ok=False, pending=True, error=str(exc))
        except (PermissionError, ValueError) as exc:
            state['ack'] = dict(token=token, ok=False, error=str(exc))
        except Exception:
            logging.exception('Teacher planner mutation failed')
            state['ack'] = dict(token=token, ok=False, error='저장을 확인하지 못했어요. 새로고침으로 기록을 확인한 뒤 다시 시도해 주세요.')
        st.rerun()
    if mode == 'progress':
        if st.toggle('기존 상세 입력표 · 반별 요약 · CSV 열기', value=False, key=key + '_legacy'):
            from views.teaching_progress import page as legacy_page
            legacy_page(user)


def diary_page(user):
    page(user, 'diary')
