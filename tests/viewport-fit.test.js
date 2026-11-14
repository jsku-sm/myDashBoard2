import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {fitGeometry,contentWidth} from '../../game_core/play_viewport_frontend/geometry.js';

test('explicit reward fullscreen geometry fits desktop/tablet/phone at 80–200% zoom',()=>{
  let checked=0;
  for(const [physicalWidth,physicalHeight] of [[1920,1080],[1440,900],[1366,768],[1024,768],[820,1180],[390,844],[844,390]]){
    for(const zoom of [.8,1,1.25,1.5,1.75,2]){
      const width=physicalWidth/zoom-12,height=physicalHeight/zoom-66;
      for(const naturalHeight of [420,650,840,1200,1900]){
        const naturalWidth=contentWidth(width,height);
        const fit=fitGeometry({width,height,contentWidth:naturalWidth,contentHeight:naturalHeight});
        assert(fit.left>=0&&fit.top>=0);
        assert(fit.left+fit.width<=width+1e-6);
        assert(fit.top+fit.height<=height+1e-6);
        // Every point from the first card through the last control remains visible.
        for(const [x,y] of [[0,0],[naturalWidth,naturalHeight],[naturalWidth/2,naturalHeight-1]]){
          assert(x*fit.scale+fit.left<=width+1e-6);
          assert(y*fit.scale+fit.top<=height+1e-6);
        }
        assert(Math.abs(fit.width/naturalWidth-fit.height/naturalHeight)<1e-12);
        checked++;
      }
    }
  }
  assert.equal(checked,210);
});

test('retired controller never moves or scales game content or locks dashboard menus',async()=>{
  const dom=new JSDOM('<!doctype html><body><main style="overflow:auto"><nav>tool menus</nav><div class="st-key-good_game_stage"><div class="st-key-good_game_content">game</div></div></main></body>',{pretendToBeVisual:true,url:'https://test.invalid'});
  const host=dom.window;globalThis.window=host;globalThis.parent=host;
  const before=host.document.documentElement.outerHTML;
  let frames=0;host.requestAnimationFrame=()=>{frames++;return 1;};
  const {mountViewport}=await import('../../game_core/play_viewport_frontend/viewport.js');
  const stop=mountViewport(host);
  host.dispatchEvent(new host.Event('resize'));
  stop();stop();
  assert.equal(frames,0);
  assert.equal(host.document.documentElement.outerHTML,before);
  let released=0;host.__goodMathViewportStop=()=>{released++;};
  host.dispatchEvent(new host.MessageEvent('message',{source:host,data:{type:'streamlit:render'}}));
  assert.equal(released,1);assert.equal(host.__goodMathViewportStop,undefined);
  assert.equal(host.document.documentElement.outerHTML,before);
  host.close();
});
