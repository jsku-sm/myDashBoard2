"""Original SVG/CSS for a calm, high-school learning studio (no remote assets)."""
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
    fills=['#E1E7ED','#71998B','#8B87AF','#C29D68','#7A99AF','#B68391']
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
    last=path[-1];nodes=''.join(f'<circle cx="{30+x*43}" cy="{288-y*43}" r="9" fill="#548675"/><text x="{30+x*43}" y="{292-y*43}" text-anchor="middle" fill="white" font-size="10">{i}</text>' for i,(x,y) in enumerate(path))
    marker=f'<circle cx="{30+last[0]*43}" cy="{288-last[1]*43}" r="14" fill="none" stroke="#B68A46" stroke-width="2"/>'
    return f'<div class="gg-board"><div class="gg-board-title">CONCEPT WALK · 나만의 경로를 만드는 중</div><svg role="img" aria-label="학습할 때마다 한 칸씩 이어지는 모험 지도" viewBox="0 0 325 323" xmlns="http://www.w3.org/2000/svg">{grid}<polyline points="{points}" stroke="#548675" stroke-width="5" fill="none"/>{nodes}{marker}<text x="286" y="309" font-size="11" fill="#5F7390">동쪽 →</text><text x="7" y="21" font-size="11" fill="#5F7390">북쪽 ↑</text></svg></div>'
