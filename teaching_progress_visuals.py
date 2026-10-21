"""Pure, escaped HTML for the teacher's progress overview (no scripts)."""
from __future__ import annotations
from html import escape

CSS = """<style>
.tp{--tp-ink:light-dark(#23334D,#E5ECFB);--tp-muted:light-dark(#69788D,#B5C3D9);--tp-line:light-dark(#DFE6EF,#41526A);--tp-paper:light-dark(#FFFFFF,#1B273B);color:var(--tp-ink);font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif}
.tp-hero{padding:24px 26px;border:1px solid var(--tp-line);border-radius:20px;background:linear-gradient(110deg,light-dark(#EDF3FF,#24334F),light-dark(#F1EBFB,#332D46));margin-bottom:18px}
.tp-eyebrow{font-size:12px;font-weight:800;letter-spacing:.07em;color:light-dark(#6D58A2,#D5BDEF)}
.tp-hero h2{font-size:27px;font-weight:800;margin:8px 0 9px;padding:0;color:var(--tp-ink)}
.tp-hero p{font-size:14px;line-height:1.65;margin:0;color:var(--tp-muted)}
.tp-cards{display:grid;grid-template-columns:repeat(7,minmax(145px,1fr));gap:10px;min-width:1080px;margin:12px 0 7px}
.tp-card{background:var(--tp-paper);border:1px solid var(--tp-line);border-top:4px solid light-dark(#859BD4,#9FB5EF);border-radius:14px;padding:15px 13px;min-width:0}
.tp-card:nth-child(2n){border-top-color:light-dark(#8CBBA6,#8CBBA6)}
.tp-card:nth-child(3n){border-top-color:light-dark(#B69CD4,#B69CD4)}
.tp-card h3{font-size:19px;margin:0 0 11px;padding:0;color:var(--tp-ink)}
.tp-label{font-size:11px;color:var(--tp-muted);font-weight:800;margin:11px 0 4px}
.tp-card .tp-copy{font-size:12px;line-height:1.5;overflow-wrap:anywhere;white-space:pre-wrap;max-height:58px;overflow:auto}
.tp-date{font-size:11px;color:var(--tp-muted);margin:3px 0 0}
.tp-assessment{background:light-dark(#FFF3E4,#3D322A);border:1px solid light-dark(#F2DDC2,#816A50);border-radius:8px;padding:8px;margin-top:12px}
.tp-assessment .tp-label{margin-top:0;color:light-dark(#95602F,#F2C68F)}
.tp-scroll{max-width:100%;overflow:auto;border-radius:14px;margin-bottom:16px}
.tp-table-wrap{border:1px solid var(--tp-line);border-radius:14px;background:var(--tp-paper);max-height:650px}
.tp table{border-collapse:separate;border-spacing:0;width:100%;min-width:1100px;font-size:13px}
.tp th{background:light-dark(#F1F4FA,#27364B);text-align:left;color:var(--tp-muted);font-weight:750;padding:14px 12px;white-space:nowrap;border-bottom:1px solid var(--tp-line);position:sticky;top:0;z-index:1}
.tp td{border-bottom:1px solid var(--tp-line);padding:14px 12px;vertical-align:top;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;min-width:66px;max-width:320px}
.tp td:nth-child(1){white-space:nowrap;min-width:96px}
.tp th:nth-child(6),.tp td:nth-child(6){min-width:220px}
.tp tbody tr:last-child td{border-bottom:0}
.tp tbody tr:hover{background:light-dark(#F9FAFF,#243349)}
.tp-badge{display:inline-block;padding:3px 9px;border-radius:7px;font-size:12px;font-weight:750;white-space:nowrap;background:light-dark(#EDF2FC,#334360);color:light-dark(#3F608E,#BED8FF)}
.tp-done{background:light-dark(#E7F5ED,#274637);color:light-dark(#327657,#B9F0CD)}
.tp-progress{background:light-dark(#FFF3D9,#493D29);color:light-dark(#926B22,#FAD58C)}
.tp-cancel{background:light-dark(#F2F3F5,#3D424C);color:light-dark(#6B7482,#CAD1DD)}
.tp-danger{font-size:11px;color:light-dark(#A95742,#F3AE97);margin-top:9px}
.tp-empty{padding:28px;text-align:center;color:var(--tp-muted);border:1px dashed var(--tp-line);border-radius:14px}
.tp-note{font-size:12px;color:var(--tp-muted);margin:8px 0 16px;line-height:1.7}
@media(max-width:640px){.tp-hero{padding:20px}.tp-hero h2{font-size:24px}.tp-cards{min-width:0;grid-template-columns:repeat(2,minmax(135px,1fr))}.tp-card:last-child{grid-column:span 2}.tp-card{padding:12px}.tp table{font-size:12px}}
</style>"""


