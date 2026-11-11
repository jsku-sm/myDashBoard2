import katex from 'katex';
import {step,HZ} from './simulation.js';
import {paint} from './paint.js';
import './style.css';

const root=document.querySelector('#app');
let view=null,pending=null,game=null,lastRender='',lastReceive=performance.now(),serverBase=0,clockBase=0,sound=false,audio=null;
let keys=0,touchKeys=0,keyboardKeys=0,chosen='',lastError='',lastPost=0;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function math(value){
  return String(value??'').split(/(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g).map(s=>{
    if(!s.startsWith('$')||!s.endsWith('$'))return esc(s).replace(/\n/g,'<br>');
    const display=s.startsWith('$$'),expr=s.slice(display?2:1,display?-2:-1);
    try{return katex.renderToString(expr,{displayMode:display,throwOnError:true,trust:false,strict:'ignore'});}catch{return esc(s);}
  }).join('');
}
function post(type,data={}){window.parent.postMessage({isStreamlitMessage:true,type,...data},'*');}
function send(action,extra={}){
  if(pending)return;
  pending={id:crypto.randomUUID(),action,...extra};lastPost=performance.now();
  post('streamlit:setComponentValue',{value:pending});setBusy();
}
function setBusy(){root.querySelectorAll('[data-act]').forEach(b=>b.disabled=!!pending||(b.dataset.act==='answer'&&!!view?.feedback?.correct));}
const now=()=>serverBase+(performance.now()-clockBase)/1000;
const remaining=()=>view?.ends_at?Math.max(0,view.ends_at-now()):view?.duration??0;
const timeText=n=>{const t=Math.ceil(Math.max(0,n));return `${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toString().padStart(2,'0')}`;};
const button=(label,act,cls='primary',attrs='')=>`<button class="${cls}" data-act="${act}" ${attrs}>${label}</button>`;
const stat=(label,value)=>`<div class="stat"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
function beep(win=true){if(!sound)return;try{audio??=new(window.AudioContext||window.webkitAudioContext)();audio.resume();const o=audio.createOscillator(),v=audio.createGain();o.type='triangle';o.frequency.value=win?660:220;v.gain.setValueAtTime(.055,audio.currentTime);v.gain.exponentialRampToValueAtTime(.001,audio.currentTime+.16);o.connect(v).connect(audio.destination);o.start();o.stop(audio.currentTime+.17);}catch{sound=false;}}
function cards(play=false){return `<div class="grid">${Object.entries(view.games).map(([id,g])=>`<button class="game-card ${chosen===id?'selected':''}" style="background:${g.color}" ${play?'data-select':'data-act'}="${play?id:'play'}" data-game="${id}"><i>${g.icon}</i><span><b>${esc(g.title)}</b><small>${esc(g.help)}</small>${view.personal_best?`<small>나의 최고 기록 ${view.personal_best[id]||0}점</small>`:''}</span></button>`).join('')}</div>`;}
function ranking(){return `<div class="panel dark"><span class="eyebrow">90 SECOND BEST</span><h2>우리 반 순위</h2><p style="color:#bdb5d6;font-size:13px">90초 한 판 최고 점수 · 동점은 같은 순위</p>${view.leaderboard.length?view.leaderboard.map(r=>`<div class="rank-row"><span class="place">${r.rank}</span><span>${esc(r.alias)}${r.alias===view.alias?' · 나':''}</span><b>${r.score}점</b></div>`).join(''):'<p class="empty">첫 90초 기록을 기다리고 있어요.</p>'}</div>`;}
function coop(){const n=Math.min(100,view.goal?view.contribution/view.goal*100:0);return `<div class="panel dark"><span class="eyebrow">ONE CLASS, ONE MISSION</span><h2>${n>=100?'함께 해냈어요! ✦':'우리 반 에너지 충전'}</h2><p style="margin-top:10px">${view.contribution.toLocaleString()} / ${view.goal.toLocaleString()}점</p><div class="meter" role="progressbar" aria-label="학급 목표" aria-valuenow="${Math.floor(n)}" aria-valuemin="0" aria-valuemax="100"><div style="width:${n}%"></div></div><p style="color:#cfc7e6;font-size:14px">각자의 게임 점수가 우리 반의 힘!<br>활동 종료 후 목표를 달성하면 모두 별 조각 5개와 협동 배지를 받아요.</p></div>`;}
function sidebar(){return view.mode==='rank'?ranking():view.mode==='coop'?coop():`<div class="panel dark"><span class="eyebrow">MY NEXT LEVEL</span><h2>어제의 나를 넘어서!</h2><p style="margin-top:14px;color:#d5cdea">게임마다 나의 최고 기록을 남겨요. 모은 별 조각으로 기존 아바타를 꾸밀 수 있어요.</p></div>`;}
function lobby(){return `<div class="split"><div class="panel lime"><span class="eyebrow">READY, CLASS?</span><h2>${view.role==='teacher'?'참여코드를 보여 주세요':'입장 완료! 곧 시작해요'}</h2><div class="code">${esc(view.code)}</div><p>${esc(view.title)}</p><p><b>${view.games[view.game].icon} ${esc(view.games[view.game].title)}</b> · ${esc(view.modes[view.mode])}</p><div class="stats">${stat('입장한 학생',view.participants+'명')}${stat('활동 시간',view.duration/60+'분')}</div>${view.role==='teacher'?button('모두 준비됐나요? 활동 시작','start'): `<p><b>${esc(view.alias)}</b> · 선생님이 시작하면 문제가 열려요.</p>`}</div><div class="panel"><h2>오늘의 플레이 규칙</h2><div class="splash-icon">🧠 → 🎮</div><p>서로 다른 <b>3문제</b>를 맞히면 <b>90초</b> 게임!<br>힌트를 사용해도 정답으로 인정해요.<br>틀려도 지금까지 맞힌 개수는 유지돼요.</p><p class="footer-note">게임 점수는 별 조각과 배지로 바뀌어요.<br>게임 중 화면을 벗어나도 시간은 계속 흘러요.</p></div></div>${view.role==='teacher'?studentTable():''}`;}
function studentTable(){return `<div class="panel"><h2>우리 반 진행 상황</h2><div class="table-wrap"><table><thead><tr><th>학생</th><th>정답</th><th>다시 도전</th><th>힌트</th><th>게임</th><th>최고 점수</th><th>별 조각</th><th>현재</th></tr></thead><tbody>${view.students.map(s=>`<tr><td>${esc(s.class_name)} · ${esc(s.student_id)} ${esc(s.name)}<br><small>${esc(s.alias)}</small></td><td>${s.correct}</td><td>${s.wrong}</td><td>${s.hints}</td><td>${s.games}</td><td>${s.best}</td><td>${s.coins}</td><td>${esc(s.phase)}</td></tr>`).join('')}</tbody></table></div>${!view.students.length?'<div class="empty">학생이 참여코드를 입력하면 여기에 보여요.</div>':''}</div>`;}
function teacher(){const correct=view.students.reduce((v,s)=>v+s.correct,0);return `<div class="stats">${stat('참여한 학생',view.participants+'명')}${stat('함께 맞힌 문제',correct+'개')}${stat('게임 종류',view.games[view.game].title)}${stat('참여코드',view.code)}</div><div class="actions" style="margin:0 0 22px">${view.status==='running'?button('활동 종료','end',''):''}<p class="subtle">수학 정답과 게임 점수는 따로 기록합니다.</p></div><div class="split"><div>${studentTable()}</div><div>${sidebar()}</div></div>`;}
function resultCards(){const r=view.runs?.at(-1);return r?`<div class="panel pink"><span class="eyebrow">NICE PLAY!</span><h2>${view.games[r.game].icon} ${esc(view.games[r.game].title)}</h2><div class="results" style="margin-top:16px"><div class="result">게임 점수<b>${r.score}</b></div><div class="result">별 조각 획득<b>+${r.coins} ✦</b></div><div class="result">최고 연속 성공<b>${r.combo}</b></div></div>${r.badge?'<p style="margin-top:16px"><b>마스터 배지 획득!</b> 이 게임의 골드 캐릭터 색을 사용할 수 있어요.</p>':''}${!r.ranked?'<p class="footer-note">수업 종료에 맞춘 짧은 판 · 보상과 개인 활동에 기록하고 순위에서는 제외해요.</p>':''}</div>`:'';}
function student(){
  if(view.status==='ended')return `${resultCards()}<div class="panel lime"><span class="eyebrow">TODAY, YOU GREW!</span><h2>오늘의 도전 완료!</h2><div class="stats">${stat('맞힌 문제',view.correct)}${stat('다시 도전',view.wrong)}${stat('게임 횟수',view.runs.length)}${stat('내 별 조각',view.coins)}</div><p>${view.settling?'마지막 게임 기록을 마무리하고 있어요. 잠시 기다려 주세요.':'성장 기록에 반영했어요. 다음 단원에서도 함께 도전해요!'}</p><div class="badges">${view.badges.map(id=>id==='coop'?'🤝':view.games[id]?.icon||'').join(' ')}</div><p class="footer-note">기존 ‘개념 학습게임 → 아바타 퀘스트’에서 별 조각으로 꾸밀 수 있어요.</p></div>${sidebar()}`;
  const count=view.correct%3;
  let body='';
  if(view.ticket){
    chosen=view.mode==='solo'?(chosen||view.game):view.game;
    body=`${resultCards()}<div class="panel lime"><span class="eyebrow">YOU EARNED IT!</span><h2>3문제 성공! 게임 문이 열렸어요.</h2><p style="margin-top:12px">${remaining()<90?`남은 활동 시간 <b>${Math.ceil(remaining())}초</b> 동안 플레이해요. 이번 판은 순위에 포함하지 않아요.`:'준비되면 시작해요. 시작 버튼을 누르면 90초가 흘러요.'}</p></div>${view.mode==='solo'?cards(true):`<div class="panel"><h2>${view.games[chosen].icon} ${esc(view.games[chosen].title)}</h2><p>${esc(view.games[chosen].help)}</p></div>`}<div class="actions">${button('90초 게임 시작 →','play','primary',`data-game="${chosen}"`)}</div>`;
  }else if(view.question){
    const q=view.question,f=view.feedback;
    body=`<div class="panel"><div style="display:flex;justify-content:space-between;gap:10px"><span class="tag">${esc(q.topic_title)}</span><span class="tag">${view.index+1} / ${view.question_count}</span></div><div class="question">${math(q.prompt)}</div><div class="options">${q.options.map((o,i)=>button(`<span class="num">${i+1}</span><span>${math(o)}</span>`,'answer',`option ${f?.choice===i?'chosen':''}`,`data-choice="${i}" ${f?.correct?'disabled':''}`)).join('')}</div>${f?`<div class="feedback ${f.correct?'good':''}" role="status">${f.correct?'✦ 정답이에요!<br>':''}${math(f.message)}</div>`:''}${q.hint?`<div class="hint">💡 ${math(q.hint)}</div>`:''}<div class="actions">${f?.correct?button(view.correct%3===0?'게임 고르기 →':'다음 문제 →','next'):button(q.hint?'힌트 확인했어요':'힌트 보기 · 정답 인정','hint','')}</div></div>`;
    const r=view.runs.at(-1);
    if(r&&view.index%3===0)body=`<div class="banner" role="status"><b>✦ 방금 ${r.score}점 · 별 조각 +${r.coins}개!</b>${r.badge?' 마스터 배지도 획득했어요!':''}<br>다음 3문제로 새 게임에 도전해요.</div>`+body;
  }else body=`${resultCards()}<div class="panel lime"><h2>선생님이 준비한 문제를 모두 해결했어요!</h2><p style="margin-top:12px">다른 친구들을 응원하며 활동 결과를 기다려요.</p></div>`;
  return `<div class="stats">${stat('누적 정답',view.correct+'개')}${stat('다음 게임까지',view.ticket?'입장 가능':(3-count)+'문제')}${stat('내 별 조각',view.coins+'개')}${stat('나의 번호',view.alias)}</div><div class="split"><div>${body}</div><div>${sidebar()}<div class="panel"><h3>힌트도 배움이에요 💡</h3><p class="subtle" style="margin-top:12px">틀렸다면 힌트를 보고 다시 도전해요. 정답을 맞히면 게임 입장에 똑같이 인정해요.</p></div></div></div>`;
}
function gameHtml(run){return `<div class="split"><div><div class="arena"><div class="hud"><div>${view.games[run.game].icon} <b>${esc(view.games[run.game].title)}</b><br><strong id="score">0점</strong> <span id="combo"></span></div><div class="clock" id="gameclock">90</div></div><canvas id="gamecanvas" width="720" height="430" tabindex="0" aria-label="${esc(view.games[run.game].title)} 게임. ${esc(view.games[run.game].help)}"></canvas><div class="controls"><div class="direction"><button class="control" data-key="1" aria-label="왼쪽">←</button><button class="control" data-key="2" aria-label="오른쪽">→</button></div>${run.game==='jump'?'<button class="control jump" data-key="4">점프 ↑</button>':run.game==='maze'?'<div class="direction"><button class="control" data-key="4" aria-label="위">↑</button><button class="control" data-key="8" aria-label="아래">↓</button></div>':''}</div><p class="game-help">${esc(view.games[run.game].help)}</p><p class="game-help">화면을 벗어나도 시간은 흘러요. 같은 입력은 한 번만 기록해요.</p><div id="finish-status"></div></div></div><aside><div id="live-side">${sidebar()}</div><div class="panel"><h3>나의 기록</h3><p style="margin-top:10px">최고 <b>${view.personal_best[run.game]||0}점</b></p><p class="subtle">잘할수록 별 조각을 더 모아요.<br>${view.games[run.game].medal}점 달성 시 마스터 배지!</p>${view.badges.includes(run.game)?'<p>🏅 골드 캐릭터 색 적용 중</p>':''}</div></aside></div>`;}
function render(force=false){
  if(!view)return;
  if(game&&view.run?.id===game.id&&!force){document.querySelector('#live-side').innerHTML=sidebar();setBusy();return;}
  const {server_time,...stable}=view;
  const fingerprint=JSON.stringify([stable,!!pending,lastError]);if(!force&&fingerprint===lastRender){setBusy();return;}lastRender=fingerprint;
  const focused=document.activeElement?.closest('[data-act]');
  const focusSelector=focused?`[data-act="${focused.dataset.act}"]${focused.dataset.choice!==undefined?`[data-choice="${focused.dataset.choice}"]`:''}`:null;
  const inGame=!!view.run;
  root.innerHTML=`<main class="shell"><header class="head"><div><div class="eyebrow">GOOD MATH · AFTER CLASS ARCADE</div><h1>${view.role==='teacher'?'우리 반 플레이 보드':'3문제, 그다음은 PLAY!'}</h1><p>${esc(view.title)} · ${esc(view.modes[view.mode])}</p></div><div class="timer" id="roomclock"><span>남은 활동 시간</span>${timeText(remaining())}</div></header><div id="error" class="banner error" role="alert">${esc(lastError)}</div><div id="net" class="banner" role="status"></div><div style="display:flex;gap:8px;justify-content:flex-end;margin-bottom:14px"><button class="sound" data-util="sound">${sound?'♪ 효과음 켜짐':'♪ 효과음 꺼짐'}</button><button class="sound" data-util="full">⛶ 전체화면</button></div>${view.status==='lobby'?lobby():view.role==='teacher'?teacher():inGame?gameHtml(view.run):student()}<p class="footer-note">정답은 쌓이고, 도전은 계속! · 게임 보상은 아바타 꾸미기에 사용해요.</p></main>`;
  setBusy();if(view.feedback?.correct)root.querySelectorAll('[data-act="answer"]').forEach(b=>b.disabled=true);
  if(focusSelector)root.querySelector(focusSelector)?.focus({preventScroll:true});
  if(inGame&&view.role==='student')mountGame(view.run);
  else if(game){try{sessionStorage.removeItem('reward-run-'+game.id);}catch{}game=null;keys=0;keyboardKeys=0;touchKeys=0;}
  height();
}
function height(){post('streamlit:setFrameHeight',{height:Math.ceil(document.documentElement.scrollHeight)});}
new ResizeObserver(height).observe(root);
function persist(){if(!game)return;try{sessionStorage.setItem('reward-run-'+game.id,JSON.stringify(game.inputs));}catch{}}
function mountGame(run){
  if(game?.id===run.id)return;
  let inputs=Array(run.sim.t).fill(0),state=structuredClone(run.sim);
  try{const cache=JSON.parse(sessionStorage.getItem('reward-run-'+run.id)||'null');if(Array.isArray(cache)&&cache.length<=1800&&cache.every(k=>Number.isInteger(k)&&k>=0&&k<=15)&&cache.length>=run.sim.t){inputs=cache;for(const k of inputs.slice(run.sim.t))step(state,k);}}catch{}
  game={id:run.id,state,inputs,confirmed:run.sim.t,start:run.start,until:run.until,lastSync:performance.now(),finalSent:false};
  keys=0;keyboardKeys=0;touchKeys=0;paint(document.querySelector('#gamecanvas'),state,view.badges.includes(run.game));
  document.querySelector('#gamecanvas')?.focus({preventScroll:true});
}
function progress(final=false){
  if(!game||pending||game.finalSent)return;
  if(!final&&game.state.t<=game.confirmed)return;
  const inputs=game.inputs.slice(game.confirmed,game.state.t);
  send('progress',{run:game.id,start:game.confirmed,inputs,final});game.lastSync=performance.now();if(final)game.finalSent=true;persist();
}
function tick(){
  if(view){const clock=root.querySelector('#roomclock');if(clock)clock.innerHTML=`<span>남은 활동 시간</span>${timeText(remaining())}`;
    if(view.ticket&&view.status==='running'){const b=root.querySelector('[data-act="play"]');if(b){b.textContent=`${Math.min(90,Math.ceil(remaining()))}초 게임 시작 →`;b.disabled=!!pending||remaining()<1;}
      const panel=root.querySelector('.panel.lime p');if(panel)panel.innerHTML=remaining()<90?`남은 활동 시간 <b>${Math.ceil(remaining())}초</b> 동안 플레이해요. 이번 판은 순위에 포함하지 않아요.`:'준비되면 시작해요. 시작 버튼을 누르면 90초가 흘러요.';
    }
    const net=root.querySelector('#net');if(net)net.textContent=performance.now()-lastReceive>8000?'연결을 확인하고 있어요. 최근 조작은 이 기기에 임시 보관하고, 다시 연결되면 전송합니다.':'';
    if(pending&&performance.now()-lastPost>6000){post('streamlit:setComponentValue',{value:{...pending,retry:Date.now()}});lastPost=performance.now();}
  }
  if(game&&view?.run?.id===game.id){
    const before=game.state.score,target=Math.min(1800,Math.floor(Math.max(0,Math.min(now()-.25,game.until)-game.start)*HZ));
    let steps=0;
    while(game.state.t<target&&steps<1800){const input=document.hidden?0:keys;game.inputs.push(input);step(game.state,input);steps++;}
    if(game.state.score>before)beep();
    const canvas=root.querySelector('#gamecanvas');if(canvas)paint(canvas,game.state,view.badges.includes(game.state.game));
    const score=root.querySelector('#score'),combo=root.querySelector('#combo'),clock=root.querySelector('#gameclock');
    if(score)score.textContent=game.state.score+'점';if(combo)combo.textContent=game.state.combo>=3?game.state.combo+' COMBO!':'';
    const left=Math.max(0,game.until-now());if(clock){clock.textContent=Math.ceil(left)+'초';clock.classList.toggle('time-low',left<=10);}
    if(now()>=game.until+.35){const status=root.querySelector('#finish-status');if(status)status.innerHTML='<div class="finish-banner">이번 도전 완료! 기록을 반영하고 있어요.</div>';progress(true);}
    else if(performance.now()-game.lastSync>4000)progress(false);
  }
  requestAnimationFrame(tick);
}
window.addEventListener('message',event=>{
  if(event.source!==window.parent||event.data?.type!=='streamlit:render')return;
  const args=event.data.args||{},next=args.view;if(!next)return;
  const old=view;view=next;lastReceive=performance.now();serverBase=view.server_time;clockBase=performance.now();
  const acked=pending&&args.ack===pending.id;
  if(acked){const was=pending;pending=null;lastError=args.error||'';if(was.action==='answer')beep(!!view.feedback?.correct);
    if(lastError&&game&&view.run?.id===game.id){game.state=structuredClone(view.run.sim);game.inputs=game.inputs.slice(0,view.run.sim.t);game.confirmed=view.run.sim.t;game.finalSent=false;persist();}
  }
  if(game&&view.run?.id===game.id){game.confirmed=view.run.sim.t;game.until=view.run.until;if(game.state.t<view.run.sim.t){game.state=structuredClone(view.run.sim);while(game.inputs.length<game.state.t)game.inputs.push(0);}}
  const changed=old?.run?.id!==view.run?.id;
  render(changed);
  const error=root.querySelector('#error');if(error)error.textContent=lastError;
});
root.addEventListener('click',e=>{
  const util=e.target.closest('[data-util]');if(util){if(util.dataset.util==='sound'){sound=!sound;util.textContent=sound?'♪ 효과음 켜짐':'♪ 효과음 꺼짐';beep();}else{const shell=root.querySelector('.shell');if(document.fullscreenElement)document.exitFullscreen?.();else shell.requestFullscreen?.().catch(()=>{lastError='이 브라우저에서는 전체화면이 제한돼요. 넓은 화면이나 가로 모드로 플레이해 주세요.';root.querySelector('#error').textContent=lastError;});}return;}
  const select=e.target.closest('[data-select]');if(select){chosen=select.dataset.select;render(true);return;}
  const b=e.target.closest('[data-act]');if(!b||b.disabled)return;
  const action=b.dataset.act;
  if(action==='end'&&!window.confirm('활동을 종료하고 현재 기록을 저장할까요?'))return;
  if(action==='answer')send(action,{index:view.index,turn:view.turn,choice:Number(b.dataset.choice)});
  else if(action==='hint'||action==='next')send(action,{index:view.index,turn:view.turn});
  else if(action==='play')send(action,{game:b.dataset.game||chosen||view.game});
  else send(action);
});
const held=new Map();
root.addEventListener('pointerdown',e=>{const b=e.target.closest('[data-key]');if(!b||!game)return;e.preventDefault();b.setPointerCapture?.(e.pointerId);held.set(e.pointerId,{key:Number(b.dataset.key),button:b});b.classList.add('held');updateTouch();});
function release(e){const item=held.get(e.pointerId);if(item){item.button.classList.remove('held');held.delete(e.pointerId);updateTouch();}}
function updateTouch(){touchKeys=0;for(const item of held.values())touchKeys|=item.key;keys=touchKeys|keyboardKeys;}
root.addEventListener('pointerup',release);root.addEventListener('pointercancel',release);root.addEventListener('lostpointercapture',release);
const keymap={ArrowLeft:1,a:1,A:1,ArrowRight:2,d:2,D:2,ArrowUp:4,w:4,W:4,' ':4,ArrowDown:8,s:8,S:8};
window.addEventListener('keydown',e=>{if(!game||!keymap[e.key]||e.target.matches('input,textarea,select'))return;e.preventDefault();keyboardKeys|=keymap[e.key];keys=keyboardKeys|touchKeys;});
window.addEventListener('keyup',e=>{if(keymap[e.key]){keyboardKeys&=~keymap[e.key];keys=keyboardKeys|touchKeys;}});
function clearInput(){keyboardKeys=0;touchKeys=0;keys=0;for(const {button}of held.values())button.classList.remove('held');held.clear();persist();}
window.addEventListener('blur',clearInput);document.addEventListener('visibilitychange',()=>{clearInput();if(document.hidden)progress(false);});window.addEventListener('pagehide',clearInput);
post('streamlit:componentReady',{apiVersion:1});post('streamlit:setFrameHeight',{height:650});requestAnimationFrame(tick);
