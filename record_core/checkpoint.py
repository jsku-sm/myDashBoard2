# GOOD_RECORDS_1.1_FINAL5
"""Explicit commit checkpoints for note submissions and point events.

A failed commit retains the pending batch in this authenticated session, so a
retry commits it rather than appending the same rows a second time.
"""
from __future__ import annotations
import copy
from .archive import ArchiveError


def append_confirmed(db, state, key, table, rows=()):
    pending=state.get(key)
    if pending:
        if pending['table']!=table:
            raise ArchiveError('이전 저장 요청을 먼저 확인하세요.')
    else:
        if not rows:
            raise ArchiveError('저장할 자료가 없습니다.')
        pending={'table':table,'rows':copy.deepcopy(list(rows))}
        db.append_many(table,pending['rows'])
        state[key]=pending
    db.flush_now()
    state.pop(key,None)
    return pending['rows']
