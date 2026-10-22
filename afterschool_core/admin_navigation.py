"""Keep the teacher's cohort target separate from disposable widget state.

No enrollment data is kept here. IDs are checked against service-authorized
cohorts on every render; membership remains in as_cohorts.members_json.
Works on Streamlit 1.55 without newer persist_state widget parameters.
"""
from __future__ import annotations

COHORT_WIDGET = 'as_manage_cohort'
MENU_WIDGET = 'as_manage_menu'
MENUS = ('기수 설정', '참여 학생', '자료·과제', '질문·댓글', '제출 확인')
_OWNER = '_as_manager_navigation_owner'
_TARGET = '_as_manager_open_target'


def _key(owner_id: str) -> str:
    return '_as_manager_selection_' + owner_id


def request_open(state, owner_id: str, cohort_id: str, menu: str = '참여 학생') -> None:
    """Queue a navigation command; never change an already-rendered widget."""
    if not owner_id or not cohort_id or menu not in MENUS:
        raise ValueError('관리할 기수와 메뉴를 확인해 주세요.')
    state[_TARGET] = {'owner_id': owner_id, 'cohort_id': cohort_id, 'menu': menu}


def restore(state, owner_id: str, rows: list[dict]) -> None:
    """Call BEFORE either selector is rendered. Reject stale/other-owner IDs."""
    allowed = {row['id'] for row in rows}
    previous_owner = state.get(_OWNER)
    if previous_owner not in (None, owner_id):
        state.pop(COHORT_WIDGET, None)
        state.pop(MENU_WIDGET, None)
    state[_OWNER] = owner_id
    saved = state.get(_key(owner_id), {})
    command = state.pop(_TARGET, None)
    if (isinstance(command, dict) and command.get('owner_id') == owner_id
            and command.get('cohort_id') in allowed and command.get('menu') in MENUS):
        state[COHORT_WIDGET] = command['cohort_id']
        state[MENU_WIDGET] = command['menu']
    else:
        if state.get(COHORT_WIDGET) not in allowed:
            candidate = saved.get('cohort_id')
            state[COHORT_WIDGET] = candidate if candidate in allowed else (rows[0]['id'] if rows else None)
        if state.get(MENU_WIDGET) not in MENUS:
            state[MENU_WIDGET] = saved.get('menu') if saved.get('menu') in MENUS else '기수 설정'


def remember(state, owner_id: str, cohort_id: str, menu: str | None = None) -> None:
    """Store only navigation in a non-widget key, scoped to the current teacher."""
    chosen_menu = menu or state.get(MENU_WIDGET)
    state[_key(owner_id)] = {'cohort_id': cohort_id,
                            'menu': chosen_menu if chosen_menu in MENUS else '기수 설정'}
