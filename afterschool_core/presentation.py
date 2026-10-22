"""Escaped presentation helpers and locally-scoped pastel styles (no network)."""
from html import escape

SHELL = ':is(.st-key-as_admin_shell,.st-key-as_student_math1,.st-key-as_student_math2,.as-demo-shell)'


def styles():
    s = SHELL
    return f'''<style>
{s} {{
  --as-ink:#303750; --as-muted:#65718a; --as-line:#e4dfef;
  --ink:#303750; --muted:#65718a; --card:#fff; --soft:#f4f0fa;
  color-scheme:light; color:var(--as-ink); background:#fcfbff;
  border:1px solid #e7e1ef; border-radius:24px; padding:22px;
}}
{s} :is(h1,h2,h3,h4,h5,p,label) {{color:var(--as-ink);}}
{s} [data-testid="stCaptionContainer"] p {{color:var(--as-muted);}}
{s} :is([data-testid="stVerticalBlockBorderWrapper"], [data-testid="stForm"]) {{
  background:#fff; border-color:var(--as-line)!important; border-radius:18px;
}}
{s} :is([data-testid="stTextInput"], [data-testid="stTextArea"]) input,
{s} [data-testid="stTextArea"] textarea {{color:#303750;background:#fff;}}
{s} [data-baseweb="input"], {s} [data-baseweb="textarea"],
{s} [data-baseweb="select"]>div {{background:#fff;border-color:#d9d5e7;border-radius:12px;}}
{s} [data-testid="stButton"] button, {s} [data-testid="stFormSubmitButton"] button,
{s} [data-testid="stDownloadButton"] button {{
  min-height:44px;border-radius:12px;border:1px solid #d8cde9;background:#f1ebfa;color:#51416d;
}}
{s} button[kind="primary"] {{background:#ddd1f3!important;color:#44355f!important;border-color:#bca5df!important;}}
{s} button[kind="primary"] p {{color:#44355f!important;font-weight:700;}}
{s} button:disabled {{opacity:.52;}}
{s} :is(button,input,textarea):focus-visible {{outline:3px solid #a791ca;outline-offset:2px;}}
{s} [role="radiogroup"] {{display:flex;flex-wrap:wrap;gap:8px;}}
[data-testid="stMain"] {s} [data-testid="stRadio"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]) {{
  background:#f3effa!important;border:1px solid #dfd4ed!important;border-radius:13px!important;
  box-shadow:none!important;padding:9px 13px!important;min-height:44px;
}}
[data-testid="stMain"] {s} [data-testid="stRadio"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]):has(input:checked) {{
  background:#e6ddf6!important;border-color:#aa92cc!important;box-shadow:0 2px 0 #cfbee6!important;
}}
[data-testid="stMain"] {s} [data-testid="stRadio"] label p {{color:#51416d!important;}}
{s} [class*="st-key-as_add_panel_"] {{background:#eef8f3!important;border:1px solid #cce7da;border-radius:18px;padding:20px;}}
{s} [class*="st-key-as_roster_panel_"] {{background:#fff!important;border:1px solid #e6e1ef;border-radius:18px;padding:20px;}}
{s} [class*="st-key-as_member_row_"] {{background:#fdfbff;border:1px solid #ebe6f1;border-radius:14px;padding:9px 14px;margin-bottom:7px;}}
{s} [class*="st-key-as_remove_"] button {{background:#fff0ec!important;border-color:#ecc8bd!important;color:#964f43!important;}}
{s} [class*="st-key-as_remove_"] button p {{color:#964f43!important;}}
{s} .as-hero {{background:linear-gradient(115deg,#eee8f8,#eaf6f1);border:1px solid #ddd4eb;border-radius:19px;padding:22px 24px;margin:0 0 16px;}}
{s} .as-overline {{font-size:12px;font-weight:700;letter-spacing:.08em;color:#74658c;}}
{s} .as-title {{margin:8px 0;font-size:27px;font-weight:800;line-height:1.4;color:#343a53;}}
{s} .as-sub {{color:#637084;font-size:14px;line-height:1.7;margin:5px 0;white-space:pre-wrap;}}
{s} .as-chip {{display:inline-flex;align-items:center;padding:5px 11px;border-radius:30px;font-size:13px;font-weight:700;background:#fff;border:1px solid #d9d0e5;color:#625179;margin:3px 5px 3px 0;}}
{s} .as-chip.mint {{background:#e3f3e9;border-color:#bfddcd;color:#376550;}}
{s} .as-chip.peach {{background:#fff0e7;border-color:#f1d5c2;color:#8b5940;}}
{s} .as-stats {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:10px 0 18px;}}
{s} .as-stat {{border:1px solid #dfd5ed;border-radius:17px;padding:17px 20px;background:#eee7fa;}}
{s} .as-stat:nth-child(2) {{background:#e8f5ee;border-color:#cde6d9;}}
{s} .as-stat:nth-child(3) {{background:#fff2e9;border-color:#eed9c8;}}
{s} .as-stat span {{font-size:13px;font-weight:600;display:block;color:#586178;}}
{s} .as-stat strong {{display:block;font-size:29px;margin-top:7px;color:#373c56;}}
{s} .as-count-title {{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:2px 0 14px;}}
{s} .as-count-title h4 {{margin:0;font-size:20px;}}
{s} .as-count {{background:#ece3f9;border:1px solid #d5c3eb;border-radius:30px;padding:6px 15px;font-weight:700;color:#634a86;}}
{s} .as-management-context {{background:#f4effa;border:1px solid #daceed;border-left:5px solid #aa92cc;border-radius:16px;padding:16px 20px;margin:0 0 18px;}}
{s} .as-management-context strong {{display:block;font-size:20px;line-height:1.5;margin:7px 0;color:#44355f;overflow-wrap:anywhere;}}
{s} .as-management-context p {{font-size:13px;line-height:1.65;margin:7px 0 0;color:#65718a;}}
{s} .as-enrollment-target {{color:#376550;font-size:14px;line-height:1.8;overflow-wrap:anywhere;}}
{s} .as-person {{display:flex;align-items:center;gap:13px;min-height:46px;}}
{s} .as-avatar {{background:#e8e1f5;border-radius:13px;color:#6e5990;width:40px;min-width:40px;height:40px;display:grid;place-items:center;font-size:15px;font-weight:700;}}
{s} .as-person strong {{color:#343b52;font-size:16px;}}
{s} .as-person small {{display:block;color:#66718a;font-size:13px;margin-top:2px;}}
{s} .as-person small, {s} .as-sub {{overflow-wrap:anywhere;}}
{s} [data-testid="stExpander"] {{background:#fff;border-color:#e2daee;border-radius:15px;}}
@media(max-width:640px) {{
{s} {{padding:13px;border-radius:18px;}}
{s} .as-hero {{padding:18px;}}
{s} .as-title {{font-size:22px;}}
{s} .as-stats {{gap:8px;}}
{s} .as-stat {{padding:12px 10px;}}
{s} .as-stat strong {{font-size:18px;line-height:1.4;word-break:keep-all;}}
{s} .as-stat:first-child strong {{font-size:24px;}}
{s} [class*="st-key-as_add_panel_"], {s} [class*="st-key-as_roster_panel_"] {{padding:14px;}}
}}
</style>'''


