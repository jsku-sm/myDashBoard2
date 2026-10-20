"""Accessible, horizontally scrollable seven-class checklist (Streamlit v2).

Only static trusted HTML/CSS/JS is executed. All server strings are rendered
with textContent; browser events are proposals, never authorization or receipts.
"""
from functools import lru_cache
from time import monotonic_ns

import streamlit as st

_CSS = r"""
.board{font-family:system-ui,-apple-system,'Noto Sans KR','Malgun Gothic',sans-serif;color:#1f2b40;background:#f3f6fa;border-radius:18px;padding:22px;box-sizing:border-box}
.board *{box-sizing:border-box}.board button,.board input{font:inherit}
.board .heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 22px}
.board h2{font-size:25px;letter-spacing:-1px;line-height:1.35;margin:0}.board .term{color:#637790;font-size:14px;white-space:nowrap}
.board .cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:24px}
.board .card{padding:19px;background:white;border:1px solid #e7edf4;border-radius:16px;box-shadow:0 2px 4px #23365306}
.board .card-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:20px}
.board .class-name{font-size:19px;font-weight:800;white-space:nowrap}.board .subject{padding:5px 8px;border-radius:7px;background:#eaf1ff;color:#275fe7;font-size:12px;font-weight:700}
.board .percent{display:flex;justify-content:space-between;align-items:center;font-size:14px;color:#52627c;margin:0 0 9px}.board .percent strong{font-size:20px;color:#31435e}
.board .bar{height:9px;background:#eef3f9;border-radius:10px;overflow:hidden}.board .bar span{display:block;height:100%;background:#3b82f6;border-radius:10px}
.board .card:nth-child(2n) .bar span{background:#6366f1}.board .card:nth-child(3n) .bar span{background:#9261ee}
.board .card small{display:block;color:#6b7b91;font-size:12px;margin-top:10px}
.board .panel{background:white;border:1px solid #e7edf4;border-radius:16px;overflow:hidden;box-shadow:0 2px 5px #23365305}
.board .panel-heading{padding:23px 24px 17px;background:#f9fbfe;display:flex;justify-content:space-between;align-items:center;gap:12px}
.board h3{font-size:20px;margin:0;letter-spacing:-.5px}.board .count{font-size:13px;color:#637790}
.board .instructions{font-size:12px;color:#657891;padding:0 24px 18px;margin:0;background:#f9fbfe;line-height:1.65}
.board .scroll{overflow:auto;max-height:660px;overscroll-behavior-x:contain;position:relative}
.board table{border-collapse:separate;border-spacing:0;width:100%;min-width:1060px;table-layout:fixed}
.board th{position:sticky;top:0;z-index:2;background:#f7f9fc;text-align:center;color:#647892;font-size:14px;padding:19px 9px;border-top:1px solid #e8eef5;border-bottom:1px solid #e2e9f2}
.board th:first-child{width:36%;text-align:left;padding-left:24px;left:0;z-index:4}
.board td{height:92px;text-align:center;padding:12px 7px;border-bottom:1px solid #edf2f8;background:white;vertical-align:middle}
.board td:first-child{position:sticky;left:0;z-index:1;text-align:left;padding:15px 24px;background:white;box-shadow:1px 0 #edf2f8}
.board tr:last-child td{border-bottom:0}.board tr.selected td{background:#f3f7ff}
.board .title-btn{border:0;background:none;color:#22314b;text-align:left;padding:6px 0;min-height:32px;font-weight:700;font-size:16px;cursor:pointer;line-height:1.55;white-space:normal;overflow-wrap:anywhere}
.board .title-btn:hover{color:#2361e9;text-decoration:underline}.board .sub{color:#8290a5;font-size:11px;display:block;margin-top:2px;line-height:1.5}
.board .cell{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-height:54px;cursor:pointer}
.board input[type=checkbox]{width:23px;height:23px;accent-color:#2676f6;cursor:pointer;margin:8px}
.board .cell small{font-size:11px;color:#8a97a9}.board .cell.done small{color:#3375d7}.board .not-applied{font-size:11px;color:#9ca8b8;line-height:1.8}
.board button:focus-visible,.board input:focus-visible{outline:3px solid #467df1;outline-offset:3px}
.board .status{font-size:13px;color:#2361c6;padding:12px 20px;min-height:45px;background:#fafcff;border-top:1px solid #e8eef5;margin:0}
.board .empty{padding:44px 25px;text-align:center;color:#7890a7;line-height:1.9}
.board .footer{font-size:11px;color:#8694a8;margin:13px 2px 0;line-height:1.7}
.board .cell.locked{cursor:default}.board input:disabled{cursor:not-allowed}
@media(max-width:900px){.board{padding:14px}.board .cards{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.board .card{padding:15px}.board h2{font-size:22px}.board .heading{align-items:flex-start;flex-direction:column}.board .card-top{flex-wrap:wrap;margin-bottom:12px}}
@media(max-width:550px){.board .cards{grid-template-columns:repeat(2,minmax(0,1fr))}.board .class-name{font-size:17px}.board .subject{font-size:11px}.board h2{font-size:20px}.board .panel-heading{padding:18px}.board .instructions{padding:0 18px 14px}}
"""

