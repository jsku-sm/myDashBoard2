import { test } from 'node:test'
import assert from 'node:assert/strict'
import { demoQuiz, DEMO_SETTINGS } from './demo.js'
import { validateQuiz, quizSchema, guideContext } from './quiz.js'
import { generateQuiz, askGuide } from './quiz-api.js'

function mappingQuiz() {
  const quiz = demoQuiz(0)
  quiz.questions[0].visual = {
    type: 'mapping', title: '세 가지 대응 관계', caption: '각 집합의 원소와 연결을 살펴보세요.',
    diagrams: [
      [[0, 0], [1, 1], [3, 2]],
      [[0, 0], [1, 1], [2, 1], [3, 2]],
      [[0, 0], [1, 1], [2, 1], [2, 2], [3, 2]],
    ].map((edges, index) => ({
      label: `(${index + 1})`,
      leftSet: { name: 'X', elements: ['1', '2', '3', '4'] },
      rightSet: { name: 'Y', elements: ['a', 'b', 'c'] },
      connections: edges.map(([from, to]) => ({ from, to })),
    })),
  }
  return quiz
}

test('mapping validation preserves unmapped, many-to-one and one-to-many relations', () => {
  const quiz = mappingQuiz()
  const before = structuredClone(quiz)
  assert.equal(validateQuiz(quiz, DEMO_SETTINGS), quiz)
  assert.deepEqual(quiz, before)
  // A non-function is valid question data; validation must not repair its edges.
  assert.equal(quiz.questions[0].visual.diagrams[0].connections.some(({ from }) => from === 2), false)
  assert.equal(quiz.questions[0].visual.diagrams[2].connections.filter(({ from }) => from === 2).length, 2)
  quiz.questions[0].visual.diagrams[0].connections = []
  assert.doesNotThrow(() => validateQuiz(quiz, DEMO_SETTINGS))
})

test('mapping validation rejects dangling, duplicate and malformed diagram data', () => {
  const mutations = [
    (v) => { v.diagrams = [] },
    (v) => { v.diagrams = Array(6).fill(v.diagrams[0]) },
    (v) => { v.diagrams[0] = null },
    (v) => { v.diagrams[0].label = '' },
    (v) => { v.diagrams[1].label = v.diagrams[0].label },
    (v) => { v.diagrams[0].leftSet.elements = [] },
    (v) => { v.diagrams[0].rightSet.elements = Array(7).fill('a') },
    (v) => { v.diagrams[0].leftSet.elements[1] = '\\(1\\)' },
    (v) => { v.diagrams[0].rightSet.name = ' ' },
    (v) => { v.diagrams[0].rightSet.elements[0] = 'a'.repeat(81) },
    (v) => { v.diagrams[0].connections.push({ from: 4, to: 0 }) },
    (v) => { v.diagrams[0].connections.push({ from: 0, to: 3 }) },
    (v) => { v.diagrams[0].connections.push({ from: -1, to: 0 }) },
    (v) => { v.diagrams[0].connections.push({ from: 0.5, to: 0 }) },
    (v) => { v.diagrams[0].connections.push({ from: 0, to: Infinity }) },
    (v) => { v.diagrams[0].connections.push({ from: 0, to: 0 }) },
  ]
  for (const mutate of mutations) {
    const quiz = mappingQuiz()
    mutate(quiz.questions[0].visual)
    assert.throws(() => validateQuiz(quiz, DEMO_SETTINGS))
  }
})

const response = (text) => Response.json({ status: 'completed', output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text }] }] })

test('generation accepts the mapping schema and keeps diagram labels and edges while shuffling choices', async (t) => {
  const quiz = mappingQuiz()
  const original = quiz.questions[0]
  const schema = quizSchema(3)
  const branches = schema.properties.questions.items.properties.visual.anyOf
  assert.ok(branches.some((branch) => branch.type === 'null'))
  assert.deepEqual(branches.find((branch) => branch.properties?.type.enum.includes('mapping')).properties.type.enum, ['mapping'])
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const body = JSON.parse(options.body)
    assert.deepEqual(body.text.format.schema, schema)
    assert.match(body.instructions, /반드시 visual.type을 mapping/)
    assert.match(body.instructions, /대응이 없는 원소/)
    return response(JSON.stringify(quiz))
  })
  const generated = await generateQuiz({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, stage: 0 })
  const question = generated.questions.find(({ prompt }) => prompt === original.prompt)
  assert.deepEqual(question.visual, original.visual)
  assert.equal(question.options[question.correctIndex], original.options[original.correctIndex])
})

test('the guide receives the given mapping without the answer key or solution', async (t) => {
  const question = mappingQuiz().questions[0]
  const context = guideContext(DEMO_SETTINGS, question)
  assert.deepEqual(context.visual, question.visual)
  for (const key of ['correctIndex', 'options', 'hints', 'explanation']) assert.equal(key in context, false)
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const body = JSON.parse(options.body)
    const sent = JSON.parse(body.input[0].content.replace('현재 학습 맥락: ', ''))
    assert.deepEqual(sent, context)
    return response('왼쪽 집합에서 원소를 하나 골라, 그 원소에서 나가는 연결을 세어 볼까요?')
  })
  const reply = await askGuide({ apiKey: 'fake-test-key', settings: DEMO_SETTINGS, question, history: [], text: '그림을 어떻게 봐야 해요?' })
  assert.match(reply, /연결을 세어/)
})
