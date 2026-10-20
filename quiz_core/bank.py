"""Parameterized, locally generated common-math concept questions.

This is a curated template generator, NOT an AI response. Every paper is a
teacher-reviewable draft. Four choices, one answer, 1-10 unique question types.
No network calls or eval/exec. The generation seed never goes to students.
"""
from __future__ import annotations
import hashlib
import json
import math
import random
import re
from fractions import Fraction
from config import DEFAULT_UNITS, SUBJECTS

VERSION = "concept-templates-2-unique-types"
MAX_QUESTIONS = 10

# A question type denotes the mathematical operation, not its wording/numbers.
# Different x/y coordinates, signs or story contexts are grouped conservatively.
TYPE_ALIASES = {
    "상수항과 나머지": "나머지정리",
    "항등식": "항등식의 계수 비교",
    "인수분해와 부호": "이차식 인수분해",
    "이차함수의 최댓값": "이차함수의 최솟값",
    "이차부등식과 구간": "절댓값 부등식",
    "조합의 대칭": "조합",
    "두 점과 기울기": "기울기",
    "반지름과 지름": "반지름",
    "합성함수의 순서": "합성함수",
    "함수와 대응": "역함수",
}

def question_type(question):
    """Stable, hidden grouping identity. Presentation changes don't create types."""
    concept = re.sub(r"\\s+", " ", str(question.get("concept", "")).strip())
    canonical = TYPE_ALIASES.get(concept, concept)
    return str(question.get("type_id") or ("concept:" + canonical))

def concept_type(question):
    concept = re.sub(r"\\s+", " ", str(question.get("concept", "")).strip())
    return TYPE_ALIASES.get(concept, concept)

def unique_draft_questions(questions):
    """Explicit teacher action only. Never use on already published papers."""
    result, seen_types, seen_concepts = [], set(), set()
    for question in questions:
        key, concept = question_type(question), concept_type(question)
        if key in seen_types or (concept and concept in seen_concepts):
            continue
        result.append(question)
        seen_types.add(key)
        if concept:
            seen_concepts.add(concept)
    return validate_questions(result[:MAX_QUESTIONS])

def available_type_count(subject, unit):
    if subject not in SUBJECTS or unit not in units(subject):
        return 0
    rng = random.Random(12345)
    idx = units(subject).index(unit)
    return len({concept_type(_candidate(subject, idx, k, rng)) for k in range(7)})



def text(v):
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return str(v)


def fingerprint(q):
    # Shuffling choices or changing distractors does not make a new question.
    return hashlib.sha256(re.sub(r"\s+", " ", q["prompt"].strip()).encode()).hexdigest()


def validate_questions(questions):
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise ValueError("객관식 문제는 1~10문항으로 구성해 주세요.")
    out, seen, seen_types, seen_concepts = [], set(), set(), set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ValueError(f"{i+1}번 문제 형식을 확인하세요.")
        p, options, answer = q.get("prompt"), q.get("options"), q.get("answer")
        if not isinstance(p, str) or not p.strip() or len(p) > 2500:
            raise ValueError(f"{i+1}번 발문을 1~2500자로 입력하세요.")
        if (not isinstance(options, list) or len(options) != 4
                or any(not isinstance(x, str) or not x.strip() or len(x) > 800 for x in options)
                or len({re.sub(r"\s+", " ", x.strip()) for x in options}) != 4):
            raise ValueError(f"{i+1}번 보기는 서로 다른 4개를 입력하세요.")
        if type(answer) is not int or not 0 <= answer < 4:
            raise ValueError(f"{i+1}번 정답을 선택하세요.")
        explanation, concept = q.get("explanation", ""), q.get("concept", "개념 확인")
        if not isinstance(explanation, str) or len(explanation) > 4000 or not isinstance(concept, str) or len(concept)>150:
            raise ValueError(f"{i+1}번 해설 또는 개념 이름을 확인하세요.")
        new = {"id": f"q{i+1:02}", "prompt": p.strip(), "options": [x.strip() for x in options],
               "answer": answer, "explanation": explanation.strip(), "concept": concept.strip() or "개념 확인"}
        supplied_type = q.get("type_id")
        if supplied_type is not None and (
            not isinstance(supplied_type, str) or not supplied_type.strip() or len(supplied_type) > 200
        ):
            raise ValueError(f"{i+1}번 유형 식별자를 확인하세요.")
        new["type_id"] = supplied_type.strip() if supplied_type else question_type(new)
        key, concept_key = question_type(new), concept_type(new)
        fp = fingerprint(new)
        if fp in seen:
            raise ValueError("같은 발문의 문제가 중복되어 있습니다.")
        if key in seen_types or concept_key in seen_concepts:
            raise ValueError(f"{i+1}번과 같은 문제 유형이 중복됩니다. 한 퀴즈에서는 유형별 한 문항만 출제해 주세요.")
        seen.add(fp); seen_types.add(key); seen_concepts.add(concept_key)
        new["fingerprint"] = fp
        out.append(new)
    return out


