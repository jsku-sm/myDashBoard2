"""Real Chromium tests of the component, not of the complete Streamlit runtime.

Requires the optional dev dependencies and CHROMIUM_PATH (default /usr/bin/chromium).
The Python/JS boundary is simulated; GitHub is not contacted.
"""
import ast
import copy
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def source_strings():
    tree = ast.parse((ROOT / "views/classroom_progress_grid.py").read_text())
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("_CSS", "_JS")}


def sample():
    classes = [f"1-{i}" for i in range(1, 8)]
    counts = [2, 1, 3, 2, 1, 2, 0]
    titles = ["직선의 방정식 — 기울기와 절편", "원의 방정식 — 중심과 반지름",
              "도형의 평행이동 — 움직인 만큼 좌표 바꾸기", "픽토그램 만들기 — 전공과 수학 연결"]
    rows = []
    for i, title in enumerate(titles):
        cells = {cls: dict(course_id=cls, lesson_id=f"lesson-{i}", expected_version=3,
                          completed=i < counts[j], actual_date="2026-10-20" if i < counts[j] else "",
                          disabled=False, reason="", makeup_needed=False) for j, cls in enumerate(classes)}
        rows.append(dict(id=f"row-{i}", title=title, subtitle="첨부 1개 · 수업내용", cells=cells))
    return dict(classes=classes, cards=[dict(class_name=cls, subject="공통수학2", completed=counts[i], total=4,
                     percent=counts[i]*25, label=f"{counts[i]} / 4 수업 완료") for i, cls in enumerate(classes)],
                rows=rows, term="2026학년도 2학기", subject="공통수학2", selected="")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        path = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
        if not Path(path).exists():
            pytest.skip("Chromium path not available; install browser or set CHROMIUM_PATH")
        browser = p.chromium.launch(executable_path=path, headless=True, args=["--no-sandbox"])
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1480, "height": 1120}, device_scale_factor=1)
    text = source_strings()
    page.set_content('<!doctype html><html lang="ko"><head><meta charset="utf-8"></head>'
                     '<body style="margin:0;padding:24px;background:#f3f6fa"><div id="host"></div></body></html>')
    page.evaluate("""(css) => {
        const host=document.querySelector('#host');const shadow=host.attachShadow({mode:'open'});
        const style=document.createElement('style');style.textContent=css;shadow.append(style);
        const root=document.createElement('div');root.className='board';shadow.append(root);
        window.testRoot=shadow;window.events=[];
    }""", text["_CSS"])
    page.add_script_tag(content=text["_JS"].replace("export default function(component)", "window.renderProgress = function(component)", 1))
    page.evaluate("""data=>{
       window.model=data;
       window.showBoard=()=>window.renderProgress({data:window.model,parentElement:window.testRoot,
           setTriggerValue:(name,event)=>window.events.push(event)});
       window.showBoard();
    }""", sample())
    yield page
    page.close()


def test_seven_cards_and_content_header(page):
    assert page.locator('.card').count() == 7
    assert page.locator('th').all_text_contents() == ["수업내용"] + [f"1-{i}반" for i in range(1, 8)]
    assert page.locator('input[type=checkbox]').count() == 28
    assert page.locator('.percent strong').all_text_contents() == ['50%', '25%', '75%', '50%', '25%', '50%', '0%']


def test_toggle_emits_versioned_event_and_waits_for_saved_response(page):
    box = page.get_by_role('checkbox', name='직선의 방정식 — 기울기와 절편 · 1-7반 수업 완료', exact=True)
    box.click()
    event = page.evaluate('window.events[0]')
    assert event['completed'] is True and event['expected_version'] == 3
    assert event['course_id'] == '1-7' and event['lesson_id'] == 'lesson-0' and event['event_id']
    assert not box.is_checked() and box.is_disabled()
    assert '저장 중' in page.locator('.status').inner_text()


def test_uncheck_is_also_a_proposal_not_optimistic_success(page):
    box=page.get_by_role('checkbox',name='직선의 방정식 — 기울기와 절편 · 1-1반 수업 완료',exact=True)
    box.click()
    assert page.evaluate('window.events[0].completed') is False
    assert box.is_checked()


def test_server_rerender_updates_checkbox_and_percent(page):
    page.evaluate("""()=>{
      window.model.rows[0].cells['1-7'].completed=true;
      window.model.rows[0].cells['1-7'].actual_date='2026-10-20';
      window.model.cards[6].completed=1;window.model.cards[6].percent=25;
      window.model.cards[6].label='1 / 4 수업 완료';window.showBoard();
    }""")
    assert page.get_by_role('checkbox',name='직선의 방정식 — 기울기와 절편 · 1-7반 수업 완료',exact=True).is_checked()
    assert page.locator('.percent strong').all_text_contents()[-1] == '25%'


def test_row_open_event_does_not_change_completion(page):
    before = page.locator('input:checked').count()
    page.get_by_role('button',name='원의 방정식 — 중심과 반지름 자료 확인 및 배포',exact=True).click()
    assert page.evaluate('window.events[0].type') == 'open'
    assert page.evaluate('window.events[0].row_id') == 'row-1'
    assert page.locator('input:checked').count() == before


def test_unapplied_cells_are_not_actionable(page):
    page.evaluate("""()=>{
      delete window.model.rows[0].cells['1-7'];
      window.model.rows[0].cells['1-6'].disabled=true;
      window.model.rows[0].cells['1-6'].reason='미적용';window.showBoard();
    }""")
    assert page.locator('input[type=checkbox]').count() == 27
    assert page.get_by_role('checkbox',name='직선의 방정식 — 기울기와 절편 · 1-6반 수업 완료',exact=True).is_disabled()
    assert '미배포' in page.locator('tbody tr').first.inner_text()


def test_titles_use_text_content_not_executable_html(page):
    title='<img src=x onerror="window.pwned=true"> 수업내용'
    page.evaluate('(value)=>{window.model.rows[0].title=value;window.showBoard()}', title)
    assert page.locator('tbody img').count() == 0
    assert title in page.locator('.title-btn').first.inner_text()
    assert page.evaluate('window.pwned === undefined')


def test_ipad_width_has_horizontal_scroll_and_all_classes(page):
    page.set_viewport_size({'width':820,'height':1180})
    overflow = page.locator('.scroll').evaluate('(el)=>el.scrollWidth>el.clientWidth')
    assert overflow
    assert page.locator('.card').count() == 7
    page.locator('.scroll').evaluate('(el)=>el.scrollLeft=el.scrollWidth')
    last=page.get_by_role('checkbox',name='직선의 방정식 — 기울기와 절편 · 1-7반 수업 완료',exact=True)
    last.click()
    assert page.evaluate('window.events[0].course_id') == '1-7'


def test_focus_and_minimum_touch_target(page):
    box=page.get_by_role('checkbox',name='직선의 방정식 — 기울기와 절편 · 1-7반 수업 완료',exact=True)
    box.focus()
    assert box.evaluate('(el)=>el.parentElement.getBoundingClientRect().height >= 44')
    box.press('Space')
    assert page.evaluate('window.events.length') == 1


def test_empty_board_has_guidance_and_no_fake_completion(page):
    page.evaluate("""()=>{window.model.rows=[];for(const card of window.model.cards){card.percent=null;card.label='수업 미개설'}window.showBoard()}""")
    assert page.locator('input[type=checkbox]').count() == 0
    assert '아직 등록한' in page.locator('.empty').inner_text()
    assert page.locator('.percent strong').all_text_contents() == ['—']*7
