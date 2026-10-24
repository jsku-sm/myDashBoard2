"""2022-revised Cheonjae textbook headings, transcribed from official TOC images.

The school's representative author was not supplied. Default Hong; the teacher
can switch to Jeon without changing concept IDs or deleting learning records.
'세부 주제' is our own subdivision, not a claim about printed textbook headings.
Source/verification notes are in GAME_CONTENT_SOURCES.md.
"""
from __future__ import annotations

EDITIONS = {"hong": "천재교과서 · 홍진곤", "jeon": "천재 · 전인태"}
DEFAULT_EDITION = "hong"
# id, subject, label, old-bank unit, family numbers (or a custom-generator id), concept card, usefulness
TOPIC_DEFS = [
 ("poly.add",1,"동류항의 덧셈과 뺄셈",0,[0,2],"같은 문자와 차수를 가진 항끼리 계수를 계산합니다. 괄호 앞의 −는 괄호 안 모든 항에 적용합니다.","판매량이나 제작 비용을 항목별로 정리할 때 같은 종류끼리 계산할 수 있습니다."),
 ("poly.multiply",1,"다항식의 곱셈과 곱셈 공식",0,[1,6],"각 항을 빠짐없이 곱한 뒤 동류항끼리 모읍니다. (x+a)(x+b)=x²+(a+b)x+ab입니다.","가로·세로가 달라지는 디자인의 넓이를 식으로 표현할 수 있습니다."),
 ("poly.divide",1,"다항식의 나눗셈",None,"divide","나누어지는 식=(나누는 식)×(몫)+(나머지)입니다. 나머지의 차수는 나누는 식보다 작습니다.","복잡한 식을 규칙과 남는 부분으로 나누어 이해하는 연습입니다."),
 ("identity",1,"항등식의 계수 비교",1,[2,6],"모든 x에서 두 다항식이 같으려면 같은 차수 항의 계수가 각각 같아야 합니다.","겉모습이 다른 두 계산 방법이 같은 결과를 주는지 판단할 수 있습니다."),
 ("remainder",1,"나머지정리와 인수정리",1,[0,4,5],"P(x)를 x−a로 나눈 나머지는 P(a)입니다. P(a)=0이면 x−a는 P(x)의 인수입니다.","식을 끝까지 나누지 않고도 필요한 정보를 빠르게 확인하는 도구입니다."),
 ("factor",1,"인수분해 공식 적용",2,[0,1,2,3,4,5,6],"합으로 된 다항식을 곱으로 바꿉니다. 공통인수부터 찾고 두 수의 합과 곱을 확인합니다.","복잡한 조건을 작은 요소로 나누어 해결하는 사고를 연습합니다."),
 ("complex",1,"복소수와 켤레복소수",3,[0,1,2,6],"허수단위 i는 i²=−1을 만족합니다. 실수부분과 허수부분을 구분해 계산합니다.","수의 범위를 넓혀, 실수만으로 표현하기 어려운 관계를 이해합니다."),
 ("quadratic.discriminant",1,"이차방정식의 판별식",3,[4],"ax²+bx+c=0에서 D=b²−4ac입니다. D>0이면 서로 다른 두 실근, D=0이면 중근, D<0이면 허근을 갖습니다.","조건에 따라 가능한 결과가 몇 가지인지 판단할 수 있습니다."),
 ("quadratic.roots",1,"근과 계수의 관계",3,[3,5],"ax²+bx+c=0의 두 근 α, β에 대해 α+β=−b/a, αβ=c/a입니다.","답을 직접 모두 구하지 않고도 합과 곱의 관계를 알아낼 수 있습니다."),
 ("quadratic.graph",1,"이차함수와 이차방정식",4,[0,3,4,6],"그래프와 x축의 교점은 y=0인 방정식의 실근과 연결됩니다. y=a(x−p)²+q의 꼭짓점은 (p,q)입니다.","수식과 그래프를 오가며 결과를 눈으로 검증할 수 있습니다."),
 ("quadratic.extrema",1,"이차함수의 최대와 최소",4,[1,2,5],"제곱은 0 이상입니다. 주어진 정의역에서 꼭짓점과 끝점의 값을 함께 살펴봅니다.","비용·넓이처럼 가장 크거나 작은 값을 찾아야 하는 선택에 활용합니다."),
 ("equation.high",1,"삼차·사차방정식의 인수분해",None,"high_equation","곱이 0이면 인수 중 적어도 하나가 0입니다. 인수분해한 뒤 각 방정식을 풉니다.","큰 문제를 해결할 수 있는 여러 작은 조건으로 나눕니다."),
 ("equation.system",1,"연립이차방정식",None,"quadratic_system","한 식을 다른 식에 대입하거나 두 식을 조합해 미지수를 줄입니다. 구한 값은 원래 두 식에 모두 대입합니다.","두 조건을 동시에 만족하는 선택을 찾는 연습입니다."),
 ("inequality.linear",1,"연립일차부등식",None,"linear_system","각 부등식을 풀고 해의 공통부분을 찾습니다. 음수로 나누면 부등호 방향이 바뀝니다.","예산과 시간처럼 여러 제한을 동시에 만족하는 범위를 찾습니다."),
 ("inequality.quadratic",1,"이차부등식과 연립이차부등식",None,"quadratic_inequality","두 근을 경계로 부호를 확인합니다. 연립부등식의 해는 각 해의 공통부분입니다.","허용되는 값의 범위를 정확히 설명하는 연습입니다."),
 ("count.rules",1,"합의 법칙과 곱의 법칙",6,[0,1],"겹치지 않는 경우 중 하나를 선택하면 더하고, 연달아 각각 선택하면 곱합니다.","메뉴 구성·디자인 조합 등 가능한 선택의 수를 셀 수 있습니다."),
 ("count.permutation",1,"순열: 순서가 있는 선택",6,[2,4,5],"순서나 역할이 다르면 다른 경우입니다. 중복 없이 순서대로 뽑을 때 선택 수를 차례로 곱합니다.","발표 순서나 역할 배정의 가능성을 계산합니다."),
 ("count.combination",1,"조합: 순서 없는 선택",6,[3,6],"순서를 구분하지 않는 선택에서는 같은 구성원을 다른 순서로 센 중복을 제거합니다.","대표나 팀원을 고르는 경우를 중복 없이 셀 수 있습니다."),
 ("matrix.meaning",1,"행렬의 크기와 성분",7,[0,4,5],"행은 가로, 열은 세로입니다. (i,j)성분은 i행 j열에 있습니다.","표·픽셀·판매 자료를 일정한 구조로 읽는 연습입니다."),
 ("matrix.add",1,"행렬의 덧셈·뺄셈·실수배",7,[1,2],"같은 크기의 행렬은 같은 위치의 성분끼리 더하거나 뺍니다. 실수배는 모든 성분에 적용합니다.","여러 품목의 자료를 한꺼번에 계산할 수 있습니다."),
 ("matrix.multiply",1,"행렬의 곱",7,[3,6],"앞 행렬의 행과 뒤 행렬의 열을 대응시켜 곱한 후 더합니다. 앞 행렬의 열 수와 뒤 행렬의 행 수가 같아야 합니다.","여러 상품의 수량과 가격을 묶어 총액을 계산하는 데 연결됩니다."),
 ("coordinate.distance",2,"두 점 사이의 거리",0,[0,4],"두 점의 x좌표 차와 y좌표 차를 이용합니다. 거리는 √((x₂−x₁)²+(y₂−y₁)²)입니다.","지도나 화면에서 두 위치 사이의 거리를 계산할 수 있습니다."),
 ("coordinate.section",2,"선분의 내분점과 중점",0,[1,2,3,6],"AP:PB=m:n이면 P는 A에서 B 방향으로 전체의 m/(m+n)만큼 이동한 점입니다.","지도에서 중간 지점이나 디자인 요소의 비율에 맞는 위치를 찾습니다."),
 ("line.equation",2,"직선의 기울기와 방정식",1,[0,1,2,5],"기울기는 y의 변화량을 x의 변화량으로 나눈 값입니다. y−y₁=m(x−x₁)에 한 점과 기울기를 넣습니다.","일정한 변화나 직선 형태를 수학으로 표현합니다."),
 ("line.relationship",2,"두 직선의 평행과 수직",1,[3,4],"기울기가 있는 서로 다른 두 직선에서 평행이면 기울기가 같고, 수직이면 기울기의 곱이 −1입니다.","도면과 픽토그램에서 선의 방향 관계를 정확히 표현합니다."),
 ("line.distance",2,"점과 직선 사이의 거리",None,"line_distance","점 (x₀,y₀)에서 직선 ax+by+c=0까지의 거리는 |ax₀+by₀+c|/√(a²+b²)입니다.","어떤 위치에서 선까지 가장 짧은 거리를 구할 수 있습니다."),
 ("circle.equation",2,"원의 중심·반지름·방정식",2,[0,1,2,3,5,6],"(x−a)²+(y−b)²=r²인 원의 중심은 (a,b), 반지름은 r입니다. 우변은 반지름의 제곱입니다.","원형 아이콘·안내 표지의 크기와 위치를 설계합니다."),
 ("circle.line",2,"원과 직선의 위치 관계",None,"circle_line","원의 중심에서 직선까지의 거리 d와 반지름 r를 비교합니다. d<r이면 두 점, d=r이면 한 점, d>r이면 만나지 않습니다.","경계선이 원형 영역과 만나는지를 판단합니다."),
 ("move.translation",2,"점과 도형의 평행이동",3,[3,5],"점의 좌표에 이동량을 더합니다. 도형 전체를 옮겨도 모양과 크기는 유지됩니다.","그래픽·레이아웃에서 위치만 바꿀 때 쓰는 원리입니다."),
 ("move.reflection",2,"축·원점·직선에 대한 대칭이동",3,[0,1,2,4,6],"x축 대칭은 y의 부호, y축 대칭은 x의 부호를 바꿉니다. y=x 대칭은 두 좌표를 서로 바꿉니다.","대칭적인 로고·픽토그램을 정확하게 만들 수 있습니다."),
 ("set.meaning",2,"집합의 뜻과 표현",None,"set_meaning","집합은 대상을 명확하게 구별할 수 있는 모임입니다. 같은 원소를 여러 번 적어도 하나로 셉니다.","자료를 기준에 따라 분류하고 중복을 구별하는 데 연결됩니다."),
 ("set.inclusion",2,"부분집합과 포함 관계",4,[3,5],"A의 모든 원소가 B에 속하면 A는 B의 부분집합입니다. 원소가 n개이면 부분집합은 2ⁿ개입니다.","어떤 분류가 다른 분류에 포함되는지 판단할 수 있습니다."),
 ("set.operations",2,"집합의 연산",4,[0,1,2,4,6],"합집합은 어느 한쪽에 속하는 원소, 교집합은 양쪽에 공통인 원소를 모읍니다.","검색 조건과 설문 자료의 겹침을 정확히 다룰 수 있습니다."),
 ("logic.condition",2,"명제·조건과 부정",5,[0,4,6],"명제는 참·거짓을 분명하게 판단할 수 있는 문장입니다. 조건의 부정은 그 조건이 아닌 모든 경우입니다.","주장에 빠진 경우가 없는지 점검하는 데 도움이 됩니다."),
 ("logic.implication",2,"역·대우·필요충분조건",5,[1,2,3],"역은 가정과 결론을 바꾸고, 대우는 바꾼 뒤 둘 다 부정합니다. p⇒q이면 p는 q의 충분조건입니다.","정보와 주장의 논리적 관계를 검토할 수 있습니다."),
 ("logic.proof",2,"반례와 명제의 증명",None,"proof","참이라고 보이려면 주어진 범위의 모든 경우를 다루어야 합니다. 거짓임을 보이려면 반례 하나로 충분합니다.","그럴듯한 주장과 근거가 있는 주장을 구별하는 연습입니다."),
 ("function.meaning",2,"함수의 뜻·정의역·치역",6,[0,3,5,6],"함수는 정의역의 각 원소에 공역의 원소가 오직 하나씩 대응하는 관계입니다. 치역은 실제로 나오는 출력값의 모임입니다.","입력과 출력으로 가격·거리·시간의 관계를 읽을 수 있습니다."),
 ("function.composition",2,"합성함수의 계산 순서",6,[1,4],"(f∘g)(x)=f(g(x))이므로 안쪽 g부터 계산합니다. 순서를 바꾸면 결과가 달라질 수 있습니다.","여러 처리 단계를 연결하는 과정을 이해하는 데 도움이 됩니다."),
 ("function.inverse",2,"역함수의 대응",6,[2],"f(a)=b이면 f⁻¹(b)=a입니다. 역함수는 입력과 출력의 역할을 되돌립니다.","결과에서 원래 입력을 되짚어 찾는 사고를 연습합니다."),
 ("function.rational",2,"유리함수의 정의역과 그래프",7,[0,1,2,6],"분모가 0인 값은 정의역에서 제외합니다. y=a/(x−p)+q의 점근선은 x=p, y=q입니다.","한 값이 커질수록 다른 값이 줄어드는 관계와 제한을 해석합니다."),
 ("function.radical",2,"무리함수의 정의역과 그래프",7,[3,4,5],"실수 범위에서 제곱근 안은 0 이상이어야 합니다. 제곱근의 값도 0 이상입니다.","입력 가능한 범위와 실제 출력 범위를 구분할 수 있습니다."),
]
TOPICS = {v[0]: dict(id=v[0], subject=f"공통수학{v[1]}", label=v[2], unit=v[3], families=v[4], concept=v[5], usefulness=v[6]) for v in TOPIC_DEFS}

