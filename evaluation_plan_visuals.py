"""Conservative, local-only evaluation-plan visualisation.

No model/API/PDF extraction. Only explicitly written numbers are plotted; the
original description stays the source of truth. This module has no Streamlit
or storage dependencies, and escapes every piece of teacher-supplied text.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import html
import re
import unicodedata


_SECTION_MARKERS = [
    ("weights", r"(?:성적\s*반영\s*비율|평가\s*반영\s*비율|평가\s*비율)"),
    ("schedule", r"(?:단원별\s*(?:주요\s*)?학습\s*내용|단원별\s*수업\s*계획|학습\s*일정|수업\s*일정)"),
    ("criteria", r"(?:성취도\s*산출(?:\s*및\s*미도달\s*(?:\(F\))?\s*기준)?|성취도\s*평가\s*[:：]|이수\s*기준\s*[:：])"),
]
_GROUP = re.compile(r"(?P<label>지필\s*(?:고사|평가)|수행\s*평가)\s*(?:[:：]\s*)?\(?\s*(?P<pct>\d+(?:\.\d+)?)\s*%\s*\)?")
_CHILD = re.compile(
    r"(?P<label>중간\s*고사|기말\s*고사|(?:수학\s*)?탐구\s*활동\s*\d+|"
    r"수행\s*(?:평가|과제)\s*\d+|프로젝트(?:\s*\d+)?|포트폴리오|발표(?:\s*평가)?|보고서(?:\s*평가)?)"
    r"\s*(?:[:：]\s*)?\(?\s*(?P<pct>\d+(?:\.\d+)?)\s*%\s*\)?"
)
_PERIOD = r"(?:\d{1,2}\s*월?\s*[~∼〜–—-]\s*)?\d{1,2}\s*월"
_UNIT_NAMES = (
    "도형의 방정식", "집합과 명제", "집합·명제", "함수와 그래프", "함수의 뜻과 그래프",
    "직선의 방정식", "원의 방정식", "도형의 이동", "평행이동", "대칭이동", "평면좌표",
    "선분의 내분", "집합의 연산", "명제와 조건", "합성함수", "역함수", "집합", "명제", "함수",
)
_SCHEDULE_KNOWN = re.compile(
    r"(?P<title>" + "|".join(re.escape(n) for n in sorted(_UNIT_NAMES, key=len, reverse=True)) +
    r")\s*\(\s*(?P<period>" + _PERIOD + r")\s*\)\s*[:：]"
)
_SCHEDULE_LINE = re.compile(
    r"(?m)^[ \t]*(?:[-*•]\s*)?(?P<title>[^\n():：]{1,50}?)\s*\(\s*(?P<period>" +
    _PERIOD + r")\s*\)\s*[:：]"
)


def _normalise(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    # Formatting marks are not substantive plan content. Original is kept intact.
    return value.replace("**", "").replace("__", "")


def _clean(text: str) -> str:
    text = text.strip(" \n\t:：/+-·")
    # Remove an isolated list number at a section boundary, never a decimal.
    return re.sub(r"(?:^|\s)\d{1,2}[.)]\s*$", "", text).strip()


def _pct(text: str) -> Decimal | None:
    try:
        number = Decimal(text)
    except (InvalidOperation, TypeError):
        return None
    return number if number.is_finite() and 0 <= number <= 100 else None


def _num(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _sections(text: str) -> dict[str, str]:
    found = []
    for kind, pattern in _SECTION_MARKERS:
        match = re.search(pattern, text)
        if match:
            found.append((match.start(), match.end(), kind))
    found.sort()
    result: dict[str, str] = {}
    for i, (start, end, kind) in enumerate(found):
        stop = found[i + 1][0] if i + 1 < len(found) else len(text)
        # Preserve the criterion heading: it can be the only meaningful label.
        body = text[start if kind == "criteria" else end:stop]
        result[kind] = _clean(body)
    return result


def _extract_weights(body: str) -> tuple[list[dict], bool, list[str]]:
    matches = list(_GROUP.finditer(body))
    groups, warnings, seen = [], [], set()
    for i, match in enumerate(matches):
        canonical = "지필평가" if match.group("label").startswith("지필") else "수행평가"
        pct = _pct(match.group("pct"))
        if canonical in seen:
            warnings.append(f"{canonical} 비율이 여러 번 적혀 있어요. 원문의 기준을 확인해 주세요.")
            continue
        seen.add(canonical)
        if pct is None:
            warnings.append(f"{canonical} 비율이 0~100% 범위를 벗어나 그래프에서 제외했어요.")
            continue
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        details = body[match.end():stop]
        child_matches = list(_CHILD.finditer(details))
        children = []
        for j, child in enumerate(child_matches):
            child_pct = _pct(child.group("pct"))
            if child_pct is None:
                warnings.append("세부 평가 비율이 0~100% 범위를 벗어나 원문 확인이 필요해요.")
                continue
            child_stop = child_matches[j + 1].start() if j + 1 < len(child_matches) else len(details)
            children.append({"label": child.group("label"), "percent": _num(child_pct),
                             "note": _clean(details[child.end():child_stop])})
        if children and sum(Decimal(c["percent"]) for c in children) != pct:
            warnings.append(f"{canonical}의 세부 항목 합계와 전체 반영 비율이 달라요. "
                            "평가 내부 비율인지 원문에서 확인해 주세요. 숫자는 보정하지 않았어요.")
        groups.append({"label": match.group("label"), "kind": canonical, "percent": _num(pct),
                       "intro": _clean(details[:child_matches[0].start()] if child_matches else details),
                       "children": children})
    valid = bool(groups) and sum(Decimal(g["percent"]) for g in groups) == Decimal("100")
    if matches and not valid:
        warnings.append("인식한 전체 평가 비율의 합계가 100%가 아니므로 구성비 막대는 표시하지 않았어요. 원문을 확인해 주세요.")
    # Ambiguous/invalid repeated groups are not suitable for a composition chart.
    if len(matches) != len(groups):
        valid = False
    return groups, valid, warnings


def _valid_period(value: str) -> bool:
    numbers = [int(n) for n in re.findall(r"\d+", value)]
    return bool(numbers) and all(1 <= n <= 12 for n in numbers)


def _extract_schedule(body: str) -> list[dict]:
    if not body:
        return []
    matches = list(_SCHEDULE_KNOWN.finditer(body))
    for candidate in _SCHEDULE_LINE.finditer(body):
        if not any(a.start() < candidate.end() and candidate.start() < a.end() for a in matches):
            matches.append(candidate)
    matches.sort(key=lambda m: m.start())
    rows = []
    for i, match in enumerate(matches):
        if not _valid_period(match.group("period")):
            continue
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        rows.append({"title": match.group("title").strip(), "period": match.group("period").strip(),
                     "detail": _clean(body[match.end():stop])})
    return rows


def _extract_criteria(body: str) -> list[dict]:
    if not body:
        return []
    # Keep the source's actual claims, including dates, thresholds and caveats.
    markers = list(re.finditer(
        r"(?P<label>성취도\s*평가|이수\s*/\s*미이수\s*(?:\(P/F\))?\s*기준|"
        r"이수\s*기준|미이수\s*기준|최소\s*성취수준\s*보장\s*지도)\s*[:：]", body))
    if not markers:
        return [{"label": "성취 기준 안내", "text": body}]
    rows = []
    for i, marker in enumerate(markers):
        stop = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        rows.append({"label": marker.group("label"), "text": _clean(body[marker.end():stop])})
    return rows


def analyse_plan(description: str) -> dict:
    """Recognise familiar headings without changing stored source text.

    Unknown formats remain readable as section cards or a full text card.
    This function never invents a subject's official grading rules or dates.
    """
    if not isinstance(description, str):
        description = "" if description is None else str(description)
    text = _normalise(description)
    sections = _sections(text)
    # No recognised headings: percentages can still be recognised by labels.
    weights_body = sections.get("weights", text.split(sections.get("schedule", "\0"))[0])
    groups, valid, warnings = _extract_weights(weights_body)
    schedule = _extract_schedule(sections.get("schedule", ""))
    criteria = _extract_criteria(sections.get("criteria", ""))
    return {"groups": groups, "composition_valid": valid, "schedule": schedule,
            "criteria": criteria, "sections": sections, "warnings": warnings,
            "source": description, "has_content": bool(description.strip())}


CSS = """
<style>
.epv{--ep-ink:#203052;--ep-muted:#66758d;--ep-blue:#3e70c4;--ep-purple:#8b62c6;
 color:var(--ep-ink);font-family:inherit;line-height:1.65;box-sizing:border-box;width:100%;}
