import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {COMMON2_GAMES,mission,initialInput,accepts} from '../src/common2-data.js';

function solve(q){
 const s=initialInput(q);
 switch(q.id){
 case 'coordinate-drone':s.cursor=q.stage===1?q.stations.find(p=>(p[0]-q.A[0])**2+(p[1]-q.A[1])**2===25):q.A.map((v,i)=>(q.n*v+q.m*q.B[i])/(q.m+q.n));break;
 case 'line-rail':{const [a,b]=q.reference;const d=q.stage===1?q.Q.map((v,i)=>v-q.P[i]):q.stage===2?[b,-a]:[a,b];s.rail=[q.P,q.P.map((v,i)=>v+d[i])];break;}
 case 'circle-radar':s.center=[q.h,q.k];s.radius=q.stage===3?Math.abs(q.line[0]*q.h+q.line[1]*q.k+q.line[2])/Math.hypot(q.line[0],q.line[1]):q.stage===2?Math.hypot(q.P[0]-q.h,q.P[1]-q.k):q.r;break;
 case 'move-portal':s.shape=q.shape.map(([x,y])=>{if(q.stage!==2){x+=q.dx;y+=q.dy;}return q.stage===1?[x,y]:q.axis==='x'?[x,-y]:q.axis==='y'?[-x,y]:q.axis==='origin'?[-x,-y]:[y,x];});break;
 case 'venn-catcher':{const a=new Set(q.A).has(q.value),b=new Set(q.B).has(q.value);s.lane=a&&b?1:a?0:b?2:3;break;}
 case 'logic-bridge':if(q.stage===3){s.value=q.values.find(x=>x>q.a&&!(x>q.b));}else{s.bridge=q.stage===1?[0,1]:[3,2];for(let x=-30;x<=30;x++){assert.ok(q.stage===1?!(x>q.b)||(x>q.a):!(x<=q.a)||(x<=q.b));}}break;
 case 'function-factory':s.order=q.answerOrder.slice();{const [a,b]=q.machines.f,[c,d]=q.machines.g;const calc=x=>q.stage===2?a*x+b:s.order[0]==='g'?a*(c*x+d)+b:c*(a*x+b)+d;s.input=Array.from({length:13},(_,i)=>i-6).find(x=>calc(x)===q.target);}break;
 case 'graph-rider':s.undefined=q.family==='rational'?q.x===q.h:q.x<q.h;if(!s.undefined)s.y=q.family==='rational'?q.a/(q.x-q.h)+q.k:q.a*Math.sqrt(q.x-q.h)+q.k;break;
 }
 return s;
}
for(const g of COMMON2_GAMES)test(g.title+': attainable, bounded, variable mathematics across all stages',()=>{
 const variants=new Set();
 for(let stage=1;stage<=3;stage++)for(let seed=0;seed<100;seed++){
  const q=mission(g.id,stage,seed),s=solve(q);variants.add(q.prompt+JSON.stringify(q.A));
  assert.ok(accepts(q,s),JSON.stringify({q,s}));
  for(const p of [s.cursor,...s.rail,s.center,...(s.shape||[])])assert.ok(p.every(n=>Number.isInteger(n)&&Math.abs(n)<=6));
  assert.ok(Number.isFinite(s.input)&&Math.abs(s.input)<=6);assert.ok(Number.isFinite(s.y)&&Math.abs(s.y)<=6);
  const bad=structuredClone(s);
  if(g.id==='coordinate-drone')bad.cursor=[s.cursor[0]+1,s.cursor[1]];
  if(g.id==='line-rail')bad.rail=[s.rail[0],s.rail[0]];
  if(g.id==='circle-radar')bad.radius+=1;
  if(g.id==='move-portal')bad.shape[0][0]+=1;
  if(g.id==='venn-catcher')bad.lane=(s.lane+1)%4;
  if(g.id==='logic-bridge'){bad.bridge=[];bad.value=q.a-1;}
  if(g.id==='function-factory')bad.input+=1;
  if(g.id==='graph-rider'){if(s.undefined)bad.undefined=false;else bad.y+=1;}
  assert.equal(accepts(q,bad),false);
 }
 assert.ok(variants.size>30,g.id+' lacks variety');
});
test('server catalog contains old games and every added game with identical labels',()=>{
 const rows=JSON.parse(fs.readFileSync(new URL('../../game_core/play_lab_catalog.json',import.meta.url),'utf8'));
 assert.equal(rows.length,20);assert.equal(new Set(rows.map(g=>g.id)).size,20);
 for(const g of COMMON2_GAMES)assert.equal(rows.find(r=>r.id===g.id)?.title,g.title);
 assert.ok(rows.some(g=>g.id==='bubble'));assert.ok(rows.some(g=>g.id==='root-maze'));
});
