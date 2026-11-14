import test from 'node:test';
import assert from 'node:assert/strict';
import {createRewardAudio,REWARD_AUDIO_KEY,soundSnapshot,stepSounds,clockSounds,liveSoundWindow} from '../src/audio.js';
import {initial,step} from '../src/simulation.js';

function harness({ saved, deferred = false } = {}) {
  const intervals = new Map(), sources = [], values = new Map(saved ? [[REWARD_AUDIO_KEY, JSON.stringify(saved)]] : []);
  let timerId = 0, creations = 0, resolveResume;
  const param = () => ({ value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {}, cancelScheduledValues() {}, setTargetAtTime() {} });
  const node = () => ({ connect() {}, disconnect() {} });
  const source = () => { const s = { ...node(), frequency: param(), stops: [], start(at) { this.startedAt = at; }, stop(at) { this.stops.push(at); } }; sources.push(s); return s; };
  const context = {
    state: 'suspended', currentTime: 0, sampleRate: 44100, destination: node(),
    createGain: () => ({ ...node(), gain: param() }),
    createBiquadFilter: () => ({ ...node(), frequency: param() }),
    createDynamicsCompressor: () => ({ ...node(), threshold: param(), knee: param(), ratio: param() }),
    createOscillator: source, createBufferSource: source,
    createBuffer: (_, length) => ({ getChannelData: () => new Float32Array(length) }),
    async resume() {
      if (deferred) await new Promise(resolve => { resolveResume = resolve; });
      this.state = 'running'; this.onstatechange?.();
    }
  };
  const scope = { document: { hidden: false }, setInterval(fn) { intervals.set(++timerId, fn); return timerId; }, clearInterval(id) { intervals.delete(id); } };
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const audio = createRewardAudio({ scope, storage, contextFactory: () => { creations++; return context; } });
  const advance = seconds => {
    context.currentTime += seconds;
    // Deliver ended events as a browser would, freeing voice connections.
    for (const s of sources) if (!s.ended && Math.min(...s.stops) <= context.currentTime) { s.ended = true; s.onended?.(); }
    [...intervals.values()].forEach(fn => fn());
  };
  return { audio, context, intervals, sources, values, scope, advance, resolve: () => resolveResume(), creations: () => creations };
}

test('reward effects need a gesture, never run music, and have independent saved preferences',async()=>{
  const h=harness();h.audio.setScene('space');h.audio.cue('shoot');
  assert.equal(h.creations(),0);assert.equal(h.sources.length,0);
  await h.audio.unlock();h.audio.cue('shoot');assert(h.sources.length>0);assert.equal(h.intervals.size,0);
  h.audio.updateSettings({effects:false,volume:.3});const n=h.sources.length;
  h.advance(1);h.audio.cue('shoot');assert.equal(h.sources.length,n);
  const saved=JSON.parse(h.values.get(REWARD_AUDIO_KEY));assert.deepEqual(saved,{effects:false,volume:.3});
  assert.deepEqual(harness({saved}).audio.settings,saved);
  assert.equal(h.values.has('goodssaem-arcade-audio-v1'),false);
  h.audio.updateSettings({effects:true,volume:0});h.audio.cue('finish');assert.equal(h.sources.length,n);
});

test('all action cues synthesize bounded finite sounds without network or music loops',async()=>{
  const h=harness();h.audio.setScene('jump');await h.audio.unlock();
  for(const cue of ['jump','lane','boost','shoot','bounce','step','collect','hit','damage','key','stage','combo','countdown','start','finish','correct','wrong']){
    const n=h.sources.length;h.audio.cue(cue);assert(h.sources.length>n,cue);h.advance(2);
  }
  const n=h.sources.length;for(let i=0;i<200;i++)h.audio.cue('shoot');assert.equal(h.sources.length-n,1);
  assert.equal(h.intervals.size,0);assert(h.sources.every(s=>Number.isFinite(s.startedAt)&&s.stops.every(Number.isFinite)));
});

test('mute, hiding and leaving stop voices; delayed unlock cannot revive a departed game',async()=>{
  const h=harness({deferred:true});h.audio.setScene('space');const pending=h.audio.unlock();
  h.audio.stop();h.resolve();await pending;h.audio.cue('shoot');assert.equal(h.sources.length,0);
  h.audio.setScene('maze');h.audio.cue('step');assert.equal(h.sources.length,0);
  await h.audio.unlock();h.audio.cue('step');assert(h.sources.length>0);
  h.scope.document.hidden=true;const n=h.sources.length;h.audio.cue('collect');assert.equal(h.sources.length,n);
  h.audio.stop();assert(h.sources.every(s=>Math.min(...s.stops)<=h.context.currentTime+.025));
});

test('actual deterministic steps trigger jump, lane, shot, bounce, collision and collect cues',()=>{
  const observed=new Set();
  for(const gid of ['jump','kart','space','blocks','maze']){
    const state=initial(gid,33),reference=initial(gid,33);
    for(let i=0;i<1800;i++){
      const key=[2,4,1,8,0][Math.floor(i/7)%5],before=soundSnapshot(state);
      step(state,key);step(reference,key);for(const cue of stepSounds(before,state))observed.add(cue);
    }
    assert.deepEqual(state,reference,'sound observation cannot change scores, input or replay state');
  }
  for(const cue of ['jump','lane','shoot','bounce','damage','collect','step','hit'])assert(observed.has(cue),cue);
  assert(!stepSounds({game:'kart',hits:0,combo:0,boost:0,lane:1,level:1},{game:'kart',hits:0,combo:0,boost:0,lane:1,level:1,score:2}).includes('collect'),'passive driving points are silent');
  assert.deepEqual(stepSounds({game:'maze',hits:0,combo:0,key:false,x:1,y:1,level:1},{game:'maze',hits:0,combo:1,key:true,x:1,y:1,level:1}),['key']);
});

test('countdown and finish sound once, and catch-up ticks do not replay a sound burst',()=>{
  const clock={previous:6,finished:false};
  assert.deepEqual(clockSounds(clock,5),['countdown']);assert.deepEqual(clockSounds(clock,4.9),[]);
  assert.deepEqual(clockSounds(clock,0),['finish']);assert.deepEqual(clockSounds(clock,-1),[]);
  assert.equal(liveSoundWindow(0,80,false),false);assert.equal(liveSoundWindow(70,72,true),false);assert.equal(liveSoundWindow(70,72,false),true);
  assert.deepEqual(clockSounds({previous:90,finished:false},3),[],'skip missed countdown notes');
});

test('unsupported audio and denied storage never block the game',async()=>{
  const a=createRewardAudio({scope:{},storage:{getItem(){throw Error('denied');},setItem(){throw Error('denied');}}});
  assert.equal(await a.unlock(),false);assert.doesNotThrow(()=>{a.cue('jump');a.updateSettings({effects:false});a.stop();});
});

