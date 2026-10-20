"""Weekly classroom calendar; the caller validates and persists browser events."""
from __future__ import annotations

from functools import lru_cache
from time import monotonic_ns

import streamlit as st


_CSS = """
.calendar {overflow-x:auto;padding:4px 2px 12px;color:var(--st-text-color,#17324d);font:14px system-ui}
.week {display:grid;grid-template-columns:repeat(7,minmax(155px,1fr));gap:9px;min-width:1120px}
.day {min-height:185px;background:var(--st-secondary-background-color,#f1f6fb);border:1px solid #cbd9e5;border-radius:12px;padding:10px}
.day.over {outline:3px solid #2274a5;background:#e6f2fa}
.day-header {display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:10px}
.date {font-weight:700;margin:0;font-size:15px}
.note-add {border:1px solid #bed2e4;border-radius:6px;padding:3px 6px;background:var(--st-background-color,#fff);color:inherit;font:inherit;font-size:12px;cursor:pointer}
.card {display:block;text-align:left;width:100%;box-sizing:border-box;border:1px solid #bed2e4;border-left:4px solid #6598bb;border-radius:8px;background:var(--st-background-color,#fff);color:inherit;padding:10px;margin:7px 0;cursor:pointer;font:inherit;line-height:1.5;white-space:normal;overflow-wrap:anywhere}
.card.completed {border-left-color:#258562}.card.in_progress {border-left-color:#c58a17}
.card.cancelled {border-left-color:#9a6470}.card:focus-visible {outline:3px solid #2274a5}
.card small {display:block;color:inherit;opacity:.8;white-space:pre-wrap;overflow-wrap:anywhere}
.card[draggable=true] {cursor:grab}.card.dragging {opacity:.5}.card[draggable=true]:active {cursor:grabbing}
.drag-handle {display:inline-block;padding:0 7px 0 0;touch-action:none;cursor:grab;font-weight:700;color:#527693;user-select:none}
.card.note {border-left-color:#c58a17;background:var(--st-background-color,#fffef2)}
article.card {cursor:default}.drop-status {font-size:12px;border:1px dashed #2274a5;border-radius:6px;padding:7px;overflow-wrap:anywhere}
.tray {display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.tray .card {width:auto;min-width:180px;max-width:320px;margin:0}
.tray-title {font-weight:600;margin:14px 0 6px}.hint {font-size:12px;opacity:.8}
"""

