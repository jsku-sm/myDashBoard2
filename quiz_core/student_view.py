"""Read-only student layout helpers. Never infer answers or include answer keys."""
from __future__ import annotations
from html import escape
import re

def e(value):
    return escape(str(value), quote=True)

STYLE = """<style>
.qz-hero,.qz-header,.qz-visual{font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;}
.qz-hero{padding:24px 26px;border:1px solid light-dark(#d9e2f8,#485773);border-radius:22px;background:light-dark(#f3f6ff,#25304a);color:light-dark(#243452,#e4ecfc);margin-bottom:8px;}
.qz-kicker{font-size:.78rem;letter-spacing:.08em;font-weight:800;color:light-dark(#586fa4,#b8cafa);}
.qz-hero h2{font-size:1.55rem;margin:8px 0 10px;line-height:1.45;overflow-wrap:anywhere;}
.qz-hero p{font-size:.87rem;color:light-dark(#63728a,#c5cfe0);margin:8px 0 14px;}
.qz-pills{display:flex;gap:7px;flex-wrap:wrap;align-items:center;}
.qz-pill{display:inline-flex;align-items:center;gap:5px;border:1px solid light-dark(#dbe2ee,#536482);border-radius:20px;background:light-dark(#fff,#2c3951);padding:5px 11px;font-size:.8rem;}
.qz-steps{display:flex;gap:7px;flex-wrap:wrap;margin:16px 0 0;}
.qz-step{display:inline-flex;align-items:center;justify-content:center;gap:3px;min-width:36px;height:34px;border:1px solid light-dark(#cfd8ec,#536482);border-radius:10px;background:light-dark(#fff,#202c43);font-size:.8rem;font-weight:750;}
.qz-step.done{background:light-dark(#dcefe8,#254a40);color:light-dark(#28624d,#b3efd6);border-color:light-dark(#a7cfbe,#548b75);}
.qz-header{display:flex;gap:13px;align-items:center;margin:0 0 12px;}
.qz-number{background:light-dark(#e8e7fb,#393454);color:light-dark(#655390,#d6c9fb);width:49px;height:49px;border-radius:14px;display:grid;place-items:center;font-weight:850;font-size:1.4rem;flex-shrink:0;}
.qz-eyebrow{font-size:.78rem;color:light-dark(#697992,#bcc9dc);font-weight:650;}
.qz-selected{display:inline-flex;margin-top:4px;font-size:.8rem;font-weight:700;color:light-dark(#40745f,#b0dfc9);}
.qz-prompt{padding:17px 19px;border-radius:15px;background:light-dark(#f6f8fe,#263248);border-left:4px solid #afa2d2;font-size:1.12rem;line-height:1.8;color:light-dark(#263454,#eef2fd);white-space:pre-wrap;overflow-wrap:anywhere;}
.qz-visual{padding:16px 18px;border:1px dashed light-dark(#d5dfef,#556781);border-radius:14px;background:light-dark(#fafcff,#1f2b42);margin:14px 0;color:light-dark(#344863,#dce9fb);}
.qz-visual small{display:block;color:light-dark(#677b94,#b5c8e0);font-size:.75rem;margin-bottom:12px;}
.qz-logic{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.qz-logic div{flex:1;min-width:120px;background:light-dark(#eaf1fd,#2b3e59);padding:12px;border-radius:12px;}
.qz-logic b{display:block;line-height:1.7;font-size:1rem;}
.qz-logic span{font-size:.74rem;opacity:.8;}
.qz-axis{display:block;max-width:460px;width:100%;height:auto;margin:auto;}
.qz-matrices{display:flex;gap:20px;align-items:center;flex-wrap:wrap;}
.qz-matrix{display:grid;gap:10px 18px;padding:8px 15px;border-left:2px solid currentColor;border-right:2px solid currentColor;}
.qz-matrix span{min-width:22px;text-align:center;font-family:Georgia,'Malgun Gothic',sans-serif;font-size:1.1rem;}
/* Scope styling to quiz question containers; keep native radio semantics. */
[class*="st-key-qv_item_"]{background:light-dark(#fff,#192339);border-radius:20px!important;padding:20px!important;border:1px solid light-dark(#e0e5ef,#40526d)!important;}
[class*="st-key-qv_item_"] [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px!important;}
[class*="st-key-qv_item_"] [role="radiogroup"]>label{width:100%;min-height:68px;border:1.5px solid light-dark(#dce3ef,#4c5e7c);border-radius:14px;padding:13px 15px!important;margin:0!important;align-items:center!important;background:light-dark(#fff,#233049);}
[class*="st-key-qv_item_"] [role="radiogroup"]>label:has(input:checked){background:light-dark(#eeebfc,#3c3155);border-color:light-dark(#9884c3,#b79cd8);box-shadow:0 0 0 1px light-dark(#c8bce8,#9174b8);}
[class*="st-key-qv_item_"] [role="radiogroup"]>label:focus-within{outline:3px solid #779fe3;outline-offset:2px;}
[class*="st-key-qv_item_"] [role="radiogroup"]>label p{font-size:1.03rem!important;line-height:1.65!important;overflow-wrap:anywhere;}
@media(max-width:620px){.qz-hero{padding:18px;}.qz-hero h2{font-size:1.22rem;}.qz-prompt{padding:13px;font-size:1.02rem;}[class*="st-key-qv_item_"]{padding:15px!important;}[class*="st-key-qv_item_"] [role="radiogroup"]{grid-template-columns:1fr;}.qz-logic div{min-width:95px;}}
@media(prefers-reduced-motion:reduce){[class*="st-key-qv_item_"] *{transition:none!important;}}
</style>"""

