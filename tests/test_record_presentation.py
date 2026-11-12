import copy
import json

from record_core.presentation import evidence_card, math_markdown


def item(category='games', **changes):
    result = dict(category=category, label='게임 학습', title='학습 활동', origin='자동 학습 기록', raw={}, text='', extra={})
    result.update(changes)
    return result


def test_arcade_screenshot_becomes_readable_math_and_source_bounded_facts():
    e=item(extra={'source_kind':'arcade_event'}, raw={'type':'success', 'skill':'합성함수 · 역함수',
            'question':r'$f(x)=3x+1,\quad g(x)=x+3$. 입력 $-2$를 g 다음 f 순서로 처리하시오.',
            'message':r'입력 $-2$ → g → f → 출력 $4$예요.', 'score':99999},
           text='게임: 함수 팩토리', origin='학생 브라우저가 보낸 학습 이벤트 · 서버 채점·교사 관찰 아님')
    before=copy.deepcopy(e); card=evidence_card(e)
    assert '성공' in card['summary'] and '함수 팩토리' in card['summary']
    sections=dict(card['sections'])
    assert sections['해결할 문제']==e['raw']['question']
    assert r'\quad' in math_markdown(sections['해결할 문제'])
    assert '$-2$' in math_markdown(sections['학생에게 표시된 피드백'])
    assert '실제 학생 답과 풀이 과정은 이 기록에 없어' in card['check']
    assert '교사 관찰 아님' in card['fact'] and '99999' not in card['fact']
    assert e==before


def test_notes_show_learning_meaning_instead_of_question_numbers():
    e=item('sudanotes', raw={'q1':'합성함수의 순서를 설명함', 'q3':'함수 적용 순서를 고침', 'q5':''})
    c=evidence_card(e)
    assert dict(c['sections'])=={'학생이 설명한 핵심 개념':'합성함수의 순서를 설명함', '생각이 달라진 부분':'함수 적용 순서를 고침'}
    assert '자기평가' in c['check']


def test_quiz_matches_by_id_and_displays_option_text_without_guessing_marks():
    qs=[{'id':'a','prompt':'첫 문제','options':['영','일'],'answer':0},
        {'id':'b','prompt':'두 번째 문제','options':['둘','셋'],'answer':1}]
    e=item('quizzes', text='문항 원본: '+json.dumps(qs)+'\n학생 답: '+json.dumps({'b':1,'a':0})+'\n채점 결과: '+json.dumps({'a':False}))
    c=evidence_card(e)
    first=dict(c['questions'][0][1]); second=dict(c['questions'][1][1])
    assert first['학생 응답']=='1번 · 영' and first['채점 결과']=='오답'
    assert second['학생 응답']=='2번 · 셋' and second['채점 결과']=='판정 기록 없음'
    assert '"options"' not in c['fact'] and '"correct"' not in c['fact']


def test_quizpop_uses_exact_session_questions_and_shows_retry_and_hints():
    qs=[{'prompt':'실제로 푼 단계 문제','options':['오답','정답'],'correctIndex':1}]
    e=item('quizzes', raw={'state_json':json.dumps({'session':{'questions':qs}})},
           text='문항 원본: []\n문항별 학생 응답·힌트·재도전: '+json.dumps([{'attempts':[0,1],'solved':True,'hintsUsed':2}]))
    rows=dict(evidence_card(e)['questions'][0][1])
    assert rows['문제']=='실제로 푼 단계 문제'
    assert rows['응답 순서']=='1번 · 오답 → 2번 · 정답'
    assert rows['힌트 사용']=='2회' and rows['재도전']=='1회'


def test_reward_attempts_keep_question_match_and_chronology():
    qs=[{'id':'a','prompt':'문제 A','options':['오답','정답'],'answer':1},
        {'id':'b','prompt':'미응답 문제','options':['0','1'],'answer':0}]
    answers=[{'qid':'a','choice':0,'correct':False,'hint':False},{'qid':'a','choice':1,'correct':True,'hint':True}]
    e=item(text='문항 원본: '+json.dumps(qs)+'\n문제 풀이·힌트·재도전: '+json.dumps(answers))
    c=evidence_card(e); rows=dict(c['questions'][0][1])
    assert len(c['questions'])==1 and rows['재도전']=='1회'
    assert '오답' in rows['응답 순서'] and '정답' in rows['응답 순서']
    assert '미응답 문제' not in c['fact']


def test_empty_and_unread_attachment_do_not_create_ai_facts():
    assert evidence_card(item(text='문항 원본: []'))['fact']==''
    assert evidence_card(item('uploads', raw={'filename':'풀이.pdf'}))['fact']==''
    assert evidence_card(item('assessments',text='활동: 과제\n문제: x를 구하세요'))['fact']==''


def test_assessment_feedback_has_provenance_and_readable_criteria():
    e=item('assessments', text='활동: 좌표\n학생 풀이: y 부호를 고침',
           raw={'assessment_result':{'feedback':{'teacher_comment':'직접 대조하여 확인함',
                 'observation':'부호 수정 흔적', 'criteria':[{'criterion':'풀이과정','evidence':'처음 답을 지우고 재계산함'}]}}})
    c=evidence_card(e)
    assert dict(c['sections'])['교사 검토 의견']=='직접 대조하여 확인함'
    assert dict(c['sections'])['자동 분석 의견 (참고)']=='부호 수정 흔적'
    assert '"criteria"' not in c['fact']


def test_rendering_keeps_latex_but_does_not_activate_user_links_or_html():
    text=math_markdown(r'분수 $\frac{1}{2}$ 및 \(x^2\)'+'\n![이미지](https://example.invalid/a.png) <script>x</script>')
    assert r'$\frac{1}{2}$' in text and '$x^2$' in text
    assert '<script>' not in text and r'\!\[이미지\]\(' in text
