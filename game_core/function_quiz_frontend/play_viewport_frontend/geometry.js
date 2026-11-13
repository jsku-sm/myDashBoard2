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
