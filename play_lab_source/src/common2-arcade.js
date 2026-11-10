import katex from 'katex';
import 'katex/dist/katex.min.css';
import './common2-arcade.css';
import {escapeHTML as esc} from './ui.js';
import {COMMON2_GAMES,mission,initialInput,accepts,transform,point,factoryValue} from './common2-data.js';
import {createArcadeAudio} from './arcade-audio.js';

export function mathText(value){return String(value).split(/(\$[^$]+\$)/g).map(t=>t.startsWith('$')&&t.endsWith('$')?katex.renderToString(t.slice(1,-1),{throwOnError:false,trust:false,strict:'ignore'}):esc(t)).join('');}
const clamp=n=>Math.max(-6,Math.min(6,n));
const X=x=>280+x*32,Y=y=>230-y*32;
const txt=(x,y,text,cls='')=>`<text x="${x}" y="${y}" class="${cls}" text-anchor="middle">${esc(text)}</text>`;
const dot=(p,label,cls='c2-target')=>`<g class="${cls}"><circle cx="${X(p[0])}" cy="${Y(p[1])}" r="7"/>${txt(X(p[0])+14,Y(p[1])-13,label)}</g>`;
const segment=(a,b,cls)=>`<line class="${cls}" x1="${X(a[0])}" y1="${Y(a[1])}" x2="${X(b[0])}" y2="${Y(b[1])}"/>`;
function infiniteLine([a,b,c],cls){return b?segment([-12,(-c+12*a)/b],[12,(-c-12*a)/b],cls):segment([-c/a,-12],[-c/a,12],cls);}
function axes(){let out='';for(let i=-6;i<=6;i++){out+=`<path class="${i?'c2-grid':'c2-axis'}" d="M88 ${Y(i)}H472M${X(i)} 38V422"/>`;if(i)out+=txt(X(i),Y(0)+18,i)+txt(X(0)-15,Y(i)+5,i);}return out+txt(486,248,'x')+txt(265,24,'y')+txt(267,248,'0');}
const B=(label,action,attrs='',cls='')=>`<button type="button" data-c2-action="${action}" ${attrs} class="${cls}">${label}</button>`;

