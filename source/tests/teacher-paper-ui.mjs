import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { demoQuiz, DEMO_SETTINGS } from '../src/demo.js'

const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {url: 'https://test.invalid/component'})
const { window } = dom
for (const name of ['window','document','HTMLElement','HTMLInputElement','Option','MutationObserver']) globalThis[name] = name === 'window' ? window : window[name]
globalThis.ResizeObserver = class { observe() {} disconnect() {} }
window.HTMLElement.prototype.scrollIntoView = function () { this.dataset.scrolled = 'true' }
const paper = {title: '교사용 전체 문항', code: '123456', stage: 0, settings: structuredClone(DEMO_SETTINGS), questions: demoQuiz(0).questions}
paper.questions[0].visual = {type: 'mapping', title: '대응 관계', caption: '연결을 확인하세요.', diagrams: [{
  label: '(1)', leftSet: {name: 'X', elements: ['1', '2']}, rightSet: {name: 'Y', elements: ['a', 'b']}, connections: [{from: 0, to: 1}, {from: 1, to: 0}],
}]}
paper.questions[1].prompt += ' <img src=x onerror=alert(1)>'
const before = structuredClone(paper)
const props = {data: {userId: 'test-teacher', role: 'teacher', preview: true, teacherPaper: paper}}
const messages = []
const parent = {postMessage(message) {
  messages.push(message)
  if (message.type === 'streamlit:componentReady') queueMicrotask(render)
}}
Object.defineProperty(window, 'parent', {value: parent})
function render() { window.dispatchEvent(new window.MessageEvent('message', {source: parent, data: {type: 'streamlit:render', args: structuredClone(props)}})) }
await import('../src/main.js')
const $ = selector => document.querySelector(selector)
assert.equal(document.querySelectorAll('.paper-question').length, 3)
assert.equal(document.querySelectorAll('.paper-option').length, 15)
assert.ok($('.paper-prompt .katex'))
assert.ok($('.visual-mapping svg'))
assert.equal(document.querySelectorAll('.paper-solution[open]').length, 0)
assert.equal($('#start-button'), null)
assert.equal($('.answer-option'), null)
assert.equal($('img'), null, 'model text must never be interpreted as HTML')
$('.paper-header .primary-button').click()
assert.equal(document.querySelectorAll('.paper-solution[open]').length, 3)
for (const [i, el] of [...document.querySelectorAll('.paper-solution')].entries()) {
  assert.match(el.querySelector('h3').textContent, new RegExp(`정답 ${paper.questions[i].correctIndex + 1}번`))
  assert.ok(el.querySelector('.paper-correct-answer .katex'))
  assert.equal(el.querySelectorAll('.paper-hints li').length, 3)
}
document.querySelectorAll('.paper-nav button')[2].click()
assert.equal(document.activeElement.id, 'paper-question-3')
render()
assert.equal(document.querySelectorAll('.paper-solution[open]').length, 3, 'periodic Streamlit refresh preserves disclosure state')
$('.paper-header .primary-button').click()
assert.equal(document.querySelectorAll('.paper-solution[open]').length, 0)
assert.deepEqual(paper, before)
assert.equal(messages.filter(m => m.type === 'streamlit:setComponentValue').length, 0, 'teacher reading never creates attempts, saves, publishes, or asks AI')
props.data.teacherPaper = {...paper, title: '다음 퀴즈', questions: paper.questions.slice(0, 1)}
render()
assert.equal(document.querySelectorAll('.paper-question').length, 1)
assert.equal($('.paper-header h1').textContent, '다음 퀴즈')
console.log('PASS teacher paper: all questions, math, diagrams, answer toggles, navigation, safe text, read-only refresh')
window.close()