def subjects():
    return list(SUBJECTS)


def units(subject):
    return list(DEFAULT_UNITS.get(subject, []))


def make(prompt, correct, wrongs, concept, explanation, rng):
    correct = text(correct)
    opts = [correct]
    for x in wrongs:
        s = text(x)
        if s not in opts: opts.append(s)
        if len(opts) == 4: break
    if len(opts) != 4: raise ValueError("서로 다른 보기를 생성하지 못했습니다.")
    rng.shuffle(opts)
    return {"prompt": prompt, "options": opts, "answer": opts.index(correct),
            "concept": concept, "explanation": explanation}


def numeric(prompt, value, concept, explanation, rng, distractors=()):
    pool = list(distractors) + [value+1, value-1, -value, value+2, value-2, value+3, value+4]
    return make(prompt, value, pool, concept, explanation, rng)


def _candidate(subject, unit_index, k, r, span=9):
    a,b,c = r.randint(1,span), r.randint(1,span), r.randint(1,span)
    x,y = r.randint(-8,8), r.randint(-8,8)
    def n(prompt, value, tag, why, wrong=()): return numeric(prompt, value, tag, why, r, wrong)
    def m(prompt, value, wrong, tag, why): return make(prompt, value, wrong, tag, why, r)
    if subject == "공통수학1":
        if unit_index == 0:
            if k==0: return n(f"({a}x+{b})+({c}x+{a})에서 x의 계수는?", a+c,"동류항의 덧셈",f"x항끼리 더하면 ({a}+{c})x입니다.")
            if k==1: return n(f"({a}x+{b})({c}x+{a})를 전개할 때 x²의 계수는?",a*c,"다항식의 곱셈",f"최고차항의 곱 {a}x×{c}x={a*c}x²입니다.")
            if k==2: return n(f"({a}x+{b})-({c}x+{a})의 상수항은?",b-a,"다항식의 뺄셈",f"뒤 괄호의 부호를 바꾸어 상수항 {b}-{a}를 계산합니다.")
            if k==3: return n(f"다항식 P(x)={a}x²+{b}x+{c}일 때 P({x})의 값은?",a*x*x+b*x+c,"다항식의 값",f"x에 {x}를 대입하면 {a}×({x})²+{b}×({x})+{c}입니다.")
            if k==4: return n(f"x^{a} × x^{b}을 정리하면 x의 지수는?",a+b,"단항식의 곱셈",f"밑이 같으므로 지수를 더해 {a+b}입니다.")
            if k==5: return n(f"다항식 {a}x^{b+2}+{c}x+{b}의 차수는?",b+2,"다항식의 차수",f"0이 아닌 항의 차수 중 가장 큰 {b+2}입니다.")
            return n(f"(x+{a})(x+{b})를 전개했을 때 x의 계수는?",a+b,"곱셈 공식",f"x²+({a}+{b})x+{a*b}이므로 {a+b}입니다.")
        if unit_index == 1:
            if k==0: return n(f"P(x)=x²+{a}x+{b}를 x-{c}로 나눈 나머지는?",c*c+a*c+b,"나머지정리",f"나머지는 P({c})={c*c+a*c+b}입니다.")
            if k==1: return n(f"P(x)={a}x²+{b}x+{c}를 x로 나눈 나머지는?",c,"상수항과 나머지",f"x=0을 대입한 P(0)={c}입니다.")
            if k==2: return n(f"ax+{b}={c}x+b가 모든 실수 x에 대해 성립할 때 a는?",c,"항등식의 계수 비교",f"양변 x의 계수가 같아야 하므로 a={c}입니다.")
            if k==3: return n(f"P(x)={a}x³+{b}x²+{c}x+{a+b}의 모든 계수의 합은?",2*a+2*b+c,"계수의 합",f"x=1을 대입한 P(1)={2*a+2*b+c}입니다.")
            if k==4: return n(f"x²+kx+{a*b}가 x-{a}로 나누어떨어질 때 k는?",-(a+b),"인수정리",f"x={a}일 때 0이므로 {a*a}+{a}k+{a*b}=0입니다.")
            if k==5: return n(f"P(x)=x²+{a}x+{b}를 x+{c}로 나눈 나머지는?",c*c-a*c+b,"나머지정리",f"x=-{c}를 대입한 P(-{c})를 구합니다.")
            return n(f"x²+{a+b}x+{a*b}=(x+{a})(x+k)가 항등식일 때 k는?",b,"항등식",f"전개하여 계수를 비교하면 k={b}입니다.")
        if unit_index == 2:
            if k==0: return n(f"x²+{a+b}x+{a*b}=(x+{a})(x+k)로 인수분해할 때 k는?",b,"이차식 인수분해",f"두 수의 합은 {a+b}, 곱은 {a*b}입니다.")
            if k==1: return n(f"x²-{a*a}=(x-{a})(x+k)일 때 k는?",a,"제곱의 차",f"x²-a²=(x-a)(x+a)를 사용합니다.")
            if k==2: return n(f"x²+{2*a}x+{a*a}=(x+k)²일 때 k는?",a,"완전제곱식",f"(x+a)²=x²+2ax+a²입니다.")
            if k==3: return n(f"{a*b}x²+{a*c}x={a}x({b}x+k)일 때 k는?",c,"공통인수",f"각 항에서 {a}x를 묶습니다.")
            if k==4: return n(f"x²-{a+b}x+{a*b}=(x-{a})(x-k)일 때 k는?",b,"인수분해와 부호",f"(x-a)(x-b)=x²-(a+b)x+ab입니다.")
            if k==5: return n(f"x³-{a**3}=(x-{a})(x²+kx+{a*a})일 때 k는?",a,"세제곱의 차",f"x³-a³=(x-a)(x²+ax+a²)입니다.")
            return n(f"x³+{a**3}=(x+{a})(x²-kx+{a*a})일 때 k는?",a,"세제곱의 합",f"x³+a³=(x+a)(x²-ax+a²)입니다.")
        if unit_index == 3:
            if k==0:
                e=r.randint(2,40); v=['1','i','-1','-i'][e%4]
                return m(f"허수단위 i에 대하여 i^{e}의 값은?",v,['1','i','-1','-i'],"허수단위의 거듭제곱","i의 거듭제곱은 i, -1, -i, 1을 주기로 반복합니다.")
            if k==1: return n(f"복소수 ({a}+{b}i)+({c}+{a}i)의 실수부분은?",a+c,"복소수의 덧셈","실수부분끼리, 허수부분끼리 더합니다.")
            if k==2: return n(f"({a}+{b}i)({a}-{b}i)의 값은?",a*a+b*b,"켤레복소수",f"i²=-1이므로 {a}²+{b}²입니다.")
            if k==3: return n(f"이차방정식 x²-{a+b}x+{a*b}=0의 두 근의 합은?",a+b,"근과 계수의 관계","이차방정식 x²+px+q=0에서 두 근의 합은 -p입니다.")
            if k==4: return n(f"이차방정식 {a}x²+{b}x+{c}=0의 판별식 D=b²-4ac의 값은?",b*b-4*a*c,"판별식",f"{b}²-4×{a}×{c}를 계산합니다.")
            if k==5: return n(f"이차방정식 x²-{a+b}x+{a*b}=0의 두 근의 곱은?",a*b,"근과 계수의 관계","최고차항 계수가 1이므로 두 근의 곱은 상수항입니다.")
            return n(f"실수 x, y에 대하여 x+yi={a}+{b}i일 때 x+y는?",a+b,"복소수가 같을 조건","실수부분과 허수부분이 각각 같아야 합니다.")
        if unit_index == 4:
            if k==0: return n(f"이차함수 y=(x-{a})²+{b}의 꼭짓점의 x좌표는?",a,"꼭짓점",f"꼭짓점은 ({a}, {b})입니다.")
            if k==1: return n(f"실수 전체에서 y=(x-{a})²+{b}의 최솟값은?",b,"이차함수의 최솟값",f"제곱은 0 이상이므로 x={a}에서 최솟값 {b}입니다.")
            if k==2: return n(f"실수 전체에서 y=-(x-{a})²+{b}의 최댓값은?",b,"이차함수의 최댓값",f"-(x-{a})²≤0이므로 최댓값은 {b}입니다.")
            if k==3: return n(f"y=x²-{a*a}의 그래프와 x축의 교점 중 x좌표가 양수인 점의 x좌표는?",a,"방정식과 그래프",f"x²={a*a}의 양의 해는 {a}입니다.")
            if k==4: return n(f"y=(x-{a})²+{b}의 그래프와 직선 y={b}의 교점 개수는?",1,"직선과 이차함수의 위치","(x-a)²=0은 중근을 가지므로 한 점에서 접합니다.")
            if k==5: return n(f"0≤x≤{a}에서 y=x²+{b}의 최댓값은?",a*a+b,"제한된 구간의 최대",f"구간에서 x²는 x={a}일 때 최대입니다.")
            return n(f"y=x²-{2*a}x+{b}의 그래프의 대칭축 x=k에서 k는?",a,"대칭축","이차함수 y=ax²+bx+c의 대칭축은 x=-b/(2a)입니다.")
        if unit_index == 5:
            if k==0: return n(f"부등식 {a}x+{b}<{a*c+b}의 해를 x<k로 쓸 때 k는?",c,"일차부등식","양수로 나누면 부등호 방향이 유지됩니다.")
            if k==1: return m(f"부등식 -{a}x<{a*b}의 해는?",f"x > -{b}",[f"x < -{b}",f"x > {b}",f"x < {b}"],"음수로 나누는 부등식","음수로 나누면 부등호 방향이 바뀝니다.")
            if k==2: return n(f"|x|<{a}를 만족하는 정수 x의 개수는?",2*a-1,"절댓값 부등식",f"-{a}<x<{a} 사이의 정수는 {2*a-1}개입니다.")
            if k==3: return n(f"연립방정식 x+y={a+b}, x-y={a-b}에서 x는?",a,"연립방정식",f"두 식을 더하면 2x={2*a}입니다.")
            if k==4: return n(f"방정식 (x-{a})(x-{a+1})(x-{a+2})=0의 서로 다른 실근 개수는?",3,"삼차방정식","곱이 0이려면 각 인수 중 하나가 0이며 세 근은 서로 다릅니다.")
            if k==5: return n(f"부등식 (x-{a})(x-{a+b})<0의 해를 {a}<x<k로 나타낼 때 k는?",a+b,"이차부등식",f"최고차항 계수가 양수이므로 두 근 사이에서 음수입니다. 작은 근은 {a}입니다.")
            return n(f"x²<{a*a}를 만족하는 정수 x의 개수는?",2*a-1,"이차부등식과 구간",f"-{a}<x<{a}입니다.")
        if unit_index == 6:
            if k==0: return n(f"상의 {a}벌과 하의 {b}벌 중 각각 1벌씩 고르는 방법의 수는?",a*b,"곱의 법칙",f"{a}×{b}={a*b}입니다.")
            if k==1: return n(f"서로 다른 주스 {a}종과 차 {b}종 중 음료를 딱 1개 고르는 방법의 수는?",a+b,"합의 법칙","서로 겹치지 않는 두 경우의 수를 더합니다.")
            if k==2:
                n1=r.randint(3,8)
                return n(f"서로 다른 {n1}명 중 회장과 부회장을 1명씩 뽑는 방법의 수는?",n1*(n1-1),"순열","역할이 다르므로 순서를 구분합니다.")
            if k==3:
                n1=r.randint(3,span+3); picked=r.randint(1,min(3,n1-1))
                return n(f"서로 다른 {n1}명 중 대표 {picked}명을 뽑는 방법의 수는?",math.comb(n1,picked),"조합",f"역할을 구분하지 않는 선택이므로 {n1}C{picked}을 계산합니다.")
            if k==4:
                n1=r.randint(3,span+2); picked=r.randint(2,3)
                return n(f"서로 다른 책 {n1}권 중 {picked}권을 골라 한 줄로 배열하는 방법의 수는?",math.perm(n1,picked),"순열",f"고른 책의 순서를 구분하므로 {n1}P{picked}을 계산합니다.")
            if k==5: return n(f"숫자 1부터 {a+2}까지 중 두 숫자를 중복 없이 골라 순서대로 놓는 방법의 수는?",(a+2)*(a+1),"순열","첫 자리와 둘째 자리에 놓을 수 있는 수를 곱합니다.")
            return n(f"{a+2}명 중 {a+1}명을 대표로 고르는 방법의 수는?",a+2,"조합의 대칭","고르지 않을 1명을 정하는 것과 같습니다.")
        if unit_index == 7:
            if k==0: return n(f"행렬 [[{a}, {b}], [{c}, {a+b}]]의 (2, 1) 성분은?",c,"행렬의 성분","(2, 1)은 2행 1열에 있는 성분입니다.")
            if k==1: return n(f"A=[[{a}, {b}], [0, 1]], B=[[{c}, 0], [1, 0]]일 때 A+B의 (1, 1) 성분은?",a+c,"행렬의 덧셈","같은 위치의 성분끼리 더합니다.")
            if k==2: return n(f"A=[[{a}, {b}], [0, 1]]일 때 {c}A의 (1, 2) 성분은?",c*b,"행렬의 실수배","모든 성분에 같은 실수를 곱합니다.")
            if k==3: return n(f"A=[[{a}, {b}]], B=[[{c}], [2]]일 때 AB의 유일한 성분은?",a*c+2*b,"행렬의 곱셈",f"행과 열의 대응 성분을 곱하여 더하면 {a}×{c}+{b}×2입니다.")
            if k==4: return n(f"{a}×{b} 행렬에는 성분이 모두 몇 개 있는가?",a*b,"행렬의 크기","행의 수와 열의 수를 곱합니다.")
            if k==5: return n(f"[[x, {b}], [{c}, 1]]=[[{a}, {b}], [{c}, 1]]일 때 x는?",a,"행렬이 같을 조건","같은 위치의 성분이 모두 같아야 합니다.")
            return n(f"A=[[{a}, {b}], [{c}, 1]], I=[[1, 0], [0, 1]]일 때 AI의 (1, 2) 성분은?",b,"단위행렬","AI=A이므로 (1, 2) 성분은 그대로입니다.")
    if subject == "공통수학2":
        if unit_index == 0:
            if k==0: return n(f"A({x}, {y}), B({x+a}, {y}) 사이의 거리는?",a,"두 점 사이의 거리","y좌표가 같으므로 x좌표 차의 절댓값을 구합니다.")
            if k==1: return n(f"A({x}, {y}), B({x+2*a}, {y+2*b})의 중점의 x좌표는?",x+a,"중점",f"x좌표의 평균 ({x}+{x+2*a})÷2를 구합니다.")
            if k==2: return n(f"A({x}, {y}), B({x+2*a}, {y+2*b})의 중점의 y좌표는?",y+b,"중점","양 끝점 y좌표의 평균을 구합니다.")
            if k==3: return n(f"A(0, 0), B({3*a}, {3*b})를 AP:PB=1:2로 내분하는 P의 x좌표는?",a,"내분점","A에서 B까지 1/3만큼 이동하므로 x좌표는 B의 x좌표의 1/3입니다.")
            if k==4: return n(f"A({x}, {y}), B({x+3*a}, {y+4*a}) 사이의 거리는?",5*a,"두 점 사이의 거리",f"√[({3*a})²+({4*a})²]={5*a}입니다.")
            if k==5: return n(f"점 (-{a}, {b})는 제몇 사분면에 있는가?",2,"좌표와 사분면","x<0, y>0이므로 제2사분면입니다.")
            return n(f"A(0, 0), B({4*a}, {4*b})를 AP:PB=3:1로 내분하는 P의 y좌표는?",3*b,"내분점","A에서 B까지 3/4만큼 이동합니다.")
        if unit_index == 1:
            if k==0: return n(f"직선 y={a}x+{b}의 기울기는?",a,"기울기","y=mx+n에서 기울기는 m입니다.")
            if k==1: return n(f"직선 y={a}x+{b}의 y절편은?",b,"절편","x=0일 때의 y값입니다.")
            if k==2: return n(f"두 점 ({x}, {y}), ({x+a}, {y+a*b})를 지나는 직선의 기울기는?",b,"두 점과 기울기",f"y의 증가량 {a*b}를 x의 증가량 {a}로 나눕니다.")
            if k==3: return n(f"직선 y={a}x+{b}와 평행한 직선 y=kx+{b+c}의 k는?",a,"평행 조건","두 직선의 기울기가 같아야 합니다.")
            if k==4: return n(f"직선 y={a}x+{b}와 수직인 직선의 기울기는?",Fraction(-1,a),"수직 조건","기울기의 곱이 -1이므로 -1/m입니다.")
            if k==5: return n(f"점 ({x}, {y})를 지나고 기울기가 {a}인 직선 y={a}x+k의 k는?",y-a*x,"직선의 방정식","주어진 점의 좌표를 대입하여 k를 구합니다.")
            return n(f"점 ({x}, {y})에서 직선 x={x+a}까지의 거리는?",a,"점과 직선 사이 거리","수직선 x=c까지 거리는 x좌표 차의 절댓값입니다.")
        if unit_index == 2:
            if k==0: return n(f"원 (x-{a})²+(y-{b})²={c*c}의 중심의 x좌표는?",a,"원의 중심",f"원의 중심은 ({a}, {b})입니다.")
            if k==1: return n(f"원 (x-{a})²+(y-{b})²={c*c}의 반지름은?",c,"반지름","우변은 반지름의 제곱입니다.")
            if k==2: return n(f"중심이 ({a}, {b})이고 반지름이 {c}인 원의 방정식을 (x-{a})²+(y-{b})²=k로 나타낼 때 k는?",c*c,"원의 방정식","우변은 반지름을 제곱한 수입니다.")
            if k==3: return n(f"원 (x-{a})²+(y-{b})²={c*c}의 중심의 y좌표는?",b,"원의 중심","(x-h)²+(y-k)²=r²에서 중심은 (h, k)입니다.")
            if k==4: return n(f"원 x²+y²={a*a}와 직선 x={a}의 교점 개수는?",1,"원과 직선의 위치","직선에 대입하면 y²=0으로 한 점에서 접합니다.")
            if k==5: return n(f"원 x²+y²={a*a} 위의 점 중 x={a}인 점의 y좌표는?",0,"원 위의 점","x=a를 대입하면 y²=0입니다.")
            return n(f"원 (x-{a})²+(y-{b})²={c*c}의 지름의 길이는?",2*c,"반지름과 지름","지름은 반지름의 두 배입니다.")
        if unit_index == 3:
            if k==0: return m(f"점 ({x}, {a})를 x축에 대하여 대칭이동한 점은?",f"({x}, {-a})",[f"({-x}, {a})",f"({x+a}, {a})",f"({x}, {a})",f"({a}, {x+2*a})"],"x축 대칭","x좌표는 그대로, y좌표의 부호만 바꿉니다.")
            if k==1: return m(f"점 ({a}, {y})를 y축에 대하여 대칭이동한 점은?",f"({-a}, {y})",[f"({a}, {-y})",f"({a}, {y})",f"({a}, {y+a})",f"({2*a}, {y})"],"y축 대칭","y좌표는 그대로, x좌표의 부호만 바꿉니다.")
            if k==2: return m(f"점 ({a}, {b})를 원점에 대하여 대칭이동한 점은?",f"({-a}, {-b})",[f"({a}, {-b})",f"({-a}, {b})",f"({a}, {b})"],"원점 대칭","두 좌표의 부호를 모두 바꿉니다.")
            if k==3: return n(f"점 ({x}, {y})를 x방향으로 {a}, y방향으로 {b}만큼 평행이동한 점의 x좌표는?",x+a,"점의 평행이동","x좌표에 x방향 이동량을 더합니다.")
            if k==4: return n(f"점 ({x}, {y})를 직선 y=x에 대하여 대칭이동한 점의 x좌표는?",y,"y=x 대칭","x좌표와 y좌표를 서로 바꿉니다.")
            if k==5: return n(f"원 (x-{a})²+(y-{b})²={c*c}를 x방향으로 {c}만큼 평행이동하면 중심의 x좌표는?",a+c,"도형의 평행이동","중심의 x좌표에 이동량을 더하며 반지름은 유지됩니다.")
            return n(f"점 ({x}, {y})를 직선 x={a}에 대하여 대칭이동한 점의 x좌표는?",2*a-x,"직선에 대한 대칭","대칭 전후 두 x좌표의 평균이 대칭축의 x좌표입니다.")
        if unit_index == 4:
            if k==0: return n(f"n(A)={a+b}, n(B)={b+c}, n(A∩B)={b}일 때 n(A∪B)는?",a+b+c,"합집합의 원소 수","n(A∪B)=n(A)+n(B)-n(A∩B)입니다.")
            if k==1: return n(f"전체집합 U에 대해 n(U)={a+b}, n(A)={a}일 때 n(A의 여집합)은?",b,"여집합","전체집합의 원소 수에서 A의 원소 수를 뺍니다.")
            if k==2: return n(f"n(A)={a+b}, n(A∩B)={b}일 때 n(A-B)는?",a,"차집합","A에서 B와 공통인 원소를 제외합니다.")
            if k==3:
                t=r.randint(1,7)
                return n(f"원소가 {t}개인 집합의 부분집합은 모두 몇 개인가?",2**t,"부분집합","각 원소를 포함하거나 포함하지 않는 두 선택이 있습니다.")
            if k==4: return n(f"A={{1, 2, ..., {a+2}}}, B={{{a+2}, {a+3}}}일 때 n(A∩B)는?",1,"교집합",f"공통인 원소는 {a+2} 하나뿐입니다.")
            if k==5:
                t=r.randint(2,7)
                return n(f"원소가 {t}개인 집합의 진부분집합은 모두 몇 개인가?",2**t-1,"진부분집합","모든 부분집합 중 자기 자신 하나를 제외합니다.")
            return n(f"서로소인 집합 A, B에 대해 n(A)={a}, n(B)={b}이면 n(A∩B)는?",0,"서로소","서로소인 두 집합에는 공통인 원소가 없습니다.")
        if unit_index == 5:
            if k==0: return m(f"실수 x에 대한 조건 ‘x>{a}’의 부정은?",f"x ≤ {a}",[f"x < {a}",f"x ≥ {a}",f"x = {a}"],"조건의 부정","x>a가 아닌 모든 경우는 x≤a입니다.")
            if k==1: return m(f"명제 ‘x>{a+b}이면 x>{a}이다’의 역은?",f"x>{a}이면 x>{a+b}이다",[f"x≤{a}이면 x≤{a+b}이다",f"x≤{a+b}이면 x≤{a}이다",f"x>{a+b}이면 x>{a}이다"],"명제의 역","가정과 결론을 서로 바꿉니다.")
            if k==2: return m(f"명제 ‘x>{a+b}이면 x>{a}이다’의 대우는?",f"x≤{a}이면 x≤{a+b}이다",[f"x>{a}이면 x>{a+b}이다",f"x≤{a+b}이면 x≤{a}이다",f"x>{a+b}이면 x>{a}이다"],"명제의 대우","가정과 결론을 바꾼 뒤 각각 부정합니다.")
            if k==3: return m(f"p: x>{a+b}, q: x>{a}일 때 p는 q이기 위한 어떤 조건인가?","충분조건이지만 필요조건은 아니다",["필요조건이지만 충분조건은 아니다","필요충분조건이다","필요조건도 충분조건도 아니다"],"필요·충분조건","p이면 q이지만, q라고 해서 항상 p인 것은 아닙니다.")
            if k==4: return m(f"실수 x에 대해 ‘x={a} 또는 x={a+1}’의 부정은?",f"x≠{a} 그리고 x≠{a+1}",[f"x≠{a} 또는 x≠{a+1}",f"x={a} 그리고 x={a+1}",f"x={a} 또는 x={a+1}"],"드모르간 법칙","‘또는’의 부정은 각각의 부정을 ‘그리고’로 연결합니다.")
            if k==5: return n(f"명제 ‘실수 x에 대해 x²={a*a}이면 x={a}이다’의 반례가 되는 x의 값은?",-a,"반례",f"x=-{a}이면 가정은 참이지만 결론은 거짓입니다.")
            return m(f"‘모든 실수 x에 대해 x²>{a}이다’의 부정은?",f"어떤 실수 x에 대해 x²≤{a}이다",[f"모든 실수 x에 대해 x²≤{a}이다",f"어떤 실수 x에 대해 x²>{a}이다",f"모든 실수 x에 대해 x²<{a}이다"],"전칭명제의 부정","‘모든’을 ‘어떤’으로 바꾸고 조건을 부정합니다.")
        if unit_index == 6:
            if k==0: return n(f"f(x)={a}x+{b}일 때 f({c})는?",a*c+b,"함숫값","x에 주어진 값을 대입합니다.")
            if k==1: return n(f"f(x)=x+{a}, g(x)={b}x일 때 (f∘g)({c})는?",b*c+a,"합성함수",f"g({c})={b*c}를 먼저 구한 뒤 f에 넣습니다.")
            if k==2: return n(f"f(x)={a}x+{b}일 때 f⁻¹({a*c+b})는?",c,"역함수",f"f({c})={a*c+b}이므로 역함수의 값은 {c}입니다.")
            if k==3: return n(f"정의역이 {{1, 2, 3}}인 함수 f(x)={a}x+{b}의 치역에 속한 가장 큰 값은?",3*a+b,"정의역과 치역","a가 양수이므로 x=3에서 가장 큰 함숫값을 가집니다.")
            if k==4: return n(f"f(x)=x+{a}, g(x)=x-{b}일 때 (g∘f)({c})는?",c+a-b,"합성함수의 순서","f를 먼저, g를 나중에 적용합니다.")
            if k==5: return n(f"항등함수 f에 대하여 f({a+b})는?",a+b,"항등함수","항등함수는 입력값을 그대로 돌려줍니다.")
            return n(f"실수 전체에서 f(x)={a}x+{b}가 f(k)={a*c+b}를 만족할 때 k는?",c,"함수와 대응","주어진 함숫값에 대응하는 입력값을 구합니다.")
        if unit_index == 7:
            if k==0: return n(f"유리함수 y={a}/(x-{b})+{c}의 수직 점근선 x=k에서 k는?",b,"유리함수의 점근선","분모가 0이 되는 x값을 찾습니다.")
            if k==1: return n(f"유리함수 y={a}/(x-{b})+{c}의 수평 점근선 y=k에서 k는?",c,"유리함수의 점근선","|x|가 커질 때 분수 부분이 0에 가까워집니다.")
            if k==2: return n(f"유리함수 f(x)={a}/(x-{b})+{c}일 때 f({b+1})은?",a+c,"유리함수의 값","분모에 x=b+1을 대입하면 1입니다.")
            if k==3: return n(f"무리함수 y=√(x-{a})+{b}의 정의역을 x≥k로 나타낼 때 k는?",a,"무리함수의 정의역","제곱근 안이 0 이상이어야 합니다.")
            if k==4: return n(f"무리함수 y=√(x-{a})+{b}의 최솟값은?",b,"무리함수의 치역","제곱근의 값은 0 이상입니다.")
            if k==5: return n(f"f(x)=√(x-{a})+{b}일 때 f({a+c*c})는?",b+c,"무리함수의 값",f"√({c*c})={c}이므로 {b+c}입니다.")
            return n(f"유리함수 y={a}/(x-{b})에서 정의역에 포함되지 않는 실수는?",b,"유리함수의 정의역","분모가 0이 되는 값은 제외합니다.")
    raise ValueError("기본 출제 단원을 선택해 주세요.")


