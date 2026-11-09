import { shuffled, shifted, linearText, setText } from './practice-random.js';

export const QUIZ_TOPICS = ['함수의 뜻', '정의역과 치역', '합성함수', '역함수', '유리함수', '무리함수'].map(title => ({ title }));
export const QUIZ_VARIANTS = 120;

function question(index, variant, q, correct, distractors, why, meta, random) {
  const wrong = [...new Set(distractors.map(String))].filter(value => value !== String(correct)).slice(0, 2);
  if (wrong.length !== 2) throw new Error('A quiz needs two distinct distractors.');
  const options = shuffled([String(correct), ...wrong], random);
  return { title: QUIZ_TOPICS[index].title, variant, q, options, answer: options.indexOf(String(correct)), why, meta };
}
export function createQuizQuestion(index, variant, random = Math.random) {
  const build = (q, correct, wrong, why, meta) => question(index, variant, q, correct, wrong, why, meta, random);
  const v = variant % QUIZ_VARIANTS;
  if (index === 0) {
    const base = v + 1, kind = v % 3;
    const edges = kind === 0 ? [[base, 'a'], [base + 1, 'b'], [base + 2, 'b']] : kind === 1 ? [[base, 'a'], [base + 1, 'b']] : [[base, 'a'], [base, 'b'], [base + 1, 'b'], [base + 2, 'c']];
    const choices = ['함수이다', `함수가 아니다: 입력 ${base + 2}의 출력이 없다`, `함수가 아니다: 입력 ${base}의 출력이 두 개다`];
    const why = kind === 0 ? '모든 입력에 출력이 오직 하나씩 있어 함수예요. 서로 다른 입력이 같은 출력 b에 대응해도 괜찮아요.' : kind === 1 ? `입력 ${base + 2}에 대응하는 출력이 없어 함수가 아니에요.` : `입력 ${base}에 a와 b가 동시에 대응하므로 함수가 아니에요.`;
    return build(`X=${setText([base, base + 1, base + 2])}, Y={a, b, c}에서 대응 ${edges.map(([x, y]) => `${x}→${y}`).join(', ')}는 함수일까요?`, choices[kind], choices.filter((_, i) => i !== kind), why, { kind: 'mapping', domain: [base, base + 1, base + 2], edges });
  }
  if (index === 1) {
    const a = 1 + Math.floor(v / 15) % 4, c = v % 15 - 7, k = 2 + Math.floor(v / 60), domain = [-k, 0, k];
    const outputs = domain.map(x => a * x * x + c), correct = setText(outputs);
    return build(`f(x)=${a}x² ${c < 0 ? '−' : '+'} ${Math.abs(c)}, 정의역이 ${setText(domain)}일 때 치역은?`, correct, [setText([c - 1, a * k * k + c]), setText([c, a * k * k + c + 1])], `각 입력을 대입한 출력은 ${outputs.join(', ')}예요. 중복을 제외하면 치역은 ${correct}예요.`, { kind: 'range', a, c, domain });
  }
  const a = 2 + Math.floor(v / 24), b = v % 6 - 3, x = 1 + Math.floor(v / 6) % 4;
  if (index === 2) {
    const inner = a * x + b, result = inner ** 2;
    return build(`f(x)=${linearText(a, b)}, g(x)=x²일 때 (g∘f)(${x})는?`, result, [result + 1, result + 2], `안쪽부터 f(${x})=${inner}, 이어서 g(${inner})=${result}예요.`, { kind: 'composition', a, b, x });
  }
  if (index === 3) {
    const output = a * x + b;
    return build(`f(x)=${linearText(a, b)}일 때 f⁻¹(${output})는?`, x, [x + 1, x - 1], `${linearText(a, b)}=${output}을 풀면 x=${x}예요. 역함수는 출력을 만드는 원래 입력을 찾아요.`, { kind: 'inverse', a, b, output });
  }
  if (index === 4) {
    const boundary = v % 15 - 7, coefficient = 1 + Math.floor(v / 15) % 4, numerator = 1 + Math.floor(v / 60);
    return build(`y=${numerator}/(${coefficient}(${shifted('x', boundary)}))의 정의역에서 제외되는 수는?`, boundary, [boundary - 1, boundary + 1], `분모 ${coefficient}(${shifted('x', boundary)})가 0인 x=${boundary}를 제외해요.`, { kind: 'rational-domain', coefficient, boundary, numerator });
  }
  const boundary = v % 15 - 7, coefficient = (v < 60 ? 1 : -1) * (1 + Math.floor(v / 15) % 4), constant = -coefficient * boundary;
  const relation = coefficient > 0 ? '≥' : '≤', opposite = coefficient > 0 ? '≤' : '≥';
  return build(`y=√(${linearText(coefficient, constant)})의 정의역은?`, `x ${relation} ${boundary}`, [`x ${opposite} ${boundary}`, `x ${coefficient > 0 ? '>' : '<'} ${boundary}`], `근호 안 ${linearText(coefficient, constant)}이 0 이상이어야 해요. ${coefficient < 0 ? '음수로 나누면 부등호가 바뀌므로 ' : ''}x ${relation} ${boundary}이고 경계도 포함해요.`, { kind: 'root-domain', a: coefficient, b: constant, boundary });
}