export function createCommon2Arcade(api){
 let g,s,q,input,root=null,controller=null,raf=0,last=0,pointer=false;
 const audio=createArcadeAudio({onChange:()=>soundUI()});
 function fresh(id,mode='relaxed'){
  g=COMMON2_GAMES.find(row=>row.id===id);if(!g)throw Error('Unknown game');
  const seed=crypto.getRandomValues(new Uint32Array(1))[0];
  s={id,seed,runId:crypto.randomUUID(),mode,index:0,score:0,correct:0,errors:0,seconds:0,phase:'ready',started:false,finished:false,detached:false,hint:false,endpoint:0,drop:0,message:'조작법을 확인하고 출발하세요!'};
  loadMission();
 }
 function loadMission(){q=mission(g.id,stage(),(s.seed+Math.imul(s.index+1,2654435761))>>>0);input=initialInput(q);s.hint=false;s.endpoint=0;s.drop=0;}
 const stage=()=>Math.min(3,Math.floor(s.index/3)+1);
 const active=()=>s.phase==='playing';
 function report(type,message=''){
  if(!s.started&&type!=='start')return;
  api.onEvent?.({game:g.id,runId:s.runId,type,elapsed:s.seconds,stage:stage(),stageCount:3,mode:s.mode,score:s.score,skill:g.topic,question:q.prompt,message});
 }
 function soundUI(){if(!root)return;for(const channel of ['music','effects']){const b=root.querySelector(`[data-channel="${channel}"]`);if(b){b.textContent=`${channel==='music'?'♫ 음악':'♪ 효과음'} ${audio.settings[channel]?'켜짐':'꺼짐'}`;b.setAttribute('aria-pressed',String(audio.settings[channel]));b.disabled=!audio.status.supported;}}}
 function setPhase(phase){s.phase=phase;audio.setScene(g.id,phase==='playing'?'playing':'paused');}
 function feedback(message){s.message=message;const box=root?.querySelector('[data-feedback]');if(box)box.innerHTML=mathText(message);}
 function scene(){
  if(g.id==='venn-catcher'){
   const labels=['A만','A와 B 모두','B만','어느 쪽도 아님'];
   return `<div class="c2-catcher"><div class="c2-set-info"><span>A = {${q.A.join(', ')}}</span><span>B = {${q.B.join(', ')}}</span><small>${esc(q.condition)}</small></div><div class="c2-lanes">${labels.map((label,i)=>`<div class="c2-lane ${input.lane===i?'chosen':''}"><b>${label}</b><small>${mathText(['$A-B$','$A\\cap B$','$B-A$','$(A\\cup B)^c$'][i])}</small><span class="c2-landing">${input.lane===i?'🧺':'·'}</span></div>`).join('')}<div class="c2-capsule" style="--lane:${input.lane}">${q.value}</div></div><p>${s.mode==='challenge'?'8초 안에 바구니를 옮겨요. 준비되면 바로 받을 수도 있어요.':'시간 제한 없이 생각하고 ‘캡슐 받기’를 눌러요.'}</p></div>`;
  }
  if(g.id==='logic-bridge'){
   const cards=q.stage===3?(input.value===null?[]:[`x=${input.value}`]):input.bridge.map(i=>q.cards[i]);
   return `<div class="c2-bridge-scene"><span class="c2-cloud">☁</span><div class="c2-bridge"><span class="c2-island">출발<br>🚶</span>${[0,1].map((_,i)=>`<div class="c2-plank ${cards[i]?'filled':''}">${cards[i]?mathText('$'+cards[i]+'$'):q.stage===3&&i===1?'반례 발견':i===0?'가정':'결론'}</div>`).join('<b class="c2-arrow">→</b>')}<span class="c2-island">도착<br>⚑</span></div><p>조건을 연결해 끊어진 길을 열어요.</p></div>`;
  }
  if(g.id==='function-factory'){
   let v=input.input;const steps=input.order.map(id=>{v=q.machines[id][0]*v+q.machines[id][1];return [id,v];});
   return `<div class="c2-factory-scene"><span class="c2-factory-tag">FUNCTION ASSEMBLY LINE</span><div class="c2-belt"><div class="c2-product"><small>입력</small><b>${input.input}</b></div>${steps.map(([id,out])=>`<span>→</span><div class="c2-machine"><b>${id}</b><small>처리 후 ${out}</small></div>`).join('')}${!steps.length?'<div class="c2-empty-slot">함수 기계를 놓아 주세요</div>':''}<span>→</span><div class="c2-product final"><small>목표 출력</small><b>${q.target}</b></div></div><div class="c2-belt-track">▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰</div><p>왼쪽 기계부터 지나가요. 입력과 출력의 변화를 살펴봐요.</p></div>`;
  }
  let shapes='';
  if(g.id==='coordinate-drone'){
   shapes+=dot(q.A,'A'+point(q.A));if(q.B)shapes+=segment(q.A,q.B,'c2-reference')+dot(q.B,'B'+point(q.B));
   if(q.stations)shapes+=q.stations.map((p,i)=>dot(p,String(i+1)+':'+point(p),'c2-station')).join('');
   shapes+=`<g class="c2-ship">${txt(X(input.cursor[0]),Y(input.cursor[1])+8,'✈')}</g>`;
  }
  if(g.id==='line-rail'){
   if(q.stage>1)shapes+=infiniteLine(q.reference,'c2-reference');
   shapes+=dot(q.P,'P'+point(q.P));if(q.stage===1)shapes+=dot(q.Q,'Q'+point(q.Q));
   const [a,b]=input.rail;if(a[0]!==b[0]||a[1]!==b[1]){const A=b[1]-a[1],B=a[0]-b[0],C=b[0]*a[1]-a[0]*b[1];shapes+=infiniteLine([A,B,C],'c2-rail');}
   shapes+=input.rail.map((p,i)=>dot(p,`조절점 ${i+1}`,'c2-handle')).join('');
   shapes+=`<circle class="c2-train" cx="${X(a[0])}" cy="${Y(a[1])}" r="10" style="--dx:${(b[0]-a[0])*32}px;--dy:${-(b[1]-a[1])*32}px"/>`;
  }
  if(g.id==='circle-radar'){
   shapes+=`<circle class="c2-radar" cx="${X(input.center[0])}" cy="${Y(input.center[1])}" r="${input.radius*32}"/>`+dot(input.center,'내 중심','c2-handle');
   if(q.stage===2)shapes+=dot(q.P,'P'+point(q.P));if(q.stage===3)shapes+=infiniteLine(q.line,'c2-reference');
  }
  if(g.id==='move-portal'){
   const polygon=(pts,cls)=>`<polygon class="${cls}" points="${pts.map(([x,y])=>`${X(x)},${Y(y)}`).join(' ')}"/>`;
   shapes+=polygon(q.target,'c2-ghost')+polygon(input.shape,'c2-craft');
   shapes+=input.shape.map((p,i)=>dot(p,['A','B','C'][i],'c2-handle')).join('');
  }
  if(g.id==='graph-rider'){
   if(q.family==='rational')shapes+=segment([q.h,-6],[q.h,6],'c2-danger')+segment([-6,q.k],[6,q.k],'c2-reference');
   else shapes+=dot([q.h,q.k],'시작점','c2-station');
   shapes+=segment([q.x,-6],[q.x,6],'c2-gate')+txt(X(q.x),26,`이번 관문 x=${q.x}`)+`<g class="c2-ship">${txt(X(q.x),Y(input.y)+9,'➤')}</g>`;
   if(['feedback','won'].includes(s.phase)&&q.answer!==null)shapes+=dot([q.x,q.answer],'✓','c2-target');
  }
  return `<svg viewBox="0 0 560 460" role="img" aria-label="${esc(g.title)} 좌표판. x와 y는 -6부터 6까지." class="c2-coordinate"><defs><clipPath id="c2-clip"><rect x="75" y="10" width="430" height="430"/></clipPath></defs>${axes()}<g clip-path="url(#c2-clip)">${shapes}</g></svg>`;
 }
 function adjust(field,value,min=-6,max=6,label=field){return `<div class="c2-adjust"><span>${esc(label)}</span>${B('−','adjust',`data-field="${field}" data-delta="-1" aria-label="${esc(label)} 줄이기"`)}<output data-value="${field}">${value}</output>${B('+','adjust',`data-field="${field}" data-delta="1" aria-label="${esc(label)} 늘리기"`)}</div>`;}
 function directions(){return `<div class="c2-dpad">${[['up','↑'],['left','←'],['down','↓'],['right','→']].map(([dir,label])=>B(label,'move',`data-dir="${dir}" aria-label="${dir} 이동"`)).join('')}</div>`;}
 function controls(){
  if(g.id==='coordinate-drone')return directions()+`<p data-coordinate>현재 ${point(input.cursor)}</p>`;
  if(g.id==='line-rail')return `<div class="c2-picks">${[0,1].map(i=>B(`조절점 ${i+1}`,'endpoint',`data-value="${i}" aria-pressed="${s.endpoint===i}"`)).join('')}</div><p>선택한 조절점을 좌표판에서 옮겨요.</p>`+adjust('railX',input.rail[s.endpoint][0],-6,6,'x')+adjust('railY',input.rail[s.endpoint][1],-6,6,'y');
  if(g.id==='circle-radar')return adjust('centerX',input.center[0],-6,6,'중심 x')+adjust('centerY',input.center[1],-6,6,'중심 y')+adjust('radius',input.radius,1,6,'반지름 r');
  if(g.id==='move-portal')return directions()+`<div class="c2-reflections">${[['x','x축 대칭'],['y','y축 대칭'],['origin','원점 대칭'],['swap','y=x 대칭']].map(([op,label])=>B(label,'reflect',`data-op="${op}"`)).join('')}</div>`;
  if(g.id==='venn-catcher')return `<div class="c2-picks">${['A만','둘 다','B만','둘 다 아님'].map((v,i)=>B(v,'lane',`data-value="${i}" aria-pressed="${i===input.lane}"`)).join('')}</div>`;
  if(g.id==='logic-bridge')return `<div class="c2-picks">${q.stage===3?q.values.map(v=>B(mathText('$x='+v+'$'),'counter',`data-value="${v}" aria-pressed="${input.value===v}"`)).join(''):q.cards.map((v,i)=>B(mathText('$'+v+'$'),'condition',`data-value="${i}" aria-pressed="${input.bridge.includes(i)}"`)).join('')}</div><p>${q.stage===3?'가정은 참, 결론은 거짓인 발판을 골라요.':'앞 조건 → 뒤 조건 순서로 두 블록을 골라요.'}</p>`;
  if(g.id==='function-factory')return `<div class="c2-picks">${['f','g'].map(id=>B(`${id} 기계`,'machine',`data-id="${id}"`)).join('')}</div>`+adjust('input',input.input,-6,6,'입력 x')+'<p>기계를 바꾸려면 ‘배치 초기화’를 눌러요.</p>';
  return adjust('y',input.y,-6,6,'라이더 높이 y')+B('이 x에서는 통과 불가','undefined','','c2-domain');
 }
 function submitLabel(){return {'coordinate-drone':'배송 확인 ✈','line-rail':'열차 출발 →','circle-radar':'레이더 스캔 ◎','move-portal':'포털 통과 ◇','venn-catcher':'캡슐 받기 ↓','logic-bridge':'다리 건너기 →','function-factory':'공장 가동 ⚙','graph-rider':'라이딩 →'}[g.id];}
 function body(){return `<header class="c2-top"><div><span class="c2-eyebrow">COMMON MATH 2 · ARCADE LAB</span><h2>${esc(g.title)}</h2><p>${esc(g.topic)}</p></div><div class="c2-top-actions">${B('처음부터','restart')}${B(s.phase==='paused'?'이어서':'잠깐 쉬기',s.phase==='paused'?'resume':'pause',`${!['playing','paused'].includes(s.phase)?'disabled':''}`)}</div></header><div class="c2-hud"><b>STAGE ${stage()} / 3</b><span>미션 ${s.index%3+1} / 3</span><span>성공 ${s.correct} / 9</span><span class="c2-score">${s.score}점</span><span>${s.mode==='challenge'?`실드 ${Math.max(0,5-s.errors)} / 5`:'천천히 · 시간 제한 없음'}</span><time data-clock>${Math.floor(s.seconds)}초</time></div><section class="c2-mission"><span>YOUR MISSION</span><div>${mathText(q.prompt)}</div></section><div class="c2-layout"><div><div class="c2-board-shell" data-c2-board tabindex="0" aria-label="게임 조작 영역: ${esc(g.controls)}"><div data-scene>${scene()}</div>${overlay()}</div><div class="c2-feedback" data-feedback role="status" aria-live="polite">${mathText(s.message)}</div></div><aside class="c2-console"><span class="c2-eyebrow">MOVE · MAKE · DISCOVER</span><h3>내가 조종하는 수학</h3><fieldset ${!active()?'disabled':''}><legend class="c2-sr">게임 조작</legend><div data-controls>${controls()}</div><div class="c2-main-controls">${B(submitLabel(),'submit','','c2-primary')}${B('배치 초기화','reset','','c2-reset')}</div></fieldset>${B(s.hint?'힌트 접기':'생각의 힌트 ✦','hint','','c2-hint-button')}<div class="c2-hint" ${s.hint?'':'hidden'}>${mathText(q.hint)}</div><small class="c2-guidance">${esc(g.controls)}<br>각 단계에서 3개 미션을 해결해요.</small></aside></div><footer class="c2-audio">${B('♫ 음악','sound','data-channel="music"')}${B('♪ 효과음','sound','data-channel="effects"')}<label>음량 <input type="range" data-volume min="0" max="100" value="${Math.round(audio.settings.volume*100)}" aria-label="게임 음량"></label><small>게임 기록은 화면 아래 저장 상태에서 확인하세요.</small></footer>`;}
 function overlay(){
  if(['playing','feedback'].includes(s.phase)&&s.phase==='playing')return '';
  if(s.phase==='ready')return `<div class="c2-overlay"><div><span class="c2-eyebrow">READY TO DISCOVER?</span><h3>${esc(g.genre)}로 배우는 수학</h3><p>${esc(g.desc)}</p><label>플레이 모드<select data-mode><option value="relaxed" ${s.mode==='relaxed'?'selected':''}>천천히 탐구 · 재도전 무제한</option><option value="challenge" ${s.mode==='challenge'?'selected':''}>도전 · 실드 5개 · 점수 보너스</option></select></label><p class="c2-small">${g.id==='venn-catcher'?'도전 모드에서는 캡슐이 8초마다 내려와요.':'관찰하고 조작한 뒤 확인 버튼을 눌러요.'}</p>${B('플레이 시작 →','start','','c2-primary')}</div></div>`;
  if(s.phase==='paused')return `<div class="c2-overlay"><div><h3>잠깐 쉬어 가요</h3><p>시간과 게임이 멈춰 있어요.</p>${B('이어서 플레이','resume','','c2-primary')}</div></div>`;
  if(s.phase==='feedback')return `<div class="c2-result-toast"><b>✦ 연결 성공!</b><p>${mathText(q.why)}</p>${B(s.correct%3===0?'다음 스테이지 →':'다음 미션 →','next','','c2-primary')}</div>`;
  return `<div class="c2-overlay"><div><span class="c2-trophy">${s.phase==='won'?'★':'✦'}</span><h3>${s.phase==='won'?'3개 스테이지 완주!':'다시 도전할 준비!'}</h3><p>${s.correct}개 미션 성공 · ${s.score}점</p><p>${mathText(s.message)}</p>${B('새 미션으로 다시','restart','','c2-primary')}<button type="button" data-action="arcade-lobby">모든 게임 보기</button></div></div>`;
 }
 function focused(){const el=document.activeElement;return root?.contains(el)&&el?.dataset?.c2Action?{...el.dataset}:null;}
 function restoreFocus(data){if(data){const next=[...root.querySelectorAll('[data-c2-action]')].find(el=>Object.entries(data).every(([k,v])=>el.dataset[k]===v));next?.focus({preventScroll:true});}}
 function refresh(){if(!root)return;const focus=focused();root.innerHTML=body();root.dataset.phase=s.phase;soundUI();restoreFocus(focus);}
 function paint(){if(!root)return;const focus=focused();root.querySelector('[data-scene]').innerHTML=scene();root.querySelector('[data-controls]').innerHTML=controls();restoreFocus(focus);}
 function pause(){if(!active())return;setPhase('paused');report('pause');refresh();}
 function check(undefinedValue=false){
  if(!active())return;input.undefined=undefinedValue;audio.cue('shoot');
  if(accepts(q,input)){
   s.correct++;s.score+=s.mode==='challenge'?150:100;report('success',q.why);
   if(s.correct%3===0)report('clear',q.why);
   if(s.correct===9){s.finished=true;setPhase('won');s.message='수학의 조건을 직접 조작하며 9개 미션을 해결했어요.';report('win',s.message);audio.cue('win');}
   else {setPhase('feedback');s.message=q.why;report('wait');audio.cue('hit');}
   refresh();
  }else{
   s.errors++;s.drop=0;const message='아직 조건과 맞지 않아요. '+q.hint;report('error',message);audio.cue('damage');feedback(message);
   if(s.mode==='challenge'&&s.errors>=5){s.finished=true;setPhase('lost');s.message='힌트를 읽고 다시 조작해 보세요. 천천히 모드에서는 제한 없이 도전할 수 있어요.';report('retry',s.message);}
   refresh();
  }
 }
 function adjustValue(field,delta){
  if(field==='railX'||field==='railY'){const i=field==='railX'?0:1;input.rail[s.endpoint][i]=clamp(input.rail[s.endpoint][i]+delta);}
  else if(field==='centerX'||field==='centerY'){const i=field==='centerX'?0:1;input.center[i]=clamp(input.center[i]+delta);}
  else if(field==='radius')input.radius=Math.max(1,Math.min(6,input.radius+delta));
  else if(['input','y'].includes(field))input[field]=clamp(input[field]+delta);
 }
 function move(dir){
  const dx=dir==='left'?-1:dir==='right'?1:0,dy=dir==='down'?-1:dir==='up'?1:0;
  if(g.id==='coordinate-drone')input.cursor=[clamp(input.cursor[0]+dx),clamp(input.cursor[1]+dy)];
  if(g.id==='line-rail')input.rail[s.endpoint]=[clamp(input.rail[s.endpoint][0]+dx),clamp(input.rail[s.endpoint][1]+dy)];
  if(g.id==='circle-radar')input.center=[clamp(input.center[0]+dx),clamp(input.center[1]+dy)];
  if(g.id==='move-portal'){const next=transform(input.shape,dir);if(next.every(p=>p.every(n=>Math.abs(n)<=6)))input.shape=next;}
  if(g.id==='venn-catcher')input.lane=Math.max(0,Math.min(3,input.lane+dx));
  if(g.id==='graph-rider')input.y=clamp(input.y+dy);
 }
 function action(name,el={dataset:{}}){
  const d=el.dataset;
  if(name==='sound'){audio.updateSettings({[d.channel]:!audio.settings[d.channel]});if(active())void audio.unlock();return;}
  if(name==='restart'){if(s.started&&!s.finished)report('retry','새 실행으로 다시 시작');audio.stop();fresh(g.id,s.mode);refresh();return;}
  if(name==='start'&&s.phase==='ready'){s.mode=root.querySelector('[data-mode]').value;s.started=true;setPhase('playing');s.message='직접 움직여 조건을 맞춰 보세요.';report('start');refresh();void audio.unlock();root.querySelector('[data-c2-board]').focus({preventScroll:true});return;}
  if(name==='pause'){pause();return;}
  if(name==='resume'&&s.phase==='paused'){setPhase('playing');report('resume');refresh();void audio.unlock();return;}
  if(name==='next'&&s.phase==='feedback'){s.index++;loadMission();setPhase('playing');s.message='새로운 조건을 확인하고 도전해요.';report('resume');refresh();return;}
  if(name==='hint'){s.hint=!s.hint;if(s.hint&&s.started)report('hint',q.hint);refresh();return;}
  if(!active())return;
  if(name==='submit'){check();return;}if(name==='undefined'){check(true);return;}
  if(name==='reset'){input=initialInput(q);s.endpoint=0;s.drop=0;}
  if(name==='adjust')adjustValue(d.field,Number(d.delta));
  if(name==='move')move(d.dir);
  if(name==='reflect')input.shape=transform(input.shape,d.op);
  if(name==='endpoint')s.endpoint=Number(d.value);
  if(name==='lane')input.lane=Number(d.value);
  if(name==='counter')input.value=Number(d.value);
  if(name==='condition'){if(input.bridge.length>=2)input.bridge=[];input.bridge.push(Number(d.value));}
  if(name==='machine'){if(input.order.length>=2)input.order=[];input.order.push(d.id);}
  paint();
 }
 function coordinate(e){
  const svg=root.querySelector('svg.c2-coordinate');if(!svg)return;
  const rect=svg.getBoundingClientRect();if(!rect.width||!rect.height)return;
  // SVG keeps its aspect ratio; account for letterboxing on narrow screens.
  const scale=Math.min(rect.width/560,rect.height/460);
  const left=rect.left+(rect.width-560*scale)/2,top=rect.top+(rect.height-460*scale)/2;
  const p=[clamp(Math.round(((e.clientX-left)/scale-280)/32)),clamp(Math.round((230-(e.clientY-top)/scale)/32))];
  if(g.id==='coordinate-drone')input.cursor=p;
  if(g.id==='line-rail')input.rail[s.endpoint]=p;
  if(g.id==='circle-radar')input.center=p;
  if(g.id==='graph-rider')input.y=p[1];
  paint();
 }
 function tick(now){const dt=last?Math.min((now-last)/1000,.15):0;last=now;if(active()){
   s.seconds+=dt;s.drop+=dt;const clock=root?.querySelector('[data-clock]');if(clock)clock.textContent=Math.floor(s.seconds)+'초';
   root?.style.setProperty('--drop',String(s.mode==='challenge'?Math.min(s.drop/8,1):.25));
   if(g.id==='venn-catcher'&&s.mode==='challenge'&&s.drop>=8)check();
   if(Math.floor(s.seconds/15)>Math.floor((s.seconds-dt)/15))report('heartbeat');
  }raf=requestAnimationFrame(tick);}
 function mount(){
  root=document.getElementById('common2-arena');if(!root)return;s.detached=false;controller=new window.AbortController();const opts={signal:controller.signal};
  root.addEventListener('click',e=>{const b=e.target.closest('[data-c2-action]');if(b&&!b.disabled)action(b.dataset.c2Action,b);},opts);
  root.addEventListener('input',e=>{if(e.target.matches('[data-volume]'))audio.updateSettings({volume:Number(e.target.value)/100});},opts);
  root.addEventListener('pointerdown',e=>{if(active()&&e.target.closest('svg.c2-coordinate')){pointer=true;root.querySelector('[data-c2-board]').focus({preventScroll:true});root.setPointerCapture?.(e.pointerId);coordinate(e);}},opts);
  root.addEventListener('pointermove',e=>{if(pointer&&active())coordinate(e);},opts);
  root.addEventListener('pointerup',()=>{pointer=false;},opts);root.addEventListener('pointercancel',()=>{pointer=false;},opts);
  root.addEventListener('keydown',e=>{if(!active()||!e.target.closest('[data-c2-board]'))return;const dir={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down'}[e.key];if(dir){e.preventDefault();move(dir);paint();}if(e.key==='Enter'||e.key===' '){e.preventDefault();check();}},opts);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();},opts);
  soundUI();last=0;raf=requestAnimationFrame(tick);
 }
 function unmount(){if(s&&!s.detached){if(s.started&&!s.finished)report('leave');s.detached=true;audio.stop();}controller?.abort();cancelAnimationFrame(raf);root=null;pointer=false;}
 return {open:id=>fresh(id),html:()=>`<section id="common2-arena" class="c2-arcade" data-phase="${s.phase}">${body()}</section>`,mount,unmount,action};
}