.epv *{box-sizing:border-box;}
.epv .ep-kicker{font-size:12px;letter-spacing:.07em;color:var(--ep-muted);margin:0 0 8px;}
.epv .ep-section{background:#fff;border:1px solid #e0e7f1;border-radius:18px;padding:22px;margin:12px 0 18px;}
.epv .ep-heading{color:var(--ep-ink)!important;font-family:inherit!important;font-size:19px;font-weight:800!important;display:flex;gap:10px;align-items:center;margin:0 0 17px;}
.epv .ep-index{display:inline-flex;align-items:center;justify-content:center;background:#edf2fb;
 color:var(--ep-blue);font-size:13px;font-weight:800;width:30px;height:30px;border-radius:10px;flex:none;}
.epv .ep-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:14px;}
.epv .ep-card{border:1px solid #dfe7f3;border-radius:14px;padding:17px 19px;background:#f5f8fd;min-width:0;}
.epv .ep-card:nth-child(2n){background:#f8f5fc;border-color:#e8dff6;}
.epv .ep-card-title{font-size:16px;font-weight:750;}
.epv .ep-value{font-size:36px;letter-spacing:-.04em;line-height:1.2;font-weight:850;margin:8px 0 4px;color:var(--ep-blue);}
.epv .ep-card:nth-child(2n) .ep-value{color:var(--ep-purple);}
.epv .ep-sub{font-size:12px;color:var(--ep-muted);}
.epv .ep-source{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;margin:5px 0 0;}
.epv .ep-child{background:rgba(255,255,255,.9);border:1px solid #e4e9f1;border-radius:10px;padding:11px 13px;margin-top:10px;}
.epv .ep-child-head{display:flex;gap:10px;justify-content:space-between;font-size:14px;font-weight:750;}
.epv .ep-child-head strong{white-space:nowrap;}
.epv .ep-composition{height:38px;border-radius:10px;display:flex;overflow:hidden;margin:15px 0 5px;background:#eef1f6;}
.epv .ep-segment{background:var(--ep-blue);height:100%;min-width:0;}
.epv .ep-segment:nth-child(2n){background:var(--ep-purple);}
.epv .ep-legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--ep-muted);}
.epv .ep-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:var(--ep-blue);}
.epv .ep-legend span:nth-child(2n) .ep-dot{background:var(--ep-purple);}
.epv .ep-period{display:inline-block;background:#dff2ee;color:#246459;border-radius:8px;padding:3px 10px;font-size:13px;font-weight:750;margin-bottom:10px;}
.epv .ep-timeline .ep-card{background:#f5fbf9;border-color:#dcece7;}
.epv .ep-criteria .ep-card{background:#fffaf0;border-color:#efe4cc;}
.epv .ep-alert{background:#fff8e7;border:1px solid #edddb2;color:#77551e;border-radius:10px;padding:12px 15px;font-size:13px;margin:10px 0;}
.epv .ep-note{color:var(--ep-muted);font-size:12px;margin:10px 1px 0;overflow-wrap:anywhere;}
@media(max-width:600px){.epv .ep-section{padding:16px;}.epv .ep-heading{font-size:17px;}.epv .ep-value{font-size:31px;}}
</style>
"""


def _escape(text) -> str:
    return html.escape(str(text), quote=True)


def render_plan_html(description: str) -> str:
    """Scoped responsive HTML, no JavaScript and no external network resources."""
    data = analyse_plan(description)
    if not data["has_content"]:
        return CSS + '<section class="epv"><div class="ep-section"><p class="ep-note">평가계획 설명이 아직 없어요. 첨부파일을 확인해 주세요.</p></div></section>'
    parts = [CSS, '<section class="epv" aria-label="평가계획 한눈에 보기">',
             '<p class="ep-kicker">평가계획 한눈에 보기 · 저장된 텍스트 기준</p>']
    number = 0

    def start(title: str, css: str = ""):
        nonlocal number
        number += 1
        parts.append(f'<section class="ep-section {css}"><h3 class="ep-heading"><span class="ep-index">{number:02d}</span>{_escape(title)}</h3>')

    if data["groups"]:
        start("성적 반영 비율")
        parts.append('<div class="ep-grid">')
        for group in data["groups"]:
            parts.append(f'<article class="ep-card"><div class="ep-card-title">{_escape(group["label"])}</div>'
                         f'<div class="ep-value">{_escape(group["percent"])}<span style="font-size:20px">%</span></div><div class="ep-sub">원문에 기재된 반영 비율</div>')
            if group["intro"]:
                parts.append(f'<p class="ep-source">{_escape(group["intro"])}</p>')
            for child in group["children"]:
                parts.append(f'<div class="ep-child"><div class="ep-child-head"><span>{_escape(child["label"])}</span><strong>{_escape(child["percent"])}%</strong></div>')
                if child["note"]:
                    parts.append(f'<p class="ep-source">{_escape(child["note"])}</p>')
                parts.append('</div>')
            parts.append('</article>')
        parts.append('</div>')
        if data["composition_valid"]:
            aria = " / ".join(f'{g["label"]} {g["percent"]}%' for g in data["groups"])
            parts.append(f'<div class="ep-composition" role="img" aria-label="{_escape(aria)}">')
            for g in data["groups"]:
                # percent is a range-checked Decimal, never a raw style string.
                parts.append(f'<div class="ep-segment" style="width:{g["percent"]}%"></div>')
            parts.append('</div><div class="ep-legend">')
            for g in data["groups"]:
                parts.append(f'<span><i class="ep-dot"></i>{_escape(g["label"])} {_escape(g["percent"])}%</span>')
            parts.append('</div>')
        for warning in data["warnings"]:
            parts.append(f'<div class="ep-alert">{_escape(warning)}</div>')
        parts.append('</section>')
    elif data["sections"].get("weights"):
        start("평가 안내")
        parts.append(f'<p class="ep-source">{_escape(data["sections"]["weights"])}</p>')
        parts.append('<p class="ep-note">명확한 평가 항목·비율을 찾지 못해 숫자 그래프 대신 원문을 표시합니다.</p></section>')
    if data["schedule"]:
        start("단원별 학습 일정", "ep-timeline")
        parts.append('<div class="ep-grid">')
        for item in data["schedule"]:
            parts.append(f'<article class="ep-card"><span class="ep-period">{_escape(item["period"])}</span>'
                         f'<div class="ep-card-title">{_escape(item["title"])}</div><p class="ep-source">{_escape(item["detail"])}</p></article>')
        parts.append('</div></section>')
    elif data["sections"].get("schedule"):
        start("단원별 학습 내용", "ep-timeline")
        parts.append(f'<p class="ep-source">{_escape(data["sections"]["schedule"])}</p></section>')
    if data["criteria"]:
        start("성취도 · 이수 기준", "ep-criteria")
        parts.append('<div class="ep-grid">')
        for item in data["criteria"]:
            parts.append(f'<article class="ep-card"><div class="ep-card-title">{_escape(item["label"])}</div>'
                         f'<p class="ep-source">{_escape(item["text"])}</p></article>')
        parts.append('</div></section>')
    if not number:
        start("평가계획 안내")
        parts.append(f'<p class="ep-source">{_escape(data["source"])}</p></section>')
    parts.append('<p class="ep-note">입력된 텍스트를 항목별로 정리한 화면입니다. 평가 기준을 새로 판단하거나 보완하지 않습니다. 전체 내용은 아래 원문과 첨부파일을 확인해 주세요.</p></section>')
    return "".join(parts)
