import test from 'node:test';
import assert from 'node:assert/strict';
import { createVariantPicker, setText } from '../src/practice-random.js';
import { QUIZ_TOPICS, QUIZ_VARIANTS, createQuizQuestion } from '../src/quiz-generator.js';
import { GAME_VARIANTS, createArcadeContent } from '../src/arcade-generator.js';
import { compileFormula, valueMission, trajectory, createDomainMaze } from '../src/arcade-math.js';
import { setupTerritory, territoryMask } from '../src/set-logic-arcade.js';
import { regionValue } from '../src/set-logic-math.js';

test('draws exclude the preceding variant even with constant randomness and after reload', () => {
  const values = new Map(), storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) };
  const next = createVariantPicker({ storage, random: () => 0 });
  assert.equal(next('quiz:0', 120), 0); assert.equal(next('quiz:0', 120), 1);
  const reloaded = createVariantPicker({ storage, random: () => 0 });
  assert.equal(reloaded('quiz:0', 120), 0);
  for (const [id, count] of Object.entries(GAME_VARIANTS)) {
    let previous = next(id, count);
    for (let i = 0; i < 40; i++) { const value = next(id, count); assert.notEqual(value, previous); assert.ok(value >= 0 && value < count); previous = value; }
  }
  assert.throws(() => next('bad', 1));
  const denied = createVariantPicker({ random: () => 0, storage: { getItem() { throw Error(); }, setItem() { throw Error(); } } });
  assert.notEqual(denied('x', 3), denied('x', 3));
});

test('all 720 concept quizzes have unique stems per topic, distinct choices and independently correct answers', () => {
  for (let topic = 0; topic < QUIZ_TOPICS.length; topic++) {
    const stems = new Set();
    for (let v = 0; v < QUIZ_VARIANTS; v++) {
      const q = createQuizQuestion(topic, v), m = q.meta, answer = q.options[q.answer]; stems.add(q.q);
      assert.equal(new Set(q.options).size, 3); assert.ok(q.answer >= 0 && q.answer < 3); assert.ok(q.why.length > 15);
      if (topic === 0) {
        const outputs = m.domain.map(x => m.edges.filter(([input]) => input === x).length);
        assert.equal(answer === '함수이다', outputs.every(n => n === 1));
        if (answer.includes('없다')) assert.ok(outputs.includes(0));
        if (answer.includes('두 개')) assert.ok(outputs.includes(2));
      }
      if (topic === 1) assert.equal(answer, setText(m.domain.map(x => m.a * x ** 2 + m.c)));
      if (topic === 2) assert.equal(Number(answer), (m.a * m.x + m.b) ** 2);
      if (topic === 3) assert.equal(Number(answer) * m.a + m.b, m.output);
      if (topic === 4) assert.equal(m.coefficient * (Number(answer) - m.boundary), 0);
      if (topic === 5) {
        const permits = x => answer.includes('≥') ? x >= m.boundary : x <= m.boundary;
        for (const x of [m.boundary - 1, m.boundary, m.boundary + 1]) assert.equal(permits(x), m.a * x + m.b >= 0);
      }
    }
    assert.equal(stems.size, QUIZ_VARIANTS, QUIZ_TOPICS[topic].title);
  }
});

test('every arcade has genuinely different mathematical content for every available variant', () => {
  for (const [id, count] of Object.entries(GAME_VARIANTS)) {
    const signatures = new Set();
    for (let v = 0; v < count; v++) {
      const c = createArcadeContent(id, v);
      const signature = c.domainLevels?.map(l => l.formula) || c.marbleLevels?.map(l => [l.start, l.fn(3), l.fn(11)]) || c.shotLevels?.map(l => [l.target, l.wall]) || c.pairs?.map(p => [p.left, p.right, p.graph]).sort() || c.counterRounds?.map(q => q.prompt) || c.territoryLevels?.map(l => l.label) || valueMission(3, id === 'bubble' ? 0 : 2, v).prompt;
      signatures.add(JSON.stringify(signature));
    }
    assert.equal(signatures.size, count, id);
  }
});

test('random shooter missions retain their exposed answer across every family and coefficient', () => {
  for (let v = 0; v < 40; v++) for (let family = 0; family < 4; family++) for (let answer = -3; answer <= 14; answer++) {
    const q = valueMission(answer, family, v), m = q.meta;
    const result = m.kind === 'inverse' ? (m.output - m.b) / m.a : m.kind === 'composition' ? m.a * (m.x + m.shift) + m.b : m.kind === 'square' ? m.a * m.x ** 2 + m.b : m.a * m.x + m.b;
    assert.equal(result, answer); assert.ok(q.why.includes(String(answer)));
  }
});

