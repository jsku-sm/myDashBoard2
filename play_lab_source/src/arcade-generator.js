import { MARBLE_LEVELS, trajectory } from './arcade-math.js';
import { ROOT_MARBLE_LEVELS } from './root-arcade-data.js';
import { shuffled, shifted, linearText, setText } from './practice-random.js';

export const GAME_VARIANTS = { bubble: 40, invaders: 40, maze: 160, marble: 11, shot: 48, memory: 120, territory: 8, counter: 20, 'set-memory': 16, 'logic-memory': 20, 'root-marble': 11, 'root-maze': 160 };
const round = value => Math.round(value * 1e6) / 1e6;
const display = value => String(Math.round(value * 100) / 100).replace('-', '−');

export function createDomainLevels(id, v) {
  const boundary = (v % 10 - 5) / 2, a = 1 + Math.floor(v / 10) % 4, c = Math.floor(v / 40);
  const rootLevel = (h, coefficient, strict = false) => {
    const b = -coefficient * h, direction = coefficient > 0 ? 1 : -1, inside = linearText(coefficient, b);
    const rule = `x ${direction > 0 ? strict ? '>' : '≥' : strict ? '<' : '≤'} ${display(h)}`;
    return {
      formula: `f(x) = ${strict ? '1 / ' : ''}√(${inside})${!strict && c ? ` + ${c}` : ''}`, rule,
      valid: x => strict ? coefficient * x + b > 0 : coefficient * x + b >= 0,
      legal: Array.from({ length: 7 }, (_, i) => h + direction * (i + (strict ? 1 : 0)) / 2),
      illegal: [h - direction / 2, h - direction, h - direction * 2, ...(strict ? [h] : [])],
      why: x => `x=${display(x)}에서 근호 안은 ${display(coefficient * x + b)}. ${strict ? '분모의 제곱근은 0이 될 수 없어 근호 안이 0보다 커야 해요.' : '근호 안은 0 이상이어야 해요.'} ${coefficient < 0 ? '음수로 나눌 때 부등호 방향이 바뀌어요. ' : ''}정의역은 ${rule}예요.`
    };
  };
  if (id === 'root-maze') return [rootLevel(boundary, a), rootLevel(boundary + .5, -a), rootLevel(boundary - 1, a, true)];
  const numerator = c + 1, pole = boundary + 2, lower = boundary - 1;
  return [
    { formula: `f(x) = ${numerator} / (${linearText(a, -a * boundary)})`, rule: `x ≠ ${display(boundary)}`, valid: x => x !== boundary,
      legal: [-3, -2, -1, 1, 2, 3, 4].map(n => boundary + n), illegal: [boundary],
      why: x => `x=${display(x)}에서 분모는 ${display(a * (x - boundary))}. 분모가 0인 x=${display(boundary)}는 제외해요.` },
    rootLevel(boundary, a),
    { formula: `f(x) = √(${shifted('x', lower)}) / (${shifted('x', pole)})`, rule: `x ≥ ${display(lower)} 이고 x ≠ ${display(pole)}`, valid: x => x >= lower && x !== pole,
      legal: Array.from({ length: 9 }, (_, i) => lower + i).filter(x => x !== pole), illegal: [lower - 1, lower - 2, pole],
      why: x => `x=${display(x)}에서 근호 안은 ${display(x - lower)}, 분모는 ${display(x - pole)}. x≥${display(lower)}와 x≠${display(pole)}를 동시에 만족해야 해요.` }
  ];
}

