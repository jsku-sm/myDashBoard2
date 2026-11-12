import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createQuestionHistory, QUESTION_HISTORY_KEY, MAX_UNIT_QUESTIONS, unitHistoryKey, repeatedPrompts, shuffleQuiz } from './question-history.js'
import { demoQuiz, DEMO_SETTINGS } from './demo.js'
import { generateQuiz } from './quiz-api.js'
import { validateQuiz } from './quiz.js'

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial))
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) }
}

function seededRandom(seed) {
  return () => { seed = (Math.imul(1664525, seed) + 1013904223) >>> 0; return seed / 2 ** 32 }
}

test('question history survives a new session and returns independent snapshots', () => {
  const storage = memoryStorage()
  const first = createQuestionHistory(storage)
  first.remember(DEMO_SETTINGS, demoQuiz(0).questions)
  const restarted = createQuestionHistory(storage)
  assert.deepEqual(restarted.get(DEMO_SETTINGS), demoQuiz(0).questions.map((q) => q.prompt))
  restarted.get(DEMO_SETTINGS).push('external mutation')
  assert.equal(restarted.get(DEMO_SETTINGS).length, 3)
  first.remember(DEMO_SETTINGS, demoQuiz(0).questions)
  assert.equal(restarted.get(DEMO_SETTINGS).length, 3)
})

test('history follows the unit across changed criteria, difficulty and count but separates courses', () => {
  const history = createQuestionHistory(memoryStorage())
  history.remember(DEMO_SETTINGS, demoQuiz(0).questions)
  assert.equal(history.get({ ...DEMO_SETTINGS, range: '다른 쪽수', startStage: 4, count: 7, standards: [] }).length, 3)
  assert.equal(history.get({ ...DEMO_SETTINGS, course: '공통수학2' }).length, 0)
  assert.equal(history.get({ ...DEMO_SETTINGS, unit: '행렬' }).length, 0)
  assert.equal(unitHistoryKey({ course: '공통수학1', unit: '  ', range: ' 직접 범위 ' }), unitHistoryKey({ course: '공통수학1', range: '직접 범위' }))
})

test('corrupt history is repaired, and unavailable storage retains history in memory', () => {
  const storage = memoryStorage({ [QUESTION_HISTORY_KEY]: '{broken json' })
  const recovered = createQuestionHistory(storage)
  assert.deepEqual(recovered.get(DEMO_SETTINGS), [])
  recovered.remember(DEMO_SETTINGS, demoQuiz(0).questions)
  assert.equal(createQuestionHistory(storage).get(DEMO_SETTINGS).length, 3)
  for (const blocked of [undefined, { getItem() { throw new Error('blocked') } }, { getItem() { return null }, setItem() { throw new Error('quota') } }]) {
    const history = createQuestionHistory(blocked)
    history.remember(DEMO_SETTINGS, demoQuiz(0).questions)
    assert.equal(history.get(DEMO_SETTINGS).length, 3)
  }
})

test('history retains only the recent bounded unit question set', () => {
  const history = createQuestionHistory(memoryStorage())
  history.remember(DEMO_SETTINGS, Array.from({ length: MAX_UNIT_QUESTIONS + 5 }, (_, i) => ({ prompt: `문제 ${i}` })))
  assert.equal(history.get(DEMO_SETTINGS).length, MAX_UNIT_QUESTIONS)
  assert.equal(history.get(DEMO_SETTINGS)[0], '문제 5')
})

test('duplicate checks catch reworded or reordered math and duplicates in the new batch', () => {
  const old = String.raw`\(2x+3\)과 \(x+4\)의 합은?`
  const repeated = '$x+4$ 와 $2x+3$ 을 더한 식을 골라 보세요.'
  assert.deepEqual(repeatedPrompts([{ prompt: repeated }], [old]), [repeated])
  const overescaped = String.raw`\\(x+4\\)와 \\\\(2x+3\\\\)을 더해 보세요.`
  assert.deepEqual(repeatedPrompts([{ prompt: overescaped }], [old]), [overescaped])
  assert.equal(repeatedPrompts([{ prompt: String.raw`\(3x+3\)과 \(x+4\)의 합은?` }], [old]).length, 0)
  assert.equal(repeatedPrompts([{ prompt: old }, { prompt: repeated }]).length, 1)
  assert.equal(repeatedPrompts([{ prompt: '같은 문제!' }], ['같은  문제?']).length, 1)
})

test('shuffling preserves the correct answer and source quiz without corrupting numbered explanations', () => {
  const original = demoQuiz(0)
  const snapshot = structuredClone(original)
  const shuffled = shuffleQuiz(original, seededRandom(2026))
  assert.deepEqual(original, snapshot)
  for (const q of shuffled.questions) {
    const source = original.questions.find((item) => item.prompt === q.prompt)
    assert.equal(q.options[q.correctIndex], source.options[source.correctIndex])
    assert.deepEqual([...q.options].sort(), [...source.options].sort())
  }
  original.questions[0].explanation = '정답은 2번입니다.'
  const numbered = shuffleQuiz(original, seededRandom(6)).questions.find((q) => q.prompt === original.questions[0].prompt)
  assert.deepEqual(numbered.options, original.questions[0].options)
  assert.equal(numbered.correctIndex, original.questions[0].correctIndex)
})

test('repeated five-stage demo runs use fresh valid math questions', () => {
  const random = seededRandom(20261109)
  const previous = []
  for (let round = 0; round < 12; round++) {
    for (let stage = 0; stage < 5; stage++) {
      const quiz = demoQuiz(stage, { previous, randomize: true, random })
      validateQuiz(quiz, DEMO_SETTINGS)
      assert.deepEqual(repeatedPrompts(quiz.questions, previous), [])
      previous.push(...quiz.questions.map((q) => q.prompt))
    }
  }
  assert.equal(previous.length, 180)
})

const response = (quiz) => Response.json({ status: 'completed', output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: JSON.stringify(quiz) }] }] })

test('AI retries duplicates from the full history and gives each request a new variation id', async (t) => {
  const old = demoQuiz(0)
  const previous = [...old.questions.map((q) => q.prompt), ...Array.from({ length: 130 }, (_, i) => `지난 문제 ${i}`)]
  const fresh = demoQuiz(0, { previous, randomize: true, random: seededRandom(33) })
  const requests = []
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    requests.push(JSON.parse(JSON.parse(options.body).input[0].content))
    return response(requests.length === 1 ? old : fresh)
  })
  const result = await generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 0, previous })
  assert.equal(requests.length, 2)
  assert.notEqual(requests[0].variationId, requests[1].variationId)
  assert.equal(requests[0].avoidRepeating.includes(old.questions[0].prompt), false)
  assert.ok(requests[1].avoidRepeating.includes(old.questions[0].prompt))
  assert.deepEqual(repeatedPrompts(result.questions, previous), [])
})

test('AI stops after bounded duplicate retries and never presents a repeated quiz', async (t) => {
  const old = demoQuiz(0)
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return response(old) })
  await assert.rejects(generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 0, previous: old.questions.map((q) => q.prompt) }), /이전에 풀었던/)
  assert.equal(calls, 3)
})

test('cancelling between duplicate attempts prevents another API call', async (t) => {
  const old = demoQuiz(0)
  const controller = new AbortController()
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; controller.abort(); return response(old) })
  await assert.rejects(generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 0, previous: old.questions.map((q) => q.prompt), signal: controller.signal }), /취소/)
  assert.equal(calls, 1)
})
