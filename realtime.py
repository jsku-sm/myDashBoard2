"""모든 접속자가 공유하는 '실시간' 상태 (서버 메모리).

- 화면 잠금 상태 (학급별)
- 접속 중 신호 (학생별 마지막 신호 시각)
- 학생에게 보낼 알림 (상점 폭죽, 벌점 메시지)

구글 시트를 거치지 않으므로 API 사용량이 0 이고 반응이 빠릅니다.
앱이 재시작되면 초기화됩니다(잠금 해제 상태로 돌아감).
"""
import threading
import time
from collections import defaultdict

import streamlit as st

from config import CLASSES, ONLINE_WINDOW_SEC


@st.cache_resource(show_spinner=False)
def _state():
    return {
        "mutex": threading.Lock(),
        "locked": {c: False for c in CLASSES},
        "presence": {},  # student_id -> epoch seconds
        "notify": defaultdict(list),
    }


# 잠금 ---------------------------------------------------------------
def is_locked(cls: str) -> bool:
    return bool(_state()["locked"].get(cls, False))


def set_lock(classes, value: bool):
    s = _state()
    with s["mutex"]:
        for c in classes:
            s["locked"][c] = value


def locked_classes():
    return [c for c, v in _state()["locked"].items() if v]


# 접속 신호 -----------------------------------------------------------
def touch(uid: str):
    _state()["presence"][uid] = time.time()


def leave(uid: str):
    _state()["presence"].pop(uid, None)


def is_online(uid: str) -> bool:
    t = _state()["presence"].get(uid)
    return bool(t and time.time() - t < ONLINE_WINDOW_SEC)


# 알림 ---------------------------------------------------------------
def push(uid: str, item: dict):
    s = _state()
    with s["mutex"]:
        s["notify"][uid].append(item)


def pop_all(uid: str):
    s = _state()
    with s["mutex"]:
        items = s["notify"].pop(uid, [])
    return items


def has_pending(uid: str) -> bool:
    return bool(_state()["notify"].get(uid))
