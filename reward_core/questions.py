"""Reuse reviewed, curriculum-scoped banks; no live AI or API key needed."""
from copy import deepcopy
import random
from game_core.concept_quiz_catalog import UNITS, unit_info
from game_core.function_quiz_engine import bank
from game_core.math_text import markdown
from .catalog import DIFFICULTIES


def build(unit, topics, difficulty, seed):
    info = unit_info(unit)
    if difficulty not in DIFFICULTIES or not isinstance(topics, list) or not topics:
        raise ValueError("세부 주제와 난이도를 선택해 주세요.")
    indices = [i for i, t in enumerate(info['topics']) if t['id'] in topics]
    if len(indices) != len(set(topics)):
        raise ValueError("선택한 단원에 속하는 주제만 사용할 수 있어요.")
    rng = random.Random(seed)
    groups = []
    for i in indices:
        pool = [deepcopy(q) for q in bank(unit)['questions'] if q['topic'] == i and q['level'] in DIFFICULTIES[difficulty][1]]
        rng.shuffle(pool)
        seen, selected = set(), []
        for q in pool:
            stem = q['prompt'].removeprefix('기초 개념 확인: ')
            if stem in seen: continue
            seen.add(stem)
            answer = q['options'][q['answer']]
            rng.shuffle(q['options'])
            q['answer'] = q['options'].index(answer)
            if unit == 'functions':
                q['prompt'] = markdown(q['prompt'])
                q['options'] = [markdown(v) for v in q['options']]
                q['explanation'] = markdown(q['explanation'])
            q.update(topic_id=info['topics'][i]['id'], topic_title=info['topics'][i]['title'],
                     standard=info['topics'][i]['standard'], hint=markdown(info['topics'][i]['description']))
            selected.append(q)
            if len(selected) == 9: break
        groups.append(selected)
    # Interleave selected topics so even a short lesson touches the whole scope.
    paper = [g[i] for i in range(max(map(len, groups))) for g in groups if i < len(g)]
    if len(paper) < 3: raise ValueError("서로 다른 문제가 3개 이상 필요합니다.")
    return paper


def validate(paper, unit, topics):
    allowed = {t['id'] for t in unit_info(unit)['topics'] if t['id'] in topics}
    if not isinstance(paper, list) or not 3 <= len(paper) <= 120:
        raise ValueError("문제는 3~120개 선택해 주세요.")
    ids, stems = set(), set()
    for q in paper:
        if not isinstance(q, dict) or q.get('topic_id') not in allowed or not isinstance(q.get('id'), str):
            raise ValueError("문제의 단원을 확인해 주세요.")
        if q['id'] in ids or q.get('prompt') in stems: raise ValueError("같은 문제를 중복해서 넣을 수 없어요.")
        ids.add(q['id']); stems.add(q.get('prompt'))
        opts = q.get('options')
        if not isinstance(opts, list) or not 2 <= len(opts) <= 5 or len(set(opts)) != len(opts):
            raise ValueError("보기는 서로 다른 2~5개여야 합니다.")
        if type(q.get('answer')) is not int or not 0 <= q['answer'] < len(opts): raise ValueError("정답을 확인해 주세요.")
        if any(not isinstance(s, str) or not s.strip() or len(s) > 4000 for s in [q.get('prompt'), q.get('explanation'), q.get('hint'), *opts]):
            raise ValueError("문제·해설·힌트의 내용을 확인해 주세요.")
    return deepcopy(paper)
