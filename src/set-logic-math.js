export const unique = values => [...new Set(values.map(String))];
export const sameSet = (left, right) => unique(left).length === unique(right).length && unique(left).every(value => unique(right).includes(value));
export const subsetOf = (left, right) => unique(left).every(value => unique(right).includes(value));
export const prime = n => Number.isInteger(n) && n >= 2 && !Array.from({ length: Math.max(0, Math.floor(Math.sqrt(n)) - 1) }, (_, i) => i + 2).some(d => n % d === 0);
export const range = (start, end) => Array.from({ length: end - start + 1 }, (_, i) => start + i);
export const implies = (p, q) => !p || q;
export function membership(value, sets, names = ['A', 'B']) {
  return names.reduce((mask, name, i) => mask | (sets[name]?.map(String).includes(String(value)) ? 1 << i : 0), 0);
}
export function regionValue(expression, mask, names = ['A', 'B', 'C']) {
  if (expression === 'U') return true;
  if (expression === 'empty') return false;
  if (typeof expression === 'string') return Boolean(mask & (1 << names.indexOf(expression)));
  const [op, a, b] = expression;
  if (op === 'not') return !regionValue(a, mask, names);
  if (op === 'union') return regionValue(a, mask, names) || regionValue(b, mask, names);
  if (op === 'intersect') return regionValue(a, mask, names) && regionValue(b, mask, names);
  if (op === 'diff') return regionValue(a, mask, names) && !regionValue(b, mask, names);
  throw new Error('Unknown set operation: ' + op);
}
export const expressionRegions = (expression, count = 2) => range(0, (1 << count) - 1).filter(mask => regionValue(expression, mask));
export const calculateSet = (expression, universe, sets) => unique(universe).filter(value => regionValue(expression, membership(value, sets, ['A', 'B', 'C'])));
export const allSubsetMasks = (count, proper = false) => range(0, (1 << count) - 1 - (proper ? 1 : 0));
export const maskElements = (elements, mask) => elements.filter((_, i) => mask & 1 << i);
export const regionName = (mask, count = 2) => mask === 0 ? '어느 집합에도 속하지 않음' : range(0, count - 1).map(i => `${'ABC'[i]}${mask & 1 << i ? '에 속함' : '에 속하지 않음'}`).join(' · ');
export const isSetLogic = q => q?.widget?.type?.startsWith('sl-');

export function evaluateSetLogicActivity(question, record) {
  const issues = [], values = record.responses || {}, lab = { ...question.widget.defaults, ...record.lab }, w = question.widget;
  for (const field of question.fields) {
    const answer = values[field.key];
    if (field.type === 'set' || field.type === 'multi') {
      if (!Array.isArray(answer) || !sameSet(answer, field.answer)) issues.push(`${field.label}: 선택한 원소나 보기에 빠진 것 또는 불필요한 것이 없는지 확인해요. 공집합은 ∅ 버튼으로 확인해요.`);
    } else if (field.type === 'text') {
      if (String(answer || '').trim().length < (field.minLength || 15)) issues.push(`${field.label}을(를) 자신의 말로 15자 이상 적어 주세요.`);
    } else if (field.type === 'witness') {
      const value = readNumber(answer);
      if (!Number.isFinite(value) || !field.validate(value)) issues.push(`${field.label}: 조건을 만족하는 구체적인 수를 찾아요.`);
    } else if (field.type === 'number') {
      const value = readNumber(answer);
      if (!Number.isFinite(value) || Math.abs(value - field.answer) > 1e-6 * Math.max(1, Math.abs(field.answer))) issues.push(`${field.label}의 계산과 조건을 다시 확인해요.`);
    } else if (String(answer) !== String(field.answer)) issues.push(`${field.label}에서 조건과 방향을 다시 살펴보세요.`);
  }
  if (w.type === 'sl-venn' && w.checkRegions) {
    const expected = expressionRegions(w.expression, w.count || 2);
    if (!sameSet(lab.regions || [], expected) || (!expected.length && !lab.emptyConfirmed)) issues.push('색칠한 영역을 원소의 포함 조건과 비교해요. 공집합이면 ∅ 버튼으로 빈 영역을 확인해요.');
  }
  if (w.type === 'sl-place' && unique(w.universe).some(value => lab.placements?.[value] !== membership(value, w.sets, w.names || ['A', 'B']))) issues.push('모든 원소를 해당하는 영역에 배치해요. 두 집합에 공통이면 겹친 곳에 놓아요.');
  if (w.type === 'sl-subset' && !w.exploratory && !sameSet(lab.found || [], allSubsetMasks(w.elements.length, w.proper))) issues.push('공집합을 포함해 가능한 부분집합을 빠짐없이 모아 보세요. 진부분집합에서는 자기 자신을 제외해요.');
  if (w.type === 'sl-proof' && (lab.order || []).join(',') !== w.steps.map((_, i) => i).join(',')) issues.push('가정 → 근거 → 식의 변형 → 결론 순서로 증명 카드를 연결해요.');
  if (w.type === 'sl-detective' && !sameSet(lab.suspects || [], w.answer)) issues.push('선택한 사람들과 모든 진술이 동시에 일치하는지 확인해요.');
  if (w.type === 'sl-transform' && w.target && (Boolean(lab.swap) !== w.target.swap || Boolean(lab.negate) !== w.target.negate)) issues.push('가정·결론의 순서와 두 조건의 부정 여부를 함께 맞춰요.');
  if (question.requireTrials && (record.trials || []).length < question.requireTrials) issues.push(`서로 다른 ${question.requireTrials}가지 경우 이상을 직접 탐색해 보세요.`);
  const reviewNeeded = question.fields.some(field => field.type === 'text');
  return { correct: !issues.length && !reviewNeeded, reviewNeeded: !issues.length && reviewNeeded, message: issues.length ? issues.slice(0, 2).join(' ') : reviewNeeded ? '기준 점검과 글쓰기를 마쳤어요. 자유 서술은 정답을 자동 판정하지 않고 Good쌤의 확인을 기다려요.' : question.explanation, issues };
}
export function readNumber(value) {
  const parts = String(value ?? '').replace(/−/g, '-').replace(/\s/g, '').split('/');
  if (parts.length > 2 || parts.some(part => !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(part))) return NaN;
  const number = parts.length === 2 ? Number(parts[0]) / Number(parts[1]) : Number(parts[0]);
  return Number.isFinite(number) ? number : NaN;
}