# Ordered (major, middle, [(minor, [topic IDs])]) entries.
COMMON_1 = [
 ("Ⅰ. 다항식", "1. 다항식의 연산", [("01. 다항식의 덧셈과 뺄셈",["poly.add"]),("02. 다항식의 곱셈과 나눗셈",["poly.multiply","poly.divide"])]),
 ("Ⅰ. 다항식", "2. 나머지정리와 인수분해",[("01. 항등식과 나머지정리",["identity","remainder"]),("02. 인수분해",["factor"])]),
]
VAR_1 = ("Ⅱ. 방정식과 부등식","3. 여러 가지 방정식과 부등식",[("01. 삼차방정식과 사차방정식",["equation.high"]),("02. 연립이차방정식",["equation.system"]),("03. 연립일차부등식",["inequality.linear"]),("04. 이차부등식과 연립이차부등식",["inequality.quadratic"])])
MOVE = ("Ⅰ. 도형의 방정식","3. 도형의 이동",[("01. 평행이동",["move.translation"]),("02. 대칭이동",["move.reflection"])])
HONG = {
 "공통수학1": COMMON_1 + [
 ("Ⅱ. 방정식과 부등식","1. 복소수와 이차방정식",[("01. 복소수와 그 연산",["complex"]),("02. 이차방정식의 판별식",["quadratic.discriminant"]),("03. 이차방정식의 근과 계수의 관계",["quadratic.roots"])]),
 ("Ⅱ. 방정식과 부등식","2. 이차방정식과 이차함수",[("01. 이차함수의 그래프와 이차방정식",["quadratic.graph"]),("02. 이차함수의 최대, 최소",["quadratic.extrema"])]), VAR_1,
 ("Ⅲ. 경우의 수","1. 경우의 수",[("01. 합의 법칙과 곱의 법칙",["count.rules"]),("02. 순열",["count.permutation"]),("03. 조합",["count.combination"])]),
 ("Ⅳ. 행렬","1. 행렬과 그 연산",[("01. 행렬의 뜻",["matrix.meaning"]),("02. 행렬의 덧셈과 뺄셈, 실수배",["matrix.add"]),("03. 행렬의 곱셈",["matrix.multiply"])])],
 "공통수학2": [
 ("Ⅰ. 도형의 방정식","1. 평면좌표와 직선의 방정식",[("01. 선분의 내분",["coordinate.section"]),("02. 두 직선의 평행과 수직",["line.equation","line.relationship"]),("03. 점과 직선 사이의 거리",["line.distance"])]),
 ("Ⅰ. 도형의 방정식","2. 원의 방정식",[("01. 원의 방정식",["circle.equation"]),("02. 원과 직선의 위치 관계",["circle.line"])]), MOVE,
 ("Ⅱ. 집합과 명제","1. 집합",[("01. 집합의 뜻과 표현",["set.meaning"]),("02. 집합 사이의 포함관계",["set.inclusion"]),("03. 집합의 연산",["set.operations"])]),
 ("Ⅱ. 집합과 명제","2. 명제",[("01. 명제와 조건",["logic.condition"]),("02. 명제 p ⇒ q",["logic.implication"]),("03. 명제의 증명",["logic.proof"])]),
 ("Ⅲ. 함수와 그래프","1. 함수",[("01. 함수의 뜻과 그래프",["function.meaning"]),("02. 합성함수",["function.composition"]),("03. 역함수",["function.inverse"])]),
 ("Ⅲ. 함수와 그래프","2. 유리함수와 무리함수",[("01. 유리함수의 그래프",["function.rational"]),("02. 무리함수의 그래프",["function.radical"])])]
}
JEON = {
 "공통수학1": COMMON_1 + [
 ("Ⅱ. 방정식과 부등식","1. 복소수와 이차방정식",[("01. 복소수와 그 연산",["complex"]),("02. 이차방정식의 근의 성질",["quadratic.discriminant","quadratic.roots"])]),
 ("Ⅱ. 방정식과 부등식","2. 이차방정식과 이차함수",[("01. 이차방정식과 이차함수의 관계",["quadratic.graph"]),("02. 이차함수의 최대, 최소",["quadratic.extrema"])]), VAR_1,
 ("Ⅲ. 경우의 수","1. 경우의 수",[("01. 합의 법칙과 곱의 법칙",["count.rules"]),("02. 순열과 조합",["count.permutation","count.combination"])]),
 ("Ⅳ. 행렬","1. 행렬과 그 연산",[("01. 행렬의 뜻",["matrix.meaning"]),("02. 행렬의 연산",["matrix.add","matrix.multiply"])])],
 "공통수학2": [
 ("Ⅰ. 도형의 방정식","1. 평면좌표와 직선의 방정식",[("01. 평면좌표",["coordinate.distance","coordinate.section"]),("02. 직선의 방정식",["line.equation","line.relationship","line.distance"])]),
 ("Ⅰ. 도형의 방정식","2. 원의 방정식",[("01. 원의 방정식",["circle.equation"]),("02. 원과 직선",["circle.line"])]), MOVE,
 ("Ⅱ. 집합과 명제","1. 집합",[("01. 집합의 뜻과 포함 관계",["set.meaning","set.inclusion"]),("02. 집합의 연산",["set.operations"])]),
 ("Ⅱ. 집합과 명제","2. 명제",[("01. 명제와 조건",["logic.condition"]),("02. 명제 사이의 관계",["logic.implication"]),("03. 명제의 증명",["logic.proof"])]),
 ("Ⅲ. 함수와 그래프","1. 함수",[("01. 함수의 뜻과 그래프",["function.meaning"]),("02. 합성함수와 역함수",["function.composition","function.inverse"])]),
 ("Ⅲ. 함수와 그래프","2. 유리함수와 무리함수",[("01. 유리함수",["function.rational"]),("02. 무리함수",["function.radical"])])]
}
BOOKS = {"hong": HONG, "jeon": JEON}

def rows(edition=DEFAULT_EDITION, subject=None):
    if edition not in BOOKS: raise ValueError("교과서 판본을 선택하세요.")
    result = []
    for sub, groups in BOOKS[edition].items():
        if subject and sub != subject: continue
        for major,middle,smalls in groups:
            for small,topics in smalls:
                for tid in topics:
                    result.append(dict(TOPICS[tid], major=major, middle=middle, small=small))
    return result

def topic(topic_id):
    if topic_id not in TOPICS: raise ValueError("선택한 세부 주제를 찾을 수 없습니다.")
    return dict(TOPICS[topic_id])