export function createMarbleLevels(id, v) {
  const delta = (v - 5) / 10, root = id === 'root-marble', base = root ? ROOT_MARBLE_LEVELS : MARBLE_LEVELS;
  const solutions = root ? [{ a: -1.5, b: 0, c: 6 }, { a: -1.4, b: -1, c: 7.4 }, { a: 1.5, b: 0, c: 1 }] : [{ a: 0, b: -.4, c: 6 }, { a: .04, b: -.9, c: 6 }, { a: -1.5, b: 0, c: 6 }];
  return base.map((level, index) => {
    const solution = { ...solutions[index], c: round(solutions[index].c + delta) };
    const parameters = Object.entries(solution).filter(([key]) => new RegExp(`\\b${key}\\b`).test(level.expression)).map(([key, value]) => `${key}=${display(value)}`).join(', ');
    const start = level.start + delta;
    const lesson = root && index === 1 ? `근호 안 x+1은 정의역 x≥−1을 만들고, 그래프의 시작점은 (−1, ${display(solution.c)})예요.` : root && index === 2 ? `근호 안 12−x는 정의역 x≤12를 만들고, 그래프의 시작점은 (12, ${display(solution.c)})예요.` : '근호 밖 상수 또는 y절편을 바꾸면 모든 점의 높이와 출발 높이가 함께 바뀌어요.';
    return { ...level, start, initial: { ...level.initial, c: round(level.initial.c + delta) }, fn: x => level.fn(x) + delta, solution,
      hint: `이번 출발점은 (0, ${display(start)}). ${level.expression}에서 ${parameters}를 기준으로 별의 높이를 비교해 보세요.`, lesson };
  });
}
export function createShotLevels(v) {
  return Array.from({ length: 3 }, (_, stage) => {
    const angle = 26 + v % 12 + stage * 4, speed = round(10.8 + Math.floor(v / 12) * .4 + stage * .9), x = round(9 + stage * 2 + v % 3 * .4);
    const wallX = round((x + 1) / 2), height = Math.max(.5, Math.floor((trajectory(wallX, angle, speed) - .8) * 10) / 10);
    return { name: ['새로운 포물선', '벽 너머의 목표', '높은 곳에 착지하기'][stage], target: { x, y: round(trajectory(x, angle, speed)) }, wall: stage ? { x: wallX, height } : null, solution: { angle, speed },
      hint: `각도 ${angle}°, 속력 ${display(speed)} m/s를 기준으로 탐구해요.${stage ? ` 벽 x=${display(wallX)}에서 높이가 ${display(height)} m보다 커야 해요.` : ' 목표와 같은 높이를 지나는지 관찰해요.'}` };
  });
}
export function createCounterRounds(v) {
  const n = v + 2, m = 2 + v % 5, r = -1 - v % 4, s = 2 + Math.floor(v / 4), h = 1 + v % 5;
  return [
    { prompt: `x²=${n * n}이면 x=${n}이다. 반례 x는?`, p: x => x * x === n * n, q: x => x === n, answer: -n, choices: [-n, n, 0, n + 1], why: `${-n}의 제곱도 ${n * n}이지만 ${-n}≠${n}이에요. 가정은 참이고 결론은 거짓이에요.` },
    { prompt: `x가 ${m}의 배수이면 ${m * 2}의 배수이다. 반례 x는?`, p: x => x % m === 0, q: x => x % (2 * m) === 0, answer: m, choices: [m, 2 * m, 4 * m, m + 1], why: `${m}은 ${m}의 배수이지만 ${m * 2}의 배수는 아니에요.` },
    { prompt: `(${shifted('x', r)})(${shifted('x', s)})=0이면 x=${s}이다. 반례 x는?`, p: x => (x - r) * (x - s) === 0, q: x => x === s, answer: r, choices: [r, s, 0, s + 1], why: `방정식의 해 ${r}도 가정을 만족하지만 x=${s}는 만족하지 않아요.` },
    { prompt: `x<${h}이면 x²<${h * h}이다. 반례 x는?`, p: x => x < h, q: x => x * x < h * h, answer: -h - 1, choices: [-h - 1, 0, h / 2, h + 1], why: `x=${-h - 1}은 ${h}보다 작지만 제곱은 ${(h + 1) ** 2}이므로 결론이 거짓이에요.` },
    { prompt: `x²>${n * n}이면 x>${n}이다. 반례 x는?`, p: x => x * x > n * n, q: x => x > n, answer: -n - 1, choices: [-n - 1, n, n + 1, 0], why: `${-n - 1}을 제곱하면 ${(n + 1) ** 2}>${n * n}이지만 ${-n - 1}>${n}은 거짓이에요.` },
    { prompt: `x(x−${s})=0이면 x=${s}이다. 반례 x는?`, p: x => x * (x - s) === 0, q: x => x === s, answer: 0, choices: [0, s, s + 1, -1], why: `x=0도 방정식의 해예요. 가정은 참이지만 x=${s}라는 결론은 거짓이에요.` }
  ];
}