def esc(value):
    return escape(str(value or ""), quote=True)


def hero_html() -> str:
    return CSS + '<section class="tp tp-hero"><div class="tp-eyebrow">TEACHER ONLY · 수업 기록</div><h2>진도관리</h2><p>오늘의 수업부터 다음 수행평가까지, 반별로 차근차근 기록하세요.<br>수업일과 수행평가일을 따로 관리하고, 1-1반부터 1-7반까지 한눈에 확인합니다.</p></section>'


def cards_html(summaries: list[dict], today: str) -> str:
    cards = []
    for item in summaries:
        last, nex, assess = item.get("last"), item.get("next"), item.get("assessment")
        def lesson_block(label, row):
            if row:
                return (f'<div class="tp-label">{label}</div><div class="tp-copy">{esc(row["content"])}</div>'
                        f'<div class="tp-date">{esc(row["date"])} · {esc(row["subject"])}</div>')
            return f'<div class="tp-label">{label}</div><div class="tp-copy">기록 없음</div>'
        a = (f'<div class="tp-copy">{esc(assess["assessment_title"])}</div><div class="tp-date">{esc(assess["assessment_date"])} · {esc(assess["assessment_period"])}</div>'
             if assess else '<div class="tp-copy">예정 없음</div>')
        undated = f'<div class="tp-date">날짜 미정 {item["undated"]}건</div>' if item.get("undated") else ''
        overdue = f'<div class="tp-danger">지난 예정일 · 상태 확인 {item["overdue"]}건</div>' if item.get("overdue") else ''
        cards.append(f'<article class="tp-card"><h3>{esc(item["class"])}반</h3>'
                     + lesson_block("최근 완료 수업", last) + lesson_block("다음 예정 수업", nex)
                     + f'<div class="tp-assessment"><div class="tp-label">다가오는 수행평가</div>{a}{undated}</div>{overdue}</article>')
    return ('<div class="tp"><div class="tp-scroll"><div class="tp-cards">' + ''.join(cards)
            + f'</div></div><p class="tp-note">{esc(today)} 기준 · 현재 선택한 과목의 전체 기록입니다. 아래 표의 조회 기간과는 별도입니다. '
              '지난 예정일은 미수업으로 단정하지 않고 상태 확인 대상으로 표시합니다.</p></div>')


def table_html(display_rows: list[dict]) -> str:
    if not display_rows:
        return '<div class="tp tp-empty">선택한 조건에 해당하는 기록이 없어요. 새 기록을 등록하거나 조회 기간을 바꿔 주세요.</div>'
    heads = list(display_rows[0])
    parts = ['<div class="tp"><div class="tp-scroll tp-table-wrap" tabindex="0" role="region" aria-label="진도관리 기록표, 가로로 스크롤할 수 있습니다"><table><thead><tr>']
    parts += [f'<th scope="col">{esc(h)}</th>' for h in heads]
    parts.append('</tr></thead><tbody>')
    for row in display_rows:
        parts.append('<tr>')
        for head in heads:
            value = row.get(head, "")
            content = esc(value) or '—'
            if head in ("진행 상태", "평가 상태") and value:
                kind = ' tp-done' if value == '완료' else ' tp-progress' if value == '진행 중' else ' tp-cancel' if value in ('휴강', '취소') else ''
                content = f'<span class="tp-badge{kind}">{content}</span>'
            parts.append(f'<td>{content}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div></div>')
    return ''.join(parts)
