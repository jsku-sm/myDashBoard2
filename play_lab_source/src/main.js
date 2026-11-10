import './styles.css';
import './math-arcade.css';
import './vivid.css';
import { createMathArcade, GAMES, gameArt } from './math-arcade.js';
import { escapeHTML as esc } from './ui.js';

const root = document.getElementById('lab');
const post = (type, extra={}) => window.parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
let args=null, data=null, filter='all', query='', current='', arcade=null, state={}, height=0;
let pending=[], inFlight=null, saveTimer=null, saveError='', destination=null, storageKey='', sequences={};
const keys = new Set(GAMES.map(g=>g.id));
const makeId=()=>globalThis.crypto?.randomUUID?.() || `event-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const categories=[['all','전체'],['function','함수'],['sets','집합'],['logic','명제']];
function resize(){const n=Math.ceil(root.getBoundingClientRect().height)+8;if(n!==height){height=n;post('streamlit:setFrameHeight',{height:n});}}
function persist(){try{sessionStorage.setItem(storageKey,JSON.stringify({pending,sequences}));}catch{saveError='브라우저 임시 저장 공간이 부족해요. 저장 상태를 확인해 주세요.';}}
function status(){
 const label=document.getElementById('lab-save');if(!label)return;
 label.textContent=saveError || (inFlight?'기록 반영 중…':pending.length?`기록 ${pending.length}개 저장 대기`:(data?.preview?'교사 체험 기록':'학습 기록 반영됨'));
 label.classList.toggle('has-error',!!saveError);
 document.getElementById('lab-retry')?.toggleAttribute('hidden',!saveError);
}
function navigate(target){
 if(!['hub','avatar','quiz',...keys].includes(target))return;
 arcade?.unmount();
 if(pending.length||inFlight){destination=target;flush();status();return;}
 destination=null;
 post('streamlit:setComponentValue',{dataType:'json',value:{id:makeId(),action:'navigate',target}});
}
function flush(){
 clearTimeout(saveTimer);saveTimer=null;
 if(!data||inFlight||!pending.length){if(destination&&!inFlight&&!pending.length){const d=destination;destination=null;navigate(d);}return;}
 if(saveError)return;
 inFlight={id:makeId(),action:'record',revision:data.revision,events:pending.slice(0,40)};
 post('streamlit:setComponentValue',{dataType:'json',value:inFlight});status();
}
function onEvent(e){
 const seq=(sequences[e.runId]||0)+1;sequences[e.runId]=seq;
 pending.push({...e,seq,score:Math.max(0,e.score||0)});persist();
 if(!saveTimer)saveTimer=setTimeout(flush,['win','retry','leave','pause','clear'].includes(e.type)?180:6000);
 if(['win','retry','leave','pause','clear'].includes(e.type)){clearTimeout(saveTimer);saveTimer=setTimeout(flush,180);}
 status();
}
function restore(){
 storageKey=`goodmath-play-queue-v1:${data.userId}:${data.preview?'preview':'student'}`;
 try{const p=JSON.parse(sessionStorage.getItem(storageKey)||'{}');pending=Array.isArray(p.pending)?p.pending:[];sequences=p.sequences&&typeof p.sequences==='object'?p.sequences:{};}catch{pending=[];sequences={};}
}
function top(title='개념 학습게임',back=false){return `<div class="lab-top"><div class="lab-wordmark"><i>✦</i> GOOD MATH <b>PLAY!</b></div><div class="lab-tools">${back?'<button class="lab-back" data-home>← 모든 게임</button>':''}<span class="lab-user">${esc(data.name)}</span></div></div>${back?`<div class="lab-route"><span>개념 학습게임</span><b> / ${esc(title)}</b></div>`:''}`;}
function saving(){return `<div class="lab-savebar" role="status"><span class="lab-dot"></span><span id="lab-save"></span><button id="lab-retry" class="lab-back" data-retry hidden>다시 저장</button></div>`;}
function hero(){return `<section class="lab-hero"><div class="lab-hero-copy"><span class="lab-sticker">SMALL STEPS. BIG DISCOVERIES.</span><h1>오늘의 수학,<br><em>플레이해 볼까?</em></h1><p>취향대로 고르고, 직접 움직이고.<br>한 번 더 도전하는 순간에도 나는 성장 중!</p><div class="lab-hero-tags"><span>12가지 아케이드</span><span>5단계 개념퀴즈</span><span>나만의 아바타</span></div></div><div class="lab-hero-art" aria-hidden="true"><span class="lab-orbit">✳</span><div class="lab-planet"><b>f(x)</b><span>● &nbsp; ●</span><i>⌣</i></div><span class="lab-cube">√x</span><span class="lab-spark">✦</span><span class="lab-float-tag">LEVEL UP ↗</span></div></section>`;}
function featured(){return `<div class="lab-featured"><button class="lab-feature avatar-feature" data-open="avatar"><div><span class="lab-label">MY AVATAR QUEST</span><h2>풀고, 모으고,<br>내 캐릭터 꾸미기</h2><p>단원 선택 · 5문제 도전 · 별 조각 · 꾸미기</p><b class="lab-pill">나의 퀘스트 시작 ↗</b></div><div class="lab-avatar-art" aria-hidden="true"><i>✦</i><span>◕ ‿ ◕</span><b>★</b></div></button><button class="lab-feature quiz-feature" data-open="quiz"><div><span class="lab-label">CONCEPT QUEST · LEVEL 01—05</span><h2>개념 하나씩,<br>마스터까지!</h2><p>공통수학1·2 전 단원 · 5단계 · 나의 인증서</p><b class="lab-pill">단계별 개념퀴즈 ↗</b></div><div class="lab-quiz-art" aria-hidden="true"><b>01</b><b>02</b><b>03</b><b>04</b><b>★</b></div></button></div>`;}
function card(g,i){const r=data.games[g.id];return `<button class="lab-card tone-${i%6}" data-open="${g.id}"><div class="lab-card-art">${gameArt(g.id)}<span class="lab-card-tag">${esc(g.genre)}</span><span class="lab-card-go">↗</span></div><div class="lab-card-copy"><small>${esc(g.topic)}</small><h3>${esc(g.title)}</h3><p>${esc(g.desc)}</p><footer><b>${r?.wins?`✓ ${r.wins}회 완주`:r?.starts?'이어서 도전!':'LET’S PLAY'}</b><span>${r?.starts?`참여 ${r.starts}회`:'START →'}</span></footer></div></button>`;}
function cards(){const list=GAMES.filter(g=>(filter==='all'||(g.subject||'function')===filter)&&`${g.title} ${g.topic} ${g.genre}`.includes(query));return list.length?list.map(g=>card(g,GAMES.indexOf(g))).join(''):'<p class="lab-empty">찾는 게임이 없어요. 다른 단어나 단원을 선택해 보세요.</p>';}
function hub(){root.innerHTML=top()+hero()+featured()+`<section class="lab-library"><div class="lab-section-title"><div><span class="lab-label">PICK YOUR PLAY</span><h2>오늘의 게임을 골라봐!</h2></div><label class="lab-search"><span>⌕</span><input id="lab-search" placeholder="게임이나 개념 검색" aria-label="게임 검색" value="${esc(query)}"></label></div><nav class="lab-filters" aria-label="게임 단원">${categories.map(([id,label])=>`<button data-filter="${id}" aria-pressed="${filter===id}" class="${filter===id?'active':''}">${label}${id==='all'?' · 12':''}</button>`).join('')}</nav><div id="lab-cards" class="lab-grid">${cards()}</div></section>`+saving();status();resize();}
function render(){
 const key=`${data.userId}:${args.view}:${args.gameId||''}`;
 if(current===key){if(args.view==='hub')hub();status();return;}
 arcade?.unmount();arcade=null;current=key;
 if(args.view==='hub'){hub();return;}
 if(args.view==='header'){root.innerHTML=top(args.title,true);resize();return;}
 const game=GAMES.find(g=>g.id===args.gameId);if(!game){hub();return;}
 state={arcadeRecords:Object.fromEntries(Object.entries(data.games).map(([id,g])=>[id,{plays:g.starts,wins:g.wins,bestScore:g.best_score}]))};
 arcade=createMathArcade({state,save(){},onEvent});
 arcade.open(game.id);
 root.innerHTML=top(game.title,true)+`<section class="lab-arena">${arcade.html()}</section>`+saving();
 arcade.mount();status();resize();
}
root.addEventListener('click',e=>{
 const open=e.target.closest('[data-open]');if(open){navigate(open.dataset.open);return;}
 if(e.target.closest('[data-home]')){navigate('hub');return;}
 if(e.target.closest('[data-retry]')){saveError='';flush();status();return;}
 const f=e.target.closest('[data-filter]');if(f){filter=f.dataset.filter;hub();return;}
 const b=e.target.closest('[data-action]');if(!b||b.disabled)return;
 if(b.dataset.action==='arcade-lobby'){navigate('hub');return;}
 arcade?.action(b.dataset.action,b);
});
root.addEventListener('input',e=>{if(e.target.id==='lab-search'){query=e.target.value;document.getElementById('lab-cards').innerHTML=cards();resize();}});
window.addEventListener('message',e=>{
 if(e.source!==window.parent||e.data?.type!=='streamlit:render')return;
 const next=e.data.args;if(!next?.data)return;
 const changed=!data||data.userId!==next.data.userId||data.preview!==next.data.preview;
 if(changed){arcade?.unmount();current='';inFlight=null;destination=null;}
 args=next;data=args.data;
 if(changed)restore();
 if(inFlight&&args.ack===inFlight.id){pending.splice(0,inFlight.events.length);inFlight=null;saveError='';persist();}
 if(inFlight&&args.failed===inFlight.id){inFlight=null;saveError=args.error||'기록을 저장하지 못했어요. 다시 저장을 눌러 주세요.';}
 render();
 if(pending.length&&!saveError&&!inFlight&&!saveTimer)saveTimer=setTimeout(flush,250);
 if(destination&&!pending.length&&!inFlight){const d=destination;destination=null;navigate(d);}
});
window.addEventListener('pagehide',()=>{arcade?.unmount();persist();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){persist();flush();}});
new ResizeObserver(resize).observe(root);
post('streamlit:componentReady',{apiVersion:1});
root.innerHTML='<div class="lab-loading"><span>✦</span> 플레이할 준비를 하고 있어요!</div>';resize();
