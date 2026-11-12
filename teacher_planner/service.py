"""One authoritative lesson record, shown in two views; teacher-owned diary.

All mutations recheck the backend role, owner, and revision under the existing
backend lock. Remote flush always occurs outside that lock. No student data.
"""
from datetime import date, timedelta
import hashlib
import json
import re
import storage as db
import teaching_progress_service as tp
from config import CLASSES, SUBJECTS
from .schema import TABLES

SCHOOL_PERIODS = tuple(f'{n}교시' for n in range(1, 8))

KINDS = {'task': '할 일', 'meeting': '회의', 'event': '행사', 'note': '하루 메모'}


def _token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}', value):
        raise ValueError('요청을 다시 시작해 주세요.')
    return value


def _id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:32]


def _flag(v):
    if v not in ('0', '1', False, True):
        raise ValueError('체크 상태를 확인해 주세요.')
    return '1' if v in ('1', True) else '0'


def _owned(b, uid, table, rid, deleted=False):
    row = next((r for r in b.read(table) if r['id'] == rid and r['author_id'] == uid), None)
    if row is None or (row.get('deleted_at') and not deleted):
        raise PermissionError('이 기록을 열거나 수정할 권한이 없어요.')
    return dict(row)


def _flush(ids=()):
    for table in (*TABLES, tp.TABLE):
        db.invalidate(table)
    try:
        db.flush_now()
    except Exception:
        raise tp.SavePendingError(list(ids)) from None
    return list(ids)


def pending(user):
    b = db._ready_backend()
    tp.require_teacher(user, b)
    if b.is_local:
        return False
    with b.lock:
        paths = {db.GitHubBackend._path(t, {'author_id': user['id']}) for t in TABLES}
        paths.add('data/teaching_progress.csv')
        return bool(paths.intersection(getattr(b, 'dirty', {})))


def retry(user):
    tp.require_teacher(user)
    return _flush()


