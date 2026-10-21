"""Real Chromium checks of progress HTML only; not the full Streamlit app."""
from copy import deepcopy
import pytest
from test_teacher_progress import env
from test_quiz_dashboard_browser import page, browser

@pytest.fixture
def content(env):
    env.create(classes=['1-1','1-2','1-3','1-4','1-5','1-6','1-7'],status='완료')
    env.create(classes=['1-1','1-2'],request='future-preview',date='2026-10-23',content='평행이동 탐구')
    rows=env.svc.list_records(env.t)
    return env.vis.hero_html()+env.vis.cards_html(env.svc.summaries(rows,'2026-10-20'),'2026-10-20')+env.vis.table_html(env.svc.display_rows(rows))

def show(page,html):
    page.set_content('<html lang="ko"><meta name="viewport" content="width=device-width,initial-scale=1">'
                     '<style>html{color-scheme:light dark}body{margin:16px}*{box-sizing:border-box}</style>'+html+'</html>')

@pytest.mark.parametrize('width',[390,768,1440])
def test_table_cards_responsive_no_page_overflow(page,content,width):
    page.set_viewport_size({'width':width,'height':950});show(page,content)
    assert page.locator('.tp-card').count()==7
    assert page.locator('tbody tr').count()==9
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert page.locator('table th').count()==12
    if width<1100:
        assert page.locator('.tp-table-wrap').evaluate('(e)=>e.scrollWidth>e.clientWidth')
    if width<640:
        assert page.locator('.tp-cards').evaluate('(e)=>getComputedStyle(e).gridTemplateColumns.split(" ").length')==2


def test_table_and_card_text_is_escaped(page,env):
    env.create(content='<img src=x onerror="window.BAD=1">',memo='<script>window.BAD=1</script>')
    rows=env.svc.list_records(env.t)
    html=env.vis.hero_html()+env.vis.cards_html(env.svc.summaries(rows,'2026-10-20'),'2026-10-20')+env.vis.table_html(env.svc.display_rows(rows))
    show(page,html)
    assert page.locator('.tp img,.tp script').count()==0
    assert page.evaluate('window.BAD') is None
    assert '<script>' in page.locator('tbody').inner_text()


def test_assessment_columns_dates_separate(page,env):
    env.create(date='2026-10-19',assessment_date='2026-11-03')
    rows=env.svc.list_records(env.t)
    show(page,env.vis.hero_html()+env.vis.table_html(env.svc.display_rows(rows,'assessment')))
    assert page.locator('thead th').first.inner_text()=='수행평가일'
    assert page.locator('tbody td').first.inner_text()=='2026-11-03'
    assert '2026-10-19' in page.locator('tbody tr').inner_text()


def test_status_labels_visible_in_light_and_dark(page,content):
    page.emulate_media(color_scheme='dark');show(page,content)
    assert page.locator('.tp-done').count()==7
    assert page.locator('.tp-card').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(27, 39, 59)'
    assert '완료' in page.locator('tbody').inner_text()


def test_table_region_keyboard_scroll(page,content):
    page.set_viewport_size({'width':390,'height':950});show(page,content)
    region=page.locator('.tp-table-wrap')
    assert region.get_attribute('tabindex')=='0'
    region.focus();region.evaluate('(e)=>e.scrollLeft=200')
    assert region.evaluate('(e)=>e.scrollLeft')>0