_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector('.calendar');
  root.replaceChildren();
  let dragged = null;
  let pointer = null;
  let suppressClickUntil = 0;
  const boxes = [];
  const mime = 'application/x-classroom-calendar';
  const text = (tag, value, cls) => {
    const element = document.createElement(tag);
    element.textContent = value || '';
    if (cls) element.className = cls;
    return element;
  };
  const clearOver = () => boxes.forEach(box => box.classList.remove('over'));
  const clearDrag = () => {
    clearOver();
    for (const element of root.querySelectorAll('.dragging')) element.classList.remove('dragging');
    dragged = null;
    pointer = null;
  };
  const payload = (item, resource) => ({
    kind: resource ? 'resource' : 'lesson', id: item.id, course_id: item.course_id,
    expected_version: item.expected_version,
    ...(resource ? { resource_kind: item.resource_kind || item.kind } : {})
  });
  const finishDrop = (box, proposal, title) => {
    if (!data.editable || !proposal) return;
    // The saved record comes back from Python. Never claim a successful save here.
    clearOver();
    const pending = text('p', (title || '일정') + ' · 저장 중…', 'drop-status');
    pending.setAttribute('role', 'status');
    box.appendChild(pending);
    setTriggerValue('event', {...proposal, date:box.dataset.date});
  };
  const pointerBox = (event) => boxes.find(box => {
    const rect = box.getBoundingClientRect();
    return event.clientX >= rect.left && event.clientX <= rect.right &&
           event.clientY >= rect.top && event.clientY <= rect.bottom;
  });
  const card = (item, resource = false) => {
    resource = resource || item.item_kind === 'resource';
    const note = item.item_kind === 'note';
    const clickable = !note || (data.editable && item.editable !== false);
    const element = text(clickable ? 'button' : 'article', '',
      'card ' + (note ? 'note ' : '') + (item.progress || '') + ' ' + (item.schedule_status || ''));
    if (clickable) element.type = 'button';
    const movable = data.editable && !note && item.movable !== false;
    if (movable) {
      const handle = text('span', '⠿', 'drag-handle');
      handle.setAttribute('aria-hidden', 'true');
      element.appendChild(handle);
    }
    element.appendChild(text('span', item.title));
    if (item.subtitle) element.appendChild(text('small', item.subtitle));
    if (item.detail) element.appendChild(text('small', item.detail));
    if (movable) {
      element.draggable = true;
      element.setAttribute('aria-description', '날짜로 끌어 놓아 배치합니다. 터치에서는 왼쪽 점 손잡이를 이용하세요.');
      element.ondragstart = (event) => {
        dragged = {...payload(item, resource), title:item.title};
        element.classList.add('dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData(mime, JSON.stringify(dragged));
        event.dataTransfer.setData('text/plain', item.title || item.id);
      };
      element.ondragend = clearDrag;
      // Native HTML drag has inconsistent touch support. The small handle gives
      // touch and pen users a drag gesture without blocking ordinary scrolling.
      element.onpointerdown = (event) => {
        if (event.pointerType === 'mouse' || !event.target.closest('.drag-handle')) return;
        event.preventDefault();
        dragged = {...payload(item, resource), title:item.title};
        pointer = event.pointerId;
        element.classList.add('dragging');
        if (element.setPointerCapture) element.setPointerCapture(pointer);
      };
      element.onpointermove = (event) => {
        if (pointer !== event.pointerId) return;
        event.preventDefault();
        clearOver();
        const box = pointerBox(event);
        if (box) box.classList.add('over');
        const rect = root.getBoundingClientRect();
        if (event.clientX > rect.right - 28) root.scrollLeft += 18;
        if (event.clientX < rect.left + 28) root.scrollLeft -= 18;
      };
      element.onpointerup = (event) => {
        if (pointer !== event.pointerId) return;
        event.preventDefault();
        suppressClickUntil = Date.now() + 500;
        const box = pointerBox(event);
        if (box) finishDrop(box, payload(item, resource), item.title);
        clearDrag();
      };
      element.onpointercancel = clearDrag;
    }
    if (clickable) element.onclick = () => {
      if (Date.now() < suppressClickUntil) return;
      if (note) setTriggerValue('event', {kind:'note', date:item.date, course_id:item.course_id});
      else if (resource) setTriggerValue('event', {
        kind:'open_resource', id:item.id, course_id:item.course_id,
        resource_kind:item.resource_kind || item.kind
      });
      else setTriggerValue('event', {kind:'open', id:item.id, course_id:item.course_id});
    };
    return element;
  };
  const week = text('div', '', 'week');
  for (const day of data.days) {
    const box = text('section', '', 'day');
    box.dataset.date = day.date;
    boxes.push(box);
    const header = text('div', '', 'day-header');
    header.appendChild(text('h3', day.label, 'date'));
    if (data.editable) {
      const add = text('button', '+ 메모', 'note-add');
      add.type = 'button';
      add.setAttribute('aria-label', day.label + ' 메모 쓰기');
      add.onclick = () => setTriggerValue('event', {kind:'note', date:day.date});
      header.appendChild(add);
    }
    box.appendChild(header);
    for (const item of data.items.filter(item => item.date === day.date)) box.appendChild(card(item));
    if (data.editable) {
      box.ondragover = (event) => {
        if (!dragged) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        clearOver();
        box.classList.add('over');
      };
      box.ondragleave = (event) => {
        if (!box.contains(event.relatedTarget)) box.classList.remove('over');
      };
      box.ondrop = (event) => {
        event.preventDefault();
        if (!dragged) return;
        const {title, ...proposal} = dragged;
        suppressClickUntil = Date.now() + 500;
        finishDrop(box, proposal, title);
        clearDrag();
      };
    }
    week.appendChild(box);
  }
  root.appendChild(week);
  if (data.tray.length) {
    root.appendChild(text('p', data.editable ? '계획일 미설정 차시 · 날짜로 끌어 놓기' : '계획일 미설정 차시', 'tray-title'));
    const tray = text('div', '', 'tray');
    for (const item of data.tray) tray.appendChild(card(item));
    root.appendChild(tray);
  }
  if (data.resources.length) {
    root.appendChild(text('p', data.editable ? '자료·과제 · 날짜로 끌어 놓기' : '자료·과제', 'tray-title'));
    const tray = text('div', '', 'tray');
    for (const item of data.resources) tray.appendChild(card(item, true));
    root.appendChild(tray);
  }
  if (data.editable && (data.items.length || data.tray.length || data.resources.length)) {
    root.appendChild(text('p', '카드나 왼쪽 점 손잡이를 날짜 칸으로 끌어 놓으면 저장됩니다. 터치에서는 점 손잡이를 잡아 이동하세요.', 'hint'));
  }
  return clearDrag;
}
"""


@lru_cache(maxsize=1)
def _component():
    return st.components.v2.component(
        "classroom_week", html='<div class="calendar" aria-label="주간 수업 달력"></div>',
        css=_CSS, js=_JS,
    )


def render_week(*, days, items, tray=(), resources=(), editable=False, key):
    """Return a single untrusted browser event; never write from the component."""
    if not hasattr(st.components, "v2"):
        st.caption("드래그 달력은 Streamlit 1.55 이상에서 사용할 수 있어요. 아래 날짜 배치로도 저장할 수 있어요.")
        return None
    result = _component()(
        data={"days": list(days), "items": list(items), "tray": list(tray),
              "resources": list(resources), "editable": bool(editable),
              "render_revision": monotonic_ns()},
        key=key, on_event_change=lambda: None,
    )
    event = result.event
    return event if isinstance(event, dict) else None
