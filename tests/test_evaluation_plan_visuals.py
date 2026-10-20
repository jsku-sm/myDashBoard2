"""Pure parser/HTML tests: no Streamlit, credentials, network, or student data."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_plan_visuals import analyse_plan, render_plan_html

SAMPLE = """1. 성적 반영 비율 (총 100%)
지필고사 (40%): 중간고사 20% (10월) + 기말고사 20% (12월)
수행평가 (60%): 과정 중심 서·논술형 평가
수학 탐구활동 1 (30%) / 9월: 도형의 방정식 탐구 및 생각쓰기
수학탐구활동 2 (30%) / 11월: 집합·명제·함수 개념을 활용한 문제 해결
2. 단원별 주요 학습 내용
도형의 방정식 (8~9월): 평면좌표, 선분의 내분, 직선·원의 방정식, 도형의 이동
집합과 명제 (10~11월): 집합의 연산, 명제와 조건
함수와 그래프 (11~12월): 함수의 뜻과 그래프, 합성함수, 역함수
3. 성취도 산출 및 미도달(F) 기준
성취도 평가: 5단계(A-B-C-D-E) 및 석차등급(1~5등급) 산출
이수/미이수(P/F) 기준: 성취율 40% 미만시 미이수 대상이며 보충 지도를 이수해야 합니다.
"""


@pytest.mark.parametrize('text', [SAMPLE, SAMPLE.replace('\n', ' '), SAMPLE.replace('%', '％'),
                                  SAMPLE.replace('지필고사', '**지필고사**')])
def test_groups_and_children_and_criteria_are_not_mixed(text):
    data = analyse_plan(text)
    assert [g['percent'] for g in data['groups']] == ['40', '60']
    assert [c['percent'] for g in data['groups'] for c in g['children']] == ['20', '20', '30', '30']
    assert data['composition_valid']
    assert len(data['criteria']) == 2
    assert '40% 미만' in data['criteria'][1]['text']
    assert not data['warnings']


@pytest.mark.parametrize('text', [SAMPLE, SAMPLE.replace('\n', ' ')])
def test_schedule_details_do_not_leak_into_next_title(text):
    data = analyse_plan(text)
    assert [r['title'] for r in data['schedule']] == ['도형의 방정식', '집합과 명제', '함수와 그래프']
    assert [r['period'] for r in data['schedule']] == ['8~9월', '10~11월', '11~12월']
    assert data['schedule'][0]['detail'].endswith('도형의 이동')
    assert '집합과 명제' not in data['schedule'][0]['detail']


def test_no_percentages_hardcoded():
    data = analyse_plan(SAMPLE.replace('지필고사 (40%)', '지필고사 (30%)').replace('수행평가 (60%)', '수행평가 (70%)'))
    assert [g['percent'] for g in data['groups']] == ['30', '70']
    assert data['composition_valid']
    assert data['warnings']  # child sums remain 40 / 60


@pytest.mark.parametrize('text', ['성적 반영 비율 지필평가 40% 수행평가 50%',
                                  '성적 반영 비율 수행평가 60%',
                                  '성적 반영 비율 지필평가 150% 수행평가 50%',
                                  '성적 반영 비율 지필평가 40% 수행평가 60% 지필평가 30%'])
def test_missing_invalid_or_conflicting_weights_do_not_fabricate_pie(text):
    data = analyse_plan(text)
    assert not data['composition_valid']
    assert data['warnings']
    assert 'class="ep-composition"' not in render_plan_html(text)


def test_criterion_percentage_is_not_assessment_weight():
    data = analyse_plan('성취도 평가: 성취율 40% 미만은 확인이 필요합니다.')
    assert not data['groups']
    assert '40%' in render_plan_html(data['source'])


def test_valid_single_category_100():
    data = analyse_plan('성적 반영 비율 수행평가 100%: 발표 활동')
    assert data['composition_valid']


def test_decimal_percentages():
    data = analyse_plan('성적 반영 비율 지필평가 37.5% 수행평가 62.5%')
    assert data['composition_valid']
    assert [g['percent'] for g in data['groups']] == ['37.5', '62.5']


@pytest.mark.parametrize('text', ['', '   ', None])
def test_empty_text_does_not_fabricate_content(text):
    data = analyse_plan(text)
    assert not data['has_content']
    assert not data['groups']
    assert '첨부파일' in render_plan_html(text)


def test_unrecognised_text_is_preserved():
    source = '별도의 비율이 없는 자유로운 평가 안내\n수업에서 함께 확인합니다.'
    result = render_plan_html(source)
    assert source in result
    assert 'class="ep-composition"' not in result


def test_unknown_schedule_is_readable_not_invented():
    source = '단원별 주요 학습 내용\n수업일은 추후 안내합니다.'
    assert not analyse_plan(source)['schedule']
    assert '수업일은 추후 안내합니다.' in render_plan_html(source)


def test_custom_line_schedule():
    source = '단원별 주요 학습 내용\n전공 연계 프로젝트 (9월): 보고서와 발표'
    assert analyse_plan(source)['schedule'][0]['title'] == '전공 연계 프로젝트'


def test_invalid_month_stays_as_source_not_timeline():
    source = '단원별 주요 학습 내용\n함수와 그래프 (1011월): 추후 확인'
    assert not analyse_plan(source)['schedule']
    assert '1011월' in render_plan_html(source)


@pytest.mark.parametrize('payload', ['<script>alert(1)</script>', '</section><img src=x onerror=alert(1)>',
                                     '<svg onload="alert(1)">', '& < > " \''])
def test_text_is_html_escaped(payload):
    result = render_plan_html('평가 안내\n' + payload)
    assert '<script>' not in result
    assert '<img ' not in result
    assert '<svg ' not in result
    assert '&lt;' in result


def test_canonical_source_is_not_rewritten():
    assert analyse_plan(SAMPLE)['source'] == SAMPLE
    assert analyse_plan('  x\r\ny  ')['source'] == '  x\r\ny  '


def test_weights_sections_without_numbers_are_retained():
    source = '성적 반영 비율\n학기별로 별도 안내\n단원별 주요 학습 내용\n차후 안내'
    result = render_plan_html(source)
    assert '학기별로 별도 안내' in result
    assert '차후 안내' in result
