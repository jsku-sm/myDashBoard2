"""Original SVG/CSS for a vivid high-school learning studio (no remote assets)."""
from html import escape
from .engine import ITEMS, rotated

CSS = '''<style>
.gg-hero{background:linear-gradient(125deg,#202d43,#354f58);border-radius:22px;padding:28px 30px;color:#f7f9fc;position:relative;overflow:hidden;margin:8px 0 20px}
.gg-eyebrow{letter-spacing:.18em;font-size:.74rem;font-weight:700;color:#bdd7ce;margin-bottom:12px}
.gg-hero h2{color:#fff!important;font-size:clamp(1.35rem,3.5vw,2rem)!important;line-height:1.4;margin:0 0 10px!important;padding:0!important}
.gg-hero p{color:#d8e5e4;font-size:.94rem;margin:0;line-height:1.8;word-break:keep-all}
.gg-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}.gg-tags span{border:1px solid #72928a;border-radius:20px;padding:5px 11px;font-size:.74rem;color:#ecf3f2}
.gg-note{padding:17px 21px;border:1px solid #d9e5df;border-left:4px solid #548274;border-radius:12px;background:#f5f9f6;color:#274239;line-height:1.75;margin:10px 0 16px;word-break:keep-all}
.gg-board{background:#f3f6fa;border:1px solid #dbe2ec;border-radius:20px;padding:15px;text-align:center;margin:8px 0}
.gg-board svg{width:100%;height:auto;max-width:340px;display:block;margin:0 auto}.gg-board-title{font-size:.82rem;color:#374d67;font-weight:700;margin:3px 0 10px}
.gg-avatar{background:#f7f6f2;border:1px solid #e5e0d5;border-radius:18px;padding:12px;text-align:center;color:#39495b}.gg-avatar svg{width:140px;max-width:100%;height:auto}.gg-avatar strong{display:block;font-size:.84rem}.gg-avatar p{font-size:.8rem;margin:4px 0}
.gg-progress{display:flex;gap:9px;align-items:center;margin:10px 0 17px}.gg-progress span{width:31px;height:31px;border-radius:50%;display:grid;place-items:center;background:#e9eef4;color:#5d6c80;font-size:.8rem}.gg-progress .done{background:#497a6a;color:#fff}.gg-progress .current{outline:2px solid #788caf;outline-offset:2px}
.gg-shape{display:inline-block;max-width:120px}.gg-review{background:#f5f8fb;border-radius:12px;padding:15px;margin:8px 0;color:#334b5c}
@media(max-width:600px){.gg-hero{padding:23px 20px}.gg-tags span{font-size:.7rem}}
@media(prefers-color-scheme:dark){.gg-note{background:#253c34;color:#e3eee7;border-color:#4e7464}.gg-board{background:#253344;border-color:#4a5e76}.gg-board-title{color:#dce7f4}.gg-avatar{background:#303749;color:#edf1f6;border-color:#566176}.gg-review{background:#293a4c;color:#e1eaf5}}
@media(prefers-reduced-motion:reduce){.gg-hero,.gg-board,.gg-avatar{animation:none!important;transition:none!important}}
</style>'''


def hero():
    return '<div class="gg-hero"><div class="gg-eyebrow">GOOD MATH · ONE STEP AT A TIME</div><h2>수학, 나의 속도로 한 걸음.</h2><p>잘해야만 들어오는 곳이 아니에요. 오늘은 한 문제부터.<br>지금의 점수가 나의 가능성이나 소중함을 정하지 않아요.</p><div class="gg-tags"><span>한 번에 5문제</span><span>시간제한 없음</span><span>도움받아도 괜찮아요</span><span>어느 게임이든 같은 성장 기록</span></div></div>'


def note(text):
    return '<div class="gg-note">'+escape(str(text))+'</div>'


def studio_banner():
    return ('<div class="gg-studio-banner"><div class="gg-studio-copy">'
            '<span class="gg-studio-kicker">MY CONCEPT · MY STYLE</span>'
            '<p class="gg-studio-title">한 문제씩, 내 캐릭터도 레벨 업!</p>'
            '<p>궁금한 개념을 고르고, 생각을 모아 나만의 아바타를 꾸며요.</p>'
            '<div class="gg-studio-steps"><span>01 개념 선택</span><span>02 다섯 번의 도전</span>'
            '<span>03 아바타 꾸미기</span></div></div>'
            '<div class="gg-studio-sticker" aria-hidden="true">✦<small>+12<br>별 조각</small></div></div>')


