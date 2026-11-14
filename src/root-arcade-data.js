export const ROOT_GAMES = [
  { id: 'root-marble', subject: 'function', title: '루트 그래프 레일', genre: '그래프 구슬 퍼즐', topic: '무리함수 · 평행이동 · 부호', tag: '루트 함수로 길 만들기!', desc: '무리함수식을 직접 쓰고 계수를 조절해 구슬이 별을 모으며 도착하는 레일을 그려요.', controls: 'sqrt(x) 함수식 입력 · a, b, c 조절 · 구슬 굴리기', goal: '루트 함수로 내리막 레일을 만들고 별 3개를 지나 도착점에 닿게 하세요. 근호 밖 부호, 근호 안의 이동과 좌우 방향을 바꾸는 3개 코스예요. 출발 높이와 별의 좌표도 함께 확인해요.', lesson: '근호 안의 식은 0 이상이어야 해요. 근호 안의 이동은 정의역을, 근호 밖의 계수와 상수는 위아래 방향과 높이를 바꿔요.' },
  { id: 'root-maze', subject: 'function', title: '무리함수 정의역 미로', genre: '미로 탈출', topic: '정의역 · 음수 계수 · 분모의 루트', tag: '경계값까지 판단!', desc: '근호 안과 분모의 조건을 모두 확인해 올바른 숫자 발판으로 미로를 탈출해요.', controls: '방향키 또는 W A S D · 화면 방향 버튼', goal: '정의역에 속하는 숫자만 밟고 열쇠 3개를 모아 출구로 가세요. 양수 계수, 음수 계수, 분모의 제곱근을 차례로 만나요. 경계값을 포함하는지 판단하는 것이 핵심이에요.', lesson: '√(2x−7)은 x≥7/2, √(−3x−2)는 x≤−2/3. 1/√(x−2)에서는 분모가 0이 될 수 없어 x>2예요.' }
];
export const ROOT_MARBLE_LEVELS = [
  { name: '근호 밖 부호로 내리막 만들기', expression: 'a*sqrt(x)+c', initial: { a: -1, b: 0, c: 5 }, start: 6, fn: x => 6 - 1.5 * Math.sqrt(x), hint: 'y=−1.5√x+6을 만들어 보세요. a=−1.5, c=6이면 (0,6)에서 오른쪽으로 내려가요.', lesson: '√x의 정의역은 x≥0이에요. 음수 계수를 곱하면 x축 대칭이 되어 내려가는 레일이 돼요.' },
  { name: '루트 레일을 왼쪽으로 옮기기', expression: 'a*sqrt(x-b)+c', initial: { a: -1, b: 0, c: 5 }, start: 6, fn: x => 7.4 - 1.4 * Math.sqrt(x + 1), hint: 'a=−1.4, b=−1, c=7.4를 출발점으로 탐구해요. x−b=x+1이므로 정의역은 x≥−1이에요.', lesson: '√(x+1)은 √x를 왼쪽으로 1만큼 옮긴 그래프예요. y=−1.4√(x+1)+7.4의 시작점은 (−1,7.4)예요.' },
  { name: '근호 안의 음수로 방향 바꾸기', expression: 'a*sqrt(12-x)+c', initial: { a: 1, b: 0, c: 4 }, start: 1.5 * Math.sqrt(12) + 1, fn: x => 1.5 * Math.sqrt(12 - x) + 1, hint: 'a=1.5, c=1을 탐구해요. 근호 안 12−x가 0 이상이어야 하므로 x≤12인 구간만 길이 존재해요.', lesson: 'y=1.5√(12−x)+1은 시작점 (12,1)에서 왼쪽 위로 뻗어요. 이 코스의 구슬은 오른쪽으로 갈수록 내려가요.' }
];
export const ROOT_DOMAIN_LEVELS = [
  { formula: 'f(x) = √(2x − 7)', rule: 'x ≥ 7/2', valid: x => x >= 3.5, legal: [3.5, 4, 4.5, 5, 6, 7], illegal: [0, 1, 2, 3], why: x => `x=${x}이면 근호 안은 ${2 * x - 7}. 2x−7≥0이어야 하므로 x≥7/2예요. 경계 7/2도 포함해요.` },
  { formula: 'f(x) = √(−3x − 2) + 1', rule: 'x ≤ −2/3', valid: x => x <= -2 / 3, legal: [-3, -2, -1.5, -1, -2 / 3], illegal: [-.5, 0, 1, 2], why: x => `x=${tileNumber(x)}에서 근호 안은 ${tileNumber(-3 * x - 2)}. −3x−2≥0을 음수로 나누면 부등호가 바뀌어 x≤−2/3이에요.` },
  { formula: 'f(x) = 1 / √(x − 2)', rule: 'x > 2', valid: x => x > 2, legal: [2.5, 3, 4, 5, 6, 7], illegal: [-1, 0, 1, 2], why: x => `x=${x}이면 근호 안은 ${x - 2}. 제곱근이 분모에 있으므로 근호 안이 0보다 커야 해요. x=2도 제외해서 x>2예요.` }
];
export function tileNumber(value) {
  if (Math.abs(value + 2 / 3) < 1e-9) return '−2/3';
  return String(Number(value.toFixed(3))).replace('-', '−');
}
