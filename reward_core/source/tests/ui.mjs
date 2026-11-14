import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import katex from 'katex';
import {initial} from '../src/simulation.js';
const dom=new JSDOM('<div id="app"></div>',{url:'https://example.test/component',pretendToBeVisual:true});
const {window}=dom;let raf,mono=0;const posted=[];
for(const key of ['window','document','sessionStorage','navigator'])Object.defineProperty(globalThis,key,{value:window[key],configurable:true});
Object.defineProperty(globalThis,'performance',{value:{now:()=>mono},configurable:true});
globalThis.ResizeObserver=class{observe(){} disconnect(){}};
globalThis.requestAnimationFrame=cb=>{raf=cb;return 1;};
window.HTMLCanvasElement.prototype.getContext=()=>new Proxy({createLinearGradient:()=>({addColorStop(){}})}, {get:(t,k)=>t[k]||(()=>{}),set:(t,k,v)=>(t[k]=v,true)});
window.postMessage=data=>posted.push(data);window.confirm=()=>true;
const audioSources=[];
const param=()=>({value:0,setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){},cancelScheduledValues(){},setTargetAtTime(){}});
const audioNode=()=>({connect(){},disconnect(){}});
window.AudioContext=class{
  constructor(){this.state='suspended';this.currentTime=0;this.sampleRate=44100;this.destination=audioNode();}
  async resume(){this.state='running';this.onstatechange?.();}
  createGain(){return {...audioNode(),gain:param()};}
  createBiquadFilter(){return {...audioNode(),frequency:param()};}
  createDynamicsCompressor(){return {...audioNode(),threshold:param(),knee:param(),ratio:param()};}
  createOscillator(){const node={...audioNode(),frequency:param(),start(){audioSources.push(this);},stop(){}};return node;}
  createBufferSource(){return this.createOscillator();}
  createBuffer(_,n){return {getChannelData:()=>new Float32Array(n)};}
};
const {math}=await import('../src/main.js');
const titles={jump:'스타 점프 어드벤처',kart:'네온 카트 러시',space:'우주 수호대',blocks:'팡팡 블록 브레이커',maze:'보물섬 대탈출'};
const games=Object.fromEntries(Object.entries(titles).map(([id,title])=>[id,{title,icon:'★',color:'#caff38',help:'방향키로 이동',medal:300}]));
const base={code:'123456',title:'공통수학2 · 함수와 그래프',status:'running',role:'student',mode:'solo',game:'jump',server_time:1000,ends_at:1600,duration:600,participants:2,goal:600,contribution:0,settling:false,games,modes:{solo:'개인 기록',rank:'순위 경쟁',coop:'학급 협동'},leaderboard:[],question_count:9,alias:'플레이어 01',index:0,turn:0,correct:0,wrong:0,hints:0,ticket:false,run:null,runs:[],feedback:null,coins:0,badges:[],personal_best:{},question:{prompt:'$f(x)=2x+1$에서 $f(2)$는?',options:['$5$','$3$','$4$'],topic_title:'함수',standard:'10공수2-03-01',hint:null}};
let current=structuredClone(base);
function render(v=current,ack=null,error=''){current=v;window.dispatchEvent(new window.MessageEvent('message',{source:window,data:{type:'streamlit:render',args:{view:v,ack,error}}}));}
const click=selector=>{const el=document.querySelector(selector);assert(el,selector);el.click();};
function last(){const e=posted.filter(e=>e.type==='streamlit:setComponentValue').at(-1);assert(e);return e.value;}
render();assert.equal(document.querySelectorAll('.katex').length,5);assert.equal(document.querySelectorAll('.option').length,3);
assert.equal(audioSources.length,0,'loading must not start audio');
click('[data-util="sound"]');await Promise.resolve();
assert.equal(document.querySelector('[data-util="sound"]').getAttribute('aria-pressed'),'true');
click('[data-util="sound"]');assert.equal(document.querySelector('[data-util="sound"]').getAttribute('aria-pressed'),'false');
click('[data-util="sound"]');await Promise.resolve();
const volume=document.querySelector('[data-volume]');volume.value=25;volume.dispatchEvent(new window.Event('input',{bubbles:true}));
assert.deepEqual(JSON.parse(window.localStorage.getItem('goodssaem-reward-audio-v1')),{effects:true,volume:.25});
assert.equal(posted.filter(e=>e.type==='streamlit:setComponentValue').length,0,'sound controls are local and never add server work');
click('[data-act="hint"]');let event=last();assert.equal(event.action,'hint');assert(document.querySelector('[data-act="hint"]').disabled);
render({...current,hints:1,question:{...current.question,hint:'입력 $2$를 대입해요.'}},event.id);assert(document.querySelector('.hint').textContent.includes('입력'));
click('[data-act="answer"][data-choice="1"]');event=last();assert.equal(event.choice,1);
render({...current,turn:1,wrong:1,feedback:{correct:false,choice:1,message:'다시 도전'}},event.id);assert(!document.querySelector('[data-act="answer"]').disabled);
click('[data-act="answer"][data-choice="0"]');event=last();
render({...current,turn:2,correct:1,feedback:{correct:true,choice:0,message:'정답은 $5$입니다.'}},event.id);assert(document.querySelector('[data-act="answer"]').disabled);
render({...current,server_time:1001});assert(document.querySelector('[data-act="answer"]').disabled);
click('[data-act="next"]');event=last();assert.equal(event.index,0);assert.equal(event.turn,2);
render({...base,index:3,correct:3,ticket:true,question:undefined},event.id);assert.equal(document.querySelectorAll('[data-select]').length,5);
click('[data-select="maze"]');click('[data-act="play"]');event=last();assert.equal(event.game,'maze');
let savedInputs=[];
for(const gid of Object.keys(games)){
  const run={id:'run-'+gid,game:gid,start:1000,until:1090,sim:initial(gid,33)};
  mono=0;render({...base,run,ticket:false,question:undefined},event.id);assert(document.querySelector('#gamecanvas'));
  const canvas=document.querySelector('#gamecanvas');
  const right=document.querySelector('[data-key="2"]');right.dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true}));
  mono=4300;raf();event=last();assert.equal(event.action,'progress');assert.equal(event.run,run.id);assert(event.inputs.some(i=>i&2));savedInputs=event.inputs;
  const {step}=await import('../src/simulation.js');const sim=initial(gid,33);for(const k of event.inputs)step(sim,k);
  render({...current,server_time:1004.3,run:{...run,sim}},event.id);
  assert.equal(document.querySelector('#gamecanvas'),canvas,'polling must not recreate the live canvas');
  right.dispatchEvent(new window.MouseEvent('pointerup',{bubbles:true}));
  window.dispatchEvent(new window.Event('blur'));
  mono=91000;raf();event=last();assert.equal(event.final,true);assert(event.inputs.every(i=>i===0),'released controls must not stick');
  const result={game:gid,score:120,hits:1,combo:3,coins:4,badge:'',seconds:90,ranked:true};
  render({...base,correct:3,index:3,runs:[result]},event.id);assert(!document.querySelector('#gamecanvas'));
}
render({...base,status:'ended',mode:'rank',question:undefined,runs:[{game:'jump',score:120,combo:3,coins:4,ranked:true}],leaderboard:[{alias:'플레이어 01',score:120,rank:1}]});assert(document.body.textContent.includes('우리 반 순위'));
render({...base,status:'ended',mode:'coop',goal:300,contribution:350,question:undefined});assert(document.body.textContent.includes('함께 해냈어요'));
render({...base,role:'teacher',status:'lobby',students:[]});assert(document.querySelector('.code').textContent==='123456');click('[data-act="start"]');event=last();assert.equal(event.action,'start');
render({...base,role:'teacher',students:[{class_name:'1-1',student_id:'test',name:'가상학생',alias:'플레이어 01',correct:3,wrong:1,hints:1,games:1,best:120,coins:4,phase:'문제 풀이'}]},event.id);assert(document.body.textContent.includes('가상학생'));click('[data-act="end"]');assert.equal(last().action,'end');
const endEvent=last();
for(const status of ['running','ended'])for(const mode of ['solo','rank','coop']){
  render({...base,role:'teacher',status,mode,students:[],leaderboard:[{alias:'플레이어 01',score:120,rank:1}]},endEvent.id);
  const board=document.querySelector('.teacher-dashboard');assert(board);
  assert(!board.querySelector('.split'),'progress table must not share a row with a sidebar');
  assert.equal(board.querySelector('table').closest('.panel').parentElement,board);
  assert(!document.body.textContent.includes('MY NEXT LEVEL'));
  assert(!document.body.textContent.includes('정답은 쌓이고'));
  assert(!document.body.textContent.includes('수학 정답과 게임 점수는 따로'));
  if(mode==='rank')assert(board.querySelector('.teacher-summary').textContent.includes('우리 반 순위'));
  if(mode==='coop')assert(board.querySelector('.teacher-summary [role="progressbar"]'));
}
assert(document.querySelector('[data-volume]'));
render({...base});assert(document.body.textContent.includes('MY NEXT LEVEL'),'student encouragement is preserved');
assert(document.body.textContent.includes('정답은 쌓이고'),'student reward explanation is preserved');
assert(!math('<img src=x onerror=alert(1)>').includes('<img'));
if(process.argv[2]){
  const items=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));let formulas=0;
  for(const text of items){for(const s of text.match(/\$\$[\s\S]*?\$\$|\$[^$\n]+\$/g)||[]){katex.renderToString(s.slice(s.startsWith('$$')?2:1,s.startsWith('$$')?-2:-1),{throwOnError:true,trust:false,strict:'ignore'});formulas++;}math(text);}
  console.log(`Rendered ${items.length} question texts and ${formulas} formulas without KaTeX errors.`);
}
console.log('DOM flow passed: hints, retries, tickets, five canvases, touch release, stable rerenders, timed finish, rankings, cooperation, teacher controls.');

// Leaving a live game first acknowledges its unconfirmed controls.
const leaveRun={id:'leave-run',game:'jump',start:1000,until:1090,sim:initial('jump',33)};
mono=0;
window.dispatchEvent(new window.MessageEvent('message',{source:window,data:{type:'streamlit:render',args:{view:{...base,run:leaveRun,question:undefined},ack:last().id,returnToGames:true}}}));
assert(document.querySelector('[data-game-list]'),'all-game return is present inside fullscreen content');
mono=1200;raf();click('[data-game-list]');const exitProgress=last();assert.equal(exitProgress.action,'progress');assert(exitProgress.inputs.length>0);
const leaveSim=initial('jump',33);const {step:advance}=await import('../src/simulation.js');for(const input of exitProgress.inputs)advance(leaveSim,input);
window.dispatchEvent(new window.MessageEvent('message',{source:window,data:{type:'streamlit:render',args:{view:{...base,run:{...leaveRun,sim:leaveSim},question:undefined},ack:exitProgress.id,returnToGames:true}}}));
assert.equal(last().action,'game_list','navigation happens only after input acknowledgement');
console.log('PASS: conspicuous game-list return and save-before-exit for live reward games.');