def question_badge(index):
    return f'<div class="gg-question-badge"><span>QUESTION {int(index)+1:02}</span><b>생각을 펼칠 시간 ✦</b></div>'


def avatar(equipped,coins=0):
    def value(slot,default):
        key=equipped.get(slot,default)
        return ITEMS[key]['value'] if key in ITEMS and ITEMS[key]['slot']==slot else ITEMS[default]['value']
    coat=value('coat','coat_ink');bg=value('background','back_city');cap=value('cap','cap_none');pin=value('pin','pin_none')
    head=''
    if cap=='beanie':head='<path d="M51 70Q53 23 90 23Q128 23 129 70Z" fill="#D5C5A4"/><rect x="48" y="57" width="84" height="17" rx="7" fill="#B5A588"/>'
    elif cap=='headphones':head='<path d="M50 84V66A40 40 0 0 1 130 66V84" fill="none" stroke="#B5CFD8" stroke-width="8"/><rect x="45" y="72" width="13" height="27" rx="5" fill="#D2E3E8"/><rect x="122" y="72" width="13" height="27" rx="5" fill="#D2E3E8"/>'
    badge='<text x="101" y="146" fill="#F3D591" font-family="sans-serif" font-size="17">'+('★' if pin=='star' else '∞' if pin=='math' else '')+'</text>'
    svg=f'''<svg role="img" aria-label="내 수학 탐험 캐릭터" viewBox="0 0 180 195" xmlns="http://www.w3.org/2000/svg"><rect width="180" height="195" rx="20" fill="{bg}"/><path d="M15 153V106H42V153M143 153V82H165V153M20 43H34M27 36V50M147 35H153M150 32V38" stroke="#91ACB2" opacity=".32" fill="none" stroke-width="2"/><circle cx="90" cy="81" r="39" fill="#DFBFA1"/><path d="M50 80Q42 31 89 34Q140 34 130 80L119 65Q95 72 73 61L57 81Z" fill="#28303D"/><circle cx="76" cy="83" r="2.7" fill="#30394A"/><circle cx="104" cy="83" r="2.7" fill="#30394A"/><path d="M81 99Q90 105 99 99" stroke="#7A5A4A" fill="none" stroke-width="2.5" stroke-linecap="round"/>{head}<path d="M41 181V148Q46 119 75 116L90 130L105 116Q133 119 139 148V181" fill="{coat}"/><path d="M90 131V181" stroke="#FFFFFF" opacity=".4" stroke-width="2"/>{badge}<rect x="57" y="154" width="27" height="18" rx="3" fill="#D4E4E1"/><text x="63" y="167" fill="#33575D" font-size="12" font-family="sans-serif">x+y</text></svg>'''
    return f'<div class="gg-avatar">{svg}<strong>내 가능성을 꾸미는 중</strong><p>별 조각 {int(coins)}개 · 성적과 무관</p></div>'


def progress(index):
    return '<div class="gg-progress">'+''.join(f'<span class="{"done" if i<index else "current" if i==index else ""}">{"✓" if i<index else i+1}</span>' for i in range(5))+'</div>'


def puzzle(board,index=0,preview=None):
    fills=['#EAE3FF','#7546FF','#FF6BA8','#FFCC50','#42DDF0','#B995FF']
    cells=[];previewcells=set()
    if preview is not None:
        x,y,rotation=preview
        previewcells={(x+dx,y+dy) for dx,dy in rotated(index,rotation)}
    for y in range(6):
        for x in range(6):
            val=board[y][x];fill=fills[max(0,min(5,int(val)))];stroke='none'
            if (x,y) in previewcells:fill='#D4E7DC';stroke='#386B57'
            cells.append(f'<rect x="{32+x*43}" y="{30+y*43}" width="37" height="37" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="2" stroke-dasharray="4 2"/>')
    labels=''.join(f'<text x="{49+i*43}" y="18" font-size="10" text-anchor="middle" fill="#6A7E96">{i+1}</text><text x="18" y="{54+i*43}" font-size="10" fill="#6A7E96">{i+1}</text>' for i in range(6))
    return '<div class="gg-board"><div class="gg-board-title">CONCEPT BLOCK · 생각할 때는 멈춰 있어요</div><svg role="img" aria-label="6행 6열 개념 블록판" viewBox="0 0 315 303" xmlns="http://www.w3.org/2000/svg">'+labels+''.join(cells)+'</svg></div>'


