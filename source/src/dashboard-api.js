import { request } from './dashboard-bridge.js'

export function requestResponse({input, format, signal}) {
  if (format?.name === 'math_quiz') {
    return request('generate', JSON.parse(input[0].content), {signal})
  }
  const prefix = '현재 학습 맥락: '
  if (!input[0]?.content?.startsWith(prefix)) throw new Error('학습 맥락을 다시 확인해 주세요.')
  return request('guide', {
    context:JSON.parse(input[0].content.slice(prefix.length)),
    history:input.slice(1,-1),text:input.at(-1).content,
  }, {signal})
}
