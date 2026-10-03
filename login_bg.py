"""첫 화면(로그인) 배경: 직접 그린 수학 그림 3장이 5초마다 부드럽게 겹치며 바뀝니다.

- 그림은 SVG 코드로 그려서 파일 용량이 매우 작고(장당 몇 KB), 화면 크기와 상관없이 선명합니다.
- 색은 light-dark() 로 정해서 밝은 모드/어두운 모드에 맞춰 자동으로 바뀝니다.
- 기기에서 '동작 줄이기'를 켜면 바뀌는 효과 없이 첫 그림만 보여 줍니다.
"""
import math
import random

INTERVAL_SEC = 5   # 한 장이 보이는 시간
FADE_SEC = 1.2     # 겹치며 바뀌는 시간

W, H = 1600, 1000


def _pts(fn, x0, x1, step=4):
    return " ".join(f"{x:.0f},{fn(x):.1f}" for x in range(x0, x1 + 1, step))


# ① 함수의 그래프 (모눈 1칸 = 0.5, 굵은 선 1칸 = 1) ---------------------------
def scene_graphs():
    g = []
    u = 80            # 1 단위 = 80px
    ox, oy = 900, 560  # 원점 위치
    for k in range(-40, 41):
        x = ox + k * u / 2
        if 0 <= x <= W:
            g.append(f'<line x1="{x:.0f}" y1="0" x2="{x:.0f}" y2="{H}" class="a-grid{" major" if k % 2 == 0 else ""}"/>')
        y = oy + k * u / 2
        if 0 <= y <= H:
            g.append(f'<line x1="0" y1="{y:.0f}" x2="{W}" y2="{y:.0f}" class="a-grid{" major" if k % 2 == 0 else ""}"/>')
    g.append(f'<line x1="0" y1="{oy}" x2="{W}" y2="{oy}" class="a-axis"/>')
    g.append(f'<line x1="{ox}" y1="0" x2="{ox}" y2="{H}" class="a-axis"/>')

    def sx(x):  # 수학 좌표 → 화면 좌표
        return ox + x * u

    def sy(y):
        return oy - y * u

    def plot(f, x0, x1, n=400):
        return " ".join(f"{sx(x0 + (x1 - x0) * i / n):.1f},{sy(f(x0 + (x1 - x0) * i / n)):.1f}" for i in range(n + 1))

    g.append(f'<polyline points="{plot(lambda x: 0.5 * x + 4, -12, 10)}" class="a-curve c3"/>')
    g.append(f'<polyline points="{plot(math.sin, -12, 10)}" class="a-curve c2"/>')
    g.append(f'<polyline points="{plot(lambda x: 0.5 * x * x - 2.5, -3.6, 3.6)}" class="a-curve c1"/>')
    r5 = math.sqrt(5)
    for x, y in [(0, -2.5), (-r5, 0), (r5, 0)]:       # 꼭짓점, x절편 ±√5
        g.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="9" class="a-dot c1"/>')
    g.append(f'<circle cx="{sx(-8):.1f}" cy="{sy(0):.1f}" r="9" class="a-dot c3"/>')  # y = ½x + 4 의 x절편
    g.append(f'<text x="{sx(0.4):.0f}" y="{sy(-3.1):.0f}" class="a-label c1">y = ½x² − 5/2</text>')
    g.append(f'<text x="{sx(4.6):.0f}" y="{sy(-1.6):.0f}" class="a-label c2">y = sin x</text>')
    g.append(f'<text x="{sx(-10.6):.0f}" y="{sy(-1.4):.0f}" class="a-label c3">y = ½x + 4</text>')
    return "".join(g), "a-sky1", "a-sky2"


