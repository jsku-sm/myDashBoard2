import { createQuizQuestion, QUIZ_TOPICS } from './quiz-generator.js';
import { linearText, shifted, setText, shuffled } from './practice-random.js';

export const QUIZ_LEVELS = [
  { level: 1, title: '기초 발견', description: '대응과 입력·출력의 기본 조건을 확인해요.' },
  { level: 2, title: '개념 적용', description: '구간, 평행이동, 분모의 조건에 개념을 적용해요.' },
  { level: 3, title: '개념 연결', description: '합성·역함수와 정의역을 함께 연결해요.' },
  { level: 4, title: '추론 도전', description: '조건에서 매개변수와 가능한 범위를 추론해요.' },
  { level: 5, title: '마스터 종합', description: '여러 조건을 동시에 만족하는 해를 찾아요.' }
];
const signed = n => n < 0 ? `− ${Math.abs(n)}` : `+ ${n}`;
const value = n => Number(n.toFixed(4)).toString();
const variantCache = new Map();
export function levelVariantIds(topic, level) {
  const key = `${level}:${topic}`;
  if (!variantCache.has(key)) {
    const seen = new Set(), variants = [];
    for (let v = 0; v < 120; v++) { const stem = createLevelQuiz(topic, v, level, () => .5).q; if (!seen.has(stem)) { seen.add(stem); variants.push(v); } }
    variantCache.set(key, variants);
  }
  return variantCache.get(key);
}