export function createMemoryPairs(id, v, random = Math.random) {
  if (id === 'set-memory') {
    const n = 2 + v % 7, t = v + 1, A = [t, t + 1, t + 2], B = [t + 1, t + 3], U = Array.from({ length: 6 }, (_, i) => t + i);
    return shuffled([
      { left: `원소가 ${n}개인 집합의\n부분집합의 개수`, right: `2^${n} = ${2 ** n}개`, why: `각 원소의 포함·제외를 독립적으로 고르면 2^${n}=${2 ** n}개예요.` },
      { left: `원소가 ${n}개인 집합의\n진부분집합의 개수`, right: `2^${n} − 1 = ${2 ** n - 1}개`, why: '모든 부분집합에서 자기 자신 한 개만 제외해요.' },
      { left: `A=${setText(A)}, B=${setText(B)}\nA−B는?`, right: setText([t, t + 2]), why: 'A의 원소 중 B에도 속하는 원소를 제외해요.' },
      { left: `U=${setText(U)}\nA∪B=${setText([...A, ...B])}\n(A∪B)ᶜ는?`, right: setText([t + 4, t + 5]), why: '전체집합 U 안에서 합집합에 없는 원소를 찾아요.' },
      { left: `n(A)=${v + 4}, n(B)=${v + 5}\nn(A∩B)=${v + 1}일 때 n(A∪B)는?`, right: `${v + 8}개`, why: `${v + 4}+${v + 5}−${v + 1}=${v + 8}. 공통 원소는 한 번 빼요.` },
      v % 2 ? { left: '(A∩B)ᶜ', right: 'Aᶜ∪Bᶜ', why: '적어도 한 집합에는 속하지 않는다는 뜻이에요.' } : { left: '(A∪B)ᶜ', right: 'Aᶜ∩Bᶜ', why: '두 집합 모두에 속하지 않는다는 뜻이에요.' }
    ], random);
  }
  if (id === 'logic-memory') {
    const n = v + 2, b = v - 5;
    return shuffled([
      { left: `“x>${b} → x>${b - 2}”의 대우`, right: `x≤${b - 2} → x≤${b}`, why: '가정과 결론의 순서를 바꾸고 두 조건을 모두 부정해요.' },
      { left: `“모든 실수 x에서 x²≥${n}”의 부정`, right: `어떤 실수 x에서 x²<${n}`, why: '모든을 어떤으로 바꾸고 ≥를 <로 부정해요.' },
      { left: `“어떤 실수 x에서 x²=${n * n}”의 부정`, right: `모든 실수 x에서 x²≠${n * n}`, why: '하나라도 존재한다는 말의 부정은 어느 것도 존재하지 않는다는 뜻이에요.' },
      { left: `${2 * n}의 배수인 것은 ${n}의 배수이기 위한?`, right: `충분조건 (${2 * n}의 배수 ⇒ ${n}의 배수)`, why: '앞 조건을 만족하면 뒤 조건을 반드시 만족해요.' },
      { left: `x²=${n * n}은 x=${n}이기 위한?`, right: `필요조건 (x=${n} ⇒ x²=${n * n})`, why: 'x=n이려면 제곱이 n²이어야 하지만 제곱만으로 부호를 확정할 수 없어요.' },
      { left: `“x²=${n * n} → x=${n}”의 반례`, right: `x=${-n}`, why: `x=${-n}은 가정을 만족하고 결론은 만족하지 않아요.` }
    ], random);
  }
  const a = 1 + Math.floor(v / 24), b = v % 6 - 3, h = v % 5 - 2, k = v % 3 - 1, pole = v % 11 - 5, input = 1 + v % 3, inner = a * input + 3;
  return shuffled([
    { left: `y=${linearText(a, b)}`, right: '이 직선의 식은?', graph: { kind: 'line', a, b }, why: `기울기는 ${a}, y절편은 ${b}예요.` },
    { left: `y=(${shifted('x', h)})² ${k < 0 ? '−' : '+'} ${Math.abs(k)}`, right: '이 포물선의 식은?', graph: { kind: 'square', h, k }, why: `꼭짓점은 (${h}, ${k})예요. y=x²을 평행이동한 그래프예요.` },
    { left: `y=1/(${shifted('x', pole)})`, right: `정의역: x≠${pole}`, why: `분모가 0인 x=${pole}를 제외해요.` },
    { left: `y=√(${shifted('x', pole + 1)})`, right: `정의역: x≥${pole + 1}`, why: `근호 안이 0 이상인 x≥${pole + 1}에서 정의돼요.` },
    { left: `f(x)=${a}x+3, g(x)=x²\n(g∘f)(${input}) = ?`, right: `출력값 = ${inner ** 2}`, why: `f(${input})=${inner}을 구하고 다시 제곱해 ${inner ** 2}을 얻어요.` },
    { left: `f(x)=${a + 1}x ${b < 0 ? '−' : '+'} ${Math.abs(b)}\nf⁻¹(${(a + 1) * input + b}) = ?`, right: `입력 x = ${input}`, why: `출력이 ${(a + 1) * input + b}이 되는 원래 입력은 ${input}이에요.` }
  ], random);
}

