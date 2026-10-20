"""Real Chromium checks of the read-only HTML component, not a Streamlit server.

Optional developer tooling: pip install playwright; install Chromium separately.
No production dependency is added. No real accounts or storage are contacted.
"""
from copy import deepcopy
import os
import shutil
import pytest
pw=pytest.importorskip('playwright.sync_api')
from test_concept_quiz import env
from quiz_core.presentation import dashboard_html


@pytest.fixture(scope='module')
def browser():
    executable=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium') or shutil.which('chromium-browser')
    if not executable: pytest.skip('No Chromium executable available')
    with pw.sync_playwright() as p:
        b=p.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
        yield b
        b.close()


@pytest.fixture
def page(browser):
    p=browser.new_page(viewport={'width':1400,'height':1000})
    yield p
    p.close()


@pytest.fixture
def board(env):
    qid=env.paper()
    env.answer(qid,env.students[0])
    keys=env.answer(qid,env.students[1])
    env.actor(env.students[1])
    env.svc.save_answer(env.students[1],qid,'q01',(keys[0]['answer']+1)%4,10)
    env.actor(env.students[2]); env.svc.save_answer(env.students[2],qid,'q01',1,0)
    env.actor(env.t);env.svc.grade(env.t,qid,[s['id'] for s in env.students[:2]])
    return env.svc.dashboard(env.t,qid)


def show(page,board):
    page.set_content('<html lang="ko"><meta name="viewport" content="width=device-width, initial-scale=1">'
                     '<style>html{color-scheme:light dark}body{margin:16px}</style>'+dashboard_html(board)+'</html>')


def test_ten_columns_correct_stats_and_student_rows(page,board):
    show(page,board)
    assert page.locator('tbody tr').count()==5
    assert page.locator('thead th').count()==14
    assert page.locator('.qb-stat').count()==10
    assert page.locator('.qb-stat b').first.inner_text()=='1명'
    assert page.locator('.qb-stat b').nth(1).inner_text()=='0명'
    assert '2명' in page.locator('.qb-metric').nth(2).inner_text()


def test_only_graded_rows_have_ox(page,board):
    show(page,board)
    assert page.locator('tbody tr').nth(0).locator('.qb-ok').count()==10
    assert page.locator('tbody tr').nth(1).locator('.qb-no').count()==1
    assert page.locator('tbody tr').nth(2).locator('.qb-ok,.qb-no').count()==0
    assert page.locator('tbody tr').nth(2).locator('.qb-wait').inner_text()=='②'


@pytest.mark.parametrize('width',[390,768,1440])
def test_mobile_table_scrolls_without_page_overflow(page,board,width):
    page.set_viewport_size({'width':width,'height':900});show(page,board)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    if width<1060:
        assert page.locator('.qb-scroll').evaluate('(e)=>e.scrollWidth>e.clientWidth')
        before=page.locator('td.qb-person').first.bounding_box()['x']
        page.locator('.qb-scroll').evaluate('(e)=>e.scrollLeft=400')
        after=page.locator('td.qb-person').first.bounding_box()['x']
        assert abs(before-after)<2
    columns=page.locator('.qb-metrics').evaluate('(e)=>getComputedStyle(e).gridTemplateColumns.split(" ").length')
    assert columns==(2 if width<700 else 4)


def test_untrusted_titles_and_names_are_not_executable(page,board):
    malicious=deepcopy(board)
    malicious['quiz']['title']='<script>window.BAD=1</script>'
    malicious['students'][0]['name']='<img src=x onerror="window.BAD=1">'
    show(page,malicious)
    assert page.locator('.quiz-board script,.quiz-board img').count()==0
    assert page.evaluate('window.BAD') is None
    assert '<script>' in page.locator('h3').inner_text()


def test_no_grade_shows_dash_not_wrong_count_zero(page,board):
    empty=deepcopy(board);empty['graded']=0;empty['mean']=None
    for stat in empty['stats']:stat.update(graded=0,wrong=0,blank=0)
    for s in empty['students']:s.update(state='working',marks={},score=None)
    show(page,empty)
    assert page.locator('.qb-no,.qb-ok').count()==0
    assert page.locator('.qb-stat b').all_inner_texts()==['—']*10


def test_dark_mode_uses_dark_cells(page,board):
    page.emulate_media(color_scheme='dark');show(page,board)
    assert page.locator('td.qb-person').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(32, 43, 64)'
