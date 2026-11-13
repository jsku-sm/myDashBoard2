/** Fit the entire uncut content into the visual viewport, including browser zoom. */
export function fitGeometry({width,height,contentWidth,contentHeight,padding=10}) {
  const w=Math.max(1,width-2*padding),h=Math.max(1,height-2*padding);
  const cw=Math.max(1,contentWidth),ch=Math.max(1,contentHeight);
  // Never impose a minimum scale: doing so clips content on short/zoomed displays.
  const scale=Math.min(1,w/cw,h/ch);
  return {scale,left:padding+(w-cw*scale)/2,top:padding,
          width:cw*scale,height:ch*scale};
}

export function contentWidth(width,height) {
  // A stable compact layout prevents stacking a giant board and controls vertically.
  return Math.min(1180,Math.max(width>height?900:680,width-20));
}

/** Visible main-column rectangle; never allocate space behind the navigation. */
export function mainPaneBounds({viewport,main,sidebar,header,gap=8}) {
  const vx=viewport.left||0,vy=viewport.top||0;
  const right=Math.min(vx+viewport.width,main.right);
  const bottom=Math.min(vy+viewport.height,main.bottom);
  let left=Math.max(vx,main.left),top=Math.max(vy,main.top);
  if(sidebar && sidebar.bottom>top && sidebar.top<bottom && sidebar.right>left && sidebar.left<right){
    left=Math.max(left,sidebar.right);
  }
  if(header && header.right>left && header.left<right && header.bottom>top && header.top<bottom){
    top=Math.max(top,header.bottom);
  }
  const width=Math.max(0,right-left-2*gap),height=Math.max(0,bottom-top-2*gap);
  return {left:left+gap,top:top+gap,width,height,visible:width>32&&height>32};
}
