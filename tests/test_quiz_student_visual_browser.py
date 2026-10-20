from pathlib import Path
from html import escape
import pytest
from test_quiz_dashboard_browser import page, browser
from quiz_core.student_view import STYLE,hero_html,question_html,given_visual_html
from quiz_core import bank

def html():
    qs=bank.generate("공통수학2",bank.units("공통수학2")[5],seed=100,max_questions=3)
    paper={"title":"명제 개념확인","subject":"공통수학2","questions":qs,"answers":{qs[0]["id"]:0}}
    out='<html lang="ko"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html{color-scheme:light dark}body{margin:12px}*{box-sizing:border-box}label{display:flex;gap:8px}label p{margin:0}section{margin:15px 0}</style>'+STYLE+hero_html(paper)
    for i,q in enumerate(qs,1):
        out+=f'<section class="st-key-qv_item_{i}">'+question_html(q,i,len(qs),paper["answers"].get(q["id"]))+given_visual_html(q["prompt"])
        out+='<div role="radiogroup">'
        for j,v in enumerate(q["options"]):
            out+=f'<label><input type="radio" name="q{i}" {"checked" if i==1 and j==0 else ""}><p>{escape(v)}</p></label>'
        out+='</div></section>'
    return out+'</html>'

@pytest.mark.parametrize("width",[390,768,1440])
def test_quiz_option_cards_responsive_and_no_overflow(page,width):
    page.set_viewport_size({"width":width,"height":950});page.set_content(html())
    assert page.locator(".qz-number").count()==3
    assert page.locator(".qz-step.done").count()==1
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    first=page.locator('[role="radiogroup"]').first
    cols=first.evaluate('(e)=>getComputedStyle(e).gridTemplateColumns.split(" ").length')
    assert cols==(1 if width<620 else 2)
    assert page.locator('input:checked').count()==1
    assert all(x["height"]>=68 for x in page.locator('label').evaluate_all('(els)=>els.map(e=>({height:e.getBoundingClientRect().height}))'))

def test_visual_html_pregrade_not_correctness(page):
    page.set_content(html())
    assert page.locator(".qb-ok,.qb-no").count()==0
    assert "정답:" not in page.inner_text("body")
    assert page.locator(".qz-selected").first.inner_text()=="1번 보기를 선택했어요"

def test_choice_cards_keyboard_and_dark_mode(page):
    page.emulate_media(color_scheme="dark");page.set_content(html())
    first=page.locator('input').first
    first.focus();page.keyboard.press("ArrowDown")
    assert page.locator('input').nth(1).is_checked()
    assert page.locator(".qz-hero").evaluate('(e)=>getComputedStyle(e).backgroundColor')=="rgb(37, 48, 74)"
