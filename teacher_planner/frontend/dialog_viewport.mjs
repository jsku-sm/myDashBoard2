// A Streamlit component iframe can be much taller than the browser viewport.
// Position its dialog in the visible portion, never in the whole iframe.
const modalBox = (left, top, right, bottom) => ({left, top, right, bottom, width:Math.max(0,right-left), height:Math.max(0,bottom-top)});
const modalIntersect = (a,b) => modalBox(Math.max(a.left,b.left),Math.max(a.top,b.top),Math.min(a.right,b.right),Math.min(a.bottom,b.bottom));
export function dialogPlacement(rect, gap=16) {
  if(!rect || rect.width<=0 || rect.height<=0)return null;
  const pad=Math.min(gap,rect.width/8,rect.height/8);
  return {x:rect.left+rect.width/2,y:rect.top+rect.height/2,width:Math.max(1,rect.width-2*pad),height:Math.max(1,rect.height-2*pad)};
}

// Read-only geometry. Cross-origin frames use IntersectionObserver instead.
export function visibleDialogViewport(win) {
  try {
    const width=win.innerWidth, height=win.innerHeight;
    if(win===win.parent){const v=win.visualViewport;return v?modalBox(v.offsetLeft,v.offsetTop,v.offsetLeft+v.width,v.offsetTop+v.height):modalBox(0,0,width,height);}
    const frame=win.frameElement;
    if(!frame)return null;
    const host=frame.ownerDocument.defaultView, parentRect=visibleDialogViewport(host);
    if(!parentRect)return null;
    const bounds=frame.getBoundingClientRect();
    const sx=frame.offsetWidth?bounds.width/frame.offsetWidth:1,sy=frame.offsetHeight?bounds.height/frame.offsetHeight:1;
    if(sx<=0||sy<=0)return null;
    const x=bounds.left+(frame.clientLeft||0)*sx,y=bounds.top+(frame.clientTop||0)*sy;
    let shown=modalIntersect(parentRect,modalBox(x,y,x+width*sx,y+height*sy));
    for(let p=frame.parentElement;p;p=p.parentElement){
      const css=host.getComputedStyle(p), r=p.getBoundingClientRect();
      if(/auto|scroll|hidden|clip/.test(css.overflowX))shown=modalIntersect(shown,modalBox(r.left+(p.clientLeft||0),shown.top,r.right,shown.bottom));
      if(/auto|scroll|hidden|clip/.test(css.overflowY))shown=modalIntersect(shown,modalBox(shown.left,r.top+(p.clientTop||0),shown.right,r.bottom));
    }
    // Streamlit's sticky toolbar may cover the top of the scrolling app surface.
    const header=frame.ownerDocument.querySelector('[data-testid="stHeader"]');
    if(header){const r=header.getBoundingClientRect(),css=host.getComputedStyle(header);if(css.visibility!=='hidden'&&css.display!=='none'&&r.height>0&&r.height<parentRect.height/3&&r.top<=parentRect.top&&r.right>shown.left&&r.left<shown.right)shown=modalIntersect(shown,modalBox(shown.left,r.bottom,shown.right,shown.bottom));}
    if(shown.width<=0||shown.height<=0)return modalBox(0,0,0,0);
    return modalBox((shown.left-x)/sx,(shown.top-y)/sy,(shown.right-x)/sx,(shown.bottom-y)/sy);
  }catch{return null;}
}

export function attachDialogViewport(dialog, surface, win=window) {
  let observer=null,timer=null,raf=null,stops=[],disposed=false;
  const apply=rect=>{
    const p=dialogPlacement(rect);
    if(!p)return false;
    for(const [key,value] of Object.entries(p))dialog.style.setProperty('--dialog-'+key,value+'px');
    dialog.style.visibility='visible';return true;
  };
  const measure=()=>{
    if(disposed||!dialog.open)return;
    const rect=visibleDialogViewport(win);
    if(rect){apply(rect);return;}
    // Refresh observation even when scrolling leaves the intersection ratio
    // unchanged (a long page may fill the viewport at many scroll positions).
    if(observer){observer.unobserve(surface);observer.observe(surface);}
  };
  const refresh=()=>{
    if(!dialog.open||raf!==null||disposed)return;
    raf=win.requestAnimationFrame(()=>{raf=null;measure();});
  };
  const listen=(target,event,fn,capture=false)=>{
    if(!target?.addEventListener)return;
    target.addEventListener(event,fn,{capture,passive:true});
    stops.push(()=>target.removeEventListener(event,fn,capture));
  };
  const stop=()=>{
    observer?.disconnect();observer=null;
    if(timer!==null)win.clearInterval(timer);timer=null;
    if(raf!==null)win.cancelAnimationFrame(raf);raf=null;
    stops.forEach(fn=>fn());stops=[];
  };
  const watch=()=>{
    stop();
    if(win.IntersectionObserver){observer=new win.IntersectionObserver(entries=>{
      if(!dialog.open||visibleDialogViewport(win))return;
      const e=entries.at(-1);if(e?.isIntersecting)apply(e.intersectionRect);
    },{root:null,threshold:[0,1]});observer.observe(surface);}
    let w=win;
    while(w){
      try{
        listen(w,'resize',refresh);listen(w.document,'scroll',refresh,true);
        listen(w.visualViewport,'resize',refresh);listen(w.visualViewport,'scroll',refresh);
        if(w===w.parent||!w.frameElement)break;w=w.parent;
      }catch{break;}
    }
    // Also handles parent layout shifts and iframe size updates without scroll.
    timer=win.setInterval(measure,120);
  };
  const open=()=>{
    const alreadyOpen=dialog.open;
    const rect=visibleDialogViewport(win);
    if(!apply(rect))dialog.style.visibility='hidden';
    // Focus the heading, not a lower input that might scroll the outer page.
    const heading=dialog.querySelector('#dialog-title');
    if(heading){heading.setAttribute('tabindex','-1');heading.setAttribute('autofocus','');}
    if(!alreadyOpen)dialog.showModal();
    dialog.scrollTop=0;
    if(heading)heading.focus({preventScroll:true});
    watch();measure();refresh();
  };
  dialog.addEventListener('close',stop);
  return {open,refresh,close(){stop();dialog.close();},destroy(){stop();disposed=true;dialog.removeEventListener('close',stop);}};
}
