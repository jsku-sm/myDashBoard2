# GOOD_RECORDS_1.1_FINAL5
"""Project stored learning events without treating arcade rewards as grades."""
from copy import deepcopy
from datetime import date

# Explicit curriculum assignment; a future game must be assigned deliberately.
COMMON2_ARCADES = frozenset({'bubble', 'invaders', 'maze', 'marble', 'shot', 'memory',
    'territory', 'set-memory', 'counter', 'logic-memory', 'root-marble', 'root-maze',
    'coordinate-drone', 'line-rail', 'circle-radar', 'move-portal', 'venn-catcher',
    'logic-bridge', 'function-factory', 'graph-rider'})


def _dated(record):
    try:
        date.fromisoformat(str(record.get('at', ''))[:10])
    except (TypeError, ValueError):
        return False
    return True


def learning_events(profile, profile_id):
    """Yield stable, dated projections. Never mutate a student's saved profile."""
    from game_core.concept_quiz_catalog import UNITS, unit_info
    from game_core.play_lab_engine import CATALOG

    quizzes = dict(profile.get('concept_quizzes') or {})
    # The function unit keeps its original storage key for compatibility.
    if isinstance(profile.get('function_quiz'), dict):
        quizzes['functions'] = profile['function_quiz']
    seen = set()
    for unit, state in quizzes.items():
        if unit not in UNITS or not isinstance(state, dict):
            continue
        info = unit_info(unit)
        for record in state.get('records', []):
            if not isinstance(record, dict) or not record.get('id') or not _dated(record):
                continue
            identity = f'{profile_id}:concept:{unit}:{record["id"]}'
            if identity in seen:
                continue
            seen.add(identity)
            topic = record.get('topic')
            title = info['topics'][topic]['title'] if type(topic) is int and 0 <= topic < len(info['topics']) else info['title']
            fields = ['단계별 개념퀴즈: ' + info['title'], f'주제: {title}',
                      f'단계: {record.get("level", "")}', '문제: ' + str(record.get('prompt', '')),
                      '학생 응답: ' + str(record.get('selected', '')),
                      '정답: ' + str(record.get('answer', '')),
                      '자동 정오 판정: ' + ('정답' if record.get('correct') is True else '오답' if record.get('correct') is False else '미확인')]
            yield dict(row=deepcopy(record), identity=identity, title='단계별 개념퀴즈 · ' + title,
                       text='\n'.join(fields), row_subject=info['subject'],
                       origin='서버 채점 응답 기록 · 교사 관찰·숙달 판정 아님',
                       extra={'unit': unit, 'topic': topic, 'source_kind': 'concept_quiz'})

    # The 20 catalogued learning arcades cover common mathematics 2.
    games = {g['id']: g['title'] for g in CATALOG if g['id'] in COMMON2_ARCADES}
    labels = {'success': '성공 이벤트', 'error': '오답·오류 이벤트', 'hint': '힌트 사용'}
    lab = profile.get('play_lab') or {}
    if not isinstance(lab, dict):
        return
    for record in lab.get('records', []):
        if not isinstance(record, dict) or not _dated(record):
            continue
        game, kind = record.get('game'), record.get('type')
        if game not in games or kind not in labels or not str(record.get('question', '')).strip():
            continue  # Starting/pausing/winning and score alone are not math evidence.
        if not record.get('runId') or type(record.get('seq')) is not int:
            continue
        identity = f'{profile_id}:arcade:{game}:{record["runId"]}:{record["seq"]}'
        if identity in seen:
            continue
        seen.add(identity)
        # Do not send coins, score, rank, speed or reward amounts to the writer.
        row = {k: deepcopy(record.get(k, '')) for k in ('game', 'runId', 'seq', 'type', 'at', 'stage', 'question', 'skill', 'message')}
        yield dict(row=row, identity=identity, title='아케이드 학습 · ' + games[game],
                   text='\n'.join(['게임: ' + games[game], '문제: ' + str(row['question']),
                                   '관련 개념: ' + str(row['skill']), '기록 종류: ' + labels[kind],
                                   '화면 안내: ' + str(row['message'])]),
                   row_subject='공통수학2', origin='학생 브라우저가 보낸 학습 이벤트 · 서버 채점·교사 관찰 아님 · 교사 확인 필요',
                   extra={'game': game, 'source_kind': 'arcade_event', 'client_reported': True})
