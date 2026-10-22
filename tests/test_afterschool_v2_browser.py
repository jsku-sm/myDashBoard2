"""Real Chromium style/layout checks using HTML fixtures, NOT a Streamlit app.

Production CSS and escaped render helpers are used. Widget wrappers are test
fixtures; framework form events and iPad behavior need deployment testing.
"""
from html import escape
import pytest
from test_quiz_dashboard_browser import browser,page
from afterschool_core import presentation as design


def preview_html():
    cohort={'year':'2026','subject':'공통수학2','name':'1기 · 기초수학',
            'description':'배움의 속도에 맞추어, 함께 한 걸음씩 성장하는 방과후 수업',
            'state':'active','start_date':'2026-10-22','end_date':'2026-11-19','member_count':4}
    rows=[{'id':'10101','name':'예시학생 가','class':'1-1'},
          {'id':'10203','name':'예시학생 나','class':'1-2'},
          {'id':'10405','name':'예시학생 다','class':'1-4'},
          {'id':'10702','name':'예시학생 라','class':'1-7'}]
    nav='<div data-testid="stRadio"><div role="radiogroup" aria-label="관리 메뉴">'+''.join(
        f'<label data-baseweb="radio"><input type="radio" name="menu" {"checked" if label=="참여 학생" else ""}><span>{escape(label)}</span></label>'
        for label in ['기수 설정','참여 학생','자료·과제','질문·댓글','제출 확인'])+'</div></div>'
    people=''.join(f'<div class="st-key-as_member_row_example" style="display:flex;align-items:center;justify-content:space-between;gap:10px">'
                   f'{design.person(row)}<div class="st-key-as_remove_demo" data-testid="stButton"><button>배정 취소</button></div></div>' for row in rows)
    return '''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'''+design.styles()+'''<style>
body{font-family:'Noto Sans CJK KR','Malgun Gothic',sans-serif;margin:0;padding:28px;color:#303750;background-color:#fafbff;background-image:linear-gradient(#e9eef8 1px,transparent 1px),linear-gradient(90deg,#e9eef8 1px,transparent 1px);background-size:26px 26px}
main{max-width:1060px;margin:0 auto}.preview-note{font-size:13px;color:#737a8f;margin:0 0 16px}h2{font-size:27px;margin:0 0 6px}h4{margin:4px 0 8px}button,select,input{font:inherit;box-sizing:border-box}button{padding:9px 16px;cursor:pointer}input[type=radio]{accent-color:#8b75b2}label{display:flex;gap:7px;align-items:center}input[type=text]{width:100%;height:46px;border:1px solid #c9ded2;border-radius:11px;padding:11px 14px;background:white}.mini{font-size:13px;color:#6b778a;margin:8px 0 14px;line-height:1.7}.filters{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}.filters select{padding:11px;border:1px solid #e0dae9;border-radius:11px;background:#fff;width:100%;height:44px}.field-title{font-size:13px;color:#62708a;display:block;margin:0 0 8px}.add{margin:18px 0}.grid-row{display:flex;gap:10px;align-items:end}.grow{flex:1}.fake-collapse{border-top:1px solid #d3e8db;margin-top:17px;padding-top:13px;font-size:14px}.foot{font-size:12px;color:#7a8092;margin-top:16px;line-height:1.7}
@media(max-width:600px){body{padding:10px}.filters{grid-template-columns:1fr}.grid-row{flex-wrap:wrap}.grow{flex-basis:100%}button{font-size:14px}h2{font-size:23px}}
</style></head><body><main data-testid="stMain"><p class="preview-note">화면 구성 미리보기 · 가상 학생 데이터 / 실제 Streamlit 실행 화면 아님</p><section class="st-key-as_admin_shell">
<h2>🌙 방과후 관리</h2><p class="mini">과목과 기수를 정하고 학생을 배정하세요. 자료·과제·질문·제출까지 이곳에서 관리합니다.</p>'''+design.hero(cohort,'운영 중',True)+nav+design.stats([('현재 배정 인원','4명'),('운영 과목','공통수학2'),('기수 상태','운영 중')])+'''
<section class="st-key-as_add_panel_example add"><h4>학번으로 바로 배정</h4><p class="mini">정확한 학번 + Enter → 배정 저장. 이름은 검색 결과에서 확인한 뒤 선택하세요.</p><div class="grid-row"><div class="grow"><label class="field-title" for="student-search">학번·이름 검색</label><input id="student-search" type="text" placeholder="학번 입력 후 Enter / 이름 입력 후 Enter로 검색"></div><div data-testid="stFormSubmitButton"><button kind="primary">배정 / 검색 ↵</button></div></div><div class="fake-collapse">▸ 여러 학생을 한 번에 추가하기</div></section>
<section class="st-key-as_roster_panel_example"><div class="filters"><div><label class="field-title">배정 명단 학급</label><select><option>전체</option></select></div><div><label class="field-title">배정 명단에서 찾기</label><input type="text" placeholder="학번 또는 이름 (목록 필터)"></div></div>'''+design.roster_heading(4)+'''<p class="mini">배정 취소는 이 기수에서만 제외합니다. 학생 계정·다른 기수·기존 제출 기록은 삭제하지 않습니다.</p>'''+people+'''<div data-testid="stDownloadButton" style="margin-top:15px"><button>배정 명단 CSV</button></div></section><p class="foot">학생 화면: 공통수학2 → 방과후 게시판 → 자료·과제 / 질문·댓글 / 내 제출 확인<br>기수에 배정되지 않은 학생에게는 해당 과목의 방과후 탭이 표시되지 않습니다.</p></section></main></body></html>'''


@pytest.mark.parametrize('width',[390,768,1280])
def test_pastel_layout_no_page_overflow_and_touch_targets(page,width):
    page.set_viewport_size({'width':width,'height':1100});page.set_content(preview_html())
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert page.locator('.as-count').inner_text()=='총 4명'
    assert page.locator('.as-person').count()==4
    assert page.locator('[data-testid="stFormSubmitButton"] button').bounding_box()['height']>=44
    assert page.locator('.as-title').is_visible()


def test_scoped_design_does_not_color_unrelated_buttons(page):
    page.set_content(preview_html())
    page.evaluate('''() => {let d=document.createElement('div');d.dataset.testid='stButton';d.id='outside';d.innerHTML='<button>other</button>';document.body.append(d);}''')
    inside=page.locator('.st-key-as_remove_demo button').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')
    outside=page.locator('#outside button').evaluate('(e)=>getComputedStyle(e).backgroundColor')
    assert inside=='rgb(255, 240, 236)' and inside!=outside


def test_hero_escapes_names_descriptions_and_preserves_subject(page):
    h=design.hero({'year':'2026','name':'<script>bad()</script>','subject':'공통수학1','start_date':'','end_date':'',
                   'description':'<img src=x onerror=bad()>','member_count':3},'준비 중',True)
    page.set_content(h)
    assert not page.locator('script,img').count()
    assert '공통수학1' in page.locator('body').inner_text()
