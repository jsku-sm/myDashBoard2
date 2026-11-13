import {fitGeometry,contentWidth,mainPaneBounds} from './geometry.js';
const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
let stop=()=>{};

export function mountViewport(host) {
  const doc=host.document;
  let raf=0,stage=null,content=null,main=null,stopped=false;
  let mainOverflow='',layoutNodes=[],settleUntil=0;
  const sizeObserver=new host.ResizeObserver(schedule);
  const layoutObserver=new host.MutationObserver(settle);
  function schedule(){if(!raf&&!stopped)raf=host.requestAnimationFrame(fit);}
  // Sidebar transitions may move a pane without changing its size. Only animate
  // fitting during a layout change; no timer, network call or Streamlit rerun.
  function settle(){settleUntil=host.performance.now()+500;schedule();}
  function restoreMain(){if(main&&main.style.overflow!==mainOverflow)main.style.overflow=mainOverflow;}
  function visibleRect(node){
    if(!node)return null;
    const style=host.getComputedStyle(node);
    if(style.display==='none'||style.visibility==='hidden')return null;
    const rect=node.getBoundingClientRect();
    return rect.width>0&&rect.height>0?rect:null;
  }
  function watchLayout(nextMain,nodes){
    if(nextMain===main && nodes.every((node,i)=>node===layoutNodes[i]) && nodes.length===layoutNodes.length)return;
    restoreMain();main=nextMain;mainOverflow=main?.style.overflow||'';layoutNodes=nodes;
    sizeObserver.disconnect();layoutObserver.disconnect();
    if(content)sizeObserver.observe(content);
    for(const node of nodes){
      sizeObserver.observe(node);
      layoutObserver.observe(node,{attributes:true,attributeFilter:['class','style','aria-expanded','aria-hidden']});
    }
  }
  function fit(){
    raf=0;if(stopped)return;
    const nextStage=doc.querySelector('.st-key-good_game_stage');
    const nextContent=doc.querySelector('.st-key-good_game_content');
    if(!nextStage||!nextContent){restoreMain();return;}
    stage=nextStage;
    if(content!==nextContent){if(content)sizeObserver.unobserve(content);content=nextContent;sizeObserver.observe(content);}
    const nextMain=stage.closest('[data-testid="stMain"]')||stage.closest('main')||doc.querySelector('[data-testid="stMain"],.main');
    const sidebar=doc.querySelector('[data-testid="stSidebar"]');
    const header=doc.querySelector('[data-testid="stHeader"]');
    watchLayout(nextMain,[nextMain,sidebar,header].filter(Boolean));
    // Fail closed inside the main column if the host layout has not mounted yet.
    const rect=visibleRect(main);
    if(!rect){stage.style.visibility='hidden';return;}
    const vv=host.visualViewport;
    const bounds=mainPaneBounds({
      viewport:{width:vv?.width||host.innerWidth,height:vv?.height||host.innerHeight,left:vv?.offsetLeft||0,top:vv?.offsetTop||0},
      main:rect,sidebar:visibleRect(sidebar),header:visibleRect(header)
    });
    // A narrow phone can be entirely covered by its open navigation drawer.
    // Do not move the game behind that drawer to manufacture extra space.
    stage.style.visibility=bounds.visible?'visible':'hidden';
    if(bounds.visible){
      for(const [k,v] of Object.entries({position:'fixed',inset:'auto',left:bounds.left+'px',top:bounds.top+'px',width:bounds.width+'px',height:bounds.height+'px',maxWidth:'none'})){
        stage.style.setProperty(k==='maxWidth'?'max-width':k,v,'important');
      }
      const design=contentWidth(bounds.width,bounds.height);
      if(content.style.width!==design+'px')content.style.width=design+'px';
      const naturalW=Math.max(design,content.scrollWidth,content.offsetWidth);
      const naturalH=Math.max(content.scrollHeight,content.offsetHeight);
      const fitted=fitGeometry({width:stage.clientWidth,height:stage.clientHeight,contentWidth:naturalW,contentHeight:naturalH});
      content.style.transform=`translate(${fitted.left}px,${fitted.top}px) scale(${fitted.scale})`;
      stage.dataset.fitScale=String(fitted.scale);stage.dataset.fitHeight=String(naturalH);
      stage.scrollTop=0;stage.scrollLeft=0;
    }
    // Keep the left menu scrollable and clickable. Lock only the game column.
    if(main.style.overflow!=='hidden')main.style.overflow='hidden';
    if(host.performance.now()<settleUntil)schedule();
  }
  const mutations=new host.MutationObserver(schedule);
  mutations.observe(doc.body,{childList:true,subtree:true});
  function transition(event){if(layoutNodes.includes(event.target))settle();}
  doc.addEventListener('transitionrun',transition,true);
  doc.addEventListener('transitionend',transition,true);
  doc.addEventListener('scroll',schedule,true);
  host.addEventListener('resize',schedule);
  host.visualViewport?.addEventListener('resize',schedule);
  host.visualViewport?.addEventListener('scroll',schedule);
  doc.fonts?.ready.then(schedule);
  schedule();
  return ()=>{if(stopped)return;stopped=true;host.cancelAnimationFrame(raf);sizeObserver.disconnect();layoutObserver.disconnect();mutations.disconnect();
    host.removeEventListener('resize',schedule);host.visualViewport?.removeEventListener('resize',schedule);host.visualViewport?.removeEventListener('scroll',schedule);
    doc.removeEventListener('transitionrun',transition,true);doc.removeEventListener('transitionend',transition,true);doc.removeEventListener('scroll',schedule,true);
    restoreMain();
  };
}

function mount(){
  try{stop();parent.__goodMathViewportStop?.();stop=mountViewport(parent);parent.__goodMathViewportStop=stop;}
  catch{ /* Same-origin Streamlit host is required; keep the pane inside its column. */ }
}
window.addEventListener('message',e=>{if(e.source===parent&&e.data?.type==='streamlit:render')mount();});
window.addEventListener('pagehide',()=>stop());
post('streamlit:componentReady',{apiVersion:1});post('streamlit:setFrameHeight',{height:0});