const TERRITORY_POOL = [
  { expression: ['intersect', 'A', 'B'], label: 'A ∩ B', hint: '두 원의 겹친 곳을 감싸요.', why: '두 집합에 동시에 속하는 영역이에요.' },
  { expression: ['diff', 'A', 'B'], label: 'A − B', hint: '왼쪽 원 A 안이면서 B 바깥을 감싸요.', why: 'A에 속하고 B에는 속하지 않는 영역이에요.' },
  { expression: ['diff', 'B', 'A'], label: 'B − A', hint: '오른쪽 원 B 안이면서 A 바깥을 감싸요.', why: 'B에 속하고 A에는 속하지 않는 영역이에요.' },
  { expression: ['union', 'A', 'B'], label: 'A ∪ B', hint: '두 원 중 적어도 하나에 속하는 곳을 감싸요.', why: '교집합도 합집합에 포함돼요.' },
  { expression: ['not', ['intersect', 'A', 'B']], label: '(A ∩ B)ᶜ', hint: '겹친 곳을 제외한 전체집합 U의 영역이에요.', why: '드모르간 법칙에 따라 Aᶜ∪Bᶜ와 같아요.' },
  { expression: ['not', ['union', 'A', 'B']], label: '(A ∪ B)ᶜ', hint: '전체집합 U 안에서 두 원 모두의 바깥을 감싸요.', why: '드모르간 법칙에 따라 Aᶜ∩Bᶜ와 같아요.' },
  { expression: ['union', ['diff', 'A', 'B'], ['diff', 'B', 'A']], label: '(A−B) ∪ (B−A)', hint: '겹친 곳을 빼고 두 원의 한쪽에만 속하는 부분이에요.', why: '정확히 한 집합에만 속하는 원소들의 영역이에요.' },
  { expression: 'A', label: 'A', hint: '겹친 곳을 포함해 왼쪽 원 A 전체를 감싸요.', why: 'B에 속하는지와 관계없이 A에 속하면 포함돼요.' }
];
export function createArcadeContent(id, variant, random = Math.random) {
  const v = variant % GAME_VARIANTS[id], content = { variant: v };
  if (id.endsWith('maze')) content.domainLevels = createDomainLevels(id, v);
  if (id.endsWith('marble')) content.marbleLevels = createMarbleLevels(id, v);
  if (id === 'shot') content.shotLevels = createShotLevels(v);
  if (id === 'counter') content.counterRounds = createCounterRounds(v);
  if (id.includes('memory')) content.pairs = createMemoryPairs(id, v, random);
  if (id === 'territory') content.territoryLevels = [0, 3, 5].map(offset => ({ ...TERRITORY_POOL[(v + offset) % TERRITORY_POOL.length] }));
  return content;
}
