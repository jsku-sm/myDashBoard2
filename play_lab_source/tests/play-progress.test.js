import test from 'node:test';
import assert from 'node:assert/strict';
import { createLevelQuiz, levelVariantIds } from '../src/quiz-levels.js';
import { playProgress, unlockedQuizLevel, recordQuizAttempt, recordGameEvent, learningPoints, rankLearners, playSummary, createPlayReport, parsePlayReport, mergePlayReports } from '../src/play-progress.js';
const attempt = (state, level, topic, correct = true) => recordQuizAttempt(state, { level, topic, correct, question: '테스트 문항', selected: correct ? '정답' : '오답' });
const finishLevel = (state, level) => { let result; for (let i = 0; i < 6; i++) result = attempt(state, level, i); return result; };

test('five quiz levels unlock sequentially; only all six solved topics complete a stage', () => {
  const state = {};
  assert.equal(unlockedQuizLevel(state), 1); assert.equal(attempt(state, 2, 0).accepted, false);
  attempt(state, 1, 0, false); assert.equal(Object.keys(state.playLab.quiz.stages[1].passed).length, 0);
  for (let i = 0; i < 5; i++) attempt(state, 1, i);
  assert.equal(unlockedQuizLevel(state), 1); assert.equal(learningPoints(state), 0);
  assert.equal(attempt(state, 1, 5).completed, true); assert.equal(unlockedQuizLevel(state), 2); assert.equal(learningPoints(state), 100);
  attempt(state, 1, 5); assert.equal(learningPoints(state), 100);
  for (let level = 2; level <= 5; level++) { const result = finishLevel(state, level); assert.equal(result.completed, true); assert.equal(result.mastered, level === 5); }
  assert.ok(state.playLab.quiz.masteredAt); assert.equal(learningPoints(state), 1800);
  const reloaded = JSON.parse(JSON.stringify(state)); finishLevel(reloaded, 5); assert.equal(learningPoints(reloaded), 1800);
});

test('legacy completed concepts migrate to level one without overwriting existing worksheet records', () => {
  const state = { quizAnswers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [i, { correct: true }])), answers: { q01: { drawing: '기존 필기' } } };
  playProgress(state); assert.equal(unlockedQuizLevel(state), 2); assert.equal(learningPoints(state), 100); assert.equal(state.answers.q01.drawing, '기존 필기');
  playProgress(state); assert.equal(learningPoints(state), 100);
});

test('game stage points persist immediately, are idempotent per session and use equal whole-game totals', () => {
  for (const stages of [3, 6]) for (const mode of ['relaxed', 'challenge']) {
    const state = {}, base = { game: 'game', title: '게임', runId: 'one', stageCount: stages, mode, elapsed: 0 };
    recordGameEvent(state, { ...base, type: 'start' });
    for (let stage = 1; stage <= stages; stage++) { const event = { ...base, stage, type: 'clear' }; assert.ok(recordGameEvent(state, event).points > 0); assert.equal(recordGameEvent(state, event).points, 0); }
    recordGameEvent(state, { ...base, stage: stages, type: 'win' }); recordGameEvent(state, { ...base, type: 'win' });
    assert.equal(state.playLab.games.game.wins, 1); assert.equal(state.playLab.games.game.clears, stages); assert.equal(learningPoints(state), mode === 'challenge' ? 360 : 300);
    const other = { ...base, runId: 'two' }; recordGameEvent(state, { ...other, type: 'start' });
    assert.equal(recordGameEvent(state, { ...base, stage: 1, type: 'clear' }).points, 0);
    assert.ok(recordGameEvent(state, { ...other, stage: 1, type: 'clear' }).points > 0);
  }
});

test('rankings recalculate from actual points with correct ties and no fabricated scores', () => {
  const a = {}, b = {}, c = {}; finishLevel(a, 1); finishLevel(b, 1);
  let rows = rankLearners([{ id: 'a', name: '가', state: a }, { id: 'b', name: '나', state: b }, { id: 'c', name: '다', state: c }]);
  assert.deepEqual(rows.map(r => [r.id, r.rank, r.points]), [['a', 1, 100], ['b', 1, 100], ['c', 3, 0]]);
  finishLevel(b, 2); rows = rankLearners(rows); assert.equal(rows[0].id, 'b'); assert.equal(rows[0].points, 300); assert.equal(rows.find(r => r.id === 'a').rank, 2);
});

test('teacher signals distinguish sparse evidence, repeated errors, hints, strengths and stale activity', () => {
  const s = {}, base = { game: 'maze', title: '미로', runId: 'run', stageCount: 3, stage: 1, skill: '정의역', elapsed: 5, at: '2026-11-05T00:00:00.000Z' };
  recordGameEvent(s, { ...base, type: 'start' }); recordGameEvent(s, { ...base, type: 'error' });
  assert.equal(playSummary(s).needsHelp.length, 0); recordGameEvent(s, { ...base, type: 'error' });
  assert.equal(playSummary(s).needsHelp[0][0], '정의역');
  for (let i = 0; i < 3; i++) recordGameEvent(s, { ...base, type: 'success', skill: '함숫값' });
  assert.equal(playSummary(s).strengths[0][0], '함숫값'); assert.equal(s.playLab.games.maze.seconds, 5);
  assert.equal(playSummary(s, Date.parse(base.at) + 1000).status, '플레이 중'); assert.equal(playSummary(s, Date.parse(base.at) + 100000).status, '최근 플레이');
  recordGameEvent(s, { ...base, type: 'pause', elapsed: 8 }); assert.equal(playSummary(s).status, '일시정지'); assert.equal(s.playLab.games.maze.seconds, 8);
  recordGameEvent(s, { ...base, type: 'wait', elapsed: 8 }); assert.equal(playSummary(s).status, '다음 단계 대기');
  recordGameEvent(s, { ...base, type: 'resume', elapsed: 8 }); assert.equal(playSummary(s, Date.parse(base.at) + 1000).status, '플레이 중');
});

