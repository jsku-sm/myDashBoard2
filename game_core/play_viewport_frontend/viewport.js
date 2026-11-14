// Retired viewport overlay. Keep a harmless bridge for previously deployed callers.
// Game panels now use normal Streamlit document flow; do not alter parent styles,
// scale content, move panels, lock scrolling, or attach resize observers.
export function mountViewport() { return () => {}; }

const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
window.addEventListener('message',event=>{
  if(event.source!==parent||event.data?.type!=='streamlit:render')return;
  // Release a controller left by a previous version, if one is still mounted.
  try { parent.__goodMathViewportStop?.(); delete parent.__goodMathViewportStop; } catch {}
  post('streamlit:setFrameHeight',{height:0});
});
post('streamlit:componentReady',{apiVersion:1});
post('streamlit:setFrameHeight',{height:0});
