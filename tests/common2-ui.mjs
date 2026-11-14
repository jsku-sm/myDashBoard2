import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {COMMON2_GAMES,mission} from '../src/common2-data.js';
const dom=new JSDOM('<!doctype html><body><main id="host"></main></body>',{url:'https://test.invalid',pretendToBeVisual:true});
globalThis.window=dom.window;globalThis.document=dom.window.document;
let rafs=new Map(),counter=0,run=0;
globalThis.requestAnimationFrame=f=>{rafs.set(++counter,f);return counter;};
globalThis.cancelAnimationFrame=id=>rafs.delete(id);
const seed=12345;
Object.defineProperty(globalThis,'crypto',{value:{getRandomValues(a){a[0]=seed;return a;},randomUUID(){return 'test-run-'+(++run);}},configurable:true});
dom.window.SVGElement.prototype.getBoundingClientRect=()=>({left:0,top:0,width:560,height:460});
const {createCommon2Arcade,mathText}=await import('../src/common2-arcade.js');
const events=[],snapshots={};
const click=(selector)=>{const el=document.querySelector(selector);assert.ok(el,selector);el.click();};
const act=(name,attrs='')=>click(`[data-c2-action="${name}"]${attrs}`);
function point(p){document.querySelector('svg.c2-coordinate').dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true,clientX:280+32*p[0],clientY:230-32*p[1]}));document.querySelector('#common2-arena').dispatchEvent(new window.MouseEvent('pointerup',{bubbles:true}));}
function value(field,n){while(Number(document.querySelector(`[data-value="${field}"]`).value)!==n){const v=Number(document.querySelector(`[data-value="${field}"]`).value);act('adjust',`[data-field="${field}"][data-delta="${n>v?1:-1}"]`);}}
function solve(q){
 if(q.id==='coordinate-drone')point(q.answer);
 if(q.id==='line-rail'){act('endpoint','[data-value="0"]');point(q.P);act('endpoint','[data-value="1"]');point(q.Q);}
 if(q.id==='circle-radar'){point([q.h,q.k]);value('radius',q.r);}
 if(q.id==='move-portal'){
  if(q.stage!==2){for(let i=0;i<Math.abs(q.dx);i++)act('move',`[data-dir="${q.dx>0?'right':'left'}"]`);for(let i=0;i<Math.abs(q.dy);i++)act('move',`[data-dir="${q.dy>0?'up':'down'}"]`);}
  if(q.stage>1)act('reflect',`[data-op="${q.axis}"]`);
 }
 if(q.id==='venn-catcher')act('lane',`[data-value="${q.answer}"]`);
 if(q.id==='logic-bridge'){if(q.stage===3)act('counter',`[data-value="${q.answer}"]`);else for(const i of q.answer)act('condition',`[data-value="${i}"]`);}
 if(q.id==='function-factory'){for(const id of q.answerOrder)act('machine',`[data-id="${id}"]`);value('input',q.input);}
 if(q.id==='graph-rider'&&q.answer!==null)value('y',q.answer);
 act(q.id==='graph-rider'&&q.answer===null?'undefined':'submit');
}
for(const g of COMMON2_GAMES){
 events.length=0;const game=createCommon2Arcade({onEvent:e=>events.push(e),state:{},save(){}});
 game.open(g.id);document.getElementById('host').innerHTML=game.html();game.mount();
 assert.equal(events.length,0);act('start');
 assert.equal(events[0].type,'start');act('pause');assert.equal(document.querySelector('#common2-arena').dataset.phase,'paused');act('resume');
 for(let i=0;i<9;i++){
  const q=mission(g.id,Math.floor(i/3)+1,(seed+Math.imul(i+1,2654435761))>>>0);
  assert.equal(document.querySelectorAll('.katex-error').length,0,g.id);
  if(i===0){act('hint');assert.equal(events.at(-1).type,'hint');snapshots[g.id]=document.getElementById('host').innerHTML;}
  solve(q);
  assert.equal(events.filter(e=>e.type==='success').length,i+1,`${g.id}, mission ${i}`);
  assert.equal(document.querySelector('#common2-arena').dataset.phase,i===8?'won':'feedback');
  if(i<8)act('next');
 }
 assert.equal(events.filter(e=>e.type==='clear').length,3);assert.equal(events.filter(e=>e.type==='win').length,1);assert.equal(events.at(-1).score,900);
 const before=events.length;game.unmount();game.unmount();assert.equal(events.length,before);assert.equal(rafs.size,0);
}
// Incorrect action, timer, pause-on-hidden, and abandonment are observable events.
events.length=0;const game=createCommon2Arcade({onEvent:e=>events.push(e),state:{},save(){}});game.open('venn-catcher');document.getElementById('host').innerHTML=game.html();game.mount();document.querySelector('[data-mode]').value='challenge';act('start');
const q=mission('venn-catcher',1,(seed+Math.imul(1,2654435761))>>>0);act('lane',`[data-value="${(q.answer+1)%4}"]`);
for(let t=0;t<=8200;t+=100){const frame=[...rafs];rafs.clear();frame.forEach(([,f])=>f(t));}
assert.equal(events.filter(e=>e.type==='error').length,1);
Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new window.Event('visibilitychange'));assert.equal(events.at(-1).type,'pause');
const seconds=events.at(-1).elapsed;for(let t=8300;t<10000;t+=100){const frame=[...rafs];rafs.clear();frame.forEach(([,f])=>f(t));}game.unmount();assert.equal(events.at(-1).elapsed,seconds);assert.equal(events.at(-1).type,'leave');assert.equal(rafs.size,0);
let formulaCount=0;for(const g of COMMON2_GAMES)for(let stage=1;stage<=3;stage++)for(let seed=0;seed<30;seed++){const q=mission(g.id,stage,seed);for(const text of [q.prompt,q.hint,q.why]){const html=mathText(text);assert.ok(!html.includes('katex-error'),text);formulaCount++;}}
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(snapshots));
console.log(`PASS: 8 games × 9 missions through production DOM controls; pause, timer, hints, recording, teardown; ${formulaCount} math texts`);
dom.window.close();
