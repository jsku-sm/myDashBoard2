export const MODEL = 'gpt-6-luna'
const RESPONSES_URL = 'https://api.openai.com/v1/responses'

export function createRequestBody(input, { instructions, format, maxOutputTokens = 4096 } = {}) {
  return {
    model: MODEL,
    instructions: instructions ?? String.raw`You are a patient Korean math learning guide for first-year vocational high school students. Explain one concept at a time and ask a guiding question. Never give the final answer or the correct option to a quiz. Format numbers and mathematical expressions in LaTeX using \( ... \) or \[ ... \].`,
    input,
    // 이 모델이 지원하는 none으로 추론을 끄고 간단한 텍스트 대화를 실습합니다.
    reasoning: { effort: 'none' },
    max_output_tokens: maxOutputTokens,
    store: false,
    ...(format ? { text: { format } } : {}),
  }
}

export function getErrorMessage(status, error = {}) {
  const code = error?.code
  if (['insufficient_quota', 'credit_balance_exhausted', 'billing_hard_limit_reached'].includes(code)) {
    return 'API 사용 잔액이나 결제 한도가 부족해요. OpenAI Platform의 Billing과 사용 한도를 확인해 주세요.'
  }
  if (status === 401) return 'API 키를 인증하지 못했어요. .env.local의 키가 올바른지, 만료되거나 폐기되지 않았는지 확인하고 개발 서버를 재시작해 주세요.'
  if (status === 403) return '이 요청을 사용할 권한이 없어요. OpenAI 프로젝트의 API 키 권한, 모델 접근 권한, 지원 지역을 확인해 주세요.'
  if (status === 404 || code === 'model_not_found') return `모델(${MODEL})을 찾을 수 없거나 접근 권한이 없어요. OpenAI 프로젝트의 모델 접근 권한을 확인해 주세요.`
  if (status === 429) return '요청이 너무 많거나 사용 한도에 도달했어요. 잠시 기다린 뒤 다시 시도하고 OpenAI Platform의 사용 한도를 확인해 주세요.'
  if (status >= 500) return 'OpenAI 서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요.'
  if (status === 408) return '서버의 요청 처리 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.'
  if (code === 'context_length_exceeded') return '대화가 모델이 처리할 수 있는 길이를 넘었어요. 대화를 초기화한 뒤 다시 시작해 주세요.'
  if (status === 400 || status === 422) return '요청 형식을 처리하지 못했어요. 질문을 짧게 바꾸거나 대화를 초기화해 다시 시도해 주세요.'
  return `API 요청이 실패했어요 (HTTP ${status}). 네트워크와 OpenAI 프로젝트 설정을 확인한 뒤 다시 시도해 주세요.`
}

export function parseResponse(data) {
  if (data?.error || data?.status === 'failed') throw new Error(getErrorMessage(500, data.error))
  if (data?.status === 'incomplete') {
    throw new Error(data.incomplete_details?.reason === 'max_output_tokens'
      ? '답변이 출력 길이 한도에 도달했어요. 질문 범위를 줄이거나 짧게 답해 달라고 요청해 주세요.'
      : '답변이 끝까지 생성되지 않았어요. 질문을 바꿔 다시 시도해 주세요.')
  }
  if (data?.status !== 'completed' || !Array.isArray(data.output)) {
    throw new Error('API 응답 형식이 예상과 달라 답변을 읽지 못했어요. 다시 시도해 주세요.')
  }

  // fetch의 원본 JSON에는 SDK 전용 편의 속성 output_text가 없습니다.
  // 첫 항목을 가정하지 않고 모든 assistant message를 순회합니다.
  const messages = data.output.filter((item) => item?.type === 'message' && item.role === 'assistant' && Array.isArray(item.content))
  const text = messages.flatMap((item) => item.content)
    .filter((part) => part?.type === 'output_text' || part?.type === 'refusal')
    .map((part) => part.type === 'refusal' ? part.refusal : part.text)
    .filter((part) => typeof part === 'string' && part.trim())
    .join('\n\n')
  if (!text) throw new Error('요청은 도착했지만 표시할 텍스트 답변이 없어요. 질문을 바꿔 다시 시도해 주세요.')
  // 원본 message의 phase, content 등을 유지해 다음 턴에 전달합니다.
  return { text, messages }
}

export async function requestResponse({ apiKey, input, signal, timeoutMs = 60000, instructions, format, maxOutputTokens }) {
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (signal?.aborted) controller.abort()
  else signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)

  try {
    const response = await fetch(RESPONSES_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify(createRequestBody(input, { instructions, format, maxOutputTokens })),
      signal: controller.signal,
    })
    let data
    try { data = await response.json() } catch (error) {
      if (controller.signal.aborted) throw error
      if (!response.ok) throw new Error(getErrorMessage(response.status))
      throw new Error('서버 응답을 JSON으로 읽지 못했어요. 네트워크 상태를 확인하고 다시 시도해 주세요.')
    }
    if (!response.ok) throw new Error(getErrorMessage(response.status, data?.error))
    return parseResponse(data)
  } catch (error) {
    if (timedOut) throw new Error('60초 안에 답변을 받지 못했어요. 네트워크를 확인하거나 질문을 짧게 바꿔 다시 시도해 주세요.')
    if (error.name === 'AbortError' || signal?.aborted) throw new Error('요청이 취소되었어요.')
    if (error instanceof TypeError) throw new Error('OpenAI API에 연결하지 못했어요. 인터넷 연결, 브라우저의 CORS 차단 여부, VPN·방화벽 설정을 확인해 주세요.')
    throw error
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}
