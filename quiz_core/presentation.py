"""Escaped, read-only teacher monitoring view; no answer keys in client scripts."""
from html import escape

STYLE = '''<style>
.quiz-board {font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:light-dark(#25324a,#e3eafa);padding:4px 0 12px;}
.quiz-board * {box-sizing:border-box;}
.quiz-board .qb-top {display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;}
.quiz-board h3 {margin:0;font-size:1.2rem;}
.quiz-board .qb-live {font-size:.78rem;background:light-dark(#e7f6f0,#203f36);color:light-dark(#27684c,#9fdfb8);padding:6px 10px;border-radius:20px;}
.quiz-board .qb-metrics {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0;}
.quiz-board .qb-metric {background:light-dark(#fff,#202b40);border:1px solid light-dark(#dce4ef,#495872);border-radius:15px;padding:14px 16px;}
.quiz-board .qb-metric small {display:block;color:light-dark(#65748c,#b7c5d8);font-size:.78rem;}
.quiz-board .qb-metric b {display:block;font-size:1.6rem;margin-top:5px;}
.quiz-board .qb-scroll {overflow:auto;border:1px solid light-dark(#dbe3ef,#4b5c77);border-radius:14px;max-height:520px;background:light-dark(#fff,#202b40);}
.quiz-board table {border-collapse:separate;border-spacing:0;width:100%;min-width:1060px;font-size:.84rem;}
.quiz-board th {position:sticky;top:0;z-index:1;background:light-dark(#edf2fb,#293650);color:light-dark(#536680,#c6d5ea);padding:12px 8px;font-weight:700;border-bottom:1px solid light-dark(#dbe3ef,#4b5c77);white-space:nowrap;}
.quiz-board td {padding:10px 8px;border-bottom:1px solid light-dark(#edf1f6,#354159);text-align:center;white-space:nowrap;}
.quiz-board tr:last-child td {border-bottom:0;}
.quiz-board .qb-person {position:sticky;left:0;text-align:left;background:light-dark(#fff,#202b40);min-width:145px;z-index:1;}
.quiz-board th.qb-person {background:light-dark(#edf2fb,#293650);z-index:2;}
.quiz-board .qb-person small {display:block;color:light-dark(#708099,#b7c5d8);font-size:.71rem;padding-top:3px;}
.quiz-board .qb-mark {display:inline-flex;min-width:44px;justify-content:center;gap:5px;border-radius:8px;padding:7px 4px;}
.quiz-board .qb-ok {background:light-dark(#e2f5ec,#203f36);color:light-dark(#27694a,#a7e5ba);font-weight:800;}
.quiz-board .qb-no {background:light-dark(#ffe9e7,#482e34);color:light-dark(#ae3c39,#ffb8b3);font-weight:800;}
.quiz-board .qb-wait {background:light-dark(#f0effb,#34304b);color:light-dark(#6a5e96,#dacdf9);}
.quiz-board .qb-blank {color:light-dark(#7d899b,#b7c5d8);}
.quiz-board .qb-stats {display:grid;grid-template-columns:repeat(var(--qb-count,10),minmax(65px,1fr));gap:8px;overflow:auto;margin:10px 0;}
.quiz-board .qb-stat {background:light-dark(#fff,#202b40);border:1px solid light-dark(#e0e6ef,#495872);padding:10px 7px;border-radius:12px;text-align:center;min-width:65px;}
.quiz-board .qb-stat b {display:block;color:light-dark(#ad4843,#ffb8b3);font-size:1.3rem;margin:6px 0;}
.quiz-board .qb-stat small {font-size:.66rem;color:light-dark(#6b7990,#bac5d6);display:block;}
.quiz-board .qb-bar {height:5px;border-radius:4px;background:light-dark(#f1e8e8,#3a3447);margin-top:9px;overflow:hidden;}
.quiz-board .qb-bar span {display:block;height:100%;background:#d47c75;}
.quiz-board .qb-note {color:light-dark(#66758b,#c0c9d8);font-size:.76rem;line-height:1.65;margin:10px 0;}
.quiz-board .qb-legend {font-size:.78rem;line-height:1.6;margin:10px 0;color:light-dark(#66758b,#c0c9d8);}
@media(max-width:700px){.quiz-board .qb-metrics{grid-template-columns:repeat(2,1fr);gap:8px;}.quiz-board .qb-metric{padding:10px;}}
</style>'''
CIRCLES = ['①','②','③','④']
STATE = {'not_started':'아직 시작 전','working':'풀이 중','submitted':'제출','graded':'채점 완료'}


