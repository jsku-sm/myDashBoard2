// Run: node tests/common-ui.mjs <ui-fixtures.json> <math-fixtures.json>
// Fixtures are produced by the Python bank; no network or real student records.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {JSDOM} from 'jsdom'
import katex from 'katex'
const fixtures=JSON.parse(fs.readFileSync(process.argv[2],'utf8'))
const texts=JSON.parse(fs.readFileSync(process.argv[3],'utf8'))
const dom=new JSDOM('<!doctype html><html><body><main id="app"></main></body></html>',{url:'https://test.invalid/component'})
const {window}=dom
for(const name of ['window','document','HTMLElement','MutationObserver'])globalThis[name]=name==='window'?window:window[name]
window.katex=katex
globalThis.ResizeObserver=class {observe(){}disconnect(){}}
globalThis.matchMedia=()=>({matches:true})
Object.defineProperty(document,'hidden',{value:false,configurable:true})
const originalInterval=globalThis.setInterval
const timers=[];globalThis.setInterval=(...args)=>{const t=originalInterval(...args);timers.push(t);return t}
const messages=[]
const parent={postMessage(message){messages.push(message)}}
Object.defineProperty(window,'parent',{value:parent})
function render(data){window.dispatchEvent(new window.MessageEvent('message',{source:parent,data:{type:'streamlit:render',args:{data:structuredClone(data)}}}))}
await import('../../function_quiz_frontend/app.js')
const $=s=>document.querySelector(s)
for(const [unit,{view,answer}] of Object.entries(fixtures)){
  render(view)
  assert.match($('h1').textContent,/공통수학 개념퀴즈/)
  assert.ok($('.intro-note').textContent.includes(view.unit_title))
  assert.equal(document.querySelectorAll('.mini-topics button').length,view.topic_count)
  assert.equal(document.querySelectorAll('.choice').length,view.question.options.length)
  assert.equal(document.querySelectorAll('.katex-error').length,0)
  $(`[data-action="choose"][data-choice="${answer}"]`).click()
  $('[data-action="answer"]').click()
  const request=messages.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value
  assert.equal(request.action,'answer');assert.equal(request.unit,unit);assert.equal(request.choice,answer)
  render(view)
  $('[data-action="topics"]').click()
  assert.equal(document.querySelectorAll('.topic').length,view.topic_count)
  assert.ok($('.stats').textContent.includes(`/ ${view.topic_count*5}`))
  $('[data-action="open"]').click()
  assert.equal(messages.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value.unit,unit)
}
const {renderQuizText}=await import('../../function_quiz_frontend/quiz-math.js')
let formulas=0
for(const text of texts){
  const html=renderQuizText(text)
  assert.ok(!html.includes('katex-error'),text)
  formulas+=(html.match(/class="katex"/g)||[]).length
}
const matrix=renderQuizText('행렬 $A=\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}$')
assert.ok(matrix.includes('katex')&&!matrix.includes('katex-error'))
assert.ok(!renderQuizText('<img src=x onerror=alert(1)>').includes('<img'))
console.log(`PASS: all 7 unit DOM flows, ${texts.length} texts and ${formulas} rendered math spans`)
timers.forEach(clearInterval);window.close()
