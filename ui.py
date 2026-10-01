"""화면 꾸미기와 공용 위젯."""
import html
import random

import streamlit as st

import storage as db

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Jua&display=swap');
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
:root{
  --paper:#FBFCFE; --grid:#E4ECF8; --ink:#1E2A4A; --muted:#66728A;
  --hl:#FFE45C; --mint:#2BB39A; --coral:#F0645A; --sky:#5AA9E6;
}
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button {
  font-family:'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
}
.stApp{
  background-color:var(--paper);
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:26px 26px;
  color:var(--ink);
}
h1,h2,h3,h4{font-family:'Jua','Pretendard',sans-serif !important; font-weight:400 !important; color:var(--ink);}
[data-testid="stSidebar"]{background:#F3F6FC; border-right:2px solid var(--grid);}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2{font-size:1.5rem;}
.block-container{max-width:1100px; padding-top:2.2rem;}

/* 페이지 제목: 형광펜 밑줄 */
.pg-title{font-family:'Jua',sans-serif; font-size:2.3rem; line-height:1.25; margin:0 0 .2rem 0; color:var(--ink);}
.pg-title span{background:linear-gradient(transparent 58%, var(--hl) 58%); padding:0 .15em;}
.pg-sub{color:var(--muted); margin:0 0 1.4rem 0; font-size:1.02rem;}

/* 노트 카드 */
.note{background:#fff; border:1.5px solid #D5DFEE; border-radius:14px; padding:1.1rem 1.3rem; margin:.4rem 0 1rem;}
.note.yellow{background:#FFFBE0; border-color:#F2DE7A;}
.note.mint{background:#EAF8F4; border-color:#A9E2D5;}
.note.coral{background:#FFF0EE; border-color:#F6B9B3;}
.note h4{margin:0 0 .4rem 0;}
.meta{color:var(--muted); font-size:.86rem;}
.chip{display:inline-block; padding:.08rem .55rem; border-radius:99px; background:#EEF2FA; color:var(--ink); font-size:.82rem; margin-right:.3rem;}

/* 로그인 */
.hero{font-family:'Jua',sans-serif; font-size:3rem; line-height:1.15; color:var(--ink); margin:1.2rem 0 .3rem;}
.hero span{background:linear-gradient(transparent 60%, var(--hl) 60%);}
.formula{font-family:'Jua',sans-serif; color:#9BB0D3; font-size:1.25rem; letter-spacing:.02em;}

/* 감정 선택 버튼 */
.st-key-emo_grid button{
  min-height:118px; border-radius:22px; border:2px solid #D5DFEE; background:#fff;
  transition:transform .15s ease, box-shadow .15s ease, border-color .15s;
}
.st-key-emo_grid button p{font-size:2.6rem; line-height:1.25; white-space:normal; overflow:visible; text-overflow:clip;}
.st-key-emo_grid button p strong{display:block; font-size:1.02rem; line-height:1.3; font-weight:700; white-space:nowrap; margin-top:.35rem;}
.st-key-emo_grid button div{overflow:visible;}
.st-key-emo_grid button:hover{transform:translateY(-4px) rotate(-1.5deg); border-color:var(--ink); box-shadow:4px 6px 0 var(--hl);}
.st-key-emo_grid button:focus-visible{outline:3px solid var(--sky);}

/* 잠금 화면 */
.lock-veil{position:fixed; inset:0; z-index:999990; background:var(--ink);
  display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:2rem;}
.lock-veil .lk-icon{font-size:6rem; color:#FFE45C; line-height:1; animation:lockpulse 1.8s ease-in-out infinite;}
.lock-veil .msg{font-family:'Jua',sans-serif; color:#fff; font-size:2.4rem; margin-top:1rem; max-width:16em; word-break:keep-all; line-height:1.4;}
.lock-veil .msg span{background:linear-gradient(transparent 60%, rgba(255,228,92,.55) 60%);}
.lock-veil .meta{color:#AFC0E0; margin-top:1rem; font-size:1rem;}
@keyframes lockpulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}

/* 폭죽 */
.fw-overlay{position:fixed; inset:0; z-index:999995; pointer-events:none; animation:fwfade 8s forwards;}
.fw-burst{position:absolute; width:0; height:0;}
.fw-burst i{position:absolute; display:block; left:0; top:0; width:9px; height:9px; border-radius:50%; background:var(--c);
  opacity:0; animation:fwfly 1.5s cubic-bezier(.15,.7,.3,1) both; animation-delay:var(--d);}
.fw-msg{position:absolute; left:50%; top:42%; transform:translate(-50%,-50%); background:#fff; border:3px solid var(--ink);
  border-radius:20px; padding:1.1rem 2rem; text-align:center; box-shadow:8px 8px 0 var(--hl); animation:fwpop .6s .2s both;}
.fw-msg b{font-family:'Jua',sans-serif; font-size:2.4rem; color:var(--ink); display:block;}
.fw-msg small{color:var(--muted); font-size:1.05rem;}
@keyframes fwfly{0%{transform:translate(0,0) scale(.3); opacity:1}80%{opacity:1}100%{transform:translate(var(--x),var(--y)) scale(1); opacity:0}}
@keyframes fwpop{0%{transform:translate(-50%,-50%) scale(.3); opacity:0}100%{transform:translate(-50%,-50%) scale(1); opacity:1}}
@keyframes fwfade{0%,85%{opacity:1}100%{opacity:0; visibility:hidden}}

@media (prefers-reduced-motion: reduce){
  .fw-burst i, .lock-veil .lk-icon, .st-key-emo_grid button{animation:none !important; transition:none !important;}
}
@media (max-width:640px){ .hero{font-size:2.2rem;} .pg-title{font-size:1.8rem;} .lock-veil .msg{font-size:1.7rem;} }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def page_title(title: str, sub: str = ""):
    st.markdown(f'<div class="pg-title"><span>{html.escape(title)}</span></div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<p class="pg-sub">{html.escape(sub)}</p>', unsafe_allow_html=True)


def note(body_html: str, tone: str = ""):
    st.markdown(f'<div class="note {tone}">{body_html}</div>', unsafe_allow_html=True)


def esc(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br>")


def lock_screen(message: str):
    st.markdown(
        """<style>[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"],header[data-testid="stHeader"]{display:none !important;}</style>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="lock-veil"><div class="lk-icon">🔒\uFE0F</div>'
        f'<div class="msg"><span>{esc(message)}</span></div>'
        f'<div class="meta">선생님이 잠금을 풀면 자동으로 원래 화면으로 돌아가요.</div></div>',
        unsafe_allow_html=True,
    )


def fireworks(title: str, detail: str):
    palette = ["#FFE45C", "#F0645A", "#2BB39A", "#5AA9E6", "#B58CF0", "#FF9F43"]
    bursts = []
    for b in range(12):
        left, top = random.randint(8, 92), random.randint(10, 70)
        color = random.choice(palette)
        delay = round(b * 0.4, 2)
        parts = []
        for k in range(26):
            import math
            ang = 2 * math.pi * k / 26
            r = random.randint(90, 170)
            parts.append(
                f'<i style="--x:{int(r*math.cos(ang))}px;--y:{int(r*math.sin(ang))}px;'
                f'--c:{color};--d:{delay}s"></i>'
            )
        bursts.append(f'<div class="fw-burst" style="left:{left}%;top:{top}%">{"".join(parts)}</div>')
    st.markdown(
        f'<div class="fw-overlay">{"".join(bursts)}'
        f'<div class="fw-msg"><b>{esc(title)}</b><small>{esc(detail)}</small></div></div>',
        unsafe_allow_html=True,
    )


def file_widget(row: dict, key: str):
    """첨부파일 내려받기. 공개 링크가 있으면 바로, 없으면 앱을 통해 내려받기."""
    fid, name = row.get("file_id"), row.get("file_name") or "파일"
    if not fid:
        return
    if row.get("file_url"):
        st.link_button(f"📥 {name}", row["file_url"])
        return
    backend = db.get_backend()
    flag = f"_dl_{key}"
    if backend.is_local or st.session_state.get(flag):
        data = db.load_file_cached(fid)
        if data is None:
            st.caption(f"⚠️ '{name}' 파일을 찾을 수 없어요.")
            return
        st.download_button(f"📥 {name}", data=data, file_name=name,
                           mime=row.get("mime") or None, key=f"dlb_{key}")
    else:
        if st.button(f"📂 {name} 열기", key=f"dlp_{key}"):
            st.session_state[flag] = True
            st.rerun()


def parse_links(text: str):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            name, url = line.split("|", 1)
        else:
            name, url = line, line
        out.append((name.strip(), url.strip()))
    return out


def embed(url: str, height: int = 600):
    """다른 사이트를 앱 안에 띄우기 (사이트가 허용하지 않으면 빈 화면이 보일 수 있음)."""
    if hasattr(st, "iframe"):
        st.iframe(url, height=height)
    else:
        import streamlit.components.v1 as components
        components.iframe(url, height=height, scrolling=True)
