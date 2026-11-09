// Original, locally synthesized game music. No downloads or external audio assets.
const bright = [0, 4, 7, 12, 9, 7, 4, null, 2, 5, 9, 14, 12, 9, 7, 4];
const quest = [0, null, 7, 12, 10, 7, 3, null, 5, 7, 10, null, 7, 5, 3, 2];
const calm = [0, null, 7, null, 12, 9, 7, null, 4, null, 9, null, 7, 4, 2, null];
const pulse = [0, 7, 12, 7, 3, 10, 15, 10, 5, 12, 17, 12, 7, 14, 19, 14];
export const ARCADE_THEMES = {
  bubble: { name: '버블팝 · 통통 튀는 칩튠', bpm: 116, root: 72, wave: 'sine', notes: bright, chords: [0, 5, 7, 0], drums: true },
  invaders: { name: '갤럭시 · 우주 신스', bpm: 132, root: 64, wave: 'square', notes: pulse, chords: [0, 5, 3, 7], minor: true, drums: true },
  maze: { name: '미로 · 작은 탐험', bpm: 94, root: 67, wave: 'triangle', notes: quest, chords: [0, 5, 3, 7], minor: true },
  marble: { name: '그래프 · 반짝이는 물결', bpm: 82, root: 72, wave: 'sine', notes: calm, chords: [0, 5, 2, 7] },
  shot: { name: '포물선 · 가벼운 모험', bpm: 108, root: 69, wave: 'triangle', notes: bright.slice().reverse(), chords: [0, 5, 0, 7], drums: true },
  memory: { name: '메모리 · 오르골 정원', bpm: 78, root: 76, wave: 'sine', notes: calm.slice().reverse(), chords: [0, 5, 7, 0] },
  territory: { name: '영역 · 리듬 속 개척', bpm: 110, root: 60, wave: 'triangle', notes: [0, 7, null, 12, 4, 7, null, 9, 5, 12, null, 14, 7, 9, 7, null], chords: [0, 5, 7, 0], drums: true },
  counter: { name: '반례 · 우주 탐정', bpm: 122, root: 62, wave: 'square', notes: pulse.slice().reverse(), chords: [0, 3, 5, 7], minor: true, drums: true },
  'set-memory': { name: '집합 카드 · 숲의 실로폰', bpm: 86, root: 74, wave: 'triangle', notes: calm, chords: [0, 2, 5, 7] },
  'logic-memory': { name: '논리 카드 · 생각의 오르골', bpm: 80, root: 71, wave: 'sine', notes: [0, null, 3, 7, 12, null, 10, 7, 5, null, 10, 14, 12, null, 7, 3], chords: [0, 5, 3, 7], minor: true },
  'root-marble': { name: '루트 레일 · 맑은 별빛', bpm: 76, root: 74, wave: 'sine', notes: [0, null, 2, 7, 9, null, 14, 12, 7, null, 4, 9, 12, null, 7, 2], chords: [0, 5, 2, 7] },
  'root-maze': { name: '루트 미로 · 신비한 발걸음', bpm: 98, root: 69, wave: 'triangle', notes: quest.slice().reverse(), chords: [0, 3, 7, 5], minor: true }
};
export const ARCADE_AUDIO_KEY = 'goodssaem-arcade-audio-v1';
const frequency = midi => 440 * 2 ** ((midi - 69) / 12);
const defaults = { music: true, effects: true, volume: .45 };

