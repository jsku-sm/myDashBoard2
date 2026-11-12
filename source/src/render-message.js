import renderMathInElement from 'katex/contrib/auto-render'
import { normalizeMathDelimiters } from './math-text.js'

export function renderMessage(element, text) {
  // 모델과 사용자 입력을 HTML로 해석하지 않고, 수식 부분만 KaTeX로 변환합니다.
  element.textContent = normalizeMathDelimiters(text)
  renderMathInElement(element, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
      { left: '$', right: '$', display: false },
    ],
    throwOnError: false,
    trust: false,
    maxSize: 10,
    maxExpand: 1000,
  })
}
