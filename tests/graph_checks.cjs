// Exercise the real component script against a simulated DOM and Desmos SDK.
// These checks need no API key, browser, or external network access.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../think_app/graph/index.html'), 'utf8')
  .split('<script>')[1].split('</script>')[0];
const png = 'data:image/png;base64,c2ltdWxhdGVk';
const clone = value => JSON.parse(JSON.stringify(value));

function setup({manualLoad = false, failInitialize = false, getDisplayMedia, videoFail = false, blobFail = false, manualVideo = false} = {}) {
  const messages = [], listeners = {}, timers = new Map(), captures = [], scripts = [], frames = [], downloads = [], revoked = [], canvases = [], videos = [];
  let state = {version: 11, expressions: {list: []}, graph: {viewport: {xmin: -10, xmax: 10, ymin: -10, ymax: 10}}};
  let change, now = 0, nextTimer = 0, nextUrl = 0, destroyed = false;
  let documentRef;
  function element(tag) {
    return {tag, disabled: true, textContent: '', children: [], hidden: false, clicks: 0, style: {}, attributes: {}, events: {}, width: 0, height: 0, drawCalls: [],
      setAttribute(name, value) {this.attributes[name] = value;},
      addEventListener(name, callback) {this.events[name] = callback;},
      focus() {documentRef.activeElement = this;},
      getBoundingClientRect() {return {left: 100, top: 80, width: 800, height: 400};},
      setPointerCapture(id) {this.pointer = id;}, hasPointerCapture(id) {return this.pointer === id;}, releasePointerCapture() {this.pointer = null;},
      remove() {this.removed = true;}, click() {this.clicks++; if (tag === 'a') downloads.push(this);},
      appendChild(child) {this.children.push(child); if (child.tag === 'iframe') frames.push(child);},
      getContext() {const owner = this; return {drawImage(...args) {owner.drawCalls.push(args);}, clearRect() {}, fillRect() {}, strokeRect() {}};},
      toBlob(callback, type) {callback(blobFail ? null : {type, width: this.width, height: this.height});}
    };
  }
  const elements = Object.fromEntries(['calculator', 'status', 'graph-help', 'capture', 'download', 'open', 'import', 'retry', 'screen-capture', 'screen-status', 'screen-dialog', 'screen-preview', 'screen-stage', 'screen-save', 'screen-all', 'screen-recapture', 'screen-cancel', 'screen-selection']
    .map(id => [id, element(id === 'screen-preview' ? 'canvas' : 'div')]));
  elements.retry.hidden = elements['screen-dialog'].hidden = true;
  elements['screen-capture'].disabled = false;
  elements['screen-stage'].getBoundingClientRect = () => ({left: 98, top: 78, width: 804, height: 404});
  const parent = {postMessage: message => messages.push(message)};
  const calculator = {
    getState: () => clone(state), getExpressions: () => clone(state.expressions.list),
    graphpaperBounds: {mathCoordinates: {left: -10, right: 10, bottom: -10, top: 10}, pixelCoordinates: {width: 500, height: 600}},
    setState(value) {state = clone(value); if (change) change();},
    observeEvent(name, callback) {assert.equal(name, 'change'); change = callback;},
    asyncScreenshot(options, callback) {captures.push({options, callback});},
    destroy() {destroyed = true;}
  };
  vm.runInNewContext(source, {
    document: documentRef = {
      getElementById: id => elements[id],
      createElement: tag => {
        const item = element(tag);
        if (tag === 'canvas') canvases.push(item);
        if (tag === 'video') {
          videos.push(item); item.videoWidth = 1600; item.videoHeight = 800;
          item.play = async () => {if (videoFail) throw new Error('Video unavailable'); if (!manualVideo) item.onloadeddata();};
        }
        return item;
      },
      head: {appendChild(script) {scripts.push(script); if (!manualLoad) script.onload();}},
      body: {scrollHeight: 720, appendChild() {}}
    },
    window: {parent, addEventListener: (name, callback) => listeners[name] = callback},
    navigator: {mediaDevices: getDisplayMedia ? {getDisplayMedia} : {}},
    Desmos: {GraphingCalculator: (element, options) => {
      assert.equal(element, elements.calculator);
      assert.equal(options.language, 'ko');
      if (failInitialize) throw new Error('SDK initialization failed');
      return calculator;
    }},
    Blob: class {constructor(parts, options) {this.parts = parts; this.type = options.type;}},
    URL: {createObjectURL(blob) {downloads.blob = blob; return 'blob:local-work' + (nextUrl++ || '');}, revokeObjectURL: url => revoked.push(url)},
    setTimeout(callback, delay) {const id = ++nextTimer; timers.set(id, {callback, due: now + delay}); return id;},
    clearTimeout: id => timers.delete(id)
  });
  return {
    messages, elements, scripts, frames, captures, downloads, revoked, calculator, listeners, canvases, videos,
    render: args => listeners.message({source: parent, data: {type: 'streamlit:render', args}}),
    edit(latex) {state.expressions.list = latex ? [{id: '1', latex}] : []; change();},
    tick(delta = 650) {
      const target = now + delta;
      for (;;) {
        const timer = [...timers.entries()].sort((a, b) => a[1].due - b[1].due).find(([, value]) => value.due <= target);
        if (!timer) break;
        timers.delete(timer[0]); now = timer[1].due; timer[1].callback();
      }
      now = target;
    },
    values: () => messages.filter(message => message.type === 'streamlit:setComponentValue').map(message => message.value),
    destroyed: () => destroyed,
    async import(payload, size = 200) {
      elements.import.files = [{size, text: async () => typeof payload === 'string' ? payload : JSON.stringify(payload)}];
      await elements.import.onchange();
    }
  };
}