export function createArcadeAudio({ scope = globalThis, storage, contextFactory, onChange = () => {} } = {}) {
  try { storage ??= scope.localStorage; } catch { /* Private browsing can deny storage. */ }
  const AudioContextClass = scope.AudioContext || scope.webkitAudioContext;
  const supported = !!(contextFactory || AudioContextClass);
  let context = null, master, musicBus, effectsBus, noiseBuffer;
  let settings = { ...defaults };
  try {
    const saved = JSON.parse(storage?.getItem(ARCADE_AUDIO_KEY));
    if (saved && typeof saved === 'object') {
      for (const channel of ['music', 'effects']) if (typeof saved[channel] === 'boolean') settings[channel] = saved[channel];
      if (Number.isFinite(saved.volume)) settings.volume = Math.max(0, Math.min(1, saved.volume));
    }
  } catch { /* Ignore an old or corrupt preference. */ }
  let game = null, phase = 'idle', timer = null, step = 0, nextNote = 0;
  const voices = new Set(), cooldowns = new Map();
  const theme = () => ARCADE_THEMES[game];
  const ready = () => context?.state === 'running';
  const audible = channel => supported && ready() && game && settings[channel] && settings.volume > 0 && !scope.document?.hidden;

  function stopVoices(channel) {
    for (const voice of voices) {
      if (channel && voice.channel !== channel) continue;
      voice.envelope.gain.cancelScheduledValues(context.currentTime);
      voice.envelope.gain.setTargetAtTime(.0001, context.currentTime, .004);
      try { voice.source.stop(context.currentTime + .025); } catch { /* Already ended. */ }
      voices.delete(voice);
    }
  }
  function stopMusic() {
    if (timer !== null) scope.clearInterval(timer);
    timer = null;
    stopVoices('music');
  }
  function connectVoice(source, at, duration, volume, channel, cutoff) {
    // Bound polyphony even when a key is held down or several collisions coincide.
    if (voices.size >= 64) { source.disconnect(); return; }
    const envelope = context.createGain(), filter = context.createBiquadFilter();
    filter.type = 'lowpass'; filter.frequency.value = cutoff;
    source.connect(filter); filter.connect(envelope); envelope.connect(channel === 'music' ? musicBus : effectsBus);
    envelope.gain.setValueAtTime(.0001, at);
    envelope.gain.linearRampToValueAtTime(volume, at + Math.min(.012, duration / 5));
    envelope.gain.exponentialRampToValueAtTime(.0001, at + duration);
    const voice = { source, envelope, channel };
    voices.add(voice);
    source.onended = () => { voices.delete(voice); source.disconnect(); filter.disconnect(); envelope.disconnect(); };
    source.start(at); source.stop(at + duration + .02);
  }
  function tone(midi, at, duration, volume, wave = 'sine', channel = 'effects', endMidi) {
    const source = context.createOscillator(); source.type = wave;
    source.frequency.setValueAtTime(frequency(midi), at);
    if (endMidi !== undefined) source.frequency.exponentialRampToValueAtTime(frequency(endMidi), at + duration);
    connectVoice(source, at, duration, volume, channel, wave === 'square' ? 1800 : 6500);
  }
  function noise(at, duration, volume, channel = 'effects') {
    if (!noiseBuffer) {
      noiseBuffer = context.createBuffer(1, Math.ceil(context.sampleRate * .3), context.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    }
    const source = context.createBufferSource(); source.buffer = noiseBuffer;
    connectVoice(source, at, duration, volume, channel, 3200);
  }
  function scheduleMusic() {
    if (!audible('music') || phase !== 'playing') { stopMusic(); return; }
    const t = theme(), eighth = 30 / t.bpm;
    // Recover from throttled tabs without queuing a burst of missed notes.
    if (nextNote < context.currentTime - .1) nextNote = context.currentTime + .025;
    while (nextNote < context.currentTime + .14) {
      const beat = step % 16, chord = t.chords[Math.floor(step / 8) % t.chords.length], note = t.notes[beat];
      if (note !== null) tone(t.root + chord + note, nextNote, eighth * .88, .085, t.wave, 'music');
      if (step % 4 === 0) tone(t.root - 24 + chord, nextNote, eighth * 2.5, .12, 'sine', 'music');
      if (step % 8 === 0) for (const n of [0, t.minor ? 3 : 4, 7]) tone(t.root - 12 + chord + n, nextNote, eighth * 5, .025, 'sine', 'music');
      if (t.drums) {
        if (step % 4 === 0) tone(43, nextNote, .13, .15, 'sine', 'music', 26);
        if (step % 4 === 2) noise(nextNote, .065, .045, 'music');
        else if (step % 2 === 1) noise(nextNote, .026, .018, 'music');
      }
      nextNote += eighth; step++;
    }
  }
  function syncMusic() {
    if (!audible('music') || phase !== 'playing') { stopMusic(); return; }
    if (timer !== null) return;
    step = 0; nextNote = context.currentTime + .035;
    scheduleMusic(); timer = scope.setInterval(scheduleMusic, 25);
  }
  // Call only from an explicit user gesture (start/resume/audio controls).
  async function unlock() {
    if (!supported) return false;
    try {
      if (!context) {
        context = contextFactory ? contextFactory() : new AudioContextClass();
        master = context.createGain(); musicBus = context.createGain(); effectsBus = context.createGain();
        const limiter = context.createDynamicsCompressor();
        limiter.threshold.value = -12; limiter.knee.value = 12; limiter.ratio.value = 8;
        master.gain.value = settings.volume * .65;
        musicBus.connect(master); effectsBus.connect(master); master.connect(limiter); limiter.connect(context.destination);
        context.onstatechange = () => {
          if (!ready()) { stopMusic(); stopVoices('effects'); } else syncMusic();
          onChange();
        };
      }
      if (!ready()) await context.resume();
      syncMusic(); onChange(); return ready();
    } catch {
      // Autoplay denial is recoverable with the visible sound-enable button.
      onChange(); return false;
    }
  }
  function setScene(id, nextPhase) {
    if (game === id && phase === nextPhase) return;
    stopMusic(); stopVoices('effects'); cooldowns.clear();
    game = ARCADE_THEMES[id] ? id : null; phase = nextPhase;
    syncMusic();
  }
  function updateSettings(patch) {
    for (const channel of ['music', 'effects']) if (typeof patch[channel] === 'boolean') settings[channel] = patch[channel];
    if (Number.isFinite(patch.volume)) settings.volume = Math.max(0, Math.min(1, patch.volume));
    try { storage?.setItem(ARCADE_AUDIO_KEY, JSON.stringify(settings)); } catch { /* Sound still works without persistence. */ }
    if (context) {
      master.gain.cancelScheduledValues(context.currentTime);
      master.gain.setTargetAtTime(settings.volume * .65, context.currentTime, .015);
    }
    if (!settings.effects || !settings.volume) stopVoices('effects');
    syncMusic(); onChange();
  }
  function cue(name) {
    if (!audible('effects')) return;
    const at = context.currentTime + .005, previous = cooldowns.get(name) ?? -Infinity;
    if (at - previous < (name === 'step' || name === 'tune' ? .085 : .06)) return;
    cooldowns.set(name, at);
    const t = theme(), root = t.root;
    const notes = (values, length = .09, wave = t.wave, volume = .18) => values.forEach((n, i) => tone(root + n, at + i * length, length * 1.7, volume, wave));
    if (name === 'start') notes([0, 4, 7, 12], .075);
    if (name === 'shoot') {
      if (game === 'bubble') tone(root + 12, at, .14, .22, 'sine', 'effects', root - 5);
      else tone(root + 17, at, .12, .15, 'square', 'effects', root - 12);
    }
    if (name === 'pop') { tone(root + 19, at, .15, .24, 'sine', 'effects', root); notes([7, 12], .065); }
    if (name === 'hit') { noise(at, .09, .12); notes([0, 7, 12], .055); }
    if (name === 'step') tone(root - 24, at, .045, .12, 'triangle', 'effects', root - 30);
    if (name === 'bump') tone(root - 24, at, .08, .13, 'sine', 'effects', root - 29);
    if (name === 'collect') notes([7, 12, 19], .065, 'sine');
    if (name === 'roll') { tone(root + 7, at, .3, .16, 'sine', 'effects', root - 12); noise(at, .13, .04); }
    if (name === 'launch') { noise(at, .18, .12); tone(root - 12, at, .24, .18, 'triangle', 'effects', root + 19); }
    if (name === 'flip') { noise(at, .035, .08); tone(root + 7, at, .07, .13, 'sine'); }
    if (name === 'match') notes([0, 4, 7, 12], .075, 'sine');
    if (name === 'miss') notes([2, -1], .12, 'triangle', .13);
    if (name === 'damage') { noise(at, .1, .1); tone(root - 5, at, .25, .18, 'triangle', 'effects', root - 24); }
    if (name === 'paint') notes([0, 7], .045, 'triangle', .12);
    if (name === 'capture') notes([0, 4, 7, 12, 16], .055);
    if (name === 'tune') tone(root + 12, at, .055, .075, 'sine');
    if (name === 'stage') notes([0, 4, 7, 12, 7, 12], .1, 'triangle');
    if (name === 'win') {
      notes([0, 4, 7, 12, 7, 12, 16, 19], .12, 'triangle', .18);
      [0, 4, 7, 12].forEach(n => tone(root - 12 + n, at + .84, .7, .085, 'sine'));
    }
    if (name === 'lose') notes([7, 3, 0, -5], .18, 'triangle', .14);
  }
  return {
    unlock, setScene, updateSettings, cue,
    stop() { setScene(null, 'idle'); },
    get settings() { return { ...settings }; },
    get status() { return { supported, ready: ready() }; }
  };
}