def diary_payload(p):
    if not isinstance(p, dict):
        raise ValueError('일정 내용을 확인해 주세요.')
    kind = p.get('kind', 'task')
    if kind not in KINDS:
        raise ValueError('일정 종류를 선택해 주세요.')
    when = p.get('time', '')
    if not isinstance(when, str) or (when and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', when)):
        raise ValueError('시간은 00:00~23:59로 입력해 주세요.')
    return dict(kind=kind, date=tp._date(p.get('date'), '날짜'), time=when,
                deadline=tp._date(p.get('deadline'), '마감일', False),
                title=tp._text(p.get('title', ''), '제목', 200, True),
                body=tp._text(p.get('body', ''), '메모', 10000),
                done=_flag(p.get('done', '0')), important=_flag(p.get('important', '0')))


def rule_payload(p):
    if not isinstance(p, dict):
        raise ValueError('시간표 내용을 확인해 주세요.')
    weekday = str(p.get('weekday', ''))
    if weekday not in tuple(str(n) for n in range(7)):
        raise ValueError('요일을 선택해 주세요.')
    if p.get('period') not in SCHOOL_PERIODS or p.get('class') not in CLASSES or p.get('subject') not in SUBJECTS:
        raise ValueError('학급·과목·교시를 확인해 주세요.')
    return dict(weekday=weekday, period=p['period'], **{'class': p['class']}, subject=p['subject'],
                content=tp._text(p.get('content', ''), '기본 수업내용', 4000) or '수업 내용 정하기')


def save_private(user, table, payload, token, rid='', revision=''):
    if table not in TABLES:
        raise ValueError('기록 종류를 확인해 주세요.')
    clean = diary_payload(payload) if table == 'teacher_diary' else rule_payload(payload)
    _token(token)
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        if table == 'teacher_timetable':
            for r in b.read(table):
                if r['author_id'] == actor['id'] and not r['deleted_at'] and r['id'] != rid:
                    if r['weekday'] == clean['weekday'] and r['period'] == clean['period']:
                        # An identical retried creation has the same deterministic ID.
                        if rid or r['id'] != _id(actor['id'], table, token):
                            raise ValueError('이 요일·교시에 이미 수업이 있어요. 기존 시간표를 수정해 주세요.')
        if rid:
            old = _owned(b, actor['id'], table, rid)
            tp._version(old, revision)
            b.update(table, rid, dict(clean, revision=str(int(old['revision']) + 1), updated_at=db.now_str()))
        else:
            rid = _id(actor['id'], table, token)
            old = next((r for r in b.read(table) if r['id'] == rid), None)
            if old:
                if old['author_id'] != actor['id'] or old['deleted_at'] or any(old[k] != v for k, v in clean.items()):
                    raise tp.ConflictError('이미 사용한 요청이에요. 새 기록으로 다시 열어 주세요.')
            else:
                b.append(table, dict(clean, id=rid, author_id=actor['id'], created_at=db.now_str(),
                                     updated_at=db.now_str(), revision='1', deleted_at=''))
    return _flush([rid])


def trash(user, table, rid, revision, restore=False):
    if table not in TABLES:
        raise ValueError('기록 종류를 확인해 주세요.')
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        old = _owned(b, actor['id'], table, rid, True)
        tp._version(old, revision)
        if restore and table == 'teacher_timetable':
            if any(r['author_id'] == actor['id'] and not r['deleted_at'] and r['id'] != rid
                   and r['weekday'] == old['weekday'] and r['period'] == old['period'] for r in b.read(table)):
                raise ValueError('같은 요일·교시의 시간표가 있어 복원할 수 없어요.')
        b.update(table, rid, dict(deleted_at='' if restore else db.now_str(),
                                  updated_at=db.now_str(), revision=str(int(old['revision']) + 1)))
    return _flush([rid])


def snapshot(user):
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        own = lambda table: [dict(r) for r in b.read(table) if r['author_id'] == actor['id']]
        return dict(today=db.today_str(), lessons=own(tp.TABLE), diary=own('teacher_diary'),
                    rules=own('teacher_timetable'), classes=CLASSES, subjects=SUBJECTS,
                    periods=list(tp.PERIODS), pending=pending(user), local=b.is_local)


def move(user, kind, rid, revision, target, period=None):
    target = tp._date(target, '이동할 날짜')
    if kind in ('lesson', 'assessment'):
        old = tp.get_record(user, rid)
        tp._version(old, revision)
        patch = {'date': target} if kind == 'lesson' else {'assessment_date': target}
        if period is not None:
            if period not in tp.PERIODS:
                raise ValueError('교시를 확인해 주세요.')
            patch['period' if kind == 'lesson' else 'assessment_period'] = period
        return tp.update_record(user, rid, dict(old, **patch), old['class'], revision)
    if kind != 'diary':
        raise ValueError('이동할 기록을 확인해 주세요.')
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        old = _owned(b, actor['id'], 'teacher_diary', rid)
    # Due date is deliberately independent of the day assigned to work.
    return save_private(user, 'teacher_diary', dict(old, date=target), 'move-record', rid, revision)


def carry(user, items, source):
    source = tp._date(source, '기준일')
    target = tp._date((date.fromisoformat(source) + timedelta(days=1)).isoformat(), '다음 날')
    if not isinstance(items, list) or not items or len(items) > 500:
        raise ValueError('넘길 미완료 할 일을 선택해 주세요.')
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        checked = []
        for item in items:
            r = _owned(b, actor['id'], 'teacher_diary', item.get('id'))
            tp._version(r, item.get('revision'))
            if r['kind'] != 'task' or r['done'] == '1' or r['date'] > source:
                raise tp.ConflictError('할 일의 날짜나 완료 상태가 바뀌었어요. 목록을 다시 확인해 주세요.')
            checked.append(r)
        if len({r['id'] for r in checked}) != len(checked):
            raise ValueError('중복된 할 일 요청이에요.')
        for r in checked:
            b.update('teacher_diary', r['id'], dict(date=target, updated_at=db.now_str(), revision=str(int(r['revision']) + 1)))
    return _flush([r['id'] for r in checked])


def _generation(b, uid, start, end, excluded):
    start, end = tp._date(start, '적용 시작일'), tp._date(end, '적용 종료일')
    a, z = date.fromisoformat(start), date.fromisoformat(end)
    if a > z or (z - a).days > 365:
        raise ValueError('적용 기간은 시작일부터 최대 366일로 선택해 주세요.')
    if not isinstance(excluded, list) or len(excluded) > 366:
        raise ValueError('제외 날짜를 확인해 주세요.')
    excluded = {tp._date(x, '제외 날짜') for x in excluded}
    rules = sorted([r for r in b.read('teacher_timetable') if r['author_id'] == uid and not r['deleted_at'] and r['period'] in SCHOOL_PERIODS], key=lambda r: r['id'])
    if not rules:
        raise ValueError('주간 시간표를 먼저 한 칸 이상 등록해 주세요.')
    lessons = [r for r in b.read(tp.TABLE) if r['author_id'] == uid]
    # Stable occurrence identity survives a move and a soft deletion.
    existing = {r['id'] for r in lessons}
    slots = {(r['date'], r['period']) for r in lessons if not r['deleted_at'] and r['content'] and r['status'] != '휴강'}
    rows, skipped = [], 0
    current = a
    while current <= z:
        day = current.isoformat()
        if day not in excluded:
            for rule in rules:
                if int(rule['weekday']) != current.weekday():
                    continue
                rid = _id(uid, 'timetable-lesson', rule['id'], day)
                if rid in existing or (day, rule['period']) in slots:
                    skipped += 1
                    continue
                clean = tp.normalize(dict(date=day, subject=rule['subject'], period=rule['period'], content=rule['content']))
                rows.append(dict(clean, id=rid, author_id=uid, batch_id='timetable_'+rule['id'],
                                 **{'class': rule['class']}, template_id=rule['id'], occurrence_date=day,
                                 created_at=db.now_str(), updated_at=db.now_str(), revision='1', deleted_at=''))
                slots.add((day, rule['period']))
        current += timedelta(days=1)
    fingerprint = _id(start, end, sorted(excluded), [(r['id'], r['revision']) for r in rules],
                      [(r['id'], r['revision']) for r in sorted(lessons, key=lambda r: r['id'])])
    return rows, skipped, fingerprint


def generate(user, start, end, excluded, expected=None):
    b = db._ready_backend()
    with b.lock:
        actor = tp.require_teacher(user, b)
        rows, skipped, fingerprint = _generation(b, actor['id'], start, end, excluded)
        if expected is None:
            return dict(count=len(rows), skipped=skipped, fingerprint=fingerprint,
                        sample=[{k: r[k] for k in ('date', 'period', 'class', 'subject')} for r in rows[:14]])
        if expected != fingerprint:
            raise tp.ConflictError('시간표 또는 진도가 바뀌었어요. 배치 미리보기를 다시 확인해 주세요.')
        if rows:
            b.append_many(tp.TABLE, rows)
    _flush([r['id'] for r in rows])
    return dict(count=len(rows), skipped=skipped)


def dispatch(user, command):
    if not isinstance(command, dict):
        raise ValueError('요청 형식을 확인해 주세요.')
    tp.require_teacher(user)
    action = command.get('action')
    token = _token(command.get('token'))
    p = command.get('payload', {})
    if not isinstance(p, dict):
        raise ValueError('입력 내용을 확인해 주세요.')
    if action == 'retry':
        retry(user)
        return {'message': '저장을 확인했어요.'}
    if action == 'refresh':
        return {'message': '최신 기록을 불러왔어요.'}
    if pending(user):
        raise tp.SavePendingError([])
    if action == 'save_lesson':
        if p.get('id'):
            tp.update_record(user, p['id'], p, p.get('class'), p.get('revision'))
        else:
            tp.create_records(user, p.get('classes'), p, token)
    elif action in ('save_diary', 'save_rule'):
        save_private(user, 'teacher_diary' if action == 'save_diary' else 'teacher_timetable', p, token, p.get('id', ''), p.get('revision', ''))
    elif action == 'move':
        move(user, p.get('kind'), p.get('id'), p.get('revision'), p.get('date'), p.get('period'))
    elif action in ('trash', 'restore'):
        restore = action == 'restore'
        if p.get('kind') in ('lesson', 'assessment'):
            (tp.restore_record if restore else tp.delete_record)(user, p.get('id'), p.get('revision'))
        else:
            table = {'diary': 'teacher_diary', 'rule': 'teacher_timetable'}.get(p.get('kind'))
            trash(user, table, p.get('id'), p.get('revision'), restore)
    elif action == 'carry':
        carry(user, p.get('items'), p.get('date'))
    elif action in ('preview_generate', 'generate'):
        return generate(user, p.get('start'), p.get('end'), p.get('excluded', []), p.get('fingerprint') if action == 'generate' else None)
    else:
        raise ValueError('지원하지 않는 요청이에요.')
    return {'message': '기록을 저장했어요.'}