async function main() {
  const graph = setup();
  assert(graph.messages.some(message => message.type === 'streamlit:componentReady'));
  graph.render({api_key: 'simulated key', draft_filename: '데스모스-함수-그래프.json'});
  assert(graph.scripts[0].src.endsWith('apiKey=simulated%20key&lang=ko'));
  assert.equal(graph.elements.capture.disabled, false);
  assert.equal(graph.elements.download.disabled, false);
  graph.edit('y=x');
  assert.equal(graph.values().at(-1).ready, false, 'An edit must immediately disable submission of an old capture');
  graph.tick();
  const stale = graph.captures.shift();
  graph.edit('y=2x+1');
  stale.callback(png);
  assert(!graph.values().some(value => value.ready), 'An outdated capture must never become submittable');
  graph.tick();
  const current = graph.captures.shift();
  assert.equal(current.options.width / current.options.height, 500 / 600, 'Capture must preserve screen aspect ratio');
  assert.equal(current.options.format, 'png');
  current.callback(png);
  const saved = clone(graph.values().at(-1));
  assert(saved.ready && saved.expressions[0].latex === 'y=2x+1');
  assert.deepEqual(saved.state, graph.calculator.getState(), 'The submitted state must be the exact captured state');
  graph.render({api_key: 'simulated key', initial_state: {version: 11, expressions: {list: [{latex: 'y=0'}]}}, draft_filename: '함수-그래프.json'});
  assert.equal(graph.calculator.getExpressions()[0].latex, 'y=2x+1', 'A Streamlit rerender must preserve the current work');

  // A second explicit capture supersedes any earlier capture even at the same edit revision.
  graph.elements.capture.onclick(); const older = graph.captures.shift();
  graph.elements.capture.onclick(); const newer = graph.captures.shift();
  newer.callback(png); const latestValue = graph.values().at(-1);
  older.callback('not an image');
  assert.equal(graph.values().at(-1), latestValue, 'Only the latest capture callback can alter readiness');
  graph.edit(''); graph.elements.capture.onclick();
  assert.equal(graph.values().at(-1).ready, false, 'Removing all equations invalidates the previous answer');
  graph.edit('   '); graph.tick();
  assert.equal(graph.captures.length, 0, 'Whitespace is not a mathematical expression');

  // Download retains editable state, and reopening accepts student or teacher exports.
  graph.edit('y=x^2');
  graph.elements.download.onclick();
  const exported = JSON.parse(graph.downloads.blob.parts[0]);
  assert.deepEqual(exported.state, graph.calculator.getState());
  assert.equal(graph.downloads[0].download, '함수-그래프.json');
  graph.tick(1000);
  assert.deepEqual(graph.revoked, ['blob:local-work']);
  graph.elements.open.onclick();
  assert.equal(graph.elements.import.clicks, 1);
  for (const payload of [saved.state, {state: saved.state, expressions: saved.expressions}, {graph: {state: saved.state}}]) {
    const imported = setup(); imported.render({api_key: 'test'}); await imported.import(payload);
    imported.captures.shift().callback(png);
    assert.deepEqual(clone(imported.values().at(-1).state), saved.state);
    assert.equal(imported.values().at(-1).ready, true);
    assert.equal(imported.elements.import.value, '', 'Reopening the same file must remain possible');
  }
  const unchanged = graph.calculator.getState();
  await graph.import('{broken JSON');
  await graph.import({state: {}}, 500001);
  assert.deepEqual(graph.calculator.getState(), unchanged, 'Invalid or oversized imports must preserve current work');
  assert(graph.elements.status.textContent.includes('불러오지 못했습니다'));

  const restored = setup(); restored.render({api_key: 'test', initial_state: saved.state});
  restored.captures.shift().callback(png);
  assert.deepEqual(clone(restored.values().at(-1).state), saved.state);
  const timeout = setup(); timeout.render({api_key: 'test'}); timeout.edit('y=x'); timeout.tick();
  const late = timeout.captures.shift(); timeout.tick(15000); late.callback(png);
  assert.equal(timeout.values().at(-1).ready, false, 'A timed-out capture cannot publish a late success');
  timeout.elements.capture.onclick(); timeout.captures.shift().callback(png);
  assert.equal(timeout.values().at(-1).ready, true, 'A failed capture must support retry');

  // No API key still opens a real official calculator inside this component.
  const missing = setup(); missing.render({});
  assert(missing.elements.capture.disabled); assert.equal(missing.scripts.length, 0);
  assert.equal(missing.frames[0].src, 'https://www.desmos.com/calculator?lang=ko', 'The read-only ?embed page cannot be used for student equation entry');
  assert.equal(missing.frames[0].title, '데스모스 그래프 계산기');
  assert(!missing.frames[0].attributes.sandbox, 'The official calculator must be allowed to run scripts in its own origin');
  assert(missing.elements.capture.hidden, 'Unsupported automatic capture controls must be hidden');
  assert(missing.elements['graph-help'].textContent.includes('캡처'));
  missing.frames[0].onload();
  assert.equal(missing.values().at(-1).mode, 'embed');
  assert.equal(missing.values().at(-1).ready, false, 'Loading a cross-origin page cannot claim that a graph was captured');
  assert.equal(missing.values().at(-1).connected, false, 'An iframe load cannot verify calculator readiness');
  assert.equal(missing.values().at(-1).frame_loaded, true);
  assert.equal(missing.values().at(-1).can_capture, false);
  missing.render({}); assert.equal(missing.frames.length, 1, 'Rerendering must preserve work inside the official calculator');
  const initialFrame = missing.frames[0];
  missing.elements.retry.onclick(); assert(initialFrame.removed);
  assert.equal(missing.frames.length, 2, 'A student must be able to reload a failed embedded page');
  const beforeLateLoad = missing.values().at(-1); initialFrame.onload();
  assert.equal(missing.values().at(-1), beforeLateLoad, 'An obsolete iframe cannot publish a late load');
  missing.frames[1].onerror(); assert.equal(missing.elements.retry.hidden, false);
  missing.render({api_key: 'added later'}); assert.equal(missing.elements.capture.disabled, false);
  assert.equal(missing.elements.capture.hidden, false); assert(missing.frames[1].removed);
  assert.equal(missing.values().at(-1).mode, 'sdk');

  // A lost initial ready message retries the handshake and still opens the graph inline.
  const delayed = setup(); delayed.tick(2000);
  assert.equal(delayed.messages.filter(message => message.type === 'streamlit:componentReady').length, 3);
  assert.equal(delayed.frames.length, 1);
  assert.equal(delayed.values().length, 0, 'Value messages wait until the parent has rendered the component');
  delayed.frames[0].onload(); delayed.render({});
  assert.equal(delayed.values().at(-1).frame_loaded, true);
  const readyCount = delayed.messages.filter(message => message.type === 'streamlit:componentReady').length;
  delayed.tick(5000);
  assert.equal(delayed.messages.filter(message => message.type === 'streamlit:componentReady').length, readyCount);
  assert.equal(delayed.frames.length, 1);

  // Failed SDK loading automatically falls back and still allows an explicit in-place retry.
  const offline = setup({manualLoad: true}); offline.render({api_key: 'test'});
  const originalScript = offline.scripts[0]; originalScript.onerror();
  assert.equal(offline.elements.retry.hidden, false); assert(originalScript.removed);
  assert.equal(offline.frames.length, 1);
  assert.equal(offline.values().at(-1).mode, 'embed');
  offline.render({api_key: 'test'});
  assert.equal(offline.scripts.length, 1, 'A rerender after SDK failure must keep the fallback instead of repeatedly reloading');
  offline.elements.retry.onclick(); originalScript.onload();
  assert(offline.elements.capture.disabled, 'The obsolete SDK load must not initialize after retry');
  offline.scripts[1].onload(); assert.equal(offline.elements.capture.disabled, false);
  const loadTimeout = setup({manualLoad: true}); loadTimeout.render({api_key: 'test'}); loadTimeout.tick(15000);
  assert.equal(loadTimeout.elements.retry.hidden, false);
  assert.equal(loadTimeout.frames.length, 1);
  loadTimeout.scripts[0].onload(); assert(loadTimeout.elements.capture.disabled);
  const failed = setup({failInitialize: true}); failed.render({api_key: 'test'});
  assert.equal(failed.elements.retry.hidden, false); assert(failed.elements.capture.disabled);
  assert.equal(failed.frames.length, 1);
  graph.listeners.message({source: {}, data: {type: 'streamlit:render', args: {}}});
  graph.listeners.message({source: {}, data: null});
  graph.listeners.pagehide(); assert(graph.destroyed(), 'The SDK must be destroyed when the component closes');
  console.log('Graph checks passed: inline official calculator, handshake recovery, SDK fallback/retry, capture consistency, restoration, JSON save/import, and cleanup (simulated DOM/SDK).');
}
if (require.main === module) main().catch(error => {console.error(error); process.exitCode = 1;});
module.exports = {setup};
