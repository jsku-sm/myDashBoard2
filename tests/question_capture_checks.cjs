// Exercise the shipped question drop/paste component without fetching web URLs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const path = require('node:path');

function setup() {
  const messages = [], listeners = {}, reads = [], pending = [];
  function element() {
    return {events: {}, textContent: '', attributes: {}, classes: new Set(),
      classList: {add() {}, remove() {}, toggle() {}},
      setAttribute(name, value) {this.attributes[name] = value;},
      addEventListener(name, listener) {this.events[name] = listener;}, focus() {this.focused = true;}};
  }
  const elements = {drop: element(), status: element()};
  const parent = {postMessage(message) {messages.push(message);}};
  class File {
    constructor(parts, name, options = {}) {
      this.raw = Buffer.concat(parts.map(part => Buffer.from(part)));
      this.name = name; this.type = options.type || ''; this.size = this.raw.length;
    }
  }
  class FileReader {
    readAsDataURL(file) {
      reads.push(file);
      const run = () => {this.result = 'data:' + file.type + ';base64,' + file.raw.toString('base64'); this.onload();};
      if (file.delayed) pending.push(run); else queueMicrotask(run);
    }
  }
  const context = {window: {parent, addEventListener(name, listener) {listeners[name] = listener;}},
    document: {getElementById: id => elements[id], body: {scrollHeight: 140}},
    File, FileReader, Uint8Array, crypto: webcrypto, atob, Promise, Set, Array, Number, Math, queueMicrotask};
  const html = fs.readFileSync(path.join(__dirname, '..', 'think_app', 'question_capture', 'index.html'), 'utf8');
  vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  function event(transfer, type = 'drop') {
    let prevented = false;
    const data = {preventDefault() {prevented = true;}};
    data[type === 'paste' ? 'clipboardData' : 'dataTransfer'] = transfer;
    return {data, prevented: () => prevented};
  }
  return {messages, listeners, elements, reads, pending, File, event,
    values: () => messages.filter(message => message.type === 'streamlit:setComponentValue').map(message => message.value),
    render(args = {}, source = parent) {listeners.message({source, data: {type: 'streamlit:render', args}});}};
}

async function main() {
  const component = setup();
  assert.equal(component.messages[0].type, 'streamlit:componentReady');
  const png = new component.File([Buffer.from('test image')], 'problem.png', {type: 'image/png'});
  const dropped = component.event({files: [png]});
  await component.elements.drop.events.drop(dropped.data);
  assert(dropped.prevented(), 'Dropping a file must not navigate the browser');
  assert.equal(component.values().length, 1);
  let result = component.values()[0];
  assert.match(result.event_id, /^[a-f0-9]{32}$/);
  assert.equal(result.files[0].name, 'problem.png');
  assert.equal(result.files[0].size, png.size);
  assert.equal(result.files[0].data_uri, 'data:image/png;base64,' + png.raw.toString('base64'));
  assert.equal(component.elements.drop.attributes['aria-busy'], 'false');

  const clipboard = component.event({files: [], items: [{kind: 'file', getAsFile: () => new component.File([png.raw], '', {type: 'image/png'})}]}, 'paste');
  await component.elements.drop.events.paste(clipboard.data);
  assert(clipboard.prevented());
  result = component.values()[1];
  assert.notEqual(result.event_id, component.values()[0].event_id, 'Each drop/paste needs an independent replay-safe event identity');
  assert(result.files[0].name.endsWith('.png'), 'Clipboard screenshots without a filename must receive a downloadable image name');

  const uri = component.event({files: [], getData: () => 'data:image/png;base64,' + png.raw.toString('base64')});
  await component.elements.drop.events.drop(uri.data);
  assert.equal(component.values().length, 3, 'A locally embedded data URI may be dragged as an image');
  const before = component.values().length, readsBefore = component.reads.length;
  const remote = component.event({files: [], getData: () => 'https://example.invalid/tracking.png'});
  await component.elements.drop.events.drop(remote.data);
  assert.equal(component.values().length, before);
  assert.equal(component.reads.length, readsBefore, 'A web image URL must never be fetched or loaded');
  assert(component.elements.status.textContent.includes('파일로 저장'));

  await component.elements.drop.events.drop(component.event({files: [Object.assign({}, png, {size: 10000001})]}).data);
  assert(component.elements.status.textContent.includes('10MB'));
  await component.elements.drop.events.drop(component.event({files: Array(6).fill(png)}).data);
  assert(component.elements.status.textContent.includes('최대 5개'));
  await component.elements.drop.events.drop(component.event({files: [new component.File([png.raw], 'bad.svg', {type: 'image/svg+xml'})]}).data);
  assert(component.elements.status.textContent.includes('PNG'));
  assert.equal(component.values().length, before, 'Invalid type, file count or byte size must not publish any value');

  component.render({max_file_bytes: 1}, {});
  await component.elements.drop.events.drop(component.event({files: [png]}).data);
  assert.equal(component.values().length, before + 1, 'Messages from a different source must not change the allowed limits');
  component.render({max_file_bytes: 1});
  await component.elements.drop.events.drop(component.event({files: [png]}).data);
  assert.equal(component.values().length, before + 1, 'Parent render limits must be enforced before reading bytes');

  const delayed = setup(), waiting = new delayed.File([png.raw], 'capture.png', {type: 'image/png'});
  waiting.delayed = true;
  const unfinished = delayed.elements.drop.events.drop(delayed.event({files: [waiting]}).data);
  delayed.listeners.pagehide(); delayed.pending[0](); await unfinished;
  assert.equal(delayed.values().length, 0, 'Unmount during a read must not publish a late image event');
  console.log('Question capture checks passed: local drop, screenshot paste, bounded embedded data, unique events, no URL fetches, source guard, file limits, and unmount.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
