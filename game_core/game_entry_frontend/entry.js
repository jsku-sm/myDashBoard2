// Move to the newly opened game once. Never reposition/scale the panel itself,
// lock page scrolling, or move it over the dashboard's navigation.
export function revealEntry(host,{selector='.st-key-good_game_panel',timeout=1500}={}){
  let stopped=false,raf=0,stable=0,lastTop=null,lastHeight=null;
  const started=host.performance.now();
  const cancel=()=>{
    if(stopped)return;
    stopped=true;host.cancelAnimationFrame(raf);
    for(const type of ['wheel','touchstart','pointerdown','keydown'])host.removeEventListener(type,cancel,true);
  };
  for(const type of ['wheel','touchstart','pointerdown','keydown'])host.addEventListener(type,cancel,{capture:true,passive:true});
  function align(){
    if(stopped)return;
    const panel=host.document.querySelector(selector);
    if(panel){
      const scroller=panel.closest('[data-testid="stMain"]')||host.document.scrollingElement;
      if(!scroller){cancel();return;}
      const rect=panel.getBoundingClientRect(),container=scroller.getBoundingClientRect();
      const header=host.document.querySelector('[data-testid="stHeader"]')?.getBoundingClientRect();
      const inset=Math.max(0,container.top,header?.bottom||0)+12;
      const top=Math.max(0,scroller.scrollTop+rect.top-inset);
      // Repeat only until the arriving iframe's height settles. Cancel as soon
      // as the user scrolls/acts, and never run this on ordinary record updates.
      if(Math.abs(rect.top-inset)>2)scroller.scrollTo({top,behavior:'instant'});
      stable=lastTop!==null&&Math.abs(top-lastTop)<2&&Math.abs(rect.height-lastHeight)<2?stable+1:0;
      lastTop=top;lastHeight=rect.height;
      if(rect.height>180&&stable>=8&&host.performance.now()-started>=500){cancel();return;}
    }
    if(host.performance.now()-started>=timeout){cancel();return;}
    raf=host.requestAnimationFrame(align);
  }
  raf=host.requestAnimationFrame(align);
  return cancel;
}

let current=null,stop=()=>{};
const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
window.addEventListener('message',event=>{
  if(event.source!==parent||event.data?.type!=='streamlit:render')return;
  const entry=event.data.args?.entry;
  if(!entry||entry===current)return;
  current=entry;stop();
  try{stop=revealEntry(parent);}catch{/* Cross-origin hosts retain normal navigation. */}
  post('streamlit:setFrameHeight',{height:0});
});
window.addEventListener('pagehide',()=>stop());
post('streamlit:componentReady',{apiVersion:1});
post('streamlit:setFrameHeight',{height:0});
