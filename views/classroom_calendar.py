"""Accessible weekly classroom calendar, with drag and button alternatives.

Browser events are proposals only. The caller validates the selected lesson and
resource and asks for a reason before persisting through ClassroomService.
"""
from __future__ import annotations

from functools import lru_cache

import streamlit as st


_CSS = """
.calendar {overflow-x:auto;padding:4px 2px 12px;color:var(--st-text-color,#17324d);font:14px system-ui}
.week {display:grid;grid-template-columns:repeat(7,minmax(155px,1fr));gap:9px;min-width:1120px}
.day {min-height:185px;background:var(--st-secondary-background-color,#f1f6fb);border:1px solid #cbd9e5;border-radius:12px;padding:10px}
.day.over {outline:3px solid #2274a5;background:#e6f2fa}
.date {font-weight:700;margin:0 0 10px;font-size:15px}
.card {display:block;text-align:left;width:100%;box-sizing:border-box;border:1px solid #bed2e4;border-left:4px solid #6598bb;border-radius:8px;background:var(--st-background-color,#fff);color:inherit;padding:10px;margin:7px 0;cursor:pointer;font:inherit;line-height:1.5}
.card.completed {border-left-color:#258562}.card.in_progress {border-left-color:#c58a17}
.card.cancelled {border-left-color:#9a6470}.card:focus-visible {outline:3px solid #2274a5}
.card small {display:block;color:inherit;opacity:.8}.card[draggable=true] {cursor:grab}
.tray {display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.tray .card {width:auto;min-width:180px;max-width:320px;margin:0}
.tray-title {font-weight:600;margin:14px 0 6px}.hint {font-size:12px;opacity:.8}
"""

_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector('.calendar');
  root.replaceChildren();
  let dragged = null;
  const text = (tag, value, cls) => {
    const element = document.createElement(tag);
    element.textContent = value || '';
    if (cls) element.className = cls;
    return element;
  };
  const card = (item, resource = false) => {
    const element = text('button', item.title, 'card ' + (item.progress || '') + ' ' + (item.schedule_status || ''));
    element.type = 'button';
    if (item.subtitle) element.appendChild(text('small', item.subtitle));
    if (item.detail) element.appendChild(text('small', item.detail));
    if (data.editable && item.movable !== false) {
      element.draggable = true;
      element.ondragstart = (event) => {
        dragged = { kind: resource ? 'resource' : 'lesson', id: item.id, course_id: item.course_id };
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', item.id);
      };
      element.ondragend = () => { dragged = null; };
    }
    if (!resource) element.onclick = () => setTriggerValue('event', {kind:'open', id:item.id, course_id:item.course_id});
    return element;
  };
  const week = text('div', '', 'week');
  for (const day of data.days) {
    const box = text('section', '', 'day');
    box.appendChild(text('h3', day.label, 'date'));
    for (const item of data.items.filter(item => item.date === day.date)) box.appendChild(card(item));
    if (data.editable) {
      box.ondragover = (event) => { if (dragged) {event.preventDefault(); box.classList.add('over');} };
      box.ondragleave = () => box.classList.remove('over');
      box.ondrop = (event) => {
        event.preventDefault(); box.classList.remove('over');
        if (dragged) setTriggerValue('event', {...dragged, date:day.date});
        dragged = null;
      };
    }
    week.appendChild(box);
  }
  root.appendChild(week);
  if (data.tray.length) {
    root.appendChild(text('p', '계획일 미설정 차시 · 날짜로 끌어 놓거나 아래 날짜 배치 사용', 'tray-title'));
    const tray = text('div', '', 'tray');
    for (const item of data.tray) tray.appendChild(card(item));
    root.appendChild(tray);
  }
  if (data.editable && data.resources.length) {
    root.appendChild(text('p', '자료·과제·활동을 날짜로 끌어 배치', 'tray-title'));
    const tray = text('div', '', 'tray');
    for (const item of data.resources) tray.appendChild(card(item, true));
    root.appendChild(tray);
  }
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
              "resources": list(resources), "editable": bool(editable)},
        key=key, on_event_change=lambda: None,
    )
    event = result.event
    return event if isinstance(event, dict) else None