def hero(cohort, state_label, teacher=False):
    c=cohort
    chips=f'<span class="as-chip">{escape(c["subject"])}</span><span class="as-chip mint">{escape(state_label)}</span>'
    if teacher:
        chips+=f'<span class="as-chip peach">배정 {int(c["member_count"])}명</span>'
    period=' ~ '.join(c.get(k) or '미정' for k in ('start_date','end_date'))
    return (f'<section class="as-hero"><div class="as-overline">AFTER SCHOOL · {escape(c["year"])}학년도</div>'
            f'<div class="as-title">{escape(c["name"])}</div><div>{chips}</div>'
            f'<p class="as-sub">{escape(period)}</p><p class="as-sub">{escape(c["description"])}</p></section>')


def stats(items):
    return '<div class="as-stats">'+''.join(
        f'<div class="as-stat"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>'
        for label,value in items)+'</div>'


def roster_heading(total, shown=None, cohort=None):
    extra='' if shown is None or shown==total else f'<span class="as-chip">검색 결과 {int(shown)}명</span>'
    title='현재 배정 명단' if cohort is None else f'{escape(cohort["name"])} · 현재 배정 명단'
    return f'<div class="as-count-title"><h4>{title}</h4><div>{extra}<span class="as-count">총 {int(total)}명</span></div></div>'


def person(student):
    name=str(student['name']); cls=student.get('class') or '학급 확인 필요'
    return (f'<div class="as-person"><span class="as-avatar">{escape(name[:1])}</span><div>'
            f'<strong>{escape(name)}</strong><small>{escape(cls)} · {escape(student["id"])}</small></div></div>')


def management_context(cohort):
    """Persistent visible scope for every management action (escaped user text)."""
    c=cohort
    return (f'<section class="as-management-context" aria-label="현재 관리 대상">'
            f'<span class="as-overline">현재 관리 중인 기수</span>'
            f'<strong>{escape(c["year"])}학년도 · {escape(c["subject"])} · {escape(c["name"])}</strong>'
            f'<span class="as-chip mint">이 기수 배정 {int(c["member_count"])}명</span>'
            '<p>기수 설정 · 참여 학생 · 자료·과제 · 질문·댓글 · 제출 확인은 모두 위 기수에 연결됩니다.</p></section>')


def enrollment_target(cohort):
    return (f'<p class="as-enrollment-target">배정 대상: <strong>{escape(cohort["year"])}학년도 · '
            f'{escape(cohort["subject"])} · {escape(cohort["name"])}</strong><br>'
            '아래에서 추가하는 학생은 이 기수에만 저장됩니다. 다른 기수 명단은 변경하지 않습니다.</p>')
