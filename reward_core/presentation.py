# GOOD_RECORDS_1.1_FINAL5
"""Readable, deterministic evidence cards. No AI calls or proficiency inference."""
from __future__ import annotations
import html
import json
import re


def math_markdown(value):
    """Keep math delimiters; render other input as text, not links/images/HTML."""
    text = str(value or '').replace('\\(', '$').replace('\\)', '$').replace('\\[', '$$').replace('\\]', '$$')
    parts = re.split(r'(\$\$[\s\S]*?\$\$|(?<!\\)\$[^$\n]+?(?<!\\)\$)', text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'([\\`*_{}\[\]()#+.!|>~$-])', r'\\\1', html.escape(parts[i], quote=False))
    return ''.join(parts).replace('\n', '  \n')


def _json(value, default):
    if isinstance(value, (list, dict)):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(default)) else default
    except (ValueError, TypeError):
        return default


def _str(value):
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''


def _choice(value, options):
    if type(value) is int:
        if 0 <= value < len(options):
            label = options[value]
            if isinstance(label, dict):
                label = label.get('text', label.get('label', ''))
            return f'{value + 1}번 · {_str(label)}'
        return f'선택 번호 {value + 1} (보기 내용 미저장)'
    return _str(value) or '응답 기록 없음'


def _verdict(value):
    return '정답' if value is True else '오답' if value is False else '판정 기록 없음'


def _questions(e, fields):
    """Join answers to their original question; never infer a missing mark."""
    raw = e.get('raw') or {}
    if 'questions' in raw:
        paper, answers, mode = raw.get('questions', []), raw.get('answers', []), 'avatar'
    else:
        paper = _json(fields.get('문항 원본'), [])
        mode = ('quizpop' if '문항별 학생 응답·힌트·재도전' in fields else
                'reward' if '문제 풀이·힌트·재도전' in fields else
                'review' if '학생 응답' in fields else 'quiz')
        # QuizPop sessions carry the questions for this exact stage.
        session = _json(raw.get('state_json'), {}).get('session') or {}
        if mode == 'quizpop' and session.get('questions'):
            paper = session['questions']
        key = {'quizpop':'문항별 학생 응답·힌트·재도전', 'reward':'문제 풀이·힌트·재도전',
               'review':'학생 응답', 'quiz':'학생 답'}[mode]
        answers = _json(fields.get(key), {} if mode == 'quiz' else [])
    if not isinstance(paper, list):
        return []
    marks = _json(fields.get('채점 결과'), {})
    out = []
    for i, q in enumerate(paper):
        if not isinstance(q, dict):
            continue
        opts = q.get('options') or []
        qid = q.get('id')
        rows = [('문제', q.get('prompt') or q.get('question') or q.get('stem') or '문제 내용 미저장')]
        if q.get('concept'): rows.append(('관련 개념', q['concept']))
        if mode in ('avatar', 'quizpop'):
            a = answers[i] if isinstance(answers, list) and i < len(answers) and isinstance(answers[i], dict) else {}
            choices = a.get('choices' if mode == 'avatar' else 'attempts') or []
            if not choices and not a.get('hints' if mode == 'avatar' else 'hintsUsed') and not a.get('reflection'):
                continue
            rows.append(('응답 순서', ' → '.join(_choice(c, opts) for c in choices) or '응답 기록 없음'))
            rows.append(('기록 결과', ('정답 도달' if a.get('solved') is True else '아직 정답 도달 기록 없음') if choices else '미응답'))
            hints = a.get('hints' if mode == 'avatar' else 'hintsUsed')
            if type(hints) is int: rows.append(('힌트 사용', f'{hints}회'))
            if choices: rows.append(('재도전', f'{max(0, len(choices)-1)}회'))
            if a.get('revealed'): rows.append(('해설 확인', '정답 해설을 열어 본 기록이 있음'))
            if a.get('reflection'): rows.append(('학생 성찰', a['reflection']))
        elif mode in ('review', 'reward'):
            attempts = [a for a in answers if isinstance(a, dict) and
                        ((qid is not None and a.get('qid') == qid) or (qid is None and a.get('index') == i))]
            if not attempts:
                continue
            rows.append(('응답 순서', ' → '.join(_choice(a.get('choice'), opts) + ' (' + _verdict(a.get('correct')) + ')' for a in attempts) or '응답 기록 없음'))
            if attempts:
                rows.append(('재도전', f'{len(attempts)-1}회'))
                if any(a.get('hint') for a in attempts): rows.append(('힌트 사용', '사용 기록 있음'))
        else:
            a = answers.get(str(qid)) if isinstance(answers, dict) and qid is not None else None
            if a is None:
                continue
            rows.append(('학생 응답', _choice(a, opts)))
            rows.append(('채점 결과', _verdict(marks.get(str(qid))) if qid is not None else '문항 식별 정보 없음'))
        answer = q.get('correctIndex', q.get('answer'))
        if answer is not None: rows.append(('정답', _choice(answer, opts)))
        out.append((f'{i+1}번 문항', rows))
    return out


