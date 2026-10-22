"""Real Chromium checks of the session-file component, not full Streamlit."""
from pathlib import Path
import base64
import pytest
from test_quiz_dashboard_browser import page,browser

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'afterschool_core/download_component/index.html').read_text()

def render(page,args):
    page.evaluate('(args)=>dispatchEvent(new MessageEvent("message",{source:window,data:{type:"streamlit:render",args}}))',args)

def setup(page):
    page.set_content(HTML)
    page.evaluate('window.sent=[];addEventListener("message",e=>{if(e.data.type==="streamlit:setComponentValue")sent.push(e.data.value);})')
    render(page,{'binding':'test-session-file','label':'📎 방과후 학습지.txt'})

@pytest.mark.parametrize('width',[390,768,1280])
def test_download_layout_keyboard_and_no_public_file_url(page,width):
    page.set_viewport_size({'width':width,'height':400});setup(page)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    button=page.locator('#prepare');assert button.bounding_box()['height']>=44
    button.focus();page.keyboard.press('Enter')
    page.wait_for_function('sent.some(v=>v.action==="prepare")')
    assert not page.locator('#save').is_visible()
    assert not page.locator('a[href^="http"]').count()


def test_authorized_file_blob_save_and_acknowledge(page):
    setup(page);page.locator('#prepare').click();page.wait_for_function('sent.length>0')
    rid=page.evaluate('sent.find(v=>v.action==="prepare").request_id')
    render(page,{'binding':'test-session-file','result':{'request_id':rid,'data':base64.b64encode('학습지 내용'.encode()).decode(),
                                                       'name':'학습지.txt','mime':'text/plain'}})
    assert page.locator('#save').is_visible()
    assert page.locator('#save').get_attribute('href').startswith('blob:')
    with page.expect_download() as got:page.locator('#save').click()
    assert got.value.suggested_filename=='학습지.txt'
    assert Path(got.value.path()).read_text()=='학습지 내용'
    page.wait_for_function('sent.some(v=>v.action==="received")')
    render(page,{'binding':'test-session-file','result':None})
    assert page.locator('#save').is_visible()


def test_denied_request_has_no_blob_and_safe_error_text(page):
    setup(page)
    render(page,{'binding':'test-session-file','result':{'request_id':'error-request-01','error':'<img src=x onerror=alert(1)> 권한 없음'}})
    assert not page.locator('#save').is_visible()
    assert page.locator('img').count()==0
    assert '권한 없음' in page.locator('#note').inner_text()


def test_new_record_clears_prepared_file(page):
    setup(page)
    render(page,{'binding':'test-session-file','result':{'request_id':'clear-request-01','data':'dGVzdA==','name':'a.txt','mime':'text/plain'}})
    assert page.locator('#save').is_visible()
    render(page,{'binding':'different-record'})
    assert not page.locator('#save').is_visible()