# ② 기하: 피보나치 사각형과 황금 나선, 원과 내접 삼각형 -----------------------
def scene_geometry():
    g = []
    # 피보나치 사각형 (오른쪽)
    fib = [1, 1, 2, 3, 5, 8, 13]
    s = 22
    x, y = 1306, 640
    rects, arcs = [], []
    cx, cy = x, y
    # 사각형을 시계 방향으로 붙여 나가며 사분원 호를 그림
    bx0, by0, bx1, by1 = x, y, x + s, y + s
    rects.append((bx0, by0, s))
    arcs.append(f"M {bx0} {by1} A {s} {s} 0 0 1 {bx1} {by0}")
    for i, f in enumerate(fib[1:], start=1):
        n = f * s
        d = i % 4
        if d == 1:   # 오른쪽
            rx, ry = bx1, by0
            arcs.append(f"M {rx} {ry} A {n} {n} 0 0 1 {rx + n} {ry + n}")
            bx1 = rx + n; by1 = max(by1, ry + n)
        elif d == 2:  # 아래
            rx, ry = bx1 - n, by1
            arcs.append(f"M {rx + n} {ry} A {n} {n} 0 0 1 {rx} {ry + n}")
            by1 = ry + n; bx0 = min(bx0, rx)
        elif d == 3:  # 왼쪽
            rx, ry = bx0 - n, by1 - n
            arcs.append(f"M {rx + n} {ry + n} A {n} {n} 0 0 1 {rx} {ry}")
            bx0 = rx; by0 = min(by0, ry)
        else:         # 위
            rx, ry = bx0, by0 - n
            arcs.append(f"M {rx} {ry + n} A {n} {n} 0 0 1 {rx + n} {ry}")
            by0 = ry; bx1 = max(bx1, rx + n)
        rects.append((rx, ry, n))
    for rx, ry, n in rects:
        g.append(f'<rect x="{rx}" y="{ry}" width="{n}" height="{n}" class="a-rect"/>')
    g.append(f'<path d="{" ".join(arcs)}" class="a-curve c1"/>')
    # 원과 내접 삼각형 (왼쪽 위)
    ccx, ccy, r = 330, 700, 190
    g.append(f'<circle cx="{ccx}" cy="{ccy}" r="{r}" class="a-curve c3"/>')
    tri = [(ccx + r * math.cos(a), ccy + r * math.sin(a)) for a in (math.radians(-90), math.radians(30), math.radians(150))]
    g.append('<polygon points="' + " ".join(f"{px:.0f},{py:.0f}" for px, py in tri) + '" class="a-fill c2"/>')
    g.append(f'<circle cx="{ccx}" cy="{ccy}" r="7" class="a-dot c3"/>')
    g.append(f'<line x1="{ccx}" y1="{ccy}" x2="{tri[1][0]:.0f}" y2="{tri[1][1]:.0f}" class="a-thin"/>')
    g.append(f'<text x="{ccx + 60}" y="{ccy + 70}" class="a-label c3" font-size="38">r</text>')
    # 컴퍼스 호
    for k in range(5):
        rr = 120 + k * 70
        g.append(f'<path d="M 760 {H} m {rr} 0 a {rr} {rr} 0 0 0 {-rr} {-rr}" class="a-thin"/>')
    g.append(f'<text x="880" y="{H - 40}" class="a-label c1">φ = (1 + √5) / 2</text>')
    g.append(f'<text x="{ccx - 150}" y="{ccy + r + 75}" class="a-label c2">A + B + C = π</text>')
    return "".join(g), "a-sky3", "a-sky4"


# ③ 수식 별자리 ---------------------------------------------------------------
def scene_constellation():
    rnd = random.Random(7)
    g = []
    for _ in range(120):  # 작은 별
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.choice([1.5, 2, 2.5, 3])
        g.append(f'<circle cx="{x}" cy="{y}" r="{r}" class="a-star"/>')
    groups = [
        [(980, 160), (1080, 230), (1210, 200), (1300, 300), (1230, 410)],
        [(1020, 560), (1150, 620), (1290, 600), (1380, 700), (1300, 820), (1160, 790)],
        [(140, 700), (260, 640), (380, 720), (330, 860)],
    ]
    for pts in groups:
        g.append('<polyline points="' + " ".join(f"{x},{y}" for x, y in pts) + '" class="a-link"/>')
        for x, y in pts:
            g.append(f'<circle cx="{x}" cy="{y}" r="7" class="a-dot c4"/>')
    symbols = [("π", 1420, 170, 120, "c1"), ("∞", 860, 860, 110, "c3"), ("√2", 600, 180, 90, "c2"),
               ("Σ", 1450, 520, 100, "c5"), ("∫", 120, 300, 130, "c3"), ("Δ", 740, 520, 80, "c1"),
               ("θ", 1100, 420, 70, "c2"), ("e^{iπ}+1=0", 520, 950, 52, "c4"), ("φ", 300, 520, 70, "c5"),
               ("x²", 1500, 900, 70, "c2"), ("∂", 960, 330, 60, "c4")]
    for text, x, y, size, cls in symbols:
        text = text.replace("e^{iπ}", "e<tspan dy='-18' font-size='60%'>iπ</tspan><tspan dy='18'></tspan>")
        g.append(f'<text x="{x}" y="{y}" font-size="{size}" class="a-sym {cls}">{text}</text>')
    return "".join(g), "a-sky5", "a-sky6"


SCENES = [scene_graphs, scene_constellation, scene_geometry]

