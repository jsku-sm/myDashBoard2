import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {fitGeometry,contentWidth} from '../../game_core/play_viewport_frontend/geometry.js';

test('entire game stays inside desktop/tablet/phone bounds at 80–200% browser zoom',()=>{
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

test('actual viewport controller refits on zoom, rotation, content growth and cleans up',async()=>{
  const dom=new JSDOM('<!doctype html><body><header data-testid="stHeader"></header><main data-testid="stAppViewContainer"><div class="st-key-good_game_stage"><div class="st-key-good_game_content"></div></div></main></body>',{pretendToBeVisual:true,url:'https://test.invalid'});
  const host=dom.window;globalThis.window=host;globalThis.parent=host;
  let frame=null,resizeCallback=null,disconnected=false,naturalHeight=720;
  host.requestAnimationFrame=cb=>{frame=cb;return 1};host.cancelAnimationFrame=()=>{frame=null};
  host.ResizeObserver=class{constructor(cb){resizeCallback=cb}observe(){}disconnect(){disconnected=true}};
  const vv=new host.EventTarget();Object.assign(vv,{width:1440,height:900,offsetLeft:0,offsetTop:0});
  Object.defineProperty(host,'visualViewport',{value:vv});
  const stage=host.document.querySelector('.st-key-good_game_stage'),content=stage.firstElementChild;
  host.document.querySelector('header').getBoundingClientRect=()=>({bottom:54});
  Object.defineProperties(stage,{clientWidth:{get:()=>parseFloat(stage.style.width)-6},clientHeight:{get:()=>parseFloat(stage.style.height)-6}});
  Object.defineProperties(content,{scrollWidth:{get:()=>parseFloat(content.style.width)},offsetWidth:{get:()=>parseFloat(content.style.width)},scrollHeight:{get:()=>naturalHeight},offsetHeight:{get:()=>naturalHeight}});
  const {mountViewport}=await import('../../game_core/play_viewport_frontend/viewport.js');
  const stop=mountViewport(host);
  function fitted(){assert(frame);const f=frame;frame=null;f();
    const scale=Number(stage.dataset.fitScale),matrix=content.style.transform.match(/translate\(([^p]+)px,([^p]+)px\)/);
    assert(matrix,content.style.transform);
    assert(Number(matrix[1])+content.offsetWidth*scale<=stage.clientWidth+.01);
    assert(Number(matrix[2])+naturalHeight*scale<=stage.clientHeight+.01);
    assert(parseFloat(stage.style.left)>=vv.offsetLeft);
    assert(parseFloat(stage.style.top)>=vv.offsetTop);
    assert(parseFloat(stage.style.top)+parseFloat(stage.style.height)<=vv.offsetTop+vv.height+.01);
    assert.equal(stage.scrollTop,0);assert.equal(stage.scrollLeft,0);
    return scale;
  }
  const initial=fitted();
  vv.width=960;vv.height=600;vv.dispatchEvent(new host.Event('resize'));assert(fitted()<initial);
  naturalHeight=1200;resizeCallback();fitted();
  Object.assign(vv,{width:390,height:844,offsetLeft:12,offsetTop:40});vv.dispatchEvent(new host.Event('scroll'));fitted();
  Object.assign(vv,{width:844,height:390,offsetLeft:0,offsetTop:0});host.dispatchEvent(new host.Event('resize'));fitted();
  assert.equal(host.document.documentElement.style.overflow,'hidden');
  stop();assert(disconnected);assert.equal(host.document.documentElement.style.overflow,'');
  assert.equal(host.document.querySelector('main').style.overflow,'');
  const next=mountViewport(host);fitted();stop();assert.equal(host.document.documentElement.style.overflow,'hidden');next();
  dom.window.close();
});
