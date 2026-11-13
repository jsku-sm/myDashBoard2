import {fitGeometry,contentWidth} from './geometry.js';
const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
let stop=()=>{};

export function mountViewport(host) {
  const doc=host.document;
  let raf=0,stage=null,content=null,observer=null,stopped=false;
  const prior=doc.documentElement.style.overflow;
  const app=doc.querySelector('[data-testid="stAppViewContainer"]');
  const appOverflow=app?.style.overflow;
  function schedule(){if(!raf&&!stopped)raf=host.requestAnimationFrame(fit);}
  function fit(){
    raf=0;if(stopped)return;
    const nextStage=doc.querySelector('.st-key-good_game_stage');
    const nextContent=doc.querySelector('.st-key-good_game_content');
    if(!nextStage||!nextContent){doc.documentElement.style.overflow=prior;if(app)app.style.overflow=appOverflow||'';return;}
    if(content!==nextContent){observer?.disconnect();content=nextContent;stage=nextStage;
      observer=new host.ResizeObserver(schedule);observer.observe(content);
    }
    const vv=host.visualViewport;
    const width=vv?.width||host.innerWidth,height=vv?.height||host.innerHeight;
    const x=vv?.offsetLeft||0,y=vv?.offsetTop||0;
    const header=doc.querySelector('[data-testid="stHeader"]');
    const headerBottom=header?.getBoundingClientRect().bottom||0;
    const top=Math.min(height*.15,Math.max(0,headerBottom-y))+6;
    const w=Math.max(1,width-12),h=Math.max(1,height-top-6);
    for(const [k,v] of Object.entries({inset:'auto',left:(x+6)+'px',top:(y+top)+'px',width:w+'px',height:h+'px'}))stage.style.setProperty(k,v,'important');
    const design=contentWidth(w,h);
    if(content.style.width!==design+'px')content.style.width=design+'px';
    // offset/scroll sizes are unscaled, avoiding feedback loops after transform.
    const naturalW=Math.max(design,content.scrollWidth,content.offsetWidth);
    const naturalH=Math.max(content.scrollHeight,content.offsetHeight);
    const fit=fitGeometry({width:stage.clientWidth,height:stage.clientHeight,contentWidth:naturalW,contentHeight:naturalH});
    content.style.transform=`translate(${fit.left}px,${fit.top}px) scale(${fit.scale})`;
    stage.dataset.fitScale=String(fit.scale);
    stage.dataset.fitHeight=String(naturalH);
    doc.documentElement.style.overflow='hidden';if(app)app.style.overflow='hidden';
    stage.scrollTop=0;stage.scrollLeft=0;
  }
  const mutations=new host.MutationObserver(schedule);
  // Watch replacement of Streamlit blocks; ignore game timers/text and our own styles.
  mutations.observe(doc.body,{childList:true,subtree:true});
  host.addEventListener('resize',schedule);
  host.visualViewport?.addEventListener('resize',schedule);
  host.visualViewport?.addEventListener('scroll',schedule);
  doc.fonts?.ready.then(schedule);
  schedule();
  return ()=>{if(stopped)return;stopped=true;host.cancelAnimationFrame(raf);observer?.disconnect();mutations.disconnect();
    host.removeEventListener('resize',schedule);host.visualViewport?.removeEventListener('resize',schedule);host.visualViewport?.removeEventListener('scroll',schedule);
    doc.documentElement.style.overflow=prior;if(app)app.style.overflow=appOverflow||'';
  };
}

function mount(){
  try{stop();parent.__goodMathViewportStop?.();stop=mountViewport(parent);parent.__goodMathViewportStop=stop;}
  catch{ /* Same-origin Streamlit host is required; do not alter other pages. */ }
}
window.addEventListener('message',e=>{if(e.source===parent&&e.data?.type==='streamlit:render')mount();});
window.addEventListener('pagehide',()=>stop());
post('streamlit:componentReady',{apiVersion:1});post('streamlit:setFrameHeight',{height:0});
