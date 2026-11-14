import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';

const dom=new JSDOM('<header data-testid="stHeader"></header><main data-testid="stMain"><nav>수학 플레이 메뉴</nav><section class="st-key-good_game_panel">게임</section></main>',{url:'https://test.invalid',pretendToBeVisual:true});
const host=dom.window;globalThis.window=host;globalThis.parent=host;host.postMessage=()=>{};
let now=0,id=0,frames=new Map(),calls=[];
Object.defineProperty(host.performance,'now',{value:()=>now});
host.requestAnimationFrame=fn=>{frames.set(++id,fn);return id;};host.cancelAnimationFrame=i=>frames.delete(i);
const scroller=host.document.querySelector('main'),panel=host.document.querySelector('section');
let panelHeight=800;
scroller.getBoundingClientRect=()=>({top:0});
panel.getBoundingClientRect=()=>({top:1200-scroller.scrollTop,height:panelHeight});
host.document.querySelector('header').getBoundingClientRect=()=>({bottom:56});
scroller.scrollTo=({top,behavior})=>{calls.push({top,behavior});scroller.scrollTop=top;};
const {revealEntry}=await import('../../game_core/game_entry_frontend/entry.js');
function advance(n=1){for(let i=0;i<n;i++){now+=20;const work=[...frames.values()];frames.clear();for(const fn of work)fn();}}

test('opening a game from far down the list aligns below header without any overlay or style changes',()=>{
  scroller.scrollTop=1600;calls=[];const before=host.document.body.innerHTML;
  revealEntry(host);advance(40);
  assert.equal(scroller.scrollTop,1132);assert.equal(panel.getBoundingClientRect().top,68);
  assert.equal(calls[0].behavior,'instant');assert.equal(frames.size,0);
  assert.equal(host.document.body.innerHTML,before,'no fixed positioning, scaling, removed menus or scroll locks');
});

test('wait for game panel layout, then stop; user interaction cancels pending alignment',()=>{
  scroller.scrollTop=1600;panelHeight=30;revealEntry(host);advance(30);assert(frames.size>0);
  panelHeight=800;advance(12);assert.equal(frames.size,0);
  scroller.scrollTop=1600;revealEntry(host);host.dispatchEvent(new host.Event('wheel'));advance(2);assert.equal(scroller.scrollTop,1600);
  revealEntry(host);host.dispatchEvent(new host.Event('pointerdown'));advance(2);assert.equal(scroller.scrollTop,1600);
});

test('same game record updates never reposition the page, changing games does',()=>{
  const send=entry=>host.dispatchEvent(new host.MessageEvent('message',{source:host,data:{type:'streamlit:render',args:{entry}}}));
  scroller.scrollTop=1600;send('개념 학습게임:bubble');advance(40);assert.equal(scroller.scrollTop,1132);
  scroller.scrollTop=1450;send('개념 학습게임:bubble');advance(40);assert.equal(scroller.scrollTop,1450);
  send('개념 학습게임:maze');advance(40);assert.equal(scroller.scrollTop,1132);
});

test('missing panels time out instead of observing or scrolling forever',()=>{
  revealEntry(host,{selector:'.missing'});advance(80);assert.equal(frames.size,0);
});