def adventure(path):
    grid=''.join(f'<path d="M30 {30+i*43}H290M{30+i*43} 30V288" stroke="#C6D4E1" stroke-width="1"/>' for i in range(7))
    points=' '.join(f'{30+x*43},{288-y*43}' for x,y in path)
    last=path[-1];nodes=''.join(f'<circle cx="{30+x*43}" cy="{288-y*43}" r="9" fill="#7546FF"/><text x="{30+x*43}" y="{292-y*43}" text-anchor="middle" fill="white" font-size="10">{i}</text>' for i,(x,y) in enumerate(path))
    marker=f'<circle cx="{30+last[0]*43}" cy="{288-last[1]*43}" r="14" fill="none" stroke="#FF418D" stroke-width="2"/>'
    return f'<div class="gg-board"><div class="gg-board-title">CONCEPT WALK · 나만의 경로를 만드는 중</div><svg role="img" aria-label="학습할 때마다 한 칸씩 이어지는 모험 지도" viewBox="0 0 325 323" xmlns="http://www.w3.org/2000/svg">{grid}<polyline points="{points}" stroke="#7546FF" stroke-width="5" fill="none"/>{nodes}{marker}<text x="286" y="309" font-size="11" fill="#5F7390">동쪽 →</text><text x="7" y="21" font-size="11" fill="#5F7390">북쪽 ↑</text></svg></div>'


# Scoped to the Games page: preserve all existing controls and avatar rules.
CSS += """<style>
.st-key-good_math_games{--gg-ink:#20203a;--gg-purple:#643bff}
.st-key-good_math_games .gg-hero{background:#643bff;border:2px solid #20203a;box-shadow:0 6px 0 #20203a;border-radius:24px;padding:30px;background-image:radial-gradient(#ffffff26 1px,transparent 1px);background-size:18px 18px}
.st-key-good_math_games .gg-hero h2{font-size:clamp(1.7rem,4vw,2.6rem)!important;font-weight:900!important;letter-spacing:-1.5px}
.st-key-good_math_games .gg-eyebrow{color:#d9ff4b;font-weight:900}.st-key-good_math_games .gg-hero p{color:#f0eaff}
.st-key-good_math_games .gg-tags span{background:#d9ff4b;color:#20203a;border:1.5px solid #20203a;font-weight:800;border-radius:24px}
.st-key-good_math_games .gg-avatar{background:#ffce55;color:#20203a;border:2px solid #20203a;border-radius:22px;box-shadow:4px 4px 0 #20203a;padding:18px;margin-bottom:15px}
.st-key-good_math_games .gg-avatar strong{font-size:15px;color:#20203a}.st-key-good_math_games .gg-avatar p{color:#37324c;font-size:12px}
.st-key-good_math_games .gg-board{border:2px solid #20203a;background:#f0e9ff;border-radius:20px;box-shadow:0 4px 0 #20203a}.st-key-good_math_games .gg-board-title{color:#643bff;font-weight:900}
.st-key-good_math_games .gg-note{background:#f1eaff;border:1.5px solid #b59bea;border-left:6px solid #643bff;color:#45315f;border-radius:15px}
.st-key-good_math_games .gg-progress span{background:#e8e0ff;color:#643bff;border:1.5px solid #b5a2e6;font-weight:850;box-shadow:0 2px 0 #c2b2e2}
.st-key-good_math_games .gg-progress .done{background:#d9ff4b;color:#20203a;border-color:#20203a}.st-key-good_math_games .gg-progress .current{background:#643bff;color:#fff;outline-color:#ff7cb7}
.st-key-good_math_games .gg-review{background:#fff0f7;border:1px solid #f2bad5;border-radius:15px;color:#61334b}
.st-key-good_math_games [data-testid="stButton"] button{border:1.5px solid #b7a3dc;border-radius:13px;font-weight:750;min-height:43px;transition:transform .15s,box-shadow .15s}
.st-key-good_math_games [data-testid="stButton"] button[kind="primary"]{background:#643bff;color:#fff;border:2px solid #20203a;box-shadow:0 4px 0 #20203a}
.st-key-good_math_games [data-testid="stButton"] button:hover{transform:translateY(-2px);box-shadow:0 3px 0 #c8b6e6}
.st-key-good_math_games [data-testid="stMetric"]{background:#f1eaff;border:1.5px solid #c5b4e8;border-radius:16px;padding:15px}
.st-key-good_math_games [data-testid="stMetricValue"]{color:#643bff;font-weight:900}
.st-key-good_math_games [data-testid="stForm"]{border:1.5px solid #c5b4e8;border-radius:18px;padding:20px;background:#fcfaff}
.st-key-good_math_games [data-testid="stRadio"] [role="radiogroup"]{gap:8px}
.st-key-good_math_games [data-testid="stRadio"] label[data-baseweb="radio"]{border:1.5px solid #d7cce9;border-radius:22px;padding:7px 13px;background:#faf7ff}
.st-key-good_math_games [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:#e8ddff;border-color:#643bff;color:#43258f}
@media(prefers-color-scheme:dark){.st-key-good_math_games [data-testid="stForm"],.st-key-good_math_games [data-testid="stMetric"]{background:#29233d;color:#f2eaff}.st-key-good_math_games [data-testid="stMetricValue"]{color:#d9ff4b}.st-key-good_math_games [data-testid="stRadio"] label[data-baseweb="radio"]{background:#29233d;color:#f2eaff}.st-key-good_math_games [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:#643bff;color:#fff}}
@media(prefers-reduced-motion:reduce){.st-key-good_math_games button{transition:none!important;transform:none!important}}
</style>"""