test('generated maze conditions match real evaluation and every key remains reachable', () => {
  for (const id of ['maze', 'root-maze']) for (let v = 0; v < GAME_VARIANTS[id]; v++) for (const level of createArcadeContent(id, v).domainLevels) {
    const f = compileFormula(level.formula.replace('f(x) =', ''));
    for (const x of level.legal) { assert.equal(level.valid(x), true); assert.ok(Number.isFinite(f(x))); }
    for (const x of level.illegal) { assert.equal(level.valid(x), false); assert.ok(!Number.isFinite(f(x))); }
    const cells = createDomainMaze(level), visited = new Set([46]), queue = [46];
    while (queue.length) { const i = queue.shift(); for (const next of [i - 9, i - 1, i + 1, i + 9]) { const cell = cells[next]; if (cell && !cell.wall && level.valid(cell.value) && !visited.has(next)) { visited.add(next); queue.push(next); } } }
    for (const key of [10, 31, 52, 16]) assert.ok(visited.has(key));
  }
});

test('all randomized graph rails are downhill, fit the play area and have attainable slider solutions', () => {
  for (const id of ['marble', 'root-marble']) for (let v = 0; v < GAME_VARIANTS[id]; v++) for (const level of createArcadeContent(id, v).marbleLevels) {
    const f = compileFormula(level.expression);
    assert.ok(Math.abs(f(0, level.solution) - level.start) < 1e-9);
    for (let x = 0; x <= 11; x += .1) { const y = f(x, level.solution); assert.ok(Math.abs(y - level.fn(x)) < 1e-9); assert.ok(y > 0 && y < 9); if (x > 0) assert.ok(y < f(x - .1, level.solution)); }
    for (const [key, value] of Object.entries(level.solution)) { const [lo, hi, step] = key === 'a' ? [-2, 2, .01] : key === 'b' ? [-3, 3, .05] : [-2, 9, .05]; assert.ok(value >= lo && value <= hi); assert.ok(Math.abs(value / step - Math.round(value / step)) < 1e-8); }
  }
});

test('every random projectile target has a legal launch that clears its wall', () => {
  for (let v = 0; v < GAME_VARIANTS.shot; v++) for (const level of createArcadeContent('shot', v).shotLevels) {
    const { angle, speed } = level.solution; assert.ok(angle >= 15 && angle <= 75 && speed >= 7 && speed <= 16);
    assert.ok(Math.abs(trajectory(level.target.x, angle, speed) - level.target.y) < 1e-6);
    assert.ok(level.target.y > .5 && level.target.y < 8);
    if (level.wall) for (const x of [level.wall.x - .37, level.wall.x, level.wall.x + .37]) assert.ok(trajectory(x, angle, speed) > level.wall.height + .17);
  }
});

test('counterexamples have exactly one legal target; random card graphs and territory masks stay consistent', () => {
  for (let v = 0; v < GAME_VARIANTS.counter; v++) for (const q of createArcadeContent('counter', v).counterRounds) assert.deepEqual(q.choices.filter(x => q.p(x) && !q.q(x)), [q.answer]);
  for (const id of ['memory', 'set-memory', 'logic-memory']) for (let v = 0; v < GAME_VARIANTS[id]; v++) {
    const pairs = createArcadeContent(id, v).pairs; assert.equal(pairs.length, 6); assert.equal(new Set(pairs.map(p => p.left)).size, 6); assert.equal(new Set(pairs.map(p => p.right)).size, 6);
    for (const pair of pairs.filter(p => p.graph)) { const f = compileFormula(pair.left), m = pair.graph; for (const x of [-2, 0, 2]) assert.equal(f(x), m.kind === 'line' ? m.a * x + m.b : (x - m.h) ** 2 + m.k); }
  }
  for (let v = 0; v < GAME_VARIANTS.territory; v++) for (let stage = 0; stage < 3; stage++) {
    const s = { content: createArcadeContent('territory', v), round: stage, difficulty: 'relaxed' }; setupTerritory(s);
    assert.ok(s.land.some(c => c.target));
    for (let i = 0; i < s.land.length; i++) if (!s.land[i].safe) assert.equal(s.land[i].target, regionValue(s.content.territoryLevels[stage].expression, territoryMask(i % 18, Math.floor(i / 18))));
  }
});