def evidence_card(e):
    raw = e.get('raw') or {}
    text = e.get('text', '')
    fields = dict(line.split(': ', 1) for line in text.splitlines() if ': ' in line)
    category = e.get('category')
    kind = e.get('extra', {}).get('source_kind')
    sections, questions = [], []
    summary = '기록된 내용과 실제 수업 활동을 대조해 주세요.'
    check = '기록에 없는 풀이 과정이나 성장을 덧붙이지 않습니다.'
    if category == 'sudanotes':
        labels = ['학생이 설명한 핵심 개념', '생각한 문제와 해결 방법', '생각이 달라진 부분', '남은 질문', '학생이 돌아본 변화']
        sections = [(label, raw.get(f'q{i}', '')) for i, label in enumerate(labels, 1)]
        summary = '학생이 수업을 어떻게 이해하고 돌아보았는지 확인할 수 있는 자기기록입니다.'
        check = '학생의 자기평가를 교사가 관찰한 성취로 단정하지 않습니다.'
    elif category == 'observations':
        sections = [('교사가 기록한 관찰 내용', raw.get('content', text))]
        summary = '교사가 수업에서 관찰해 남긴 기록입니다.'
    elif kind == 'arcade_event':
        status = {'success':'성공', 'error':'오답·오류', 'hint':'힌트 사용'}.get(raw.get('type'), '상태 미확인')
        summary = f"{fields.get('게임', e.get('title', '학습 게임'))} 활동에서 ‘{status}’ 기록이 남았습니다."
        sections = [('관련 개념', raw.get('skill')), ('해결할 문제', raw.get('question')),
                    ('활동 결과', status + ' (게임 화면 기록)'), ('학생에게 표시된 피드백', raw.get('message'))]
        check = '게임 화면이 보낸 결과입니다. 실제 학생 답과 풀이 과정은 이 기록에 없어 추정하지 않습니다.'
    elif kind == 'concept_quiz':
        summary = f"{fields.get('주제', '개념')} 문항의 응답 결과는 {_verdict(raw.get('correct'))}입니다."
        sections = [('학습 주제', fields.get('주제')), ('학습 단계', fields.get('단계')),
                    ('문제', raw.get('prompt')), ('학생 응답', raw.get('selected')),
                    ('정답', raw.get('answer')), ('자동 채점 결과', _verdict(raw.get('correct')))]
        check = '한 문항의 정오 결과만으로 개념 숙달이나 성장을 단정하지 않습니다.'
    elif category in ('games', 'quizzes'):
        questions = _questions(e, fields)
        sections = [('학생 성찰', raw.get('reflection', ''))]
        summary = f'저장된 {len(questions)}개 문항에서 학생 응답과 도움 사용을 확인할 수 있습니다.' if questions else '문항별 응답이 충분히 저장되지 않은 학습 기록입니다.'
        check = '정오 결과·힌트·재도전은 기록된 범위만 표시합니다. 순위와 게임 보상은 근거에서 제외합니다.'
    elif category in ('assessments', 'uploads'):
        sections = [(label, fields.get(label, '')) for label in ('활동','문제','학생 풀이','학생 설명 전사','학생 성찰','제출 선택','교사 피드백')]
        result = raw.get('assessment_result') or {}
        feedback = result.get('feedback', raw.get('feedback')) or {}
        if isinstance(feedback, dict):
            for key, label in [('teacher_comment','교사 검토 의견'), ('observation','자동 분석 의견 (참고)'),
                               ('praise','자동 분석의 긍정적 피드백 (참고)'), ('uncertainty_reason','자동 분석에서 확인이 필요한 부분')]:
                if feedback.get(key): sections.append((label, feedback[key]))
            for criterion in feedback.get('criteria') or []:
                if isinstance(criterion, dict) and criterion.get('evidence'):
                    sections.append(('평가 기준별 자동 분석 근거 (참고)', str(criterion.get('criterion', '')) + ': ' + str(criterion['evidence'])))
        review = raw.get('review') or {}
        if isinstance(review, dict) and review.get('comment'):
            sections.append(('교사 검토 의견', review['comment']))
        summary = '학생이 제출한 풀이·설명·성찰과 교사 피드백을 함께 확인합니다.'
        check = '첨부만 있는 자료는 원본을 열거나 선택 자료 분석으로 확인해 주세요. 읽지 않은 파일의 내용을 만들지 않습니다.'
    elif category in ('submissions', 'questions'):
        sections = [(label, raw.get(key, '')) for key, label in [('unit','단원'),('content','학생 작성 내용'),('feedback','피드백'),('teacher_comment','교사 의견'),('answer','답변')]]
    else:
        sections = [('기록 내용', text)]
    sections = [(k, _str(v)) for k, v in sections if _str(v)]
    facts = [f"자료 유형: {e.get('label', '')}", f"출처 구분: {e.get('origin', '')}", f"활동: {e.get('title', '')}"]
    facts += [f'{k}: {v}' for k, v in sections]
    for title, rows in questions:
        facts.append(title + '\n' + '\n'.join(f'{k}: {v}' for k, v in rows))
    # Empty/attachment-only sources must be inspected, not expanded into invented facts.
    has_content = bool(sections or questions)
    if category in ('assessments', 'uploads'):
        has_content = any(k not in ('활동', '문제') for k, _ in sections)
    fact = '\n'.join(facts + ['해석 범위: ' + check]) if has_content else ''
    if len(fact) > 5800:
        fact = fact[:5700] + '\n[이후 내용 생략: 위에 표시한 앞부분만 초안 근거로 사용합니다.]'
    return dict(summary=summary, sections=sections, questions=questions, check=check, fact=fact)
