import copy
import json
import pytest
from game_core import function_quiz_engine as quiz, play_lab_engine as lab
from game_core.concept_quiz_catalog import UNITS
from record_core.evidence import project, validate_reviews
from record_core.archive import ArchiveError


def evidence(profile, subject='공통수학2', start='2026-09-01', end='2027-02-28', sid='10101'):
    bundle = {'student_id': '10101', 'category': 'games', 'payload': {'table': 'game_profiles',
              'rows': [{'id': 'profile1', 'student_id': '10101', 'state_json': json.dumps(profile)}]}}
    return project([bundle], sid=sid, teacher_id='teacher', legacy_teacher_id='teacher', subject=subject, start=start, end=end)


def answered(unit, at='2026-11-13 09:00:00', correct=True):
    q = quiz.initial()
    quiz.apply(q, dict(id='open', action='open', level=1, topic=0), at, unit=unit)
    active = q['active']; answer = active['question']['answer']
    choice = answer if correct else (answer + 1) % len(active['question']['options'])
    quiz.apply(q, dict(id='answer', action='answer', question_id=active['id'], turn=0, choice=choice), at, unit=unit)
    return q


@pytest.mark.parametrize('unit', list(UNITS))
def test_every_unit_real_engine_record_is_projected_once_and_filtered(unit):
    state = answered(unit)
    profile = {'function_quiz': state} if unit == 'functions' else {'concept_quizzes': {unit: state}}
    before = copy.deepcopy(profile)
    subject = UNITS[unit][0]
    rows = evidence(profile, subject)
    assert len(rows) == 1 and rows[0]['date'] == '2026-11-13'
    assert state['records'][0]['selected'] in rows[0]['text']
    assert rows[0]['subject'] == subject and rows[0]['eligible']
    assert '교사 관찰' in rows[0]['origin']
    assert evidence(profile, subject, end='2026-08-31') == []
    assert evidence(profile, '공통수학1' if subject == '공통수학2' else '공통수학2') == []
    assert evidence(profile, subject)[0]['id'] == rows[0]['id']
    assert profile == before


def test_wrong_answer_is_evidence_but_requires_teacher_confirmation():
    rows = evidence({'function_quiz': answered('functions', correct=False)})
    assert '자동 정오 판정: 오답' in rows[0]['text']
    with pytest.raises(ArchiveError):
        validate_reviews(rows, [{'evidence_id': rows[0]['id'], 'evidence_hash': rows[0]['evidence_hash'],
                                'context': '정규 교과수업', 'teacher_confirmed': False}], '공통수학2')


def test_unknown_dates_duplicates_and_different_students_are_not_mixed():
    q = answered('functions')
    q['records'] += [copy.deepcopy(q['records'][0]), dict(q['records'][0], id='undated', at='')]
    assert len(evidence({'function_quiz': q})) == 1
    with pytest.raises(ArchiveError):
        evidence({'function_quiz': q}, sid='10102')


@pytest.mark.parametrize('game', [g['id'] for g in lab.CATALOG])
def test_arcades_keep_learning_events_but_not_rewards_or_controls(game):
    state = lab.initial()
    event = dict(game=game, runId='sample-run-001', type='start', seq=1, elapsed=0,
                 stage=1, stageCount=3, score=99999, mode='relaxed')
    lab.apply(state, [event, dict(event, type='hint', seq=2, question='가상 학습 문항', skill='개념 확인', message='힌트'),
                      dict(event, type='success', seq=3, question='가상 학습 문항'),
                      dict(event, type='win', seq=4)], '2026-11-13 09:00:00')
    rows = evidence({'play_lab': state})
    assert len(rows) == 2
    assert len({r['id'] for r in rows}) == 2
    assert all(r['subject'] == '공통수학2' and r['extra']['client_reported'] for r in rows)
    assert all('99999' not in json.dumps(r) and 'score' not in r['raw'] for r in rows)
    assert evidence({'play_lab': state}, '공통수학1') == []


def test_old_avatar_sessions_remain_in_evidence():
    profile = {'sessions': [{'id': 'old-session', 'topic_id': 'move.reflection', 'created_at': '2026-11-13',
                            'questions': [], 'answers': [], 'reflection': '좌표 부호를 다시 확인함'}],
               'function_quiz': answered('functions')}
    rows = evidence(profile)
    assert len(rows) == 2 and any('좌표 부호' in r['text'] for r in rows)
