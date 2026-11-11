// Deterministic twin of reward_core/simulation.py. Cross-language replay tests
// compare complete state every 100 ticks for every game, not just scores.
export const HZ=20;
function rand(s,n){s.rng=(1664525*s.rng+1013904223)%4294967296;return s.rng%n;}
function score(s,points){s.combo++;s.best_combo=Math.max(s.best_combo,s.combo);s.score+=points+Math.min(10,Math.floor(s.combo/3));}
function hit(s){if(s.t<s.safe)return;s.hits++;s.combo=0;s.safe=s.t+24;}
function blocks(s){s.objects=[];for(let r=0;r<5;r++)for(let c=0;c<7;c++)s.objects.push({x:65+c*85,y:60+r*29,w:76,h:21,kind:'block'});}
function maze(s){
  const w=13,h=7,cells=Array(w*h).fill(1);cells[w+1]=0;const stack=[[1,1]];
  while(stack.length){
    const [x,y]=stack.at(-1),opts=[];
    for(const [dx,dy] of [[2,0],[-2,0],[0,2],[0,-2]])if(x+dx>0&&x+dx<w-1&&y+dy>0&&y+dy<h-1&&cells[(y+dy)*w+x+dx]===1)opts.push([x+dx,y+dy,dx,dy]);
    if(!opts.length){stack.pop();continue;}
    const [nx,ny,dx,dy]=opts[rand(s,opts.length)];cells[(y+dy/2)*w+x+dx/2]=0;cells[ny*w+nx]=0;stack.push([nx,ny]);
  }
  const free=cells.map((v,i)=>!v&&i!==14&&i!==76?i:-1).filter(i=>i>=0);
  for(let i=free.length-1;i>0;i--){const j=rand(s,i+1);[free[i],free[j]]=[free[j],free[i]];}
  Object.assign(s,{cells,treasures:free.slice(0,6),key_cell:free[6],traps:free.slice(7,9),key:false,x:1,y:1});
}
export function initial(game,seed){
  if(!['jump','kart','space','blocks','maze'].includes(game))throw Error('Unknown game');
  const s={game,rng:seed>>>0,t:0,prev:0,score:0,combo:0,best_combo:0,hits:0,safe:0,x:140,y:340,vy:0,grounded:true,objects:[],bullets:[],lane:1,boost:0,bx:360,by:315,vx:5,bvy:-7,level:1};
  if(game==='space')s.x=360;if(game==='blocks'){s.x=360;blocks(s);}if(game==='maze')maze(s);return s;
}
export function step(s,keys){
  s.t++;const t=s.t,g=s.game,dx=Number(Boolean(keys&2))-Number(Boolean(keys&1)),jump=Boolean(keys&4)&&!(s.prev&4);
  if(g==='jump'){
    s.x=Math.max(35,Math.min(300,s.x+dx*7));const oldY=s.y;
    if(jump&&s.grounded)s.vy=-18;s.vy=Math.min(18,s.vy+1);s.y+=s.vy;s.grounded=false;
    if(s.y>=340)Object.assign(s,{y:340,vy:0,grounded:true});
    if(t%34===1){const kind=rand(s,3)?'platform':'spike',height=35+rand(s,3)*30;s.objects.push({kind,x:740,y:340-height,w:70,h:height,touched:false},{kind:'star',x:770,y:300-height,w:18,h:18,touched:false});}
    for(const o of s.objects){
      o.x-=5;
      if(o.kind==='platform'&&s.vy>=0&&oldY<=o.y&&o.y<=s.y&&Math.abs(s.x-(o.x+35))<47)Object.assign(s,{y:o.y,vy:0,grounded:true});
      if(o.kind==='star'&&Math.abs(s.x-o.x)<28&&Math.abs(s.y-20-o.y)<28){score(s,15);o.x=-100;}
      if(['spike','platform'].includes(o.kind)&&Math.abs(s.x-(o.x+35))<44&&s.y>o.y+5){hit(s);o.touched=true;}
      if(o.kind!=='star'&&!o.touched&&o.x+70<s.x-15){score(s,5);o.touched=true;}
    }s.objects=s.objects.filter(o=>o.x>-100);
  }else if(g==='kart'){
    if(dx&&(!(s.prev&3)||t%6===0))s.lane=Math.max(0,Math.min(2,s.lane+dx));s.x=210+s.lane*150;
    if(t%16===1)s.objects.push({lane:rand(s,3),y:-30,kind:['coin','car','boost'][rand(s,3)],touched:false});
    for(const o of s.objects){
      o.y+=t<s.boost?7:5;
      if(o.lane===s.lane&&Math.abs(o.y-340)<32){
        if(o.kind==='car')hit(s);else{score(s,o.kind==='boost'?20:10);if(o.kind==='boost')s.boost=t+45;}o.y=500;o.touched=true;
      }else if(o.kind==='car'&&o.y>380&&!o.touched){score(s,5);o.touched=true;}
    }if(t%20===0)s.score+=2;s.objects=s.objects.filter(o=>o.y<480);
  }else if(g==='space'){
    s.x=Math.max(30,Math.min(690,s.x+dx*10));if(t%5===0)s.bullets.push({x:s.x,y:330});
    if(t%14===1)s.objects.push({x:30+rand(s,660),y:-20,kind:'rock',dead:false});
    for(const b of s.bullets)b.y-=15;
    for(const o of s.objects){o.y+=4;for(const b of s.bullets)if(!o.dead&&b.y>-50&&Math.abs(b.x-o.x)<25&&Math.abs(b.y-o.y)<25){o.dead=true;b.y=-100;score(s,20);}if(!o.dead&&Math.abs(s.x-o.x)<35&&Math.abs(340-o.y)<30){hit(s);o.dead=true;}}
    s.bullets=s.bullets.filter(b=>b.y>-20);s.objects=s.objects.filter(o=>!o.dead&&o.y<460);
  }else if(g==='blocks'){
    s.x=Math.max(65,Math.min(655,s.x+dx*14));s.bx+=s.vx;s.by+=s.bvy;
    if(s.bx<15||s.bx>705){s.vx*=-1;s.bx=Math.max(15,Math.min(705,s.bx));}if(s.by<25)s.bvy=Math.abs(s.bvy);
    if(s.bvy>0&&s.by>=345&&s.by<=365&&Math.abs(s.bx-s.x)<=70){s.bvy=-7;s.vx=Math.max(-9,Math.min(9,Math.floor((s.bx-s.x)/7)))||3;}
    for(let i=0;i<s.objects.length;i++){const o=s.objects[i];if(o.x-8<=s.bx&&s.bx<=o.x+o.w+8&&o.y-8<=s.by&&s.by<=o.y+o.h+8){s.bvy*=-1;s.objects.splice(i,1);score(s,10);break;}}
    if(s.by>420){hit(s);Object.assign(s,{bx:s.x,by:315,vx:rand(s,2)?5:-5,bvy:-7});}if(!s.objects.length){s.level++;score(s,100);blocks(s);}
  }else if(g==='maze'){
    if(keys&&(keys!==s.prev||t%4===0)){const dy=Number(Boolean(keys&8))-Number(Boolean(keys&4)),nx=s.x+dx,ny=s.y+(dx===0?dy:0);if(nx>=0&&nx<13&&ny>=0&&ny<7&&!s.cells[ny*13+nx])Object.assign(s,{x:nx,y:ny});}
    const cell=s.y*13+s.x;
    if(s.treasures.includes(cell)){s.treasures=s.treasures.filter(i=>i!==cell);score(s,20);}
    if(cell===s.key_cell&&!s.key){s.key=true;score(s,30);}
    if(s.traps.includes(cell)&&Math.floor(t/20)%3===0&&t>=s.safe){hit(s);Object.assign(s,{x:1,y:1});}
    if(cell===76&&s.key){score(s,100);s.level++;maze(s);}
  }s.prev=keys;return s;
}
