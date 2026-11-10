"""2022 common mathematics scope. Stable IDs never follow textbook ordering.

The seven areas and achievement-standard IDs are checked against the Gyeonggi
Office of Education's 2025 common-math assessment guide. Labels are paraphrases;
all quiz questions are authored templates, not copied assessment items.
"""
from .curriculum import TOPICS

SOURCE = 'https://www.goe.go.kr/resource/goe/na/bbs_2675/2025/11/1914f44c-2310-4557-a93b-3543adfb7bb8.pdf'
UNITS = {
    'polynomials': ('공통수학1', '다항식', [
        ('poly.add','01-01'),('poly.multiply','01-01'),('poly.divide','01-01'),
        ('identity','01-02'),('remainder','01-02'),('factor','01-03')]),
    'equations': ('공통수학1', '방정식과 부등식', [
        ('complex','02-01'),('quadratic.discriminant','02-02'),('quadratic.roots','02-03'),
        ('quadratic.graph','02-04'),('quadratic.line','02-05'),('quadratic.extrema','02-06'),
        ('equation.high','02-07'),('equation.system','02-08'),('inequality.linear','02-09'),
        ('inequality.absolute','02-10'),('inequality.quadratic','02-11')]),
    'counting': ('공통수학1', '경우의 수', [
        ('count.rules','03-01'),('count.permutation','03-02'),('count.combination','03-03')]),
    'matrices': ('공통수학1', '행렬', [
        ('matrix.meaning','04-01'),('matrix.add','04-02'),('matrix.multiply','04-02')]),
    'geometry': ('공통수학2', '도형의 방정식', [
        ('coordinate.distance','01-01'),('coordinate.section','01-01'),('line.equation','01-02'),
        ('line.relationship','01-02'),('line.distance','01-03'),('circle.equation','01-04'),
        ('circle.line','01-05'),('move.translation','01-06'),('move.reflection','01-07')]),
    'sets': ('공통수학2', '집합과 명제', [
        ('set.meaning','02-01'),('set.inclusion','02-02'),('set.operations','02-03'),
        ('logic.condition','02-04'),('logic.quantified','02-04'),('logic.implication','02-05'),
        ('logic.necessary','02-06'),('logic.proof','02-07'),('logic.absolute','02-08')]),
    # Keep all six old topic indices: saved function progress is never remapped.
    'functions': ('공통수학2', '함수와 그래프', [
        ('function.meaning','03-01'),('function.domain','03-01'),('function.composition','03-02'),
        ('function.inverse','03-03'),('function.rational','03-04'),('function.radical','03-05')]),
}
EXTRA = {
    'quadratic.line': ('이차함수와 직선의 위치 관계','두 식을 연립해 얻은 이차방정식의 서로 다른 실근 수가 교점 수입니다.'),
    'inequality.absolute': ('절댓값을 포함한 일차부등식','절댓값은 수직선에서의 거리입니다. 경계와 부등호를 함께 확인합니다.'),
    'logic.quantified': ('모든·어떤을 포함한 명제','모든 것에 대한 명제의 부정은 조건을 만족하지 않는 것이 하나라도 있다는 뜻입니다.'),
    'logic.necessary': ('충분조건·필요조건','p이면 q일 때 p는 q의 충분조건이고 q는 p의 필요조건입니다.'),
    'logic.absolute': ('절대부등식과 등호 성립','실수의 제곱은 음수가 아니라는 사실로 간단한 부등식을 증명합니다.'),
    'function.domain': ('정의역과 치역','정의역은 입력 전체, 치역은 실제로 나오는 출력 전체입니다.'),
}
FUNCTION_TITLES = ['함수의 뜻','정의역과 치역','합성함수','역함수','유리함수','무리함수']
LEVELS = [
    dict(level=1,title='기초 발견',description='핵심 용어와 개념을 짧은 질문으로 확인해요.'),
    dict(level=2,title='개념 적용',description='작은 수와 기본 조건에 개념을 적용해요.'),
    dict(level=3,title='개념 연결',description='식·조건·표현을 연결하며 풀이를 연습해요.'),
    dict(level=4,title='추론 도전',description='조건과 계산 결과를 꼼꼼하게 판단해요.'),
    dict(level=5,title='마스터 종합',description='이 단원의 두 개념을 함께 확인하는 종합 도전이에요.'),
]


def unit_info(unit):
    if not isinstance(unit,str) or unit not in UNITS:
        raise ValueError('과목과 단원을 다시 선택해 주세요.')
    subject,title,rows=UNITS[unit]
    topics=[]
    for i,(tid,standard) in enumerate(rows):
        name,concept=EXTRA.get(tid,(TOPICS.get(tid,{}).get('label',''),TOPICS.get(tid,{}).get('concept','')))
        if unit=='functions':name=FUNCTION_TITLES[i]
        topics.append(dict(id=tid,title=name,description=concept,standard=f'10공수{subject[-1]}-{standard}'))
    return dict(id=unit,subject=subject,title=title,topics=topics)
