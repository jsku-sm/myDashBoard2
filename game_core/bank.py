"""AI-assisted authored templates, deterministic local generation, no runtime AI.

Existing independently tested quiz families are reused without changing quizzes.
Custom teacher items require explicit human review; semantic checking is not AI.
"""
from __future__ import annotations
from copy import deepcopy
import csv
from fractions import Fraction
import hashlib
import io
import random
import re
import uuid
from quiz_core import bank as base
from .curriculum import topic

VERSION = "good-concepts-v1"


def _canonical(value):
    s = re.sub(r"\s+", "", str(value)).replace("−", "-")
    try:
        return ("number", Fraction(s))
    except (ValueError, ZeroDivisionError):
        return ("text", s)


def validate(q):
    if not isinstance(q, dict): raise ValueError("문항은 문제·보기·정답·해설로 구성해야 합니다.")
    t = topic(q.get("topic_id"))
    prompt = str(q.get("prompt", "")).strip()
    options = q.get("options")
    if not 1 <= len(prompt) <= 3000: raise ValueError("문제를 1~3000자로 입력해 주세요.")
    if (not isinstance(options, list) or len(options) != 4
            or any(not isinstance(x, str) or not x.strip() or len(x)>800 for x in options)
            or len({_canonical(x) for x in options}) != 4):
        raise ValueError("서로 다른 보기 4개를 입력하세요. 2와 2.0처럼 같은 수를 중복 입력할 수 없습니다.")
    if type(q.get("answer")) is not int or not 0 <= q["answer"] < 4:
        raise ValueError("정답 보기를 선택해 주세요.")
    why = str(q.get("explanation", "")).strip()
    if not 1 <= len(why) <= 4000: raise ValueError("해설을 1~4000자로 입력해 주세요.")
    hints = q.get("hints") or [t["concept"], "문제의 조건을 하나씩 식에 대입하고 부호와 범위를 확인해 보세요."]
    if not isinstance(hints, list) or not 1<=len(hints)<=3 or any(not isinstance(x,str) or not x.strip() or len(x)>1500 for x in hints):
        raise ValueError("힌트는 1~3개, 각 1500자 이하로 입력해 주세요.")
    return dict(id=str(q.get("id") or uuid.uuid4().hex), topic_id=t["id"], prompt=prompt,
                options=[x.strip() for x in options], answer=q["answer"], explanation=why,
                hints=hints, concept=t["label"], source=str(q.get("source") or "AI 제작·자동 검산 개념 틀"),
                source_note=str(q.get("source_note", ""))[:300])


def _extra(kind, r, span):
    a,b,c = r.randint(1,span),r.randint(2,span+1),r.randint(1,span)
    def n(prompt,val,why): return base.numeric(prompt,val,kind,why,r)
    if kind == "divide":
        # Polynomial equals (x-a)(bx+c)+remainder, by coefficient construction.
        rem=r.randint(0,span)
        return n(f"P(x)={b}x²+({c-a*b})x+({rem-a*c})를 x−{a}로 나누었을 때 몫을 {b}x+k로 쓰면 k는?", c,
                 f"P(x)=(x−{a})({b}x+{c})+{rem}입니다. 따라서 몫의 상수항 k={c}입니다.")
    if kind == "high_equation":
        power=r.choice([1,2])
        return n(f"방정식 (x−{a}){'²' if power==2 else ''}(x−{a+1})(x−{a+2})=0의 서로 다른 실근의 합은?",3*a+3,
                 f"서로 다른 실근은 {a}, {a+1}, {a+2}입니다. 같은 인수가 반복되어도 서로 다른 실근은 한 번씩만 더해 {3*a+3}입니다.")
    if kind == "quadratic_system":
        x,y=a+b,a
        return n(f"연립방정식 x+y={x+y}, xy={x*y}에서 x>y일 때 x는?",x,
                 f"y={x+y}−x를 대입하면 (x−{x})(x−{y})=0입니다. x>y이므로 x={x}, y={y}입니다.")
    if kind == "linear_system":
        lo,hi=a,a+b
        return n(f"연립부등식 x+{c}>{lo+c}, 2x≤{2*hi}를 만족하는 정수 x의 개수는?",b,
                 f"각각 x>{lo}, x≤{hi}입니다. 공통부분은 {lo}<x≤{hi}이므로 정수는 {lo+1}부터 {hi}까지 {b}개입니다.")
    if kind == "quadratic_inequality":
        d=r.randint(1,b)
        return n(f"연립부등식 (x−{a})(x−{a+b})≤0, x≥{a+d}를 만족하는 정수 x의 개수는?",b-d+1,
                 f"첫 부등식의 해는 {a}≤x≤{a+b}입니다. 공통부분은 {a+d}≤x≤{a+b}이므로 정수는 {b-d+1}개입니다.")
    if kind == "line_distance":
        x,y=r.randint(-span,span),r.randint(-span,span)
        k=5*a-3*x-4*y
        return n(f"점 ({x}, {y})에서 직선 3x+4y+({k})=0까지의 거리는?",a,
                 f"거리 공식에 대입하면 |3×({x})+4×({y})+({k})|/√(3²+4²)={5*a}/5={a}입니다.")
    if kind == "circle_line":
        d=r.choice([c-1,c,c+1])
        val=2 if d<c else 1 if d==c else 0
        return n(f"원 (x−{a})²+(y−{b})²={c*c}와 직선 x={a+d}의 교점은 몇 개인가?",val,
                 f"중심은 ({a},{b}), 반지름 r={c}입니다. 중심에서 직선까지의 거리 d={d}이므로 교점은 {val}개입니다.")
    if kind == "set_meaning":
        unique=[a+j*b for j in range(r.randint(2,5))]
        values=unique+[r.choice(unique) for _ in range(r.randint(1,3))]
        r.shuffle(values)
        return n("집합 A={"+", ".join(map(str,values))+"}의 서로 다른 원소는 몇 개인가?",len(unique),
                 f"중복해서 적힌 원소는 하나로 셉니다. 서로 다른 원소는 {', '.join(map(str,unique))}이므로 {len(unique)}개입니다.")
    if kind == "proof":
        return n(f"명제 ‘모든 실수 x에 대하여 x²={a*a}이면 x={a}이다’가 거짓임을 보이는 반례 x는?",-a,
                 f"x=−{a}를 대입하면 x²={a*a}이므로 가정은 참이지만 x={a}은 거짓입니다. 반례 하나로 원래 명제는 거짓입니다.")
    raise ValueError("지원하지 않는 문항 틀입니다.")


