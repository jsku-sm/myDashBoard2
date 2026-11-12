import { test } from 'node:test'
import assert from 'node:assert/strict'
import { demoQuiz, DEMO_SETTINGS } from './demo.js'
import { STAGES } from './curriculum.js'
import { validateSettings, validateQuiz, createProgress, answerQuestion, stageComplete, summarize, guideContext, safeGuidance, quizSchema } from './quiz.js'
import { generateQuiz, askGuide } from './quiz-api.js'

test('settings require a unit or range, standards, and a supported stage and count', () => {
  assert.equal(validateSettings(DEMO_SETTINGS), DEMO_SETTINGS)
  assert.doesNotThrow(() => validateSettings({ ...DEMO_SETTINGS, unit: '', range: '다항식의 곱셈' }))
  for (const invalid of [{ unit: '', range: '' }, { standards: [] }, { count: 4 }, { startStage: 5 }, { startStage: -1 }]) {
    assert.throws(() => validateSettings({ ...DEMO_SETTINGS, ...invalid }))
  }
})

test('all five demo stages have valid unique choices and standards without unnecessary visuals', () => {
  assert.deepEqual(STAGES.map((s) => s.name), ['기초', '기본', '응용', '심화', '최상위'])
  STAGES.forEach((_, stage) => {
    const quiz = validateQuiz(demoQuiz(stage), DEMO_SETTINGS)
    assert.equal(quiz.questions.length, 3)
    assert.ok(quiz.questions.every((q) => q.visual === null))
  })
})

test('wrong answers reveal a hint without solving or unlocking the stage', () => {
  const quiz = demoQuiz(0)
  const progress = createProgress(quiz.questions)
  const q = quiz.questions[0]
  const wrong = (q.correctIndex + 1) % 5
  progress[0] = answerQuestion(q, progress[0], wrong)
  assert.equal(progress[0].solved, false)
  assert.equal(progress[0].hintsUsed, 1)
  assert.equal(stageComplete(progress), false)
  const existing = progress[0]
  assert.equal(answerQuestion(q, existing, wrong), existing)
  assert.equal(answerQuestion(q, existing, -1), existing)
  assert.equal(answerQuestion(q, existing, 9), existing)
  progress[0] = answerQuestion(q, progress[0], q.correctIndex)
  assert.equal(progress[0].solved, true)
  assert.equal(answerQuestion(q, progress[0], wrong), progress[0])
  assert.equal(stageComplete(progress), false)
  for (let i = 1; i < progress.length; i++) progress[i] = answerQuestion(quiz.questions[i], progress[i], quiz.questions[i].correctIndex)
  assert.equal(stageComplete(progress), true)
  assert.deepEqual(summarize(progress), { solved: 3, firstTry: 2, retried: 1 })
  assert.equal(stageComplete([]), false)
})

test('malformed, duplicate, mismatched and unsafe numerical visual data is rejected', () => {
  for (const mutate of [
    (q) => { q.questions.pop() },
    (q) => { q.questions[0].correctIndex = 7 },
    (q) => { q.questions[0].options[1] = q.questions[0].options[0] },
    (q) => { q.questions[0].options[1] = q.questions[0].options[0].replaceAll('\\', '\\\\') },
    (q) => { q.questions[0].standardId = 'unselected' },
    (q) => { q.questions[1].prompt = q.questions[0].prompt },
    (q) => { q.questions[0].visual.items[0].x = Infinity },
    (q) => { q.questions[0].visual.type = 'raw_html' },
    (q) => { q.questions[0].hints = [] },
  ]) {
    const data = demoQuiz(0)
    data.questions[0].visual = { type: 'bars', title: '생산량', caption: '각 수량을 비교하세요.', items: [{ label: '가', x: 10, y: 0 }] }
    mutate(data)
    assert.throws(() => validateQuiz(data, DEMO_SETTINGS))
  }
})

test('visuals can be null or valid diagrams, but missing and malformed visuals are rejected', () => {
  for (const visual of [null, ...['concept', 'bars', 'number_line', 'coordinate'].map((type) => ({
    type, title: '주어진 조건', caption: '자료를 읽어 보세요.', items: [{ label: '$x$', x: 1, y: 2 }],
  }))]) {
    const data = demoQuiz(0)
    data.questions[0].visual = visual
    assert.equal(validateQuiz(data, DEMO_SETTINGS), data)
  }
  for (const visual of [undefined, false, {}, { type: 'none' }]) {
    const data = demoQuiz(0)
    data.questions[0].visual = visual
    assert.throws(() => validateQuiz(data, DEMO_SETTINGS))
  }
})

test('guide context excludes the answer key, options, hints and explanation', () => {
  const context = guideContext(DEMO_SETTINGS, demoQuiz(0).questions[0])
  for (const key of ['correctIndex', 'options', 'hints', 'explanation']) assert.equal(key in context, false)
  assert.ok(context.question)
})

test('guidance blocks explicit answers and option numbers while keeping useful concepts', () => {
  const q = demoQuiz(0).questions[0]
  const helpful = '같은 문자와 차수인 항을 찾아볼까요?'
  assert.equal(safeGuidance(helpful, q), helpful)
  for (const text of ['정답은 ②입니다.', `이 식의 결과는 ${q.options[q.correctIndex]}예요.`, '2번을 선택하세요.']) {
    assert.notEqual(safeGuidance(text, q), text)
  }
  const numberAnswer = { ...q, options: ['\\(12\\)', '2', '3', '4', '5'], correctIndex: 0 }
  assert.notEqual(safeGuidance('계산하면 \\(12\\)예요.', numberAnswer), '계산하면 \\(12\\)예요.')
  assert.ok(safeGuidance('', q))
})

const response = (text) => Response.json({ status: 'completed', output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text }] }] })

test('generation requests the exact count and strict Responses JSON schema', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const body = JSON.parse(options.body)
    assert.equal(body.text.format.type, 'json_schema')
    assert.equal(body.text.format.strict, true)
    assert.deepEqual(body.text.format.schema, quizSchema(3))
    assert.equal(JSON.parse(body.input[0].content).difficulty, '심화')
    assert.equal(body.max_output_tokens, 10000)
    assert.match(body.instructions, /visual은 기본적으로 null/)
    assert.match(body.instructions, /단순 계산[\s\S]*visual을 null/)
    assert.match(body.instructions, /수식 구분자 앞에는 역슬래시를 붙이지 않는다/)
    return response(JSON.stringify(demoQuiz(3)))
  })
  const quiz = await generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 3 })
  assert.equal(quiz.questions.length, 3)
  assert.ok(quiz.questions.every((q) => q.visual === null))
})

test('generation rejects non-JSON or invalid model output rather than presenting it', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => response('모델이 문항 생성을 거절했습니다.'))
  await assert.rejects(generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 0 }), /읽지 못/)
})

test('guide requests omit solutions and filter a reply that discloses the answer', async (t) => {
  const q = demoQuiz(0).questions[0]
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const body = JSON.parse(options.body)
    const context = JSON.parse(body.input[0].content.replace('현재 학습 맥락: ', ''))
    assert.equal('correctIndex' in context, false)
    assert.equal('explanation' in context, false)
    assert.equal('options' in context, false)
    assert.match(body.instructions, /절대 제공하지/)
    return response('정답은 2번입니다.')
  })
  const text = await askGuide({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, question: q, history: [], text: '정답을 알려줘' })
  assert.doesNotMatch(text, /정답은|2번/)
})
