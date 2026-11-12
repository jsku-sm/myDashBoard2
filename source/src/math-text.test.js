import { test } from 'node:test'
import assert from 'node:assert/strict'
import katex from 'katex'
import { normalizeMathDelimiters } from './math-text.js'
import { normalizeMath } from './quiz.js'

test('overescaped inline and display delimiters are normalized after parsing JSON', () => {
  const inline = String.raw`\((2x+1)+(x+3)\)`
  const display = String.raw`\[x^2+2x+1\]`
  for (const count of [1, 2, 4]) {
    const slash = '\\'.repeat(count)
    const text = `먼저 ${slash}((2x+1)+(x+3)${slash})을 계산해요. ${slash}[x^2+2x+1${slash}]`
    const parsed = JSON.parse(JSON.stringify({ text })).text
    assert.equal(normalizeMathDelimiters(parsed), `먼저 ${inline}을 계산해요. ${display}`)
    assert.equal(normalizeMathDelimiters(normalizeMathDelimiters(parsed)), normalizeMathDelimiters(parsed))
  }
})

test('valid LaTeX commands, escaped braces, dollar math and matrix row spacing are preserved', () => {
  const formula = String.raw`\frac{1}{2}+\sqrt{x}+\{1,2\}+\begin{matrix}1 & 2 \\[4pt] 3 & 4\end{matrix}`
  const text = String.raw`그대로 $\frac{1}{2}$, $$\begin{matrix}1 \\ 2\end{matrix}$$`
  assert.equal(normalizeMathDelimiters(text), text)
  for (const [open, close] of [['(', ')'], ['[', ']']]) {
    assert.equal(normalizeMathDelimiters(`\\\\${open}${formula}\\\\${close}`), `\\${open}${formula}\\${close}`)
  }
  assert.doesNotThrow(() => katex.renderToString(formula, { throwOnError: true }))
  for (const text of ['일반 문장과 (괄호)', String.raw`미완성 \\(x+1`, String.raw`C:\work\quiz`]) {
    assert.equal(normalizeMathDelimiters(text), text)
  }
})

test('equivalent choices normalize equally even with overescaped math delimiters', () => {
  assert.equal(normalizeMath(String.raw`\\(3x+4\\)`), normalizeMath('$3x+4$'))
})
