import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MODEL, createRequestBody, parseResponse, getErrorMessage, requestResponse } from './openai.js'

const assistant = (text, extra = {}) => ({
  type: 'message', role: 'assistant', status: 'completed',
  content: [{ type: 'output_text', text, annotations: [] }], ...extra,
})
const completed = (...output) => ({ status: 'completed', output })

test('request body carries the full conversation and uses Responses parameters', () => {
  const input = [{ role: 'user', content: '내 이름은 민수야.' }, assistant('반가워!', { phase: 'final_answer' }), { role: 'user', content: '내 이름은?' }]
  const body = createRequestBody(input)
  assert.equal(body.model, MODEL)
  assert.deepEqual(body.input, input)
  assert.deepEqual(body.reasoning, { effort: 'none' })
  assert.equal(body.store, false)
  assert.equal(body.max_output_tokens, 4096)
  assert.equal('messages' in body, false)
})

test('parses all text messages after non-message items and preserves message phase', () => {
  const first = assistant('첫 번째 답변', { phase: 'final_answer' })
  const second = assistant('두 번째 답변')
  const reply = parseResponse(completed({ type: 'reasoning', summary: [] }, first, second))
  assert.equal(reply.text, '첫 번째 답변\n\n두 번째 답변')
  assert.deepEqual(reply.messages, [first, second])
  assert.equal(reply.messages[0].phase, 'final_answer')
})

test('refusals are displayed as completed API replies', () => {
  const reply = parseResponse(completed(assistant('', { content: [{ type: 'refusal', refusal: '이 요청에는 답변할 수 없어요.' }] })))
  assert.equal(reply.text, '이 요청에는 답변할 수 없어요.')
})

test('empty, malformed, failed and incomplete replies cannot count as success', () => {
  for (const data of [null, {}, { status: 'queued', output: [] }, completed(), completed(null), completed(assistant('', { content: [null] })), completed(assistant('   ')), { status: 'failed', error: { code: 'server_error' } }]) {
    assert.throws(() => parseResponse(data))
  }
  assert.throws(() => parseResponse({ status: 'incomplete', incomplete_details: { reason: 'max_output_tokens' } }), /길이 한도/)
})

test('API errors explain authentication, permission, quota, rate limits and context length', () => {
  assert.match(getErrorMessage(401), /인증/)
  assert.match(getErrorMessage(403), /권한/)
  assert.match(getErrorMessage(404), /모델/)
  assert.match(getErrorMessage(429, { code: 'insufficient_quota' }), /잔액/)
  assert.match(getErrorMessage(429, { code: 'credit_balance_exhausted' }), /잔액/)
  assert.match(getErrorMessage(429), /요청이 너무 많/)
  assert.match(getErrorMessage(503), /일시적인/)
  assert.match(getErrorMessage(400, { code: 'context_length_exceeded' }), /대화를 초기화/)
})

test('direct fetch uses POST, bearer auth and the Responses endpoint', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://api.openai.com/v1/responses')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers.Authorization, 'Bearer fake-test-key')
    assert.equal(options.headers['Content-Type'], 'application/json')
    assert.equal(JSON.parse(options.body).input[0].content, '안녕')
    return Response.json(completed(assistant('반가워요!')))
  })
  const reply = await requestResponse({ apiKey: 'fake-test-key', input: [{ role: 'user', content: '안녕' }] })
  assert.equal(reply.text, '반가워요!')
})

test('HTTP errors never expose the raw API error or key', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ error: { message: 'Incorrect API key: fake-test-key', code: 'invalid_api_key' } }, { status: 401 }))
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [] }), (error) => {
    assert.match(error.message, /인증/)
    assert.equal(error.message.includes('fake-test-key'), false)
    return true
  })
})

test('non-JSON server errors retain HTTP guidance', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<h1>Bad gateway</h1>', { status: 502 }))
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [] }), /서버에 일시적인/)
})

test('a non-JSON success response is explained rather than shown as success', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('invalid-json'))
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [] }), /JSON/)
})

test('network errors are explained', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [] }), /인터넷 연결/)
})

const pendingFetch = async (_url, { signal }) => new Promise((_resolve, reject) => {
  const abort = () => reject(new DOMException('Aborted', 'AbortError'))
  if (signal.aborted) abort()
  else signal.addEventListener('abort', abort, { once: true })
})

test('requests time out and abort the fetch', async (t) => {
  t.mock.method(globalThis, 'fetch', pendingFetch)
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [], timeoutMs: 10 }), /60초/)
})

test('reset cancellation propagates to the fetch, including already-aborted signals', async (t) => {
  t.mock.method(globalThis, 'fetch', pendingFetch)
  const controller = new AbortController()
  const request = requestResponse({ apiKey: 'fake-test-key', input: [], signal: controller.signal })
  controller.abort()
  await assert.rejects(request, /취소/)
  await assert.rejects(requestResponse({ apiKey: 'fake-test-key', input: [], signal: controller.signal }), /취소/)
})