def hero_html(paper):
    questions=paper["questions"]
    answers=paper.get("answers",{})
    total=len(questions)
    answered=sum(q["id"] in answers for q in questions)
    parts=['<section class="qz-hero" aria-label="개념 퀴즈 안내">',
           '<div class="qz-kicker">CONCEPT CHECK · 나의 생각을 확인해요</div>',
           f'<h2>{e(paper["title"])}</h2><div class="qz-pills">',
           f'<span class="qz-pill">{e(paper.get("subject",""))}</span>',
           f'<span class="qz-pill">총 {total}문항</span>',
           f'<span class="qz-pill">선택 {answered} / {total}</span></div>',
           '<p>한 문제씩 차근차근 풀어 보세요. 정답은 선생님이 결과를 공개한 뒤 확인할 수 있어요.</p>',
           '<div class="qz-steps" aria-label="문항별 답 선택 현황">']
    for i,q in enumerate(questions,1):
        done=q["id"] in answers
        parts.append(f'<span class="qz-step{" done" if done else ""}" title="{i}번 · {"선택 완료" if done else "미선택"}">{i:02d}{" ✓" if done else ""}</span>')
    parts.append('</div></section>')
    return ''.join(parts)


def question_html(question, number, total, selected=None):
    status="아직 선택하지 않았어요" if selected is None else f"{selected+1}번 보기를 선택했어요"
    return (f'<div class="qz-header"><div class="qz-number">{number:02d}</div>'
            f'<div><div class="qz-eyebrow">문항 {number} / {total} · 보기 하나를 선택하세요</div>'
            f'<span class="qz-selected">{e(status)}</span></div></div>'
            f'<div class="qz-prompt">{e(question["prompt"])}</div>')


def given_visual_html(prompt):
    """Draw only givens explicitly present in the prompt; never compute a target."""
    proposition=re.search(r"명제 [‘'](.+?)이면 (.+?)[’']의",prompt)
    if proposition:
        left,right=proposition.groups()
        return ('<div class="qz-visual"><small>문제에 제시된 명제 · 화살표는 ‘이면’을 나타냅니다.</small>'
                f'<div class="qz-logic"><div><span>가정</span><b>{e(left)}</b></div>'
                f'<b aria-hidden="true">→</b><div><span>결론</span><b>{e(right)}</b></div></div></div>')
    points=re.findall(r"\b([AB])\((-?\d+),\s*(-?\d+)\)",prompt)
    if len(points)>=2:
        pts=[(name,int(x),int(y)) for name,x,y in points[:2]]
        xmin=min(0,*(p[1] for p in pts))-2; xmax=max(0,*(p[1] for p in pts))+2
        ymin=min(0,*(p[2] for p in pts))-2; ymax=max(0,*(p[2] for p in pts))+2
        # Equal scale on both axes: do not visually distort the given geometry.
        scale=min(310/max(1,xmax-xmin),170/max(1,ymax-ymin))
        dx=(420-(xmax-xmin)*scale)/2
        dy=(230-(ymax-ymin)*scale)/2
        xp=lambda x:dx+(x-xmin)*scale
        yp=lambda y:dy+(ymax-y)*scale
        parts=['<div class="qz-visual"><small>주어진 점의 위치 · 구할 점과 정답은 표시하지 않습니다.</small>',
               '<svg class="qz-axis" viewBox="0 0 420 230" role="img" aria-label="문제에 주어진 두 점의 좌표">',
               f'<path d="M20 {yp(0):.2f}H400 M{xp(0):.2f} 10V218" stroke="currentColor" stroke-width="1" opacity=".45" fill="none"/>']
        for n,x,y in pts:
            label_y=yp(y)-14 if n=='A' else yp(y)+24
            parts.append(f'<circle cx="{xp(x):.2f}" cy="{yp(y):.2f}" r="5" fill="currentColor"/>'
                         f'<text x="{xp(x):.2f}" y="{label_y:.2f}" text-anchor="middle" font-size="12" fill="currentColor">{n}({x}, {y})</text>')
        parts.append('</svg></div>')
        return ''.join(parts)
    matrices=re.findall(r"\[\[([0-9x ,\-]+)\](?:,\s*\[([0-9x ,\-]+)\])?\]",prompt)
    if matrices:
        parts=['<div class="qz-visual"><small>문제에 주어진 행렬을 펼쳐 보았어요.</small><div class="qz-matrices">']
        for first,second in matrices[:3]:
            rows=[first]+([second] if second else [])
            cells=[[v.strip() for v in row.split(",")] for row in rows]
            cols=len(cells[0])
            if not cols or any(len(row)!=cols for row in cells): continue
            parts.append(f'<div class="qz-matrix" style="grid-template-columns:repeat({cols},minmax(22px,1fr))">')
            parts.extend(f'<span>{e(v)}</span>' for row in cells for v in row)
            parts.append('</div>')
        parts.append('</div></div>')
        return ''.join(parts)
    return ""
