import test from 'node:test';
import assert from 'node:assert/strict';
import {boardHeight,sizePlayBoard} from '../src/board-size.js';
test('board shrinks in CSS pixels as zoom increases, reserving question and controls',()=>{
  for(const zoom of [.8,1,1.25,1.5]){
    const height=1080/zoom,overhead=300,board=boardHeight(height,56,overhead);
    assert(board>=200&&board<=560);assert(board+56+32+overhead<=height);
  }
  assert(boardHeight(768,56,300)<boardHeight(1080,56,300));
  assert.equal(boardHeight(320,56,300),200,'keep a usable board at extreme small viewport heights');
});
test('cross-origin host access does not break loading a game',()=>{
  assert.doesNotThrow(()=>sizePlayBoard({querySelector:()=>({})},{get parent(){throw Error('blocked');}}));
});