def generate(topic_id, seed=None, count=5, level="천천히", custom=(), exclude=()):
    if type(count) is not int or count != 5: raise ValueError("한 번의 학습은 5문제로 구성합니다.")
    if level not in ("천천히","기본","한 걸음 더"): raise ValueError("학습 단계를 선택해 주세요.")
    t=topic(topic_id); r=random.Random(seed); seen=set(exclude); result=[]
    # Up to two teacher-reviewed items; remaining questions vary their conditions.
    candidates=[validate(x) for x in custom if x.get("topic_id")==topic_id]
    r.shuffle(candidates)
    for q in candidates[:2]:
        if q["prompt"] not in seen: result.append(q);seen.add(q["prompt"])
    span={"천천히":5,"기본":9,"한 걸음 더":15}[level]
    for _ in range(500):
        if len(result)==count: break
        if isinstance(t["families"],str): q=_extra(t["families"],r,span)
        else: q=base._candidate(t["subject"],t["unit"],r.choice(t["families"]),r,span=span)
        q.update(topic_id=topic_id, hints=[t["concept"], "정답을 서두르지 않아도 괜찮아요. 주어진 수를 표시하고 식의 부호·범위를 차례로 확인해 보세요."])
        q=validate(q)
        if q["prompt"] in seen: continue
        result.append(q);seen.add(q["prompt"])
    if len(result)!=count:
        raise ValueError("서로 다른 5문제를 구성하지 못했습니다. 다른 주제로 시작해 주세요.")
    for i,q in enumerate(result): q["id"]=f"q{i+1}"
    return result


def csv_template():
    f=io.StringIO();w=csv.writer(f)
    w.writerow(["문제","보기1","보기2","보기3","보기4","정답번호","해설","힌트1","힌트2"])
    w.writerow(["점 (2,3)을 x축에 대하여 대칭이동한 점은?","(2,-3)","(-2,3)","(-2,-3)","(3,2)",1,"x좌표는 그대로, y좌표의 부호만 바꾸므로 (2,-3)입니다.","x축 위아래로 같은 거리를 생각하세요.","x좌표와 y좌표 중 어떤 값의 부호가 바뀌나요?"])
    return f.getvalue().encode("utf-8-sig")


def parse_csv(data, topic_id):
    if len(data)>1024*1024: raise ValueError("문항 CSV는 1MB 이하로 올려 주세요.")
    try: text=data.decode("utf-8-sig")
    except UnicodeDecodeError: text=data.decode("cp949")
    rows=list(csv.DictReader(io.StringIO(text)))
    if not 1<=len(rows)<=100: raise ValueError("한 번에 1~100문제를 등록할 수 있습니다.")
    output=[]
    for i,row in enumerate(rows,1):
        try:
            q=validate(dict(topic_id=topic_id,prompt=row["문제"],options=[row[f"보기{k}"] for k in range(1,5)],
                  answer=int(row["정답번호"])-1,explanation=row["해설"],
                  hints=[row[k].strip() for k in ("힌트1","힌트2") if row.get(k,"").strip()], source="교사 등록 문항"))
        except (ValueError,KeyError) as e: raise ValueError(f"CSV {i}번 문항: {e}") from None
        output.append(q)
    return output