def generate(subject, unit, seed=None, exclude=(), focus=(), max_questions=MAX_QUESTIONS):
    """Generate at most one problem per operation, never pad a paper to ten.

    Repetition across later practice rounds is allowed, but exact old prompts
    are excluded. A finite question family exhausted by history is skipped.
    """
    if subject not in SUBJECTS or unit not in units(subject):
        raise ValueError("공통수학1·2의 지원 단원을 선택해 주세요. 사용자 정의 단원은 기본 출제 단원을 연결하세요.")
    if type(max_questions) is not int or not 1 <= max_questions <= MAX_QUESTIONS:
        raise ValueError("최대 문항 수는 1~10 사이의 정수여야 합니다.")
    r = random.Random(seed)
    idx = units(subject).index(unit)
    avoid, seen, items = set(exclude or ()), set(), []
    focus_keys = {TYPE_ALIASES.get(x, x) for x in (focus or ())}
    groups = {}
    for k in range(7):
        key = concept_type(_candidate(subject, idx, k, random.Random(k)))
        groups.setdefault(key, []).append(k)
    ordered = list(groups)
    r.shuffle(ordered)
    ordered.sort(key=lambda key: key not in focus_keys)
    for key in ordered:
        family = list(groups[key])
        r.shuffle(family)
        for trial in range(300):
            k = family[trial % len(family)]
            q = _candidate(subject, idx, k, r, span=min(15, 9+len(avoid)//20))
            fp = fingerprint(q)
            if fp in avoid or fp in seen:
                continue
            q["type_id"] = f"{subject}:{idx}:{key}"
            items.append(q); seen.add(fp)
            break
        if len(items) >= max_questions:
            break
    if not items:
        raise ValueError("기존 발문과 겹치지 않는 새 문제를 만들지 못했습니다. 다른 단원으로 출제해 주세요.")
    r.shuffle(items)
    return validate_questions(items)
