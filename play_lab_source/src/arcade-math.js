// A small arithmetic parser for student formulas. No JavaScript is evaluated.
export function compileFormula(source) {
  const text = String(source).replace(/^\s*y\s*=/i, '').replace(/[−–]/g, '-').replace(/[×·]/g, '*').replace(/÷/g, '/').replace(/²/g, '^2').replace(/³/g, '^3').replace(/√/g, 'sqrt').replace(/\s/g, '');
  if (!text || text.length > 160) throw new Error('160자 이내의 함수식을 입력해 주세요.');
  const tokens = text.match(/(?:\d+(?:\.\d*)?|\.\d+)|[a-zA-Z]+|[+\-*/^()]/g) || [];
  if (tokens.join('') !== text) throw new Error('숫자, x, a, b, c와 사칙연산, ^, sqrt(), abs()를 사용할 수 있어요.');
  let index = 0;
  const peek = () => tokens[index];
  function atom() {
    const token = tokens[index++];
    if (token === '(') {
      const node = sum();
      if (tokens[index++] !== ')') throw new Error('닫는 괄호 )를 확인해 주세요.');
      return node;
    }
    if (/^(?:\d|\.\d)/.test(token || '')) return () => Number(token);
    if (['x', 'a', 'b', 'c'].includes(token)) return values => values[token];
    if (['sqrt', 'abs'].includes(token)) {
      if (tokens[index++] !== '(') throw new Error(`${token}(x)처럼 괄호를 사용해 주세요.`);
      const node = sum();
      if (tokens[index++] !== ')') throw new Error('닫는 괄호 )를 확인해 주세요.');
      return values => Math[token](node(values));
    }
    throw new Error('함수식을 확인해 주세요. 예: a*x^2+b*x+c');
  }
  function power() {
    const left = atom();
    if (peek() === '^') { index++; const right = unary(); return values => left(values) ** right(values); }
    return left;
  }
  function unary() {
    if (peek() === '+') { index++; return unary(); }
    if (peek() === '-') { index++; const node = unary(); return values => -node(values); }
    return power();
  }
  function product() {
    let left = unary();
    while (peek() === '*' || peek() === '/' || /^(?:[a-zA-Z(]|\d|\.\d)/.test(peek() || '')) {
      let op = peek();
      if (op === '*' || op === '/') index++; else op = '*'; // 2x and 2(x+1)
      const previous = left, right = unary();
      left = op === '*' ? values => previous(values) * right(values) : values => previous(values) / right(values);
    }
    return left;
  }
  function sum() {
    let left = product();
    while (peek() === '+' || peek() === '-') {
      const op = tokens[index++], previous = left, right = product();
      left = op === '+' ? values => previous(values) + right(values) : values => previous(values) - right(values);
    }
    return left;
  }
  const evaluate = sum();
  if (index !== tokens.length) throw new Error('연산 기호와 괄호의 짝을 확인해 주세요.');
  return (x, parameters = {}) => evaluate({ a: 0, b: 0, c: 0, ...parameters, x });
}

export const shuffle = items => {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [result[i], result[j]] = [result[j], result[i]]; }
  return result;
};
export const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
export const number = n => Number(n.toFixed(2)).toString().replace('-', '−');
const term = n => n < 0 ? `− ${Math.abs(n)}` : `+ ${n}`;

// Generate a problem whose answer is an exposed bubble / one of the aliens.
export function valueMission(answer, round = 0, variant = 0) {
  const v = (variant + round * 7) % 40, x = v % 8 + 1, a = 2 + Math.floor(v / 8);
  if (round % 4 === 0) {
    const b = answer - a * x;
    return { answer, topic: '함숫값', prompt: `f(x) = ${a}x ${term(b)}일 때 f(${x})는?`, hint: `x 자리에 ${x}을 넣고, 곱셈부터 계산해요.`, why: `f(${x}) = ${a} × ${x} ${term(b)} = ${answer}. 입력을 식에 대입하면 출력이 정해져요.`, meta: { kind: 'linear', a, b, x } };
  }
  if (round % 4 === 1) {
    const b = answer - a * x * x;
    return { answer, topic: '이차함수', prompt: `f(x) = ${a}x² ${term(b)}일 때 f(${x})는?`, hint: `${x}의 제곱을 먼저 계산해요.`, why: `f(${x}) = ${a} × ${x}² ${term(b)} = ${answer}. 제곱을 먼저 계산해요.`, meta: { kind: 'square', a, b, x } };
  }
  if (round % 4 === 2) {
    const output = x + 8, b = output - a * answer;
    return { answer, topic: '역함수', prompt: `f(x) = ${a}x ${term(b)}일 때 f⁻¹(${output})는?`, hint: `출력이 ${output}가 되는 입력을 찾아요. ${a}x ${term(b)} = ${output}`, why: `${a}x ${term(b)} = ${output}를 풀면 x = ${answer}. 역함수는 출력에서 원래 입력을 찾아요.`, meta: { kind: 'inverse', a, b, output } };
  }
  const shift = 1 + v % 3, b = answer - (x + shift) * a;
  return { answer, topic: '합성함수', prompt: `f(x) = x + ${shift}, g(x) = ${a}x ${term(b)}. (g∘f)(${x})는?`, hint: `안쪽 함수부터! f(${x}) = ${x + shift}을 먼저 구해요.`, why: `f(${x}) = ${x + shift}, g(${x + shift}) = ${a * (x + shift)} ${term(b)} = ${answer}. 합성함수는 안쪽부터 계산해요.`, meta: { kind: 'composition', a, b, x, shift } };
}

