// Capture, crop, and download checks run against the real component script.
const assert = require('node:assert/strict');
const {setup} = require('./graph_checks.cjs');

function sharing() {
  const tracks = [{stops: 0, stop() {this.stops++;}}, {stops: 0, stop() {this.stops++;}}];
  return {tracks, stream: {getTracks: () => tracks}};
}
function pointer(preview, name, x, y, id = 1) {
  preview[name]({button: 0, pointerId: id, clientX: x, clientY: y, preventDefault() {}});
}
const settle = async () => {await Promise.resolve(); await Promise.resolve(); await Promise.resolve();};

async function main() {
  const shared = sharing();
  let requests = 0, options;
  const graph = setup({getDisplayMedia(value) {requests++; options = value; return Promise.resolve(shared.stream);}});
  graph.render({});
  const frame = graph.frames[0], before = graph.values().length;
  const pending = graph.elements['screen-capture'].onclick();
  assert.equal(requests, 1, 'The browser picker must be invoked directly within the click handler');
  assert.equal(options.audio, false, 'A screenshot must never request audio');
  assert.equal(options.preferCurrentTab, true);
  assert.equal(options.selfBrowserSurface, 'include');
  await pending;
  assert(shared.tracks.every(track => track.stops === 1), 'Every sharing track must stop as soon as the screenshot freezes');
  assert.equal(graph.videos[0].srcObject, null, 'Video must release the captured stream');
  assert.equal(graph.elements['screen-dialog'].hidden, false);
  assert.equal(graph.elements['screen-preview'].style.width, '800px', 'The full screenshot must fit the available component width');
  assert.equal(graph.elements['screen-preview'].style.height, '400px');
  assert.equal(graph.elements['screen-save'].disabled, true);
  assert.equal(graph.values().length, before, 'A screenshot is saved locally rather than published as a ready SDK graph');
  graph.render({});
  assert.equal(graph.frames[0], frame);
  assert.equal(graph.frames.length, 1, 'Opening the cropper and a Streamlit rerender must preserve iframe equations');
  assert(!frame.removed);

  const preview = graph.elements['screen-preview'];
  pointer(preview, 'onpointerdown', 201.3, 180.5);
  pointer(preview, 'onpointerup', 201.3, 180.5);
  assert.equal(graph.elements['screen-save'].disabled, true, 'An ordinary click must not download a zero-sized crop');
  pointer(preview, 'onpointerdown', 700, 380);
  pointer(preview, 'onpointermove', 300, 180);
  pointer(preview, 'onpointerup', 300, 180);
  assert.equal(graph.elements['screen-save'].disabled, false);
  graph.elements['screen-save'].onclick();
  const crop = graph.canvases.at(-1);
  assert.equal(crop.width, 800);
  assert.equal(crop.height, 400);
  assert.deepEqual(crop.drawCalls[0].slice(1), [400, 200, 800, 400, 0, 0, 800, 400], 'Reverse dragging must map CSS coordinates to exact bitmap pixels');
  assert.equal(graph.downloads.length, 1);
  assert.equal(graph.downloads.blob.type, 'image/png');
  assert(graph.downloads[0].download.endsWith('.png'));
  assert.equal(graph.elements['screen-dialog'].hidden, true);
  assert.equal(graph.elements['screen-capture'].disabled, false);
  assert.equal(graph.values().length, before);
  graph.tick(1000);
  assert.equal(graph.revoked.length, 1, 'The downloaded PNG URL must be released');

  await graph.elements['screen-capture'].onclick();
  pointer(preview, 'onpointerdown', 300, 180);
  pointer(preview, 'onpointerup', -100, -80);
  graph.elements['screen-save'].onclick();
  assert.deepEqual(graph.canvases.at(-1).drawCalls[0].slice(1), [0, 0, 400, 200, 0, 0, 400, 200], 'Dragging outside the canvas must clamp to valid screenshot pixels');
  await graph.elements['screen-capture'].onclick();
  graph.elements['screen-all'].onclick();
  graph.elements['screen-save'].onclick();
  assert.equal(graph.canvases.at(-1).width, 1600, 'Keyboard users can select the entire screenshot');
  assert.equal(graph.canvases.at(-1).height, 800);
  graph.listeners.pagehide();
  assert.equal(graph.elements['screen-dialog'].hidden, true);
  assert.equal(graph.revoked.length, 3, 'Unmount must release all outstanding screenshot URLs');

  const sdk = setup({getDisplayMedia: () => Promise.resolve(sharing().stream)});
  sdk.render({api_key: 'test'});
  assert.equal(sdk.elements.capture.disabled, false);
  assert.equal(sdk.elements['screen-capture'].disabled, false, 'Screen capture must also remain available with the SDK');
  await sdk.elements['screen-capture'].onclick();
  sdk.elements['screen-dialog'].events.keydown({key: 'Escape', preventDefault() {}});
  assert.equal(sdk.elements['screen-dialog'].hidden, true);
  assert.equal(sdk.destroyed(), false, 'Canceling a screenshot must leave the Desmos SDK running');

  const unsupported = setup(); unsupported.render({});
  await unsupported.elements['screen-capture'].onclick();
  assert(unsupported.elements['screen-status'].textContent.includes('모바일'));
  assert(unsupported.elements['screen-status'].textContent.includes('업로드'));
  assert.equal(unsupported.elements['screen-capture'].disabled, false);
  const denied = setup({getDisplayMedia: async () => {throw Object.assign(new Error('Permission denied'), {name: 'NotAllowedError'});}});
  await denied.elements['screen-capture'].onclick();
  assert(denied.elements['screen-status'].textContent.includes('취소'));
  assert.equal(denied.elements['screen-dialog'].hidden, true);

  const failed = sharing(), broken = setup({getDisplayMedia: () => Promise.resolve(failed.stream), videoFail: true});
  await broken.elements['screen-capture'].onclick();
  assert(failed.tracks.every(track => track.stops === 1), 'A failed frame must not leave screen sharing running');
  assert.equal(broken.elements['screen-capture'].disabled, false);
  const expired = sharing(), timeout = setup({getDisplayMedia: () => Promise.resolve(expired.stream), manualVideo: true});
  const waitingFrame = timeout.elements['screen-capture'].onclick();
  await settle(); timeout.tick(12000); await waitingFrame;
  assert(expired.tracks.every(track => track.stops === 1), 'A frame timeout must stop screen sharing');
  assert.equal(timeout.elements['screen-dialog'].hidden, true);

  let resolvePicker;
  const late = sharing(), unmounted = setup({getDisplayMedia: () => new Promise(resolve => {resolvePicker = resolve;})});
  const waitingPermission = unmounted.elements['screen-capture'].onclick();
  unmounted.listeners.pagehide(); resolvePicker(late.stream); await waitingPermission;
  assert(late.tracks.every(track => track.stops === 1), 'Permission resolving after unmount must immediately stop the returned stream');
  assert.equal(unmounted.elements['screen-dialog'].hidden, true);
  const canceled = sharing(), interrupted = setup({getDisplayMedia: () => Promise.resolve(canceled.stream), manualVideo: true});
  const preparing = interrupted.elements['screen-capture'].onclick();
  await settle(); interrupted.listeners.pagehide(); await preparing;
  assert(canceled.tracks.every(track => track.stops === 1), 'Unmount during frame preparation must stop sharing and cancel the pending frame');

  const failedBlob = setup({getDisplayMedia: () => Promise.resolve(sharing().stream), blobFail: true});
  await failedBlob.elements['screen-capture'].onclick(); failedBlob.elements['screen-all'].onclick(); failedBlob.elements['screen-save'].onclick();
  assert.equal(failedBlob.downloads.length, 0);
  assert.equal(failedBlob.elements['screen-dialog'].hidden, false);
  assert.equal(failedBlob.elements['screen-save'].disabled, false, 'A PNG encoding failure must permit retrying the chosen crop');
  console.log('Region capture checks passed: browser picker, no audio, frozen frame cleanup, scaled/reverse/clamped crop, PNG download, preserved Desmos work, cancellation, unsupported browsers, timeout, and unmount.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
