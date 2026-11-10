"""Authored, deterministic concept practice; no network or API key required."""
from copy import deepcopy
from functools import lru_cache
from fractions import Fraction
import random
from . import bank as existing
from quiz_core import bank as core
from .concept_quiz_catalog import unit_info, LEVELS
from .math_text import markdown

# Correct principle, two common misconceptions. Explanations are our own text.
FOUNDATIONS = {
 'poly.add': ('동류항은 어떤 항끼리 모으나요?','문자와 차수가 모두 같은 항','계수만 같은 항','문자가 같으면 차수가 달라도 되는 항'),
 'poly.multiply': ('다항식의 곱셈에서 옳은 방법은?','한 식의 각 항을 다른 식의 모든 항에 곱한다','같은 자리에 있는 항끼리만 곱한다','상수항끼리만 곱한다'),
 'poly.divide': ('다항식 나눗셈의 나머지가 0이 아닐 때 옳은 것은?','나머지의 차수는 나누는 식의 차수보다 작다','나머지의 차수는 반드시 더 크다','나머지는 항상 일차식이다'),
 'identity': ('항등식에 대한 설명으로 옳은 것은?','문자에 어떤 값을 넣어도 성립한다','문자에 한 값만 넣었을 때 성립한다','해가 반드시 두 개이다'),
 'remainder': ('P(x)를 x-a로 나눈 나머지는?','P(a)','P(-a)','P(0)-a'),
 'factor': ('인수분해란 어떤 변형인가요?','다항식을 다항식들의 곱으로 나타내기','곱을 무조건 합으로 펼치기','모든 항을 0으로 바꾸기'),
 'complex': ('허수단위 i에 대하여 i²은?','-1','1','0'),
 'quadratic.discriminant': ('이차방정식의 판별식 D가 0보다 작으면?','서로 다른 두 허근을 갖는다','서로 다른 두 실근을 갖는다','중근을 갖는다'),
 'quadratic.roots': ('x²+bx+c=0의 두 근의 합과 곱은?','합은 -b, 곱은 c','합은 b, 곱은 c','합은 -b, 곱은 -c'),
 'quadratic.graph': ('y=f(x)의 그래프와 x축의 교점에서 성립하는 식은?','f(x)=0','x=0','f(x)=1'),
 'quadratic.line': ('이차함수와 직선을 연립한 방정식이 중근을 가지면?','한 점에서 접한다','서로 다른 두 점에서 만난다','만나지 않는다'),
 'quadratic.extrema': ('닫힌 구간에서 이차함수의 최대·최소를 구하려면?','구간 안의 꼭짓점과 양 끝점의 값을 살핀다','항상 꼭짓점의 값만 살핀다','항상 오른쪽 끝점만 살핀다'),
 'equation.high': ('인수분해한 식의 곱이 0이면?','인수 중 적어도 하나가 0이다','모든 인수가 동시에 0이어야 한다','모든 인수가 1이다'),
 'equation.system': ('연립방정식의 해는 어떤 값인가요?','주어진 모든 방정식을 동시에 만족하는 값','어느 한 식만 만족하면 되는 값','항상 x와 y가 같은 값'),
 'inequality.linear': ('연립부등식의 해는?','각 부등식 해의 공통부분','각 부등식 해를 무조건 모두 합친 것','각 부등식의 경계값만 모은 것'),
 'inequality.absolute': ('양수 a에 대하여 |x|<a의 뜻은?','-a<x<a','x<-a 또는 x>a','x=a 또는 x=-a'),
 'inequality.quadratic': ('서로 다른 두 근 사이에서 최고차항 계수가 양수인 이차식의 부호는?','음수','양수','항상 0'),
 'count.rules': ('서로 겹치지 않는 두 경우 중 하나를 선택할 때는?','각 경우의 수를 더한다','각 경우의 수를 곱한다','각 경우의 수를 항상 나눈다'),
 'count.permutation': ('순열에서 같은 구성원의 순서가 바뀌면?','다른 경우로 센다','항상 같은 경우로 센다','두 경우를 모두 제외한다'),
 'count.combination': ('조합에서 같은 구성원의 순서가 바뀌면?','같은 선택으로 센다','반드시 다른 선택으로 센다','경우의 수가 항상 두 배가 된다'),
 'matrix.meaning': ('행렬의 (2, 1) 성분은 어디에 있나요?','2행 1열','1행 2열','2행 2열'),
 'matrix.add': ('행렬의 덧셈·뺄셈을 할 수 있는 조건은?','행의 수와 열의 수가 각각 같다','원소의 합만 같다','두 행렬 모두 반드시 정사각행렬이다'),
 'matrix.multiply': ('행렬 AB의 곱셈을 할 수 있는 조건은?','A의 열 수와 B의 행 수가 같다','A의 행 수와 B의 열 수만 같으면 된다','모든 행렬은 서로 곱할 수 있다'),
 'coordinate.distance': ('두 점 사이의 거리를 구하는 기본 원리는?','좌표의 차와 피타고라스 정리를 이용한다','두 x좌표를 무조건 더한다','두 y좌표의 곱만 구한다'),
 'coordinate.section': ('선분의 중점의 좌표는?','양 끝점의 각 좌표의 평균','양 끝점의 각 좌표의 합','양 끝점의 각 좌표의 곱'),
 'line.equation': ('기울기의 뜻으로 옳은 것은?','y의 변화량을 x의 변화량으로 나눈 값','x와 y의 변화량을 더한 값','항상 y절편과 같은 값'),
 'line.relationship': ('기울기가 있는 서로 다른 두 직선이 수직이면?','두 기울기의 곱이 -1이다','두 기울기가 항상 같다','두 기울기의 합이 항상 0이다'),
 'line.distance': ('점과 직선 사이의 거리는 어떤 길이인가요?','점에서 직선에 내린 수선의 길이','점과 직선 위 임의의 점 사이의 길이','직선의 y절편'),
 'circle.equation': ('원의 방정식 (x-a)²+(y-b)²=r²에서 중심은?','(a,b)','(-a,-b)','(r,r)'),
 'circle.line': ('원의 중심과 직선 사이의 거리가 반지름보다 작으면?','서로 다른 두 점에서 만난다','한 점에서 접한다','만나지 않는다'),
 'move.translation': ('점 (x,y)를 x방향으로 a, y방향으로 b만큼 평행이동하면?','(x+a,y+b)','(x-a,y-b)','(ax,by)'),
 'move.reflection': ('점 (x,y)를 직선 y=x에 대하여 대칭이동하면?','(y,x)','(-x,-y)','(x,-y)'),
 'set.meaning': ('집합의 원소를 표현할 때 옳은 것은?','같은 원소를 여러 번 적어도 한 원소로 센다','적은 순서가 다르면 항상 다른 집합이다','원소가 없는 집합은 존재하지 않는다'),
 'set.inclusion': ('A가 B의 부분집합이라는 뜻은?','A의 모든 원소가 B에도 속한다','B의 모든 원소가 반드시 A에 속한다','A와 B에는 공통 원소가 없다'),
 'set.operations': ('A∩B에 속하는 원소는?','A와 B에 모두 속하는 원소','A에만 속하는 원소','A와 B 어느 쪽에도 속하지 않는 원소'),
 'logic.condition': ('명제에 대한 설명으로 옳은 것은?','참인지 거짓인지 분명하게 판단할 수 있는 문장','사람마다 느낌이 다른 모든 문장','항상 참인 문장만 뜻한다'),
 'logic.quantified': ('모든 원소가 조건을 만족한다는 명제의 부정은?','조건을 만족하지 않는 원소가 적어도 하나 있다','모든 원소가 조건을 만족하지 않는다','조건을 만족하는 원소가 하나 있다'),
 'logic.implication': ('명제 p⇒q와 참·거짓이 항상 같은 명제는?','대우','역','가정 p만의 부정'),
 'logic.necessary': ('p⇒q가 참이면 옳은 설명은?','p는 q의 충분조건이다','p는 언제나 q의 필요조건이다','p와 q는 언제나 필요충분조건이다'),
 'logic.proof': ('귀류법의 핵심은?','결론의 부정을 가정한 뒤 모순을 이끈다','증명할 결론을 처음부터 참이라고 가정한다','참인 예 하나만 들면 모든 경우가 증명된다'),
 'logic.absolute': ('모든 실수 a,b에 대해 a²+b²≥2ab가 성립하는 이유는?','(a-b)²≥0이기 때문이다','a와 b가 항상 양수이기 때문이다','a와 b가 항상 같기 때문이다'),
}


