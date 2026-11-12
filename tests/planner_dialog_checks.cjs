// Geometry and modal lifecycle tests. No claim of real-browser visual QA.
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.resolve(__dirname,'../teacher_planner/frontend');
const source=fs.readFileSync(path.join(dir,'dialog_viewport.mjs'),'utf8').replaceAll('export ','');
const dom=new JSDOM('<div id="app"></div><dialog id="editor"><h2 id="dialog-title">새 수업 기록</h2><input name="content"></dialog>',{runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;w.eval(source+'\nwindow.modalAPI={dialogPlacement,visibleDialogViewport,attachDialogViewport};');
const {dialogPlacement,visibleDialogViewport,attachDialogViewport}=w.modalAPI;
const box=(left,top,width,height)=>({left,top,width,height,right:left+width,bottom:top+height});
function host(){const h={innerWidth:1440,innerHeight:900,visualViewport:null,document:{querySelector:()=>null},getComputedStyle:()=>({overflowX:'visible',overflowY:'visible'})};h.parent=h;return h;}
function child(h,top=100,left=280,width=1100,height=2200){return {innerWidth:width,innerHeight:height,parent:h,frameElement:{ownerDocument:{defaultView:h,querySelector:()=>null},getBoundingClientRect:()=>box(left,top,width,height),offsetWidth:width,offsetHeight:height,clientTop:0,clientLeft:0,parentElement:null}};}
let count=0;function test(title,fn){fn();count++;console.log('PASS',title);}
test('tall iframe at the page top centers in visible content, not at 1100px',()=>{const r=visibleDialogViewport(child(host()));const p=dialogPlacement(r);assert.equal(p.y,400);assert.equal(p.height,768);assert(p.y+p.height/2<=800);});
test('scrolled iframe uses viewport position translated into iframe coordinates',()=>{const r=visibleDialogViewport(child(host(),-700));const p=dialogPlacement(r);assert.equal(p.y,1150);assert.equal(p.y-700,450);assert.equal(p.height,868);});
test('bottom of iframe remains within visible content',()=>{const r=visibleDialogViewport(child(host(),-1800));const p=dialogPlacement(r);assert.equal(p.y,2000);assert.equal(p.height,368);});
test('narrow screen and keyboard shrink both axes',()=>{const h=host();h.innerWidth=390;h.innerHeight=844;h.visualViewport={offsetLeft:0,offsetTop:0,width:390,height:390};const r=visibleDialogViewport(child(h,-300,12,366,2200));const p=dialogPlacement(r);assert.equal(p.width,334);assert.equal(p.height,358);assert.equal(p.y-300,195);});
test('zoom/pan visual viewport offset is included',()=>{const h=host();h.visualViewport={offsetLeft:100,offsetTop:80,width:600,height:480};const p=dialogPlacement(visibleDialogViewport(child(h,-300,0)));assert.equal(p.x,400);assert.equal(p.y-300,320);});
test('scrolling container clipping is respected',()=>{const h=host(),c=child(h,-400);h.getComputedStyle=()=>({overflowY:'auto',overflowX:'visible'});c.frameElement.parentElement={getBoundingClientRect:()=>box(280,90,1100,700),clientTop:0,clientLeft:0,parentElement:null};const p=dialogPlacement(visibleDialogViewport(c));assert.equal(p.y-400,440);assert.equal(p.height,668);});
test('sticky Streamlit toolbar is outside modal bounds',()=>{const h=host(),c=child(h,-400);c.frameElement.ownerDocument.querySelector=()=>({getBoundingClientRect:()=>box(0,0,1440,64)});const p=dialogPlacement(visibleDialogViewport(c));assert.equal(p.y-400,482);assert.equal(p.y-p.height/2-400,80);});
test('scaled iframe coordinates translate correctly',()=>{const h=host(),c=child(h,-200);c.frameElement.getBoundingClientRect=()=>box(280,-200,550,1100);const p=dialogPlacement(visibleDialogViewport(c));assert.equal(p.y*.5-200,450);});
test('offscreen iframe yields no placement instead of offscreen popup position',()=>{assert.equal(dialogPlacement(visibleDialogViewport(child(host(),1200))),null);});
test('cross origin access is optional and fails closed',()=>{const c={parent:{},get frameElement(){throw new Error('SecurityError');}};assert.equal(visibleDialogViewport(c),null);});
test('content is positioned before showModal, scroll stays inside popup, close clears timers',()=>{
 const d=w.document.querySelector('dialog'),surface=w.document.querySelector('#app');let atOpen,cleared=0,intervals=0;
 const win={parent:null,innerWidth:1024,innerHeight:768,visualViewport:null,document:w.document,requestAnimationFrame:()=>7,cancelAnimationFrame:()=>{},setInterval:()=>++intervals,clearInterval:()=>cleared++};win.parent=win;
 d.showModal=()=>{atOpen=d.style.getPropertyValue('--dialog-y');d.setAttribute('open','');};d.close=()=>{d.removeAttribute('open');d.dispatchEvent(new w.Event('close'));};
 const controller=attachDialogViewport(d,surface,win);controller.open();assert.equal(atOpen,'384px');assert.equal(d.style.getPropertyValue('--dialog-height'),'736px');assert.equal(d.scrollTop,0);assert.equal(w.document.activeElement.id,'dialog-title');
 controller.open();assert.equal(cleared,1);controller.close();assert.equal(cleared,2);controller.destroy();
});
test('cross-origin intersection refresh tracks equal-size scroll changes',()=>{
 const d=w.document.querySelector('dialog'),surface=w.document.querySelector('#app');let callback,poll,observations=0,disconnected=0;
 const win={parent:{},frameElement:null,document:w.document,requestAnimationFrame:()=>8,cancelAnimationFrame:()=>{},setInterval:fn=>(poll=fn,1),clearInterval:()=>{},IntersectionObserver:class{constructor(fn){callback=fn;}observe(){observations++;}unobserve(){}disconnect(){disconnected++;}}};
 const controller=attachDialogViewport(d,surface,win);controller.open();assert.equal(d.style.visibility,'hidden');callback([{isIntersecting:true,intersectionRect:box(0,400,1000,600)}]);assert.equal(d.style.getPropertyValue('--dialog-y'),'700px');assert.equal(d.style.visibility,'visible');
 poll();callback([{isIntersecting:true,intersectionRect:box(0,700,1000,600)}]);assert.equal(d.style.getPropertyValue('--dialog-y'),'1000px');assert(observations>=3);controller.close();assert.equal(disconnected,1);controller.destroy();
});
test('dialog CSS uses measured constraints and sticky close row',()=>{const css=fs.readFileSync(path.join(dir,'style.css'),'utf8');const sheet=new JSDOM('<style>'+css+'</style>');const rules=[...sheet.window.document.styleSheets[0].cssRules];const r=rules.find(r=>r.selectorText==='dialog');assert.equal(r.style.position,'fixed');assert.equal(r.style.margin,'0');assert(r.style.getPropertyValue('max-height').includes('--dialog-height'));assert.equal(r.style.getPropertyValue('overscroll-behavior'),'contain');assert.equal(rules.find(r=>r.selectorText==='.dialog-head').style.position,'sticky');sheet.window.close();});
console.log(`${count} dialog viewport checks passed`);w.close();
