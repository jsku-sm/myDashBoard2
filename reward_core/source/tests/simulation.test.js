import test from 'node:test';
import assert from 'node:assert/strict';
import {initial,step} from '../src/simulation.js';

for(const game of ['jump','kart','space','blocks','maze'])test(`${game}: deterministic 90 second playable run`,()=>{
  const a=initial(game,71),b=initial(game,71);
  for(let t=0;t<1800;t++){const k=(Math.floor(t/20)%3===0?1:2)|(t%12===0?4:0);step(a,k);step(b,k);}
  assert.deepEqual(a,b);assert.equal(a.t,1800);assert(Number.isInteger(a.score));assert(a.score>=0);assert(a.objects.length<100);
});
test('maze: every treasure, key and exit are reachable across generated maps',()=>{
  for(let seed=0;seed<200;seed++){
    const s=initial('maze',seed),seen=new Set([14]),queue=[14];
    for(let i=0;i<queue.length;i++){const p=queue[i];for(const n of [p-13,p+13,p-1,p+1])if(n>=0&&n<91&&!s.cells[n]&&!seen.has(n)){seen.add(n);queue.push(n);}}
    for(const target of [...s.treasures,s.key_cell,76])assert(seen.has(target));
  }
});
test('breakout aiming and shooting reward skill',()=>{
  for(const game of ['blocks','space']){
    const idle=initial(game,42),active=initial(game,42);
    for(let t=0;t<1800;t++){
      const target=game==='blocks'?active.bx:(active.objects.filter(o=>o.y>50&&o.y<300).at(-1)?.x||360);
      step(active,target<active.x-8?1:target>active.x+8?2:0);step(idle,0);
    }
    assert(active.score>idle.score,`${game}: skill should produce more score`);
  }
});