# Avatar concept learning only. Native Streamlit controls keep their callbacks,
# keyboard support and MathJax/KaTeX labels; no parent-frame scripts are injected.
CSS += '''<style>
.gg-scope{--studio-ink:#231b3b;--studio-purple:#6433ef;--studio-pink:#ff53a0;--studio-lime:#dcff66;color:var(--studio-ink);}
.gg-scope .gg-studio-banner{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:30px 32px;margin:12px 5px 24px 0;background:#6433ef;color:#fff;border:2px solid #231b3b;border-radius:26px;box-shadow:7px 7px 0 #ff8cc4;overflow:hidden;position:relative;isolation:isolate;}
.gg-scope .gg-studio-banner:before{content:"";position:absolute;inset:0;z-index:-1;background-image:radial-gradient(#ffffff26 1.5px,transparent 1.5px);background-size:20px 20px;}
.gg-scope .gg-studio-kicker{color:#dcff66;font-size:.74rem;letter-spacing:.13em;font-weight:850;}
.gg-scope .gg-studio-title{color:#fff!important;font-size:clamp(1.35rem,3vw,2rem)!important;font-weight:900!important;line-height:1.4!important;letter-spacing:-.04em;margin:10px 0!important;word-break:keep-all;}
.gg-scope .gg-studio-copy>p:not(.gg-studio-title){color:#f6f1ff;font-size:1rem;line-height:1.7;word-break:keep-all;margin:0;}
.gg-scope .gg-studio-steps{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px;}
.gg-scope .gg-studio-steps span{background:#fff;color:#37215e;border:1.5px solid #231b3b;border-radius:999px;padding:7px 12px;font-size:.8rem;font-weight:800;}
.gg-scope .gg-studio-steps span:nth-child(2){background:#dcff66}.gg-scope .gg-studio-steps span:nth-child(3){background:#ffbbe0}
.gg-scope .gg-studio-sticker{flex:0 0 112px;width:112px;height:128px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#dcff66;border:2px solid #231b3b;border-radius:28px;color:#231b3b;font-size:2rem;box-shadow:5px 5px 0 #231b3b;transform:rotate(7deg);animation:gg-sticker-pop .5s ease-out both;}
.gg-scope .gg-studio-sticker small{font-size:.94rem;font-weight:900;line-height:1.4;text-align:center;}
.gg-scope .st-key-gg_concept_picker{padding:24px;border:2px solid #231b3b;border-radius:24px;background:#fff;box-shadow:5px 5px 0 #dcccff;margin-bottom:20px;}
.gg-scope .st-key-gg_concept_picker [data-testid="stWidgetLabel"] p{color:#392c55;font-size:.94rem;font-weight:750;}
.gg-scope .st-key-gg_concept_note,.gg-scope [class*="st-key-gg_hint_"]{padding:18px 20px;background:#f1eaff;border:1.5px solid #bba0f5;border-left:6px solid #7445f7;border-radius:16px;color:#302349;margin:8px 0;}
.gg-scope .st-key-gg_concept_note p,.gg-scope [class*="st-key-gg_hint_"] p{color:#302349;line-height:1.9;font-size:1.05rem;word-break:keep-all;overflow-wrap:anywhere;}
.gg-scope .st-key-gg_question_card{background:#fff;border:2px solid #231b3b;border-radius:23px;padding:24px 28px;box-shadow:6px 6px 0 #dcff66;margin:12px 6px 20px 0;}
.gg-scope .gg-question-badge{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px;}
.gg-scope .gg-question-badge span{color:#fff;background:#6433ef;border-radius:9px;padding:6px 10px;font-size:.73rem;letter-spacing:.08em;font-weight:900;}
.gg-scope .gg-question-badge b{font-size:.85rem;color:#66408b;font-weight:750;}
.gg-scope .st-key-gg_question_card [data-testid="stMarkdownContainer"]>p{color:#231b3b;font-size:clamp(1.14rem,2.2vw,1.45rem);font-weight:650;line-height:2;word-break:keep-all;overflow-wrap:anywhere;}
.gg-scope .katex{font-size:1.17em;line-height:1.45;}
.gg-scope .katex-display{overflow-x:auto;overflow-y:hidden;padding:8px 2px;max-width:100%;}
.gg-scope .st-key-gg_question_card [data-testid="stMarkdownContainer"]{overflow-x:auto;padding-bottom:4px;}
.gg-scope [data-testid="stForm"]{background:#faf8ff;border:2px solid #d9ccf5;padding:22px;border-radius:22px;}
.gg-scope [data-testid="stForm"] [data-testid="stWidgetLabel"] p{color:#45345f;font-size:.94rem;font-weight:750;}
.gg-scope [data-testid="stForm"] [role="radiogroup"]{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
.gg-scope [data-testid="stForm"] [role="radiogroup"]>div{min-width:0;width:100%;}
.gg-scope [data-testid="stForm"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]){display:flex;align-items:center;width:100%;min-height:76px;margin:0;gap:10px;padding:14px 18px;background:#fff;color:#231b3b;border:2px solid #cbb7f4;border-radius:16px;box-shadow:0 3px 0 #e4d8f7;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease;}
.gg-scope [data-testid="stForm"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]) p{color:#231b3b;font-size:1.12rem;font-weight:650;line-height:1.9;overflow-wrap:anywhere;white-space:normal;}
.gg-scope [data-testid="stForm"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]):hover{transform:translateY(-2px);border-color:#7541f2;box-shadow:0 5px 0 #dccbff;}
.gg-scope [data-testid="stForm"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]):has(input:checked){background:#ece2ff;border:2px solid #6433ef;box-shadow:0 4px 0 #b49beb;}
.gg-scope [data-testid="stForm"] :is(label[data-baseweb="radio"],label[data-testid="stRadioOption"]):has(input:focus-visible){outline:3px solid #ed3287;outline-offset:3px;}
.gg-scope :is([data-testid="stButton"],[data-testid="stFormSubmitButton"]) button[kind="primary"]{border:2px solid #231b3b;background:#6433ef;color:#fff;border-radius:15px;box-shadow:0 4px 0 #231b3b;min-height:52px;font-weight:800;}
.gg-scope :is([data-testid="stButton"],[data-testid="stFormSubmitButton"]) button[kind="primary"] p{color:#fff;font-size:1rem;font-weight:800;}
.gg-scope .gg-avatar{background:#ffda70;border-radius:24px;box-shadow:5px 5px 0 #231b3b;}
.gg-scope .gg-board{background:#effbff;border-color:#231b3b;box-shadow:5px 5px 0 #98e6fa;}
.gg-scope .gg-progress{gap:12px;padding:8px 2px;}.gg-scope .gg-progress span{width:38px;height:38px;font-size:.95rem;font-weight:850;}
.gg-scope .gg-progress .current{background:#6433ef;color:#fff;outline:3px solid #ff75b5;outline-offset:3px;}
.gg-scope .gg-progress .done{background:#dcff66;border-color:#231b3b;color:#231b3b;}
@keyframes gg-sticker-pop{from{opacity:0;transform:translateY(10px) rotate(-5deg)}to{opacity:1;transform:translateY(0) rotate(7deg)}}
@media(max-width:700px){.gg-scope .gg-studio-banner{padding:22px 20px;gap:14px}.gg-scope .gg-studio-sticker{flex-basis:76px;width:76px;height:100px;font-size:1.6rem}.gg-scope .gg-studio-sticker small{font-size:.8rem}.gg-scope .st-key-gg_concept_picker{padding:18px 15px}.gg-scope .st-key-gg_question_card{padding:20px 17px}.gg-scope [data-testid="stForm"]{padding:17px 13px}.gg-scope [data-testid="stForm"] [role="radiogroup"]{grid-template-columns:minmax(0,1fr)}.gg-scope .gg-studio-steps{gap:6px}.gg-scope .gg-studio-steps span{font-size:.73rem;padding:6px 9px}}
@media(prefers-reduced-motion:reduce){.gg-scope .gg-studio-sticker{animation:none}.gg-scope [data-testid="stForm"] label{transition:none!important;transform:none!important}}
</style>'''.replace('.gg-scope', '[data-testid="stMain"] .st-key-good_math_games .st-key-gg_concept_studio')