def _custom(tid, level, seed):
    r=random.Random(seed)
    a,b,c=r.randint(1,5),r.randint(2,6),r.randint(1,5)
    n=lambda prompt,value,why:core.numeric(prompt,value,tid,why,r)
    m=lambda prompt,right,wrong,why:core.make(prompt,right,wrong,tid,why,r)
    if tid=='inequality.absolute':
        if level==2:
            return n(f'|x-{a}|≤{b}를 만족하는 정수 x의 개수는?',2*b+1,
                     f'{a-b}≤x≤{a+b}이므로 양 끝점을 포함한 정수는 {2*b+1}개입니다.')
        if level==3:
            return n(f'|2x-{2*a}|<{2*b}를 만족하는 정수 x의 개수는?',2*b-1,
                     f'양변을 2로 나누면 |x-{a}|<{b}입니다. {a-b}<x<{a+b} 안의 정수는 {2*b-1}개입니다.')
        return n(f'|x-{a}|≤{b}이고 x>{a}인 정수 x의 개수는?',b,
                 f'{a-b}≤x≤{a+b}와 x>{a}의 공통부분은 {a}<x≤{a+b}이므로 {b}개입니다.')
    if tid=='quadratic.line':
        if level<4:
            k=r.choice([-b,0,b]);count=2 if k>0 else 1 if k==0 else 0
            return n(f'이차함수 y=(x-{a})²+{c}와 직선 y={c+k}의 교점 개수는?',count,
                     f'연립하면 (x-{a})²={k}입니다. 서로 다른 실근의 개수와 같은 {count}개입니다.')
        return n(f'이차함수 y=x²-{2*a}x+{c}와 직선 y={b}x+k가 접할 때 k는?',Fraction(4*c-(2*a+b)**2,4),
                 f'연립한 방정식 x²-({2*a+b})x+({c}-k)=0의 판별식이 0이므로 k=({4*c}-({2*a+b})²)/4입니다.')
    if tid=='logic.quantified':
        return m(f'명제 “모든 실수 x에 대하여 x²>{a}이다”의 부정은?',
                 f'어떤 실수 x에 대하여 x²≤{a}이다',
                 [f'모든 실수 x에 대하여 x²≤{a}이다',f'어떤 실수 x에 대하여 x²>{a}이다',f'모든 실수 x에 대하여 x²<{a}이다'],
                 '모든을 어떤으로 바꾸고 조건을 부정합니다. >의 부정은 ≤입니다.')
    if tid=='logic.necessary':
        return m(f'실수 x에 대해 p: x>{a+b}, q: x>{a}일 때 p는 q의 어떤 조건인가요?',
                 '충분조건이지만 필요조건은 아니다',['필요조건이지만 충분조건은 아니다','필요충분조건이다','필요조건도 충분조건도 아니다'],
                 f'x>{a+b}이면 반드시 x>{a}입니다. 그러나 x={a+1}은 q만 만족하므로 역은 거짓입니다.')
    if tid=='logic.proof':
        if level<4:
            return m(f'자연수 n에 대해 “n²이 {2**a}의 배수이면 n은 짝수이다”를 대우로 증명할 때 시작할 가정은?',
                     'n이 홀수라고 가정한다',['n이 짝수라고 가정한다',f'n²이 {2**a}의 배수라고 가정한다','증명 없이 결론을 가정한다'],
                     f'대우는 “n이 홀수이면 n²은 {2**a}의 배수가 아니다”입니다. 홀수의 제곱은 홀수이므로 2의 배수가 아닙니다.')
        return m(f'√{a*a+1}이 무리수임을 귀류법으로 증명하려 합니다. 첫 가정으로 옳은 것은?',
                 f'√{a*a+1}이 유리수라고 가정한다',[f'√{a*a+1}이 무리수라고 가정한다',f'√{a*a+1}=0이라고 가정한다',f'{a*a+1}<0이라고 가정한다'],
                 f'{a}²<{a*a+1}<({a+1})²이므로 제곱수가 아닙니다. 결론의 부정인 유리수임을 가정하고 기약분수 표현에서 모순을 이끌어야 합니다.')
    if tid=='logic.absolute':
        if level==2:
            return n(f'모든 실수 x에 대해 (x-{a})²+{b}의 최솟값은?',b,
                     f'(x-{a})²≥0이므로 전체는 {b} 이상입니다. x={a}일 때 등호가 성립합니다.')
        if level==3:
            return n(f'양수 x,y에 대하여 xy={a*a}일 때 x+y의 최솟값은?',2*a,
                     f'x+y≥2√(xy)={2*a}입니다. x=y={a}일 때 등호가 성립합니다.')
        return m(f'모든 실수 x,y에 대해 x²+{a*a}y²≥{2*a}xy를 증명하는 식은?',
                 f'x²+{a*a}y²-{2*a}xy=(x-{a}y)²≥0',
                 [f'x²+{a*a}y²-{2*a}xy=(x+{a}y)²≥0',f'x²+{a*a}y²-{2*a}xy=0',f'x²+{a*a}y²-{2*a}xy<0'],
                 f'좌변에서 우변을 빼면 (x-{a}y)²입니다. 제곱은 0 이상이고 x={a}y에서 등호가 성립합니다.')
    # Complete operations not represented by the old four-choice families.
    if tid=='complex' and level>=3:
        return n(f'복소수 ({a*b-c} + {a+b*c}i)/({b}+i)의 실수부분은?',a,
                 f'({a}+{c}i)({b}+i)=({a*b-c})+({a+b*c})i이므로 몫은 {a}+{c}i입니다.')
    if tid=='matrix.add' and level>=3:
        return n(f'A=[[{a},{b}],[{c},1]], B=[[{b},{c}],[1,0]]일 때 {c}A-B의 (1,2) 성분은?',c*b-c,
                 f'해당 성분은 {c}×{b}-{c}={c*b-c}입니다. 실수배 후 같은 위치끼리 뺍니다.')
    if tid=='quadratic.extrema':
        lo,hi=a-1,a+b
        if level==2:
            return n(f'{lo}≤x≤{hi}에서 y=(x-{a})²+{c}의 최솟값은?',c,
                     f'꼭짓점 x={a}가 구간 안에 있고 제곱은 0 이상이므로 최솟값은 {c}입니다.')
        if level==3:
            return n(f'{lo}≤x≤{hi}에서 y=(x-{a})²+{c}의 최댓값은?',b*b+c,
                     f'양 끝점의 값은 {1+c}, {b*b+c}입니다. 더 큰 값 {b*b+c}이 최댓값입니다.')
        return n(f'{a+1}≤x≤{hi}에서 y=(x-{a})²+{c}의 최솟값은?',1+c,
                 f'꼭짓점은 구간 밖입니다. x={a+1}에서 꼭짓점에 가장 가까워 최솟값은 {1+c}입니다.')
    return None