export const MARBLE_LEVELS = [
  { name: '기울기로 길 만들기', expression: 'a*x^2+b*x+c', initial: { a: 0, b: 0, c: 5 }, start: 6, fn: x => -.4 * x + 6, hint: '출발점은 (0, 6). x가 5 늘 때 높이가 2 낮아지는 직선을 만들어 보세요.', lesson: '일차함수의 b는 기울기, c는 y절편이에요. b가 음수이면 오른쪽으로 내려가요.' },
  { name: '곡선으로 이어지는 길', expression: 'a*x^2+b*x+c', initial: { a: .05, b: -.4, c: 5 }, start: 6, fn: x => .04 * x * x - .9 * x + 6, hint: 'y = 0.04x² − 0.9x + 6을 출발점으로 삼아 계수를 조금씩 바꿔 보세요.', lesson: '이차항의 계수 a는 휘어지는 방향과 정도를, c는 출발 높이를 바꿔요.' },
  { name: '루트로 만드는 미끄럼틀', expression: 'a*sqrt(x)+c', initial: { a: -1, b: 0, c: 5 }, start: 6, fn: x => 6 - 1.5 * Math.sqrt(x), hint: 'sqrt(x)를 써 보세요. 출발 높이는 6, x=4에서 그래프 높이는 3이에요.', lesson: '√x는 x ≥ 0에서 정의돼요. 음수 계수를 곱하면 오른쪽으로 내려가는 길이 돼요.' }
];

export const SHOT_LEVELS = [
  { name: '첫 번째 포물선', target: { x: 10, y: 1 }, wall: null, hint: '각도 30°, 속력 10 m/s 근처에서 시작해 보세요. 같은 높이로 돌아오는 거리를 관찰해요.' },
  { name: '벽 너머의 목표', target: { x: 12, y: 2.5 }, wall: { x: 6, height: 2.4 }, hint: '각도 35°, 속력 12 m/s 근처를 탐구해 보세요. 벽 위치에서의 높이가 2.4 m보다 커야 해요.' },
  { name: '높은 곳에 착지하기', target: { x: 14, y: 3.5 }, wall: { x: 7, height: 3.5 }, hint: '각도 40°, 속력 13 m/s 근처를 탐구해 보세요. 목표의 높이와 포물선의 높이를 비교해요.' }
];
export function trajectory(x, angle, speed) {
  const rad = angle * Math.PI / 180, dx = x - 1;
  return 1 + Math.tan(rad) * dx - 9.8 * dx * dx / (2 * speed * speed * Math.cos(rad) ** 2);
}

export const DOMAIN_LEVELS = [
  { formula: 'f(x) = 1 / (x − 2)', rule: 'x ≠ 2', valid: x => x !== 2, legal: [-3, -1, 0, 1, 3, 4, 5, 6], illegal: [2], why: x => `x=${x}이면 분모가 ${x - 2}. 분모가 0인 x=2는 정의역에서 제외해요.` },
  { formula: 'f(x) = √(x − 1)', rule: 'x ≥ 1', valid: x => x >= 1, legal: [1, 2, 3, 4, 5, 6], illegal: [-2, -1, 0], why: x => `x=${x}이면 루트 안은 ${x - 1}. 실수 범위에서는 x−1 ≥ 0, 즉 x ≥ 1이어야 해요.` },
  { formula: 'f(x) = √(x + 2) / (x − 3)', rule: 'x ≥ −2 이고 x ≠ 3', valid: x => x >= -2 && x !== 3, legal: [-2, -1, 0, 1, 2, 4, 5], illegal: [-4, -3, 3], why: x => `x=${x}: 루트 안은 ${x + 2}, 분모는 ${x - 3}. x ≥ −2와 x ≠ 3을 동시에 만족해야 해요.` }
];
export function createDomainMaze(level) {
  const cells = [];
  for (let row = 0; row < 7; row++) for (let col = 0; col < 9; col++) {
    const border = row === 0 || row === 6 || col === 0 || col === 8;
    // A connected safe route through every key and the exit always exists.
    const safe = row === 1 || row === 5 || col === 1 || col === 4;
    const wall = border || (!safe && Math.random() < .18);
    const pool = safe || Math.random() > .55 ? level.legal : level.illegal;
    cells.push({ row, col, wall, value: pool[Math.floor(Math.random() * pool.length)], revealed: false });
  }
  return cells;
}

export const MEMORY_PAIRS = [
  { left: 'y = 2x + 1', right: '이 그래프의 식은?', graph: 'line', why: '기울기는 2, y절편은 1인 직선이에요.' },
  { left: 'y = (x − 1)²', right: '이 그래프의 식은?', graph: 'square', why: 'y=x²을 오른쪽으로 1만큼 평행이동하면 꼭짓점이 (1, 0)이 돼요.' },
  { left: 'y = 1 / (x − 2)', right: '정의역: x ≠ 2', why: '분모 x−2가 0이면 정의되지 않으므로 x=2를 제외해요.' },
  { left: 'y = √(x + 3)', right: '정의역: x ≥ −3', why: '루트 안 x+3 ≥ 0을 풀면 x ≥ −3이에요.' },
  { left: 'f(x)=2x+1, g(x)=x²\n(g∘f)(1) = ?', right: '9', why: 'f(1)=3을 구한 다음 g(3)=9를 계산해요.' },
  { left: 'f(x) = 3x − 2\nf⁻¹(10) = ?', right: '4', why: '3x−2=10을 풀면 x=4예요. 역함수는 원래 입력을 찾아요.' }
];
