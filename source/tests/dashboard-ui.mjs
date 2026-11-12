// Runs the production DOM and click handlers with a controlled Streamlit parent.
// No API key, live AI call, or real student records are used.
import assert from 'node:assert/strict'
import {JSDOM} from 'jsdom'
import {demoQuiz,DEMO_SETTINGS} from '../src/demo.js'
const mode=process.argv[2] || 'generate'
const dom=new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>',{url:'https://test.invalid/component'})
const {window}=dom
for (const name of ['window','document','HTMLElement','HTMLInputElement','Option','MutationObserver']) globalThis[name]=name==='window'?window:window[name]
window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
window.HTMLElement.prototype.scrollIntoView=function(){this.dataset.scrolled='true'}
globalThis.ResizeObserver=class {observe(){} disconnect(){}}
const props={enabled:mode!=='missing',model:'test-model',unavailableMessage:'키 설정 필요 [QUIZ_KEY_MISSING]',data:{userId:'test-teacher',preview:true,revision:0,saved:null},reply:null}
const assignedQuiz=demoQuiz(0)
if(mode==='assigned') props.data={userId:'fake-student',preview:false,role:'student',revision:0,assignment:{code:'123456',title:'함께 푸는 다항식',closed:false},saved:{showingSummary:false,session:{
  runId:'assigned-run-1234',settings:structuredClone(DEMO_SETTINGS),mode:'ai',stage:0,title:'함께 푸는 다항식',
  questions:assignedQuiz.questions,questionIndex:0,progress:assignedQuiz.questions.map(()=>({attempts:[],solved:false,hintsUsed:0})),history:[],threads:assignedQuiz.questions.map(()=>[]),previous:assignedQuiz.questions.map(q=>q.prompt)
}}}
let generated=[],saved=[],pending,publishRequests=0
function publication(status='ready') {
  const session=props.data.saved.session
  return {runId:session.runId,stage:session.stage,code:status==='ready'?'123456':'',status,error:status==='error'?'GitHub 저장 확인이 필요합니다.':''}
}
const parent={postMessage(message){
  if(message.type==='streamlit:componentReady') queueMicrotask(render)
  if(message.type!=='streamlit:setComponentValue') return
  const event=message.value
  if(event.action==='generate'){generated.push(event);pending=event}
  if(event.action==='save'){
    saved.push(event);props.data.revision++;props.data.saved=structuredClone(event.payload)
    if(mode!=='assigned')props.data.publication=event.payload.session ? publication(mode==='publication_error'?'error':'ready') : null
    queueMicrotask(()=>reply(event,true,{revision:props.data.revision}))
  }
  if(event.action==='publish'){
    publishRequests++;props.data.publication=publication()
    queueMicrotask(()=>reply(event,true,{publication:props.data.publication}))
  }
}}
Object.defineProperty(window,'parent',{value:parent})
function render(){window.dispatchEvent(new window.MessageEvent('message',{source:parent,data:{type:'streamlit:render',args:structuredClone(props)}}))}
function reply(event,ok,value){props.reply=ok?{id:event.id,ok,value}:{id:event.id,ok,error:value};render()}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function until(test){for(let i=0;i<100;i++){if(test())return;await delay(10)}throw new Error('UI response timed out')}
await import('../src/main.js')
const $=selector=>window.document.querySelector(selector)
if(mode==='invalid') for(const input of document.querySelectorAll('#standards input'))input.checked=false
$('#start-button').click()
if(mode==='assigned'){
  assert.equal($('#quiz-publication').hidden,true)
  assert.equal(generated.length,0)
  assert.equal(publishRequests,0)
  assert.equal($('.settings-panel').hidden,true)
  assert.equal($('#start-button').hidden,true)
  assert.equal($('#demo-button').hidden,true)
  assert.equal($('#reset-button').hidden,true)
  assert.match($('#journey-title').textContent,/함께 푸는 다항식/)
  $('#demo-button').click();$('#reset-button').click();$('#quizpop-home').click()
  assert.equal(generated.length,0)
  assert.ok($('.answer-option'),'hidden teacher controls cannot reset the assignment')
  for(const [i,q] of assignedQuiz.questions.entries()){
    assert.equal($('.difficulty-badge').textContent.includes(`${i+1} / 3`),true)
    if(i===0){
      document.querySelectorAll('.answer-option')[(q.correctIndex+1)%5].click()
      assert.ok($('.feedback-hint'))
    }
    document.querySelectorAll('.answer-option')[q.correctIndex].click()
    $('.question-bottom .primary-button').click()
  }
  assert.match($('.summary-card h2').textContent,/모두 완료/)
  assert.equal($('.summary-card .primary-button'),null,'no next-stage generation for students')
  await until(()=>saved.some(e=>e.payload.showingSummary))
  const submitted=saved.at(-1).payload
  assert.deepEqual(submitted.session.questions,assignedQuiz.questions)
  assert.equal(submitted.session.progress[0].attempts.length,2)
  assert.equal(submitted.session.progress[0].hintsUsed,1)
  assert.ok(submitted.session.progress.every(p=>p.solved))
  assert.equal(generated.length,0)
}else if(mode==='missing' || mode==='invalid'){
  assert.equal(generated.length,0)
  assert.equal($('#setup-error').hidden,false)
  assert.equal($('#setup-error').parentElement.className,'setup-actions')
  assert.equal(document.activeElement,$('#setup-error'))
  assert.match($('#setup-error').textContent,mode==='missing'?/QUIZ_KEY_MISSING/:/성취기준/)
}else{
  assert.equal(generated.length,1,'click emits a generate RPC without a native form submission')
  assert.equal($('#quiz-workspace').getAttribute('aria-busy'),'true')
  assert.equal($('#quiz-workspace').dataset.scrolled,'true')
  $('#start-button').click();assert.equal(generated.length,1,'double click does not duplicate the request')
  assert.equal(pending.payload.settings.count,3)
  assert.equal(pending.payload.difficulty,'기초')
  reply(pending,true,{text:JSON.stringify(demoQuiz(0))})
  await until(()=>$('.answer-option'))
  assert.equal(document.querySelectorAll('.answer-option').length,5)
  await until(()=>saved.length>0)
  assert.equal(saved[0].payload.session.questions.length,3)
  if(mode==='publication_error'){
    await until(()=>!$('#publication-retry').hidden)
    assert.equal($('#publication-code').hidden,true)
    assert.match($('#publication-message').textContent,/GitHub/)
    $('#publication-retry').click()
    await until(()=>$('#publication-code').textContent==='123456')
    assert.equal(publishRequests,1)
    assert.equal(generated.length,1,'retry publishing never calls AI again')
  }else{
    await until(()=>$('#publication-code').textContent==='123456')
    assert.equal(publishRequests,0,'code arrives automatically with saved questions')
  }
  assert.equal($('#quiz-publication').hidden,false)
  assert.equal($('#quiz-publication').dataset.scrolled,'true')
  assert.equal($('#publication-code').hidden,false)
  $('#reset-button').click();$('#start-button').click()
  await until(()=>generated.length===2)
  reply(pending,false,'AI 키 인증 실패 [QUIZ_AUTH]')
  await until(()=>$('.error-notice'))
  assert.match($('.error-notice').textContent,/QUIZ_AUTH/)
  assert.equal($('#quiz-workspace').getAttribute('aria-busy'),'false')
}
console.log(`PASS ${mode}: actual button click, visible feedback and component request handling`)
await delay(600) // Let the debounced save finish before tearing down this test DOM.
window.close()