CSS = f"""
<style>
:root {{
  --a-sky1:light-dark(#EEF4FF,#0B1224); --a-sky2:light-dark(#FFF8EA,#18213D);
  --a-sky3:light-dark(#F1FBF6,#0C1A1D); --a-sky4:light-dark(#FFF3F0,#1B1630);
  --a-sky5:light-dark(#F4F0FF,#070B1A); --a-sky6:light-dark(#EAF4FF,#16203F);
  --a-grid:light-dark(rgba(30,42,74,.07),rgba(160,190,240,.08));
  --a-axis:light-dark(rgba(30,42,74,.30),rgba(200,215,245,.32));
  --a-thin:light-dark(rgba(30,42,74,.18),rgba(200,215,245,.18));
  --a-c1:light-dark(#F0645A,#FF8A80); --a-c2:light-dark(#2BB39A,#4FD8BD); --a-c3:light-dark(#5AA9E6,#7CC2FF);
  --a-c4:light-dark(#E0A800,#FFE45C); --a-c5:light-dark(#8E7CC3,#B9A6F0);
  --a-star:light-dark(rgba(30,42,74,.18),rgba(255,255,255,.55));
  --a-scrim:light-dark(rgba(251,252,254,.80),rgba(10,15,30,.72));
  --a-scrim2:light-dark(rgba(251,252,254,.35),rgba(10,15,30,.38));
}}
/* 로그인 화면에서는 모눈 배경 대신 그림 배경 */
.stApp {{ background-image:none !important; }}
.block-container {{ position:relative; z-index:1; }}
.login-bg {{ position:fixed; inset:0; z-index:-1; overflow:hidden; pointer-events:none; }}
.login-bg svg {{ position:absolute; inset:0; width:100%; height:100%; opacity:0;
  animation:bgfade {INTERVAL_SEC * 3}s linear infinite both; }}
.login-bg svg:nth-child(1) {{ animation-delay:-{FADE_SEC}s; }}
.login-bg svg:nth-child(2) {{ animation-delay:{INTERVAL_SEC - FADE_SEC}s; }}
.login-bg svg:nth-child(3) {{ animation-delay:{INTERVAL_SEC * 2 - FADE_SEC}s; }}
@keyframes bgfade {{
  0% {{ opacity:0; }}
  {FADE_SEC / (INTERVAL_SEC * 3) * 100:.2f}% {{ opacity:1; }}
  {INTERVAL_SEC / (INTERVAL_SEC * 3) * 100:.2f}% {{ opacity:1; }}
  {(INTERVAL_SEC + FADE_SEC) / (INTERVAL_SEC * 3) * 100:.2f}% {{ opacity:0; }}
  100% {{ opacity:0; }}
}}
.login-bg::after {{ content:""; position:absolute; inset:0;
  background:linear-gradient(90deg, var(--a-scrim) 0%, var(--a-scrim2) 70%, var(--a-scrim2) 100%); }}
.a-grid {{ stroke:var(--a-grid); stroke-width:1.2; }} .a-grid.major {{ stroke-width:2.2; }}
.a-axis {{ stroke:var(--a-axis); stroke-width:3; }}
.a-thin {{ stroke:var(--a-thin); stroke-width:2.5; fill:none; }}
.a-rect {{ stroke:var(--a-thin); stroke-width:3; fill:none; }}
.a-curve {{ fill:none; stroke-width:7; stroke-linecap:round; stroke-linejoin:round; opacity:.9; }}
.a-curve.c1 {{ stroke:var(--a-c1); }} .a-curve.c2 {{ stroke:var(--a-c2); }} .a-curve.c3 {{ stroke:var(--a-c3); }}
.a-fill.c2 {{ fill:var(--a-c2); fill-opacity:.18; stroke:var(--a-c2); stroke-width:5; stroke-linejoin:round; }}
.a-dot.c1 {{ fill:var(--a-c1); }} .a-dot.c3 {{ fill:var(--a-c3); }} .a-dot.c4 {{ fill:var(--a-c4); }}
.a-star {{ fill:var(--a-star); }}
.a-link {{ fill:none; stroke:var(--a-c4); stroke-width:2.5; stroke-opacity:.55; stroke-dasharray:6 8; }}
.a-label {{ font-family:'Times New Roman',Georgia,serif; font-style:italic; font-size:46px; }}
.a-sym {{ font-family:'Times New Roman',Georgia,serif; font-style:italic; opacity:.8; }}
.a-label.c1,.a-sym.c1 {{ fill:var(--a-c1); }} .a-label.c2,.a-sym.c2 {{ fill:var(--a-c2); }}
.a-label.c3,.a-sym.c3 {{ fill:var(--a-c3); }} .a-sym.c4 {{ fill:var(--a-c4); }} .a-sym.c5 {{ fill:var(--a-c5); }}
header[data-testid="stHeader"] {{ background:transparent !important; }}
/* 로그인 상자: 그림 위에서도 잘 보이게 (안내 문구까지 한 상자에) */
.st-key-login_card {{ background:light-dark(rgba(255,255,255,.93),rgba(23,33,58,.93));
  border:1.5px solid var(--line); border-radius:18px; padding:1.4rem 1.4rem 1rem;
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  box-shadow:0 10px 30px light-dark(rgba(30,42,74,.10),rgba(0,0,0,.35)); }}
.st-key-login_card [data-testid="stForm"] {{ border:none; padding:0; }}
@media (prefers-reduced-motion: reduce) {{
  .login-bg svg {{ animation:none !important; }}
  .login-bg svg:nth-child(1) {{ opacity:1; }}
}}
</style>
"""


def html() -> str:
    svgs = []
    for fn in SCENES:
        body, c1, c2 = fn()
        gid = c1
        svgs.append(
            f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" style="stop-color:var(--{c1})"/><stop offset="1" style="stop-color:var(--{c2})"/>'
            f'</linearGradient></defs><rect width="{W}" height="{H}" fill="url(#{gid})"/>{body}</svg>'
        )
    return CSS + '<div class="login-bg">' + "".join(svgs) + "</div>"
