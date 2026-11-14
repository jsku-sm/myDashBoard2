// Reserve room for the title, question and controls; shrink only the play board,
// never the dashboard text or navigation. CSS pixels already include browser zoom.
export function boardHeight(viewportHeight,headerBottom,overhead){
  return Math.round(Math.max(200,Math.min(560,viewportHeight-Math.max(0,headerBottom)-32-overhead)));
}
export function sizePlayBoard(root,scope=window){
  const board=root.querySelector?.('.arc-board-wrap'),main=root.querySelector?.('.arc-play-main');
  if(!board||!main)return;
  try{
    const host=scope.parent,header=host.document.querySelector('[data-testid="stHeader"]');
    const viewportHeight=host.visualViewport?.height||host.innerHeight;
    const r=root.getBoundingClientRect(),b=board.getBoundingClientRect(),m=main.getBoundingClientRect();
    const overhead=b.top-r.top+m.bottom-b.bottom+28;
    const next=boardHeight(viewportHeight,header?.getBoundingClientRect().bottom||0,overhead)+'px';
    if(root.style.getPropertyValue('--play-board-height')!==next)root.style.setProperty('--play-board-height',next);
  }catch{/* Isolated hosts keep the natural board size. */}
}
