import test from 'node:test';
import assert from 'node:assert/strict';
import { ARCADE_THEMES, ARCADE_AUDIO_KEY, createArcadeAudio } from '../src/arcade-audio.js';

function harness({ saved, deferred = false } = {}) {
  const intervals = new Map(), sources = [], values = new Map(saved ? [[ARCADE_AUDIO_KEY, JSON.stringify(saved)]] : []);
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
  const audio = createArcadeAudio({ scope, storage, contextFactory: () => { creations++; return context; } });
  const advance = seconds => {
    context.currentTime += seconds;
    // Deliver ended events as a browser would, freeing voice connections.
    for (const s of sources) if (!s.ended && Math.min(...s.stops) <= context.currentTime) { s.ended = true; s.onended?.(); }
    [...intervals.values()].forEach(fn => fn());
  };
  return { audio, context, intervals, sources, values, scope, advance, resolve: () => resolveResume(), creations: () => creations };
}

test('all 12 games have distinct, complete musical arrangements', () => {
  const ids = ['bubble', 'invaders', 'maze', 'marble', 'shot', 'memory', 'territory', 'counter', 'set-memory', 'logic-memory', 'root-marble', 'root-maze'];
  assert.deepEqual(Object.keys(ARCADE_THEMES).sort(), ids.sort());
  assert.equal(new Set(Object.values(ARCADE_THEMES).map(t => JSON.stringify([t.bpm, t.root, t.wave, t.notes, t.chords]))).size, 12);
  for (const t of Object.values(ARCADE_THEMES)) {
    assert.ok(t.bpm >= 60 && t.bpm <= 150);
    assert.ok(t.notes.length === 16 && t.notes.every(n => n === null || Number.isFinite(n)));
    assert.ok(t.chords.length === 4 && t.chords.every(Number.isFinite));
  }
});

test('music starts only after a gesture and never stacks loops across pauses or scene changes', async () => {
  const h = harness(); h.audio.setScene('bubble', 'playing');
  assert.equal(h.creations(), 0); assert.equal(h.intervals.size, 0);
  await h.audio.unlock(); assert.equal(h.creations(), 1); assert.equal(h.intervals.size, 1); assert.ok(h.sources.length > 0);
  const old = [...h.sources];
  h.audio.setScene('bubble', 'playing'); await h.audio.unlock(); assert.equal(h.intervals.size, 1);
  h.audio.setScene('bubble', 'paused'); assert.equal(h.intervals.size, 0);
  assert.ok(old.every(s => Math.min(...s.stops) <= h.context.currentTime + .025));
  h.audio.setScene('memory', 'playing'); assert.equal(h.intervals.size, 1); assert.equal(h.creations(), 1);
  h.audio.stop(); assert.equal(h.intervals.size, 0);
  const count = h.sources.length; h.audio.cue('win'); assert.equal(h.sources.length, count);
});

test('music, effects and zero volume are independently respected and preferences persist', async () => {
  const h = harness(); h.audio.setScene('maze', 'playing'); await h.audio.unlock();
  h.audio.updateSettings({ music: false }); assert.equal(h.intervals.size, 0);
  let count = h.sources.length; h.audio.cue('collect'); assert.ok(h.sources.length > count);
  h.audio.updateSettings({ effects: false, music: true }); assert.equal(h.intervals.size, 1);
  count = h.sources.length; h.audio.cue('collect'); assert.equal(h.sources.length, count);
  h.audio.updateSettings({ volume: 0 }); assert.equal(h.intervals.size, 0);
  h.advance(1); h.audio.cue('win'); assert.equal(h.sources.length, count);
  assert.deepEqual(JSON.parse(h.values.get(ARCADE_AUDIO_KEY)), { music: true, effects: false, volume: 0 });
  h.audio.updateSettings({ volume: .3 }); assert.equal(h.intervals.size, 1);
  const fresh = harness({ saved: JSON.parse(h.values.get(ARCADE_AUDIO_KEY)) });
  assert.deepEqual(fresh.audio.settings, { music: true, effects: false, volume: .3 });
});

test('a delayed unlock, hidden tab and interrupted audio cannot revive a stopped game', async () => {
  const h = harness({ deferred: true }); h.audio.setScene('invaders', 'playing');
  const pending = h.audio.unlock(); h.audio.stop(); h.resolve(); await pending;
  assert.equal(h.intervals.size, 0); assert.equal(h.sources.length, 0);
  h.audio.setScene('invaders', 'playing'); assert.equal(h.intervals.size, 1);
  h.context.state = 'interrupted'; h.context.onstatechange(); assert.equal(h.intervals.size, 0);
  h.audio.setScene('invaders', 'paused'); h.context.state = 'running'; h.context.onstatechange(); assert.equal(h.intervals.size, 0);
  h.audio.setScene('invaders', 'playing'); h.scope.document.hidden = true; h.advance(2);
  assert.equal(h.intervals.size, 0); const count = h.sources.length; h.audio.cue('shoot'); assert.equal(h.sources.length, count);
});

test('effects stay bounded under repeated inputs and every cue produces finite audio schedules', async () => {
  const h = harness({ saved: { music: false, effects: true, volume: .4 } }); h.audio.setScene('root-marble', 'playing'); await h.audio.unlock();
  for (const cue of ['start', 'shoot', 'pop', 'hit', 'step', 'bump', 'collect', 'roll', 'launch', 'flip', 'match', 'miss', 'damage', 'paint', 'capture', 'tune', 'stage', 'win', 'lose']) {
    const count = h.sources.length; h.audio.cue(cue); assert.ok(h.sources.length > count, cue); h.advance(2);
  }
  const count = h.sources.length; for (let i = 0; i < 200; i++) h.audio.cue('step'); assert.equal(h.sources.length - count, 1);
  assert.ok(h.sources.every(s => Number.isFinite(s.startedAt) && s.stops.every(Number.isFinite)));
});

test('unsupported browsers and blocked storage preserve silent game operation', async () => {
  const silent = createArcadeAudio({ scope: {} }); assert.equal(silent.status.supported, false);
  silent.setScene('bubble', 'playing'); assert.equal(await silent.unlock(), false); assert.doesNotThrow(() => silent.cue('shoot'));
  const h = harness({ saved: { volume: -4, music: 'not-a-boolean' } }); assert.deepEqual(h.audio.settings, { ...{ music: true, effects: true }, volume: 0 });
  const blocked = createArcadeAudio({ scope: {}, storage: { getItem() { throw Error(); }, setItem() { throw Error(); } } });
  assert.doesNotThrow(() => blocked.updateSettings({ effects: false }));
});

test('correct and incorrect quiz answers use distinct cues without starting background music', async () => {
  const h = harness({ saved: { music: true, effects: true, volume: .4 } });
  h.audio.setScene('memory', 'quiz-feedback'); await h.audio.unlock(); assert.equal(h.intervals.size, 0);
  h.audio.cue('match'); const correct = h.sources.slice(); assert.equal(correct.length, 4); assert.ok(correct.every(s => s.type === 'sine'));
  h.advance(2); const count = h.sources.length; h.audio.cue('miss'); const incorrect = h.sources.slice(count); assert.equal(incorrect.length, 2); assert.ok(incorrect.every(s => s.type === 'triangle'));
});