def practice(tid,level,seed):
    special=_custom(tid,level,seed)
    if special:return special
    return existing.generate(tid,seed,level={2:'천천히',3:'기본',4:'한 걸음 더'}[level])[seed%5]


def _display(q):
    q=deepcopy(q)
    for k in ('prompt','explanation'):q[k]=markdown(q[k])
    q['options']=[markdown(o) for o in q['options']]
    return q


@lru_cache(maxsize=6)
def bank(unit):
    info=unit_info(unit)
    if unit=='functions':raise ValueError('기존 함수 문제은행을 사용하세요.')
    questions=[]
    for i,t in enumerate(info['topics']):
        tid=t['id'];stem,right,*wrong=FOUNDATIONS[tid]
        for j,prompt in enumerate([stem,'기초 개념 확인: '+stem]):
            questions.append(dict(id=f'{unit}:1:{i}:{j}',level=1,topic=i,prompt=prompt,
                options=[right,*wrong],answer=0,explanation=right+'. '+t['description'],standard=t['standard']))
        for level in (2,3,4,5):
            seen=set()
            for seed in range(1,65):
                q=practice(tid,min(level,4),seed+level*100)
                if level==5:
                    other=info['topics'][(i+1)%len(info['topics'])]
                    b=practice(other['id'],3,seed+701)
                    answer=q['options'][q['answer']];second=b['options'][b['answer']]
                    wrong_a=q['options'][(q['answer']+1)%len(q['options'])]
                    wrong_b=b['options'][(b['answer']+1)%len(b['options'])]
                    q=dict(prompt=f'두 문제의 답을 바르게 짝지은 것은?\n㉠ {q["prompt"]}\n㉡ {b["prompt"]}',
                        options=[f'㉠ {answer} / ㉡ {second}',f'㉠ {wrong_a} / ㉡ {second}',f'㉠ {answer} / ㉡ {wrong_b}'],answer=0,
                        explanation=f'㉠ {q["explanation"]}\n㉡ {b["explanation"]}')
                if q['prompt'] in seen:continue
                seen.add(q['prompt'])
                questions.append(dict(id=f'{unit}:{level}:{i}:{seed}',level=level,topic=i,
                    **{k:q[k] for k in ('prompt','options','answer','explanation')},standard=t['standard']))
                if len(seen)>=8:break
            if len(seen)<2:raise ValueError(f'문항 변형 부족: {unit}/{tid}/{level}')
    return dict(topics=info['topics'],levels=LEVELS,questions=[_display(q) for q in questions])
