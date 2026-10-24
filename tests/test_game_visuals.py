"""Actual Chromium render test of HTML/SVG components, NOT Streamlit end-to-end."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_core import engine,presentation as art
from playwright.sync_api import sync_playwright


def document():
    p=engine.new_profile();p['equipped'].update(coat='coat_mint',cap='cap_headphones',pin='pin_math')
    board=[[0]*6 for _ in range(6)];board[0][:4]=[1]*4
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'''+art.CSS+'''<style>
body{margin:0;background:#f8f9f7;color:#24374b;font-family:'NanumSquareRound','NanumGothic',sans-serif;line-height:1.65}
main{max-width:1080px;margin:0 auto;padding:24px}nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}nav span{padding:9px 17px;border:1px solid #dce3e1;border-radius:12px;background:white;font-size:13px}nav .selected{background:#e3efe9;border-color:#65917f}
.studio{display:grid;grid-template-columns:1fr 2.8fr;gap:24px}.stages{display:grid;grid-template-columns:1fr 1fr;gap:16px}h3{font-size:20px;margin-bottom:4px}.question{border:1px solid #dbe4e1;border-radius:17px;background:white;padding:25px;margin-top:20px}.options{display:grid;grid-template-columns:1fr 1fr;gap:10px}.options span{padding:10px 15px;border:1px solid #d5dfdc;border-radius:10px}.small{font-size:12px;color:#61778a}.pill{display:inline-block;background:#497a6a;color:white;border-radius:10px;padding:8px 18px;margin-top:18px}.notice{font-size:11px;text-align:right;color:#678;margin-top:25px}
@media(max-width:650px){main{padding:14px}.studio{grid-template-columns:1fr}.stages{grid-template-columns:1fr}.gg-avatar svg{width:100px}.options{grid-template-columns:1fr}}@media(prefers-color-scheme:dark){body{background:#1f2937;color:#eaf0f5}nav span,.question{background:#2d3b4a;color:#eaf0f5}nav .selected{background:#365f53}.small,.notice{color:#bdcdd8}}
</style></head><body><main><nav><span>1. 데스모스</span><span>2. 수행평가</span><span class="selected">3. 게임으로 배우기</span><span>4. 퀴즈</span><span>5. 앱 (by Good쌤)</span></nav>'''+art.hero()+'''<div class="small">개념 학습게임 &nbsp; / &nbsp; 나의 성장기록</div><h3>공통수학2 · 대칭이동</h3><div class="small">Ⅰ. 도형의 방정식 → 3. 도형의 이동 → 02. 대칭이동 → 축·원점·직선에 대한 대칭이동</div>'''+art.progress(1)+'''<section class="studio"><aside>'''+art.avatar(p['equipped'],14)+art.note('힌트를 활용해 끝까지 해결했어요. 도움을 쓰는 것도 공부하는 힘이에요.')+'''</aside><article><div class="stages">'''+art.puzzle(board,1,(1,1,0))+art.adventure([[0,0],[1,0]])+'''</div><div class="question"><div class="small">문제 2 / 5 · 두 게임 중 하나를 선택해 배우며 기록은 합쳐집니다.</div><h3>점 (2, 3)을 x축에 대하여 대칭이동한 점은?</h3><div class="options"><span>① (2, −3)</span><span>② (−2, 3)</span><span>③ (−2, −3)</span><span>④ (3, 2)</span></div><div class="pill">내 생각 확인하기</div> <span class="small">한 단계 힌트 · 해설과 함께 배우기</span></div></article></section><div class="notice">HTML/SVG 구성요소 미리보기 · 실제 앱에서는 선택한 게임 하나만 표시됩니다.</div></main></body></html>'''


@pytest.mark.parametrize('width,dark',[(1280,False),(390,False),(820,True)])
def test_responsive_components(width,dark,tmp_path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':width,'height':1100},color_scheme='dark' if dark else 'light',reduced_motion='reduce')
        page.set_content(document(),wait_until='load')
        assert page.locator('svg').count()==3
        assert page.get_by_text('수학, 나의 속도로 한 걸음.').count()==1
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.locator('.gg-avatar').bounding_box()['width']>0
        page.screenshot(path=str(tmp_path/f'game_components_{width}.png'),full_page=True)
        if width==1280:
            output=ROOT/'game_preview';output.mkdir(exist_ok=True)
            page.screenshot(path=str(output/'게임화면_구성요소_미리보기.png'),full_page=True)
            (output/'게임화면_구성요소_미리보기.html').write_text(document(),encoding='utf-8')
        browser.close()