export function createLevelQuiz(topic, variant, level = 1, random = Math.random) {
  if (level === 1) return { ...createQuizQuestion(topic, variant, random), level };
  const v = variant % 120, a = 2 + v % 4, b = Math.floor(v / 4) % 9 - 4, n = 2 + Math.floor(v / 36), h = v % 9 - 4;
  const make = (q, correct, wrong, why, meta) => {
    const answer = String(correct), alternatives = [...new Set(wrong.map(String))].filter(x => x !== answer);
    if (alternatives.length < 2) throw Error('Distinct advanced quiz choices required');
    const options = shuffled([answer, ...alternatives.slice(0, 2)], random);
    return { title: QUIZ_TOPICS[topic].title, level, variant, q, options, answer: options.indexOf(answer), why, meta };
  };
  const numeric = (q, answer, why, meta, wrong = [answer + 1, answer - 1]) => make(q + (Math.abs(answer - Number(value(answer))) > 1e-8 ? ' (소수 넷째 자리까지 반올림)' : ''), value(answer), wrong.map(value), why, { ...meta, expected: answer });
  if (topic === 0) {
    if (level === 2) return numeric(`원소가 ${n}개인 X에서 원소가 ${a}개인 Y로 가는 함수는 모두 몇 개인가요?`, a ** n, `X의 각 원소마다 ${a}가지 출력을 독립적으로 고르므로 ${a}^${n}=${a ** n}개예요.`, { kind: 'function-count', n, m: a });
    if (level === 3) return numeric(`X=${setText([h, h + 1, h + 2])}이고 f(x)=x² ${signed(b)}예요. 공역을 치역과 같게 할 때 공역의 원소 수는?`, new Set([h, h + 1, h + 2].map(x => x ** 2 + b)).size, '각 입력의 출력을 구한 뒤 중복된 출력은 한 번만 세어요.', { kind: 'image-count', inputs: [h, h + 1, h + 2], b });
    if (level === 4) return numeric(`실수 전체에서 f(x)=(${shifted('k', h)})x+${a}가 일대일대응이 아니게 하는 k는?`, h, `기울기 k−(${h})가 0이면 상수함수예요. 따라서 k=${h}를 제외해야 일대일대응이 돼요.`, { kind: 'non-bijection', h });
    const roots = [h - n, h + n];
    return make(`공역은 [0,∞)이고, X는 실수 전체의 부분집합이며 f(x)=(${shifted('x', h)})²예요. f가 일대일대응이 되도록 하는 정의역 X는?`, `x ≥ ${h}`, ['모든 실수', `x ≥ ${h + 1}`], `꼭짓점 x=${h}를 포함해 한쪽 가지 전체를 택해야 해요. 모든 실수에서는 ${roots.join(', ')}처럼 같은 출력을 만드는 두 입력이 있어요.`, { kind: 'restricted-square', h });
  }
  if (topic === 1) {
    if (level === 2) return make(`f(x)=(${shifted('x', h)})² ${signed(b)}, 정의역이 [${h - n}, ${h + n}]일 때 치역은?`, `[${b}, ${n ** 2 + b}]`, [`[${b + 1}, ${n ** 2 + b}]`, `[${b}, ${n ** 2 + b + 1}]`], `꼭짓점 x=${h}에서 최솟값 ${b}, 양 끝에서 최댓값 ${n ** 2 + b}예요.`, { kind: 'quadratic-range', h, b, n });
    if (level === 3) return make(`f(x)=√(${shifted('x', h)}) ${signed(b)}, 정의역이 [${h}, ${h + n ** 2}]일 때 역함수의 정의역은?`, `[${b}, ${b + n}]`, [`[${h}, ${h + n ** 2}]`, `[${b}, ${b + n + 1}]`], `원함수의 치역 [${b},${b + n}]이 역함수의 정의역이 돼요.`, { kind: 'inverse-domain', h, b, n });
    if (level === 4) return numeric(`f(x)=(${shifted('x', h)})²+k의 정의역이 [${h - n},${h + 1}]이고 최댓값이 ${n ** 2 + b}일 때 k는?`, b, `꼭짓점에서 더 먼 왼쪽 끝의 값은 ${n ** 2}+k예요. 이것이 ${n ** 2 + b}이므로 k=${b}예요.`, { kind: 'range-parameter', n, b });
    return make(`f(x)=1/(${shifted('x', h)})의 정의역이 [${h + 1},${h + n}]일 때 역함수의 정의역은?`, `[1/${n}, 1]`, [`[1, ${n}]`, `[0, 1]`], `양의 구간에서 감소하므로 원함수의 치역은 [1/${n},1]이에요. 이것이 역함수의 정의역이에요.`, { kind: 'reciprocal-inverse-domain', h, n });
  }
  if (topic === 2) {
    if (level === 2) return numeric(`f(x)=${linearText(a, b)}, g(x)=x²일 때 (f∘g)(${n})는?`, a * n ** 2 + b, `g(${n})=${n ** 2}을 먼저 계산하고 f에 넣어요.`, { kind: 'linear-after-square', a, b, n });
    if (level === 3) return numeric(`f(x)=${linearText(a, b)}, g(x)=x+${n}일 때 (f∘g)⁻¹(${a * (h + n) + b})는?`, h, `f∘g는 ${a}(x+${n}) ${signed(b)}예요. 주어진 출력에서 역으로 풀면 x=${h}예요.`, { kind: 'inverse-composition', a, b, n, h });
    if (level === 4) return numeric(`f(x)=${a}x+k, g(x)=x+${n}이고 (g∘f)(${h})=${a * h + b + n}일 때 k는?`, b, `${a}×${h}+k+${n}=${a * h + b + n}을 풀어요.`, { kind: 'composition-parameter', a, b, n, h });
    return numeric(`f(x)=${linearText(a, b)}, g(x)=x+${n}일 때 (f⁻¹∘g∘f)(${h})는? (소수 또는 분수의 값)`, h + n / a, `f(${h})=${a * h + b}, g의 출력은 ${a * h + b + n}예요. f⁻¹을 적용하면 ${h}+${n}/${a}=${value(h + n / a)}예요.`, { kind: 'triple-composition', a, b, n, h });
  }
  if (topic === 3) {
    if (level === 2) return numeric(`f(x)=${linearText(a, b)}이고 f⁻¹(t)=${n}일 때 t는?`, a * n + b, `역함수 관계를 원함수로 바꾸면 t=f(${n})=${a * n + b}예요.`, { kind: 'inverse-output', a, b, n });
    if (level === 3) return numeric(`f(x)=(${shifted('x', h)})² (x≥${h})일 때 f⁻¹(${n ** 2})는?`, h + n, `x−(${h})≥0이므로 양의 제곱근을 골라 x=${h}+${n}이에요.`, { kind: 'square-inverse', h, n });
    if (level === 4) return numeric(`f(x)=${a}x+k이고 f(${h})=f⁻¹(${h})일 때 k는?`, (1 - a) * h, '증가하는 일차함수와 역함수가 같은 입력에서 만나는 점은 y=x 위예요. f(h)=h를 풀면 k=(1−a)h예요.', { kind: 'inverse-fixed-point', a, h });
    return numeric(`f(x)=√(${a}(${shifted('x', h)})) ${signed(b)}일 때 f⁻¹(${b + n})는?`, h + n ** 2 / a, `x와 y를 바꾸고 제곱하면 f⁻¹(x)=(x−(${b}))²/${a}+${h} (x≥${b})예요.`, { kind: 'root-inverse', a, b, h, n });
  }
  if (topic === 4) {
    if (level === 2) return make(`y=(${shifted('x', h)})/((${shifted('x', h)})(${shifted('x', h + n)}))의 정의역에서 제외되는 수는?`, setText([h, h + n]), [setText([h + n]), setText([h])], '약분하더라도 원래 분모를 0으로 만드는 입력은 모두 제외해야 해요.', { kind: 'cancelled-domain', excluded: [h, h + n] });
    if (level === 3) return make(`f(x)=1/(${shifted('x', h)}), g(x)=${linearText(a, -a * b + h)}일 때 f∘g의 정의역은?`, `x ≠ ${b}`, [`x ≠ ${h}`, `x ≠ ${b + 1}`, `x ≠ ${b - 1}`], `g(x)−(${h})=${a}(x−(${b}))가 0이 아니어야 하므로 x≠${b}예요.`, { kind: 'rational-composition-domain', a, b, h });
    if (level === 4) return numeric(`f(x)=(${a}x+k)/(${shifted('x', h)})에서 x≠${h}일 때 항상 f(x)=${a}가 되게 하는 k는?`, -a * h, `분자가 ${a}(x−(${h}))와 같아야 하므로 k=${-a * h}예요. x=${h}는 여전히 제외해요.`, { kind: 'rational-parameter', a, h });
    return make(`f(x)=1/(${shifted('x', h)}), g(x)=1/x일 때 g∘f의 정의역은?`, `x ≠ ${h}`, ['모든 실수', `x ≠ ${h + 1}`], `식은 x−(${h})로 정리되지만, 안쪽 f가 정의되지 않는 x=${h}는 제외해요. f의 출력은 0이 되지 않아요.`, { kind: 'nested-reciprocal-domain', h });
  }
  if (level === 2) return make(`f(x)=1/√(${shifted('x', h)})의 정의역은?`, `x > ${h}`, [`x ≥ ${h}`, `x < ${h}`], '분모의 제곱근은 존재하면서 0이 아니어야 하므로 근호 안이 0보다 커야 해요.', { kind: 'strict-root-domain', h });
  if (level === 3) return make(`f(x)=√(${a}x ${signed(-a * h)})/(${shifted('x', h + n)})의 정의역은?`, `x ≥ ${h}, x ≠ ${h + n}`, [`x ≥ ${h}`, `x > ${h}, x ≠ ${h + n}`], '근호 안의 조건과 분모가 0이 아니어야 한다는 조건을 동시에 적용해요.', { kind: 'root-and-pole', h, n, a });
  if (level === 4) return numeric(`f(x)=√(${a}x+k)의 정의역이 x≥${h}일 때 k는?`, -a * h, `시작 입력 x=${h}에서 근호 안은 0이므로 ${a}×${h}+k=0이에요.`, { kind: 'root-boundary-parameter', a, h });
  return numeric(`f(x)=√(${shifted('x', h)}) ${signed(b)}일 때 f⁻¹(${b + n}) + f(${h + n ** 2})의 값은?`, h + n ** 2 + b + n, `f⁻¹(${b + n})=${h + n ** 2}, f(${h + n ** 2})=${b + n}이므로 두 값을 더해요.`, { kind: 'root-inverse-sum', h, b, n });
}