def dashboard_html(board):
    e=lambda v:escape(str(v),quote=True)
    title=board['quiz']['title']
    count=len(board['questions'])
    mean='—' if board['mean'] is None else f"{board['mean']:.1f}점"
    parts=[STYLE,'<section class="quiz-board" aria-label="학생별 퀴즈 응답 현황">',
           f'<div class="qb-top"><h3>{e(title)}</h3><span class="qb-live">응답 현황</span></div>',
           '<div class="qb-metrics">']
    for label,value in [('배포 학생',f"{len(board['students'])}명"),('응답 중·완료',f"{board['responding']}명"),('채점 완료',f"{board['graded']}명"),('채점 학생 평균',mean)]:
        parts.append(f'<div class="qb-metric"><small>{e(label)}</small><b>{e(value)}</b></div>')
    parts.append('</div><p class="qb-legend">채점 전: 선택한 보기만 표시 · 채점 후: O 정답 / X 오답 · 미응답도 채점 시 X(0점) · 학생 결과 공개는 별도</p>')
    parts.append('<div class="qb-scroll"><table><thead><tr><th class="qb-person">학생</th><th>응답</th>')
    parts.extend(f'<th>{i}번</th>' for i in range(1,count+1))
    parts.append('<th>점수</th><th>상태 · 저장</th></tr></thead><tbody>')
    for s in board['students']:
        parts.append(f'<tr><td class="qb-person"><strong>{e(s["name"])}</strong><small>{e(s["class"])}반 · {e(s["id"])}</small></td><td>{s["count"]}/{count}</td>')
        for q in board['questions']:
            v=s['answers'].get(q['id']); choice=CIRCLES[v] if type(v) is int and 0<=v<4 else '—'
            if s['state']=='graded':
                good=s['marks'].get(q['id'],False)
                css='qb-ok' if good else 'qb-no'; value=f'{choice} {"O" if good else "X"}'
            else: css='qb-wait' if v is not None else 'qb-blank'; value=choice
            parts.append(f'<td><span class="qb-mark {css}">{e(value)}</span></td>')
        score='—' if s['score'] is None else f"{s['score']}점"
        saved='저장 확인' if s['saved'] else ('저장 대기' if s['state']!='not_started' else '—')
        parts.append(f'<td><strong>{score}</strong></td><td>{e(STATE[s["state"]])}<br><small>{saved}</small></td></tr>')
    if not board['students']: parts.append(f'<tr><td colspan="{count+4}">배포 대상이 없습니다.</td></tr>')
    parts.append(f'</tbody></table></div><h4>문항별 틀린 인원수</h4><div class="qb-stats" style="--qb-count:{max(1,count)}">')
    for i, stat in enumerate(board['stats'],1):
        ratio=100*stat['wrong']/stat['graded'] if stat['graded'] else 0
        value=f'{stat["wrong"]}명' if stat['graded'] else '—'
        parts.append(f'<div class="qb-stat"><small>{i}번</small><b>{value}</b><small>미응답 {stat["blank"]}명 포함</small>'
                     f'<div class="qb-bar"><span style="width:{ratio:.1f}%"></span></div></div>')
    parts.append(f'</div><p class="qb-note">현재 선택한 반의 채점 완료 {board["graded"]}명 기준입니다. '
                 '아직 채점하지 않은 학생과 시작하지 않은 학생은 오답 집계에서 제외합니다.<br>'
                 f'마지막 화면 갱신: {e(board["refreshed_at"][:19].replace("T"," "))}</p></section>')
    return ''.join(parts)