test('portable reports keep learner identity, reject malformed data and never replace newer snapshots', () => {
  const s = {}; finishLevel(s, 1); const report = createPlayReport(s, { name: '하늘', className: '1학년 1반' });
  assert.equal(parsePlayReport(JSON.stringify(report)).learner.id, s.playLab.learnerId);
  const reports = []; assert.equal(mergePlayReports(reports, report), true); assert.equal(mergePlayReports(reports, report), false);
  const old = structuredClone(report); old.playLab.updatedAt = '2020-01-01T00:00:00.000Z'; assert.equal(mergePlayReports(reports, old), false);
  assert.throws(() => parsePlayReport('{}')); const bad = structuredClone(report); bad.playLab.awards['quiz:1'].points = -1; assert.throws(() => parsePlayReport(JSON.stringify(bad)));
  const badSkill = structuredClone(report); badSkill.playLab.skills['함수의 뜻'].errors = 'oops'; assert.throws(() => parsePlayReport(JSON.stringify(badSkill)));
  const badName = structuredClone(report); badName.learner.name = {}; assert.throws(() => parsePlayReport(JSON.stringify(badName)));
});

test('advanced quiz pools preserve stable answers, genuine level-specific reasoning and distinct stems', () => {
  const kinds = new Map();
  for (let level = 2; level <= 5; level++) for (let topic = 0; topic < 6; topic++) {
    const variants = levelVariantIds(topic, level), stems = new Set(); assert.ok(variants.length >= 2);
    for (const v of variants) {
      const q = createLevelQuiz(topic, v, level), m = q.meta, answer = q.options[q.answer]; stems.add(q.q); assert.equal(new Set(q.options).size, 3); assert.ok(q.why);
      const key = `${topic}:${level}`; kinds.set(key, m.kind);
      let expected;
      switch (m.kind) {
        case 'function-count': expected = Array.from({ length: m.n }).reduce(n => n * m.m, 1); break;
        case 'image-count': expected = new Set(m.inputs.map(x => x * x + m.b)).size; break;
        case 'non-bijection': expected = m.h; break;
        case 'range-parameter': expected = m.n ** 2 + m.b - Math.max(m.n ** 2, 1); break;
        case 'linear-after-square': expected = m.a * m.n * m.n + m.b; break;
        case 'inverse-composition': expected = (m.a * (m.h + m.n) + m.b - m.b) / m.a - m.n; break;
        case 'composition-parameter': expected = m.a * m.h + m.b + m.n - m.a * m.h - m.n; break;
        case 'triple-composition': expected = (m.a * m.h + m.b + m.n - m.b) / m.a; break;
        case 'inverse-output': expected = m.a * m.n + m.b; break;
        case 'square-inverse': expected = m.h + Math.sqrt(m.n ** 2); break;
        case 'inverse-fixed-point': expected = (1 - m.a) * m.h; break;
        case 'root-inverse': expected = m.h + ((m.b + m.n) - m.b) ** 2 / m.a; break;
        case 'rational-parameter': expected = -m.a * m.h; break;
        case 'root-boundary-parameter': expected = -m.a * m.h; break;
        case 'root-inverse-sum': expected = m.h + m.n ** 2 + Math.sqrt(m.n ** 2) + m.b; break;
        case 'restricted-square': assert.equal(answer, `x ≥ ${m.h}`); break;
        case 'quadratic-range': assert.equal(answer, `[${m.b}, ${m.n ** 2 + m.b}]`); break;
        case 'inverse-domain': assert.equal(answer, `[${m.b}, ${m.b + m.n}]`); break;
        case 'reciprocal-inverse-domain': assert.equal(answer, `[1/${m.n}, 1]`); break;
        case 'cancelled-domain': assert.equal(answer, `{${m.excluded.join(', ')}}`); break;
        case 'rational-composition-domain': assert.equal(answer, `x ≠ ${m.b}`); break;
        case 'nested-reciprocal-domain': assert.equal(answer, `x ≠ ${m.h}`); break;
        case 'strict-root-domain': assert.equal(answer, `x > ${m.h}`); break;
        case 'root-and-pole': assert.equal(answer, `x ≥ ${m.h}, x ≠ ${m.h + m.n}`); break;
        default: assert.fail(m.kind);
      }
      if (expected !== undefined) assert.ok(Math.abs(Number(answer) - expected) <= .000051, `${q.q}: ${answer}`);
    }
    assert.equal(stems.size, variants.length);
  }
  for (let topic = 0; topic < 6; topic++) assert.equal(new Set([2, 3, 4, 5].map(level => kinds.get(`${topic}:${level}`))).size, 4);
});
