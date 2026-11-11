// Original vector artwork, drawn locally. No downloaded game assets.
const colors=['#caff38','#ff91cc','#63dcff','#bca5ff','#ffd859'];
export function paint(canvas,s,medal=false){
  const c=canvas.getContext('2d');if(!c)return;
  const rect=(x,y,w,h,color,r=8)=>{c.fillStyle=color;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();};
  const dot=(x,y,r,color)=>{c.fillStyle=color;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();};
  const text=(v,x,y,size=20,color='#fff')=>{c.fillStyle=color;c.font=`900 ${size}px system-ui`;c.textAlign='center';c.fillText(v,x,y);};
  const star=(x,y,r,color)=>{c.beginPath();for(let i=0;i<10;i++){const a=i*Math.PI/5-Math.PI/2,d=i%2?r*.45:r;c.lineTo(x+Math.cos(a)*d,y+Math.sin(a)*d);}c.closePath();c.fillStyle=color;c.fill();};
  const player=medal?'#ffd859':'#caff38';
  c.clearRect(0,0,720,430);rect(0,0,720,430,'#20203d',0);
  for(let i=0;i<24;i++){const x=(i*139)%720,y=(i*73)%430;dot(x,y,1+(i%2),'#ffffff32');}
  c.save();
  if(s.game==='jump'){
    const sky=c.createLinearGradient(0,0,0,340);sky.addColorStop(0,'#5833ed');sky.addColorStop(1,'#bda6ff');rect(0,0,720,340,sky,0);
    dot(600,60,33,'#ffd859');for(let i=0;i<6;i++){const x=((i*160-s.t*2)%960+960)%960-100;rect(x,110+i%3*35,90,22,'#ffffff55',16);}
    for(let i=0;i<9;i++)rect(i*100-((s.t*2)%100),280-(i%3)*30,75,110,'#6748bf',12);
    rect(0,340,720,90,'#252242',0);rect(0,340,720,7,'#caff38',0);
    for(const o of s.objects){if(o.kind==='star')star(o.x,o.y,15,'#ffd859');else if(o.kind==='platform'){rect(o.x,o.y,o.w,o.h,'#2c2853');rect(o.x,o.y,o.w,8,'#63dcff',3);}else{for(let j=0;j<3;j++){c.beginPath();c.moveTo(o.x+j*23,340);c.lineTo(o.x+j*23+12,o.y);c.lineTo(o.x+j*23+24,340);c.fillStyle='#ff74b7';c.fill();}}}
    if(s.t>=s.safe||s.t%4<2){rect(s.x-14,s.y-31,28,31,player,8);dot(s.x+6,s.y-22,3,'#252242');rect(s.x-18,s.y-36,36,9,'#ff91cc',4);}
  }else if(s.game==='kart'){
    for(let i=0;i<10;i++){rect(20+(i%2)*650,(i*70+s.t*7)%500-70,30,43,colors[i%5]);}
    rect(135,0,450,430,'#31304e',0);rect(130,0,6,430,'#ff91cc',0);rect(585,0,6,430,'#63dcff',0);
    for(const x of [285,435])for(let y=-50;y<430;y+=75)rect(x,y+(s.t*5)%75,4,38,'#ffffff6a',2);
    const car=(x,y,color)=>{rect(x-25,y-35,50,70,color,12);rect(x-18,y-21,36,20,'#20203d',5);rect(x-32,y-21,8,18,'#0e0e22',3);rect(x+24,y-21,8,18,'#0e0e22',3);rect(x-32,y+15,8,18,'#0e0e22',3);rect(x+24,y+15,8,18,'#0e0e22',3);};
    for(const o of s.objects){const x=210+150*o.lane;if(o.kind==='car')car(x,o.y,'#ff75b8');else if(o.kind==='coin'){dot(x,o.y,16,'#ffd859');text('★',x,o.y+7,20,'#805226');}else{star(x,o.y,23,'#63dcff');text('↟',x,o.y+8,24,'#20203d');}}
    if(s.t<s.boost){rect(s.x-17,365,14,40+(s.t%3)*5,'#63dcff');rect(s.x+3,365,14,40+(s.t%3)*5,'#ff91cc');}
    if(s.t>=s.safe||s.t%4<2)car(s.x,340,player);
  }else if(s.game==='space'){
    dot(640,85,65,'#5d3bb8');dot(620,55,19,'#7752d2');
    for(let i=0;i<45;i++)rect((i*137)%720,(i*91+s.t*3)%430,2,7,'#9edfff55',0);
    for(const b of s.bullets)rect(b.x-3,b.y-10,6,22,'#caff38',3);
    for(const o of s.objects){dot(o.x,o.y,23,'#ac8bdb');dot(o.x-7,o.y-7,7,'#69558c');dot(o.x+9,o.y+8,5,'#69558c');}
    if(s.t>=s.safe||s.t%4<2){c.beginPath();c.moveTo(s.x,309);c.lineTo(s.x+27,363);c.lineTo(s.x,350);c.lineTo(s.x-27,363);c.closePath();c.fillStyle=player;c.fill();dot(s.x,337,7,'#5935ed');rect(s.x-5,354,10,20+s.t%3*5,'#ff91cc');}
  }else if(s.game==='blocks'){
    for(let i=0;i<12;i++)rect(i*65,0,1,430,'#ffffff0b',0);
    for(const o of s.objects){rect(o.x+3,o.y+3,o.w,o.h,'#00000050',5);rect(o.x,o.y,o.w,o.h,colors[Math.floor((o.y-60)/29)%5],5);rect(o.x+6,o.y+4,o.w-12,3,'#ffffff77',2);}
    dot(s.bx-s.vx*2,s.by-s.bvy*2,7,'#ffffff44');dot(s.bx,s.by,9,'#fff');rect(s.x-65,355,130,15,player,8);text(`WAVE ${s.level}`,360,407,16,'#bca5ff');
  }else if(s.game==='maze'){
    const z=48,ox=48,oy=32;
    for(let y=0;y<7;y++)for(let x=0;x<13;x++){const i=y*13+x;rect(ox+x*z,oy+y*z,z-2,z-2,s.cells[i]?'#6441b5':'#292843',7);if(s.cells[i])rect(ox+x*z+4,oy+y*z+4,z-10,4,'#a58ae2',2);}
    const loc=i=>[ox+(i%13)*z+23,oy+Math.floor(i/13)*z+23];
    for(const i of s.treasures){const [x,y]=loc(i);star(x,y,13,'#63dcff');}
    for(const i of s.traps){const [x,y]=loc(i);dot(x,y,15,Math.floor(s.t/20)%3===0?'#ff5787':'#60364b');text('!',x,y+7,20);}
    if(!s.key){const [x,y]=loc(s.key_cell);dot(x-5,y,9,'#ffd859');rect(x,y-3,18,6,'#ffd859',2);rect(x+10,y,5,10,'#ffd859',1);}
    const [ex,ey]=loc(76);rect(ex-17,ey-19,34,38,s.key?'#caff38':'#818196',7);text('↗',ex,ey+8,25,'#22213c');
    const x=ox+s.x*z+23,y=oy+s.y*z+23;dot(x,y,15,player);dot(x+5,y-3,3,'#24213d');text(s.key?'KEY GET! 출구로!':'열쇠를 찾아 출구로!',360,402,19,'#ffd859');
  }
  c.restore();
}
