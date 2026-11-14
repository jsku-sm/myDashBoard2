// Original activity generators aligned to 2022 common mathematics 2.
export const COMMON2_GAMES = [
 ['coordinate-drone','좌표 드론 배송','geometry','좌표 이동','두 점 사이 거리 · 내분점','좌표를 읽고 드론을 움직여 정확한 배송 지점을 찾아요.','좌표판 터치 · 방향키 · 배송 확인','10공수2-01-01','✈'],
 ['line-rail','직선 레일 익스프레스','geometry','레일 설계','직선의 방정식 · 평행과 수직','두 조절점을 움직여 열차가 달릴 직선 레일을 설계해요.','조절점 선택 후 좌표판 터치 · 좌표 조절','10공수2-01-02','↗'],
 ['circle-radar','원 레이더 디펜스','geometry','레이더 조절','원의 방정식 · 점과 직선 사이 거리','중심과 반지름을 조절해 목표를 찾는 원형 레이더를 만들어요.','중심 이동 · 반지름 조절 · 스캔','10공수2-01-03 · 01-04 · 01-05','◎'],
 ['move-portal','도형 이동 포털','geometry','변환 퍼즐','평행이동 · 대칭이동','삼각형 우주선을 이동하고 뒤집어 포털에 포개 보세요.','방향 버튼 · 대칭 버튼 · 포털 통과','10공수2-01-06 · 01-07','◇'],
 ['venn-catcher','벤다이어그램 캐처','sets','분류 캐치','교집합 · 차집합 · 여집합','숫자 캡슐이 속하는 집합 영역으로 바구니를 움직여요.','← → 또는 영역 버튼 · 캡슐 받기','10공수2-02-01 · 02-03','∩'],
 ['logic-bridge','논리 브리지 빌더','logic','다리 만들기','명제 · 대우 · 충분조건과 필요조건','조건 블록을 연결하고 반례를 찾아 논리 다리를 완성해요.','조건 블록 순서 선택 · 다리 건너기','10공수2-02-04 · 02-05 · 02-06','⇒'],
 ['function-factory','함수 팩토리','function','컨베이어 퍼즐','합성함수 · 역함수','함수 기계의 순서와 입력을 바꿔 목표 출력을 만들어요.','기계 카드 선택 · 입력 조절 · 가동','10공수2-03-02 · 03-03','⚙'],
 ['graph-rider','그래프 웨이브 라이더','function','그래프 라이딩','유리함수 · 무리함수 · 정의역','그래프 높이에 맞춰 라이더를 조종하고 정의되지 않는 길을 구별해요.','↑ ↓ 높이 조절 · 라이딩 또는 통과 불가','10공수2-03-04 · 03-05','∿'],
].map(([id,title,subject,genre,topic,desc,controls,standard,symbol])=>({id,title,subject,genre,topic,desc,controls,standard,symbol,tag:'NEW · 직접 조작',goal:desc,lesson:topic}));
export const COMMON2_IDS = new Set(COMMON2_GAMES.map(g=>g.id));
export const point = p => `(${p[0]}, ${p[1]})`;
const eq=(a,b)=>Math.abs(a-b)<1e-8;
const same=(a,b)=>Array.isArray(a)&&a.length===b.length&&a.every((n,i)=>eq(n,b[i]));
export function random(seed){let a=seed>>>0;return ()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
export function transform(points,op){return points.map(([x,y])=>({left:[x-1,y],right:[x+1,y],up:[x,y+1],down:[x,y-1],x:[x,-y],y:[-x,y],origin:[-x,-y],swap:[y,x]})[op]||[x,y]);}
export function region(value,A,B){return A.includes(value)?B.includes(value)?1:0:B.includes(value)?2:3;}
export function lineThrough(P,Q){return [Q[1]-P[1],P[0]-Q[0],Q[0]*P[1]-P[0]*Q[1]];}
export function factoryValue(q,input,order){return order.reduce((value,id)=>q.machines[id][0]*value+q.machines[id][1],input);}
export function graphValue(q){return q.family==='rational'?(q.x===q.h?null:q.a/(q.x-q.h)+q.k):(q.x<q.h?null:q.a*Math.sqrt(q.x-q.h)+q.k);}
export const linear=(a,b)=>`${a}x${b>=0?'+':''}${b}`;
const square=(v,h)=>`(${v}${h>=0?'-':'+'}${Math.abs(h)})^2`;

export function mission(id,stage,seed){
 const rand=random(seed),int=(lo,hi)=>lo+Math.floor(rand()*(hi-lo+1)),pick=xs=>xs[int(0,xs.length-1)];
 const q={id,stage};
 if(id==='coordinate-drone'){
  if(stage===1){q.A=[int(-4,0),int(-3,0)];const d=pick([[3,4],[4,3],[0,5],[5,0]]);q.answer=q.A.map((x,i)=>x+d[i]);q.stations=[q.answer,[q.A[0]+2,q.A[1]+1],[q.A[0]+1,q.A[1]+3]];q.prompt=`A${point(q.A)}에서 거리가 $5$인 정거장으로 배송하세요.`;q.hint='두 점의 거리: $d=\\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}$';q.why=`${point(q.answer)}까지 거리의 제곱은 $${d[0]}^2+${d[1]}^2=25$이므로 거리는 $5$예요.`;}
  else {q.m=stage===2?1:int(1,2);q.n=stage===2?1:3-q.m;q.A=[int(-4,-2),int(-4,-2)];const d=[int(1,2),int(1,2)];q.B=q.A.map((x,i)=>x+(q.m+q.n)*d[i]);q.answer=q.A.map((x,i)=>x+q.m*d[i]);q.prompt=`A${point(q.A)}, B${point(q.B)}를 잇는 선분의 ${stage===2?'중점':`$AP:PB=${q.m}:${q.n}$인 내분점 P`}에 배송하세요.`;q.hint='$AP:PB=m:n$이면 $P=\\left(\\frac{nx_A+mx_B}{m+n},\\frac{ny_A+my_B}{m+n}\\right)$';q.why=`A에서 B 방향으로 전체의 $\\frac{${q.m}}{${q.m+q.n}}$만큼 이동해요. P는 ${point(q.answer)}예요.`;}
 }
 if(id==='line-rail'){
  const slopes=[[1,1],[1,2],[2,1],[1,-1],[1,-2],[2,-1]];const d=pick(slopes);q.P=[int(-2,2),int(-2,2)];q.direction=stage===3?[-d[1],d[0]]:d;q.Q=q.P.map((v,i)=>v+q.direction[i]);q.reference=lineThrough([0,0],d);q.target=lineThrough(q.P,q.Q);
  q.prompt=stage===1?`P${point(q.P)}, Q${point(q.Q)}를 지나는 직선 레일을 만드세요.`:`P${point(q.P)}를 지나고 $${q.reference[0]}x+(${q.reference[1]})y=0$과 ${stage===2?'평행':'수직'}인 레일을 만드세요.`;
  q.hint=stage===3?'두 방향벡터의 내적이 $0$이면 수직이에요. 기울기가 있을 때는 $m_1m_2=-1$이에요.':'두 점의 좌표 차이로 방향을 정해요. 평행한 직선은 방향이 같아요.';
  q.why=`완성한 레일은 $${q.target[0]}x+(${q.target[1]})y+(${q.target[2]})=0$을 만족해요.`;
 }
 if(id==='circle-radar'){
  q.h=int(-2,2);q.k=int(-2,2);q.r=int(1,3);q.answer=[q.h,q.k,q.r];q.P=[q.h+q.r,q.k];q.line=[3,4,-3*q.h-4*q.k+5*q.r];
  q.prompt=stage===1?`$${square('x',q.h)}+${square('y',q.k)}=${q.r*q.r}$인 원을 레이더로 만드세요.`:stage===2?`중심 C${point([q.h,q.k])}, 원 위의 점 P${point(q.P)}를 이용해 원을 만드세요.`:`중심 C${point([q.h,q.k])}에서 직선 $3x+4y+(${q.line[2]})=0$에 접하는 원을 만드세요.`;
  q.hint=stage===3?'접할 때 반지름은 중심에서 직선까지의 거리예요. $d=\\frac{|ax_0+by_0+c|}{\\sqrt{a^2+b^2}}$':'원의 방정식은 $(x-h)^2+(y-k)^2=r^2$이에요. 반지름은 $r^2$가 아니라 $r$이에요.';
  q.why=`중심은 ${point([q.h,q.k])}, 반지름은 $${q.r}$예요.${stage===3?' 중심과 직선 사이의 거리와 반지름이 같아 접점이 하나예요.':''}`;
 }
 if(id==='move-portal'){
  const x=int(-3,1),y=int(-3,1);q.shape=[[x,y],[x+2,y],[x,y+1]];q.dx=pick([-2,-1,1,2]);q.dy=pick([-2,-1,1,2]);q.axis=pick(['x','y','origin','swap']);
  const labels={x:'x축',y:'y축',origin:'원점',swap:'직선 y=x'};const translated=q.shape.map(([a,b])=>[a+q.dx,b+q.dy]);q.target=stage===1?translated:transform(stage===2?q.shape:translated,q.axis);
  q.prompt=stage===1?`우주선을 x방향 $${q.dx}$, y방향 $${q.dy}$만큼 평행이동하세요.`:stage===2?`우주선을 ${labels[q.axis]}에 대하여 대칭이동하세요.`:`x방향 $${q.dx}$, y방향 $${q.dy}$만큼 이동한 뒤 ${labels[q.axis]}에 대하여 대칭이동하세요.`;
  q.hint='평행이동: $(x+a,y+b)$ · x축: $(x,-y)$ · y축: $(-x,y)$ · 원점: $(-x,-y)$ · y=x: $(y,x)$';q.why='모든 꼭짓점이 목표 위치와 일치해요. 이동 순서를 바꾸면 결과가 달라질 수 있어요.';
 }
 if(id==='venn-catcher'){
  const U=Array.from({length:12},(_,i)=>i+1),a=int(2,4),b=int(5,9);q.U=U;q.A=U.filter(n=>n%a===0);q.B=U.filter(n=>n>=b);q.baseA=q.A.slice();
  if(stage===3)q.A=U.filter(n=>!q.A.includes(n));q.value=int(1,12);q.answer=region(q.value,q.A,q.B);
  q.prompt=`숫자 $${q.value}$ 캡슐이 속하는 바구니로 이동하세요.${stage===3?' 이번 A는 ‘원래 A의 여집합’으로 바뀌었어요.':''}`;
  q.condition=stage===1?'목록의 원소를 비교해요.':`U={1,…,12}, ${stage===3?'원래 A':'A'}는 ${a}의 배수, B는 ${b} 이상의 수예요.`;
  q.hint='A만: $A-B$ · 둘 다: $A\\cap B$ · B만: $B-A$ · 둘 다 아님: $(A\\cup B)^c$';q.why=`${q.value}은(는) A에 ${q.A.includes(q.value)?'속하고':'속하지 않고'} B에 ${q.B.includes(q.value)?'속해요':'속하지 않아요'}. 따라서 ${['A만','둘 다','B만','둘 다 아님'][q.answer]} 바구니가 맞아요.`;
 }
 if(id==='logic-bridge'){
  q.a=int(-3,1);q.b=q.a+int(2,4);q.cards=[`x>${q.b}`,`x>${q.a}`,`x\\le ${q.b}`,`x\\le ${q.a}`];
  if(stage<3){q.answer=stage===1?[0,1]:[3,2];q.prompt=`실수 x에 대해 p: $x>${q.b}$, q: $x>${q.a}$예요. ${stage===1?'q의 충분조건인 p를 앞에 두어 참인 p → q 다리를':'p → q의 대우에 해당하는 다리를'} 만드세요.`;q.hint='p → q에서 p는 q의 충분조건, q는 p의 필요조건이에요. 대우는 ¬q → ¬p예요.';q.why=stage===1?`$x>${q.b}$이면 항상 $x>${q.a}$예요. p가 q를 보장해요.`:`대우는 $x\\le ${q.a} \\Rightarrow x\\le ${q.b}$예요. 원래 명제와 참·거짓이 같아요.`;}
  else {q.values=[q.a-1,q.a+1,q.b+1];q.answer=q.a+1;q.prompt=`‘$x>${q.a}$이면 $x>${q.b}$이다’가 거짓임을 보여 주는 반례 발판을 고르세요.`;q.hint='반례는 가정이 참이면서 결론이 거짓인 경우예요.';q.why=`$x=${q.answer}$는 $x>${q.a}$를 만족하지만 $x>${q.b}$는 만족하지 않아요.`;}
 }
 if(id==='function-factory'){
  q.machines={f:[int(2,3),int(-3,3)],g:[1,pick([-3,-2,2,3])]};q.input=int(-3,3);q.answerOrder=stage===2?['f']:pick([['g','f'],['f','g']]);q.target=factoryValue(q,q.input,q.answerOrder);
  const [f,g]=[linear(...q.machines.f),linear(...q.machines.g)];q.prompt=`$f(x)=${f},\\quad g(x)=${g}$. `+(stage===1?`입력 $${q.input}$을 ${q.answerOrder.join(' 다음 ')} 순서로 처리하도록 기계를 배치하세요.`:stage===2?`$f^{-1}(${q.target})$을 구하도록 f 기계에 넣을 입력을 찾으세요.`:`$(${q.answerOrder[1]}\\circ ${q.answerOrder[0]})(x)=${q.target}$이 되도록 기계 순서와 입력을 정하세요.`);
  q.hint='기계는 왼쪽부터 통과해요. $(f∘g)(x)=f(g(x))$에서는 g가 먼저예요. 역함수는 출력에서 입력을 거꾸로 찾아요.';q.why=`입력 $${q.input}$ → ${q.answerOrder.join(' → ')} → 출력 $${q.target}$예요. 기계의 순서와 입력이 모두 맞아요.`;
 }
 if(id==='graph-rider'){
  q.family=stage===1?'rational':stage===2?'root':pick(['rational','root']);q.h=int(-2,2);q.k=int(-2,2);q.a=q.family==='rational'?pick([-2,2]):pick([-1,1]);
  q.x=q.h+pick(q.family==='rational'?[-2,-1,0,1,2]:[-1,0,1,4]);q.answer=graphValue(q);
  q.formula=q.family==='rational'?`y=\\frac{${q.a}}{x-(${q.h})}+(${q.k})`:`y=${q.a}\\sqrt{x-(${q.h})}+(${q.k})`;
  q.prompt=`$${q.formula}$에서 $x=${q.x}$인 관문이에요. 라이더 높이 y를 맞추거나, 정의되지 않으면 ‘통과 불가’를 누르세요.`;
  q.hint=q.family==='rational'?`분모는 0이 아니어야 해요. 점근선은 $x=${q.h}$, $y=${q.k}$예요.`:`근호 안이 0 이상이어야 해요. 정의역은 $x\\ge ${q.h}$, 시작점은 ${point([q.h,q.k])}예요.`;
  q.why=q.answer===null?(q.family==='rational'?'분모가 0이므로 이 x에서는 정의되지 않아요.':'근호 안이 음수이므로 실수 범위에서 정의되지 않아요.'):`$x=${q.x}$를 대입하면 $y=${q.answer}$이므로 ${point([q.x,q.answer])}을 지나가요.`;
 }
 if(!q.prompt)throw Error('Unknown common-math arcade: '+id);
 return q;
}

export function initialInput(q){return {cursor:[0,0],rail:[[-3,0],[3,0]],center:[0,0],radius:1,shape:q.shape?.map(p=>p.slice()),lane:0,bridge:[],value:null,order:[],input:q.stage===1&&q.id==='function-factory'?q.input:0,y:0,undefined:false};}
export function accepts(q,s){
 if(q.id==='coordinate-drone')return same(s.cursor,q.answer);
 if(q.id==='line-rail')return !same(s.rail[0],s.rail[1])&&s.rail.every(([x,y])=>eq(q.target[0]*x+q.target[1]*y+q.target[2],0));
 if(q.id==='circle-radar')return same([...s.center,s.radius],q.answer);
 if(q.id==='move-portal')return s.shape.every((p,i)=>same(p,q.target[i]));
 if(q.id==='venn-catcher')return s.lane===q.answer;
 if(q.id==='logic-bridge')return q.stage===3?s.value===q.answer:same(s.bridge,q.answer);
 if(q.id==='function-factory')return s.order.join(',')===q.answerOrder.join(',')&&s.input===q.input&&factoryValue(q,s.input,s.order)===q.target;
 if(q.id==='graph-rider')return q.answer===null?s.undefined:!s.undefined&&eq(s.y,q.answer);
 return false;
}

export function common2Art(id){const g=COMMON2_GAMES.find(g=>g.id===id);return `<svg viewBox="0 0 320 150" aria-hidden="true"><path d="M20 30H300M20 60H300M20 90H300M20 120H300M60 10V140M120 10V140M180 10V140M240 10V140" stroke="currentColor" fill="none" opacity=".13"/><rect x="105" y="27" width="100" height="96" rx="24" fill="currentColor" opacity=".14" transform="rotate(-8 155 75)"/><circle cx="251" cy="34" r="15" fill="currentColor" opacity=".25"/><path d="m45 110 24-24 19 18" stroke="currentColor" fill="none" stroke-width="6"/><text x="157" y="96" text-anchor="middle" fill="currentColor" font-size="66" font-weight="900">${g.symbol}</text><text x="240" y="127" fill="currentColor" font-size="16" font-weight="900">NEW ✦</text></svg>`;}
