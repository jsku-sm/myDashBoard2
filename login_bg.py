"""로그인 배경: 첨부 이미지 3장을 일정 간격으로 부드럽게 전환합니다.

- 이미지는 assets 폴더에서 읽어 HTML에 포함하므로 별도 파일 서버가 필요 없습니다.
- 밝은 모드/어두운 모드에 맞춘 반투명 덮개로 글자의 가독성을 유지합니다.
- 기기에서 '동작 줄이기'를 켜면 바뀌는 효과 없이 첫 이미지만 보여 줍니다.
"""
import base64
from functools import lru_cache
from pathlib import Path

INTERVAL_SEC = 10  # 한 장이 보이는 시간
FADE_SEC = 1.2     # 겹치며 바뀌는 시간

ASSET_DIR = Path(__file__).resolve().parent / "assets"
BACKGROUND_IMAGES = (
    ASSET_DIR / "login_bg_1.jpeg",
    ASSET_DIR / "login_bg_2.jpeg",
    ASSET_DIR / "login_bg_3.jpeg",
)
CYCLE_SEC = INTERVAL_SEC * len(BACKGROUND_IMAGES)
IMAGE_DELAYS_CSS = "\n".join(
    f".login-bg img:nth-child({i + 1}) {{ animation-delay:{i * INTERVAL_SEC - FADE_SEC:g}s; }}"
    for i in range(len(BACKGROUND_IMAGES))
)

CSS = f"""
<style>
:root {{
  --a-scrim:light-dark(rgba(251,252,254,.80),rgba(10,15,30,.72));
  --a-scrim2:light-dark(rgba(251,252,254,.35),rgba(10,15,30,.38));
}}
/* 로그인 화면에서는 모눈 배경 대신 이미지 배경 */
.stApp {{ background-image:none !important; }}
.block-container {{ position:relative; z-index:1; }}
.login-bg {{ position:fixed; inset:0; z-index:-1; overflow:hidden; pointer-events:none; }}
.login-bg img {{ position:absolute; inset:0; display:block; width:100%; height:100%;
  max-width:none; object-fit:cover; object-position:center; opacity:0;
  animation:bgfade {CYCLE_SEC}s linear infinite both; }}
{IMAGE_DELAYS_CSS}
@keyframes bgfade {{
  0% {{ opacity:0; }}
  {FADE_SEC / CYCLE_SEC * 100:.2f}% {{ opacity:1; }}
  {INTERVAL_SEC / CYCLE_SEC * 100:.2f}% {{ opacity:1; }}
  {(INTERVAL_SEC + FADE_SEC) / CYCLE_SEC * 100:.2f}% {{ opacity:0; }}
  100% {{ opacity:0; }}
}}
.login-bg::after {{ content:""; position:absolute; inset:0;
  background:linear-gradient(90deg, var(--a-scrim) 0%, var(--a-scrim2) 70%, var(--a-scrim2) 100%); }}
header[data-testid="stHeader"] {{ background:transparent !important; }}
/* 로그인 상자: 이미지 위에서도 안내 문구까지 잘 보이게 */
.st-key-login_card {{ background:light-dark(rgba(255,255,255,.93),rgba(23,33,58,.93));
  border:1.5px solid var(--line); border-radius:18px; padding:1.4rem 1.4rem 1rem;
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  box-shadow:0 10px 30px light-dark(rgba(30,42,74,.10),rgba(0,0,0,.35)); }}
.st-key-login_card [data-testid="stForm"] {{ border:none; padding:0; }}
@media (prefers-reduced-motion: reduce) {{
  .login-bg img {{ animation:none !important; }}
  .login-bg img:nth-child(1) {{ opacity:1; }}
}}
</style>
"""


@lru_cache(maxsize=1)
def html() -> str:
    images = []
    for path in BACKGROUND_IMAGES:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        images.append(f'<img src="data:image/jpeg;base64,{encoded}" alt="" draggable="false">')
    return CSS + '<div class="login-bg" aria-hidden="true">' + "".join(images) + "</div>"