_JS = r"""
export default function(component) {
  const {data, parentElement, setTriggerValue} = component;
  const root = parentElement.querySelector('.board');
  const oldScroll = root.querySelector('.scroll');
  const oldLeft = oldScroll ? oldScroll.scrollLeft : 0;
  const oldTop = oldScroll ? oldScroll.scrollTop : 0;
  root.replaceChildren();
  let pending = false;
  const make = (tag, text='', cls='') => {
    const element = document.createElement(tag);
    element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const heading = make('header','','heading');
  heading.append(make('h2','수업 및 진도 관리 대시보드'));
  heading.append(make('div',[data.term, data.subject].filter(Boolean).join(' · '),'term'));
  root.append(heading);
  const cards = make('div','','cards');
  for (const item of data.cards) {
    const card = make('section','','card');
    card.setAttribute('aria-label',item.class_name+'반 진도');
    const top = make('div','','card-top');
    top.append(make('span',item.class_name+'반','class-name'));
    if(item.subject) top.append(make('span',item.subject,'subject'));
    const pct = make('div','','percent');
    pct.append(make('span','진도율'));
    pct.append(make('strong',item.percent == null ? '—' : Number(item.percent).toLocaleString('ko-KR',{maximumFractionDigits:1})+'%'));
    const bar=make('div','','bar');
    const fill=make('span');
    fill.style.width=Math.min(100,Math.max(0,Number(item.percent)||0))+'%';
    bar.setAttribute('role','progressbar');
    bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax','100');
    if(item.percent != null) bar.setAttribute('aria-valuenow',String(item.percent));
    bar.setAttribute('aria-label',item.class_name+'반 '+item.label);bar.append(fill);
    card.append(top,pct,bar,make('small',item.label));cards.append(card);
  }
  root.append(cards);
  const panel=make('section','','panel');
  const panelHead=make('div','','panel-heading');
  panelHead.append(make('h3','☷  수업내용별 진도 체크'));
  panelHead.append(make('span',data.rows.length+'개 수업내용','count'));
  panel.append(panelHead,make('p','☑ 수업함  □ 아직 수업하지 않음  ·  자료 배포와 수업 완료는 별도입니다. 제목을 누르면 자료 확인·반별 배포가 열립니다.','instructions'));
  const status=make('p','저장된 진도입니다. 체크할 때마다 서버에서 저장 결과를 확인합니다.','status');
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const emit=(value) => {
    if(pending) return;
    pending=true;
    root.querySelectorAll('button,input').forEach(el=>el.disabled=true);
    status.textContent=value.type==='toggle'?'GitHub에 진도 저장 중… 완료 여부는 저장 후 갱신됩니다.':'수업내용을 여는 중…';
    const event_id=globalThis.crypto?.randomUUID?.() || Date.now()+'-'+Math.random();
    setTriggerValue('event',{...value,event_id});
  };
  const scroller=make('div','','scroll');
  scroller.setAttribute('tabindex','0');scroller.setAttribute('aria-label','수업내용별 7개 반 진도표. 좌우로 스크롤할 수 있습니다.');
  const table=make('table');
  const thead=make('thead');const hr=make('tr');
  hr.append(make('th','수업내용'));
  for(const cls of data.classes) hr.append(make('th',cls+'반'));
  thead.append(hr);table.append(thead);
  const body=make('tbody');
  for(const [index,row] of data.rows.entries()){
    const tr=make('tr','',row.id===data.selected?'selected':'');
    const name=make('td');const btn=make('button',(index+1)+'. '+row.title,'title-btn');
    btn.type='button';btn.setAttribute('aria-label',row.title+' 자료 확인 및 배포');
    btn.onclick=()=>emit({type:'open',row_id:row.id});
    name.append(btn,make('small',row.subtitle||'','sub'));tr.append(name);
    for(const cls of data.classes){
      const td=make('td');const cell=row.cells[cls];
      if(!cell){td.append(make('span','—','not-applied'),make('small','미배포 / 미적용','sub'));}
      else{
        const label=make('label','', 'cell '+(cell.completed?'done ':'')+(cell.disabled?'locked':''));
        const box=document.createElement('input');box.type='checkbox';box.checked=!!cell.completed;box.disabled=!!cell.disabled;
        box.setAttribute('aria-label',row.title+' · '+cls+'반 수업 완료');
        box.title=cell.disabled?cell.reason:cell.completed?'완료 취소':'수업 완료로 저장';
        box.onchange=()=>{
          const next=box.checked;
          // Keep the saved state visible while awaiting the server; not an optimistic success.
          box.checked=!!cell.completed;
          emit({type:'toggle',course_id:cell.course_id,lesson_id:cell.lesson_id,
                expected_version:cell.expected_version,completed:next});
        };
        label.append(box,make('small',cell.disabled?cell.reason:(cell.completed?'수업함':'미수업')));
        if(cell.completed&&cell.actual_date) label.append(make('small',cell.actual_date.slice(5)));
        if(cell.makeup_needed) label.append(make('small','보충 필요'));
        td.append(label);
      }
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);scroller.append(table);panel.append(scroller);
  if(!data.rows.length) panel.append(make('div','아직 등록한 수업내용이 없습니다.\n위의 수업내용 업로드에서 제목과 자료를 등록하세요.','empty'));
  panel.append(status);root.append(panel);
  root.append(make('p','진도율 = 완료한 고유 수업내용 ÷ 해당 반에 적용된 수업내용. 미배포 항목은 그 반의 분모에 포함하지 않습니다.','footer'));
  scroller.scrollLeft=oldLeft;scroller.scrollTop=oldTop;
  return ()=>{};
}
"""


@lru_cache(maxsize=1)
def _component():
    return st.components.v2.component("teaching_progress_board", html='<div class="board"></div>', css=_CSS, js=_JS)


def render_grid(model, *, term, subject, selected="", key):
    if not hasattr(st.components, "v2"):
        st.error("진도 체크 표에는 기존 requirements.txt의 Streamlit 1.55 이상이 필요합니다. 의존성을 다시 설치해 주세요.")
        return None
    result = _component()(data=dict(model, term=term, subject=subject, selected=selected,
                                   render_revision=monotonic_ns()), key=key, on_event_change=lambda: None)
    return result.event if isinstance(result.event, dict) else None
