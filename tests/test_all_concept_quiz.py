from copy import deepcopy
import math
import random
import re
import json
import pytest
from game_core import function_quiz_engine as quiz
from game_core import concept_quiz_bank as authored
from game_core.concept_quiz_catalog import UNITS, unit_info
from test_function_quiz import env, event, answer_event
from test_game_learning import game_env


def test_all_39_standards_have_selectable_topics_and_five_stages():
    expected={f'10공수{s}-{area:02}-{n:02}' for s,areas in [(1,[3,11,3,2]),(2,[7,8,5])]
              for area,count in enumerate(areas,1) for n in range(1,count+1)}
    actual={t['standard'] for unit in UNITS for t in unit_info(unit)['topics']}
    assert actual==expected and sum(len(unit_info(u)['topics']) for u in UNITS)==47
    for unit in UNITS:
        bank=quiz.bank(unit)
        for level in range(1,6):
            for topic in range(len(bank['topics'])):
                pool=[q for q in bank['questions'] if q['level']==level and q['topic']==topic]
                assert len(pool)>=2
                assert len({q['prompt'] for q in pool})==len(pool)
                for q in pool:
                    assert 3<=len(q['options'])<=4 and len(set(q['options']))==len(q['options'])
                    assert 0<=q['answer']<len(q['options']) and q['explanation']


@pytest.mark.parametrize('unit',UNITS)
def test_variable_topic_counts_unlock_and_award_only_once(unit):
    s=quiz.initial();count=len(quiz.bank(unit)['topics'])
    for level in range(1,6):
        assert quiz.unlocked(s)==level
        for topic in range(count):
            quiz.apply(s,event('open',level=level,topic=topic,unit=unit),'now',unit=unit)
            public=quiz.public(s,unit=unit)
            assert public['topic_count']==count
            assert 'answer' not in public['question'] and 'explanation' not in public['question']
            quiz.apply(s,answer_event(s),'now',unit=unit)
            quiz.apply(s,answer_event(s),'now',unit=unit)
            if topic<count-1 and level<5:
                with pytest.raises(ValueError):quiz.open_question(s,level+1,0,unit=unit)
        assert s['stages'][str(level)]['completed_at']
    assert s['totals']['correct']==5*count and sum(s['awards'].values())==1800
    before=deepcopy(s)
    with pytest.raises(ValueError):quiz.apply(s,event('open',level=1,topic=0,unit='wrong'),'now',unit=unit)
    assert s==before


def test_existing_function_records_and_other_units_survive_resume_and_disk_reload(env):
    e=env;u=e.actor(e.ss[0]);e.start(u)
    e.quiz.act(u,e.quiz.snapshot(u)['revision'],event('open',level=1,topic=0))
    e.quiz.act(u,e.quiz.snapshot(u)['revision'],answer_event(e.raw(u)['function_quiz']))
    original=deepcopy(e.raw(u))
    for unit in ('matrices','equations','sets'):
        snap=e.quiz.snapshot(u,unit=unit)
        e.quiz.act(u,snap['revision'],event('open',level=1,topic=0,unit=unit),unit=unit)
        state=e.raw(u)['concept_quizzes'][unit]
        e.quiz.act(u,e.quiz.snapshot(u,unit=unit)['revision'],answer_event(state),unit=unit)
    current=e.raw(u)
    assert current['function_quiz']==original['function_quiz']
    assert current['sessions']==original['sessions'] and current['earned']==original['earned']
    assert e.quiz.snapshot(u,unit='matrices')['totals']['correct']==1
    assert e.quiz.snapshot(u,unit='geometry')['totals']['correct']==0
    assert len(e.quiz.snapshot(u)['overview'])==7
    reloaded=e.db.LocalBackend(e.b.root)
    stored=json.loads(next(r for r in reloaded.read('game_profiles') if r['student_id']==u['id'])['state_json'])
    assert stored==current
    snap=e.quiz.snapshot(u,unit='matrices')
    with pytest.raises(ValueError):e.quiz.act(u,snap['revision'],event('open',level=1,topic=0,unit='sets'),unit='matrices')
    assert e.raw(u)==current
    with pytest.raises(PermissionError):e.quiz.snapshot(u,e.ss[1]['id'],unit='matrices')
    e.actor(e.t);before=deepcopy(e.b.read('game_profiles'))
    for unit in UNITS:
        e.quiz.act(e.t,0,event('open',level=5,topic=0,unit=unit),unit=unit,preview=True)
        assert e.quiz.snapshot(e.t,unit=unit,preview=True)['question']['level']==5
    assert e.b.read('game_profiles')==before


@pytest.mark.parametrize('tid',['inequality.absolute','quadratic.line','complex','matrix.add','quadratic.extrema','logic.absolute'])
def test_new_numerical_templates_with_independent_calculation(tid):
    from fractions import Fraction
    from quiz_core.bank import text
    for level in (2,3,4):
        for seed in range(60):
            r=random.Random(seed);a,b,c=r.randint(1,5),r.randint(2,6),r.randint(1,5)
            q=authored._custom(tid,level,seed)
            if q is None:continue
            if tid=='inequality.absolute':
                expected=sum((abs(x-a)<=b if level==2 else abs(2*x-2*a)<2*b if level==3 else abs(x-a)<=b and x>a) for x in range(-100,101))
            elif tid=='quadratic.line':
                if level<4:
                    k=r.choice([-b,0,b]);expected=len({a+math.sqrt(k),a-math.sqrt(k)}) if k>=0 else 0
                else:
                    vertex=Fraction(2*a+b,2)
                    expected=vertex**2-(2*a+b)*vertex+c
            elif tid=='complex':expected=round((complex(a*b-c,a+b*c)/complex(b,1)).real)
            elif tid=='matrix.add':
                A=[[a,b],[c,1]];B=[[b,c],[1,0]]
                result=[[c*A[i][j]-B[i][j] for j in range(2)] for i in range(2)];expected=result[0][1]
            elif tid=='quadratic.extrema':
                values=[(x-a)**2+c for x in range(a-1 if level<4 else a+1,a+b+1)]
                expected=max(values) if level==3 else min(values)
            elif level==2:expected=min((x-a)**2+b for x in range(-10,20))
            elif level==3:expected=min(x+a*a/x for x in [a/2,a,2*a])
            else:
                assert q['options'][q['answer']]==f'x²+{a*a}y²-{2*a}xy=(x-{a}y)²≥0'
                continue
            if isinstance(expected,float) and expected.is_integer():expected=int(expected)
            assert q['options'][q['answer']]==text(expected),q
