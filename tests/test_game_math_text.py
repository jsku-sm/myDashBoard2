"""Display math must preserve problem meaning, answer indices and old progress."""
from copy import deepcopy
import pytest
from game_core.math_text import markdown, latex
from test_game_learning import game_env


@pytest.mark.parametrize(('text','expected'),[
    ('유리함수 y=3/(x−2)+1의 점근선은?',r'유리함수 $y=\frac{3}{x-2}+1$의 점근선은?'),
    ('-1/3',r'$-\frac{1}{3}$'),
    ('x^12+x²',r'$x^{12}+x^{2}$'),
    ('f⁻¹(3)',r'$f^{-1}(3)$'),
    ('√((x₂−x₁)²+(y₂−y₁)²)',r'$\sqrt{(x_{2}-x_{1})^{2}+(y_{2}-y_{1})^{2}}$'),
    ('A=[[1, 2], [3, 4]]',r'$A=\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}$'),
    ('n(A∪B)=n(A)+n(B)−n(A∩B)',r'$n(A\cup B)=n(A)+n(B)-n(A\cap B)$'),
    ('점 (-2, 3)',r'점 $(-2,3)$'),
    ('5C2와 5P2',r'${}_{5}\mathrm{C}_{2}$와 ${}_{5}\mathrm{P}_{2}$'),
    ('x≤-3이면 x≠1이다',r'$x\le -3$이면 $x\ne 1$이다'),
    ('함수의 뜻을 설명하세요.', '함수의 뜻을 설명하세요.'),
])
def test_notation_preserves_values_and_prose(text,expected):
    assert markdown(text)==expected


def test_teacher_latex_is_preserved_and_delimiters_normalized():
    text=r'식 $\frac{x+1}{2}$과 \(x^2\)를 비교해요.'
    assert markdown(text)==r'식 $\frac{x+1}{2}$과 $x^2$를 비교해요.'
    assert markdown(r'\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\]').strip()==r'$$'+'\n'+r'\begin{pmatrix}1&2\\3&4\end{pmatrix}'+'\n$$'
    assert latex('|ax+by+c|/√(a²+b²)')==r'\frac{\lvert ax+by+c\rvert }{\sqrt{a^{2}+b^{2}}}'


def test_landing_hides_mission_but_preserves_ongoing_session_and_records(game_env):
    e=game_env;e.actor(e.t)
    mid=e.svc.create_mission(e.t,'진행 중인 학습','move.reflection',['1-1'])
    sid=e.start(mission=mid)
    e.action(sid,'pause')
    before=deepcopy(e.raw());p=e.profile()
    e.view._landing(e.ss[0],p)
    assert e.raw()==before
    assert any(kind=='subheader' and text=='골라 배우는 개념' for kind,text,_ in e.st.outputs)
    assert any(kind=='button' and text=='이 자리부터 이어 하기' for kind,text,_ in e.st.outputs)
    assert not any('미션 시작' in str(text) or '선생님이 보낸' in str(text) for _,text,_ in e.st.outputs)
    e.actor(e.t);assert any(m['id']==mid for m in e.svc.missions(e.t))


def test_ui_formats_published_prompt_without_mutating_the_bank(game_env):
    e=game_env;e.start(tid='function.rational')
    original=deepcopy(e.raw());p=e.profile();s=p['sessions'][0]
    e.view._lesson(e.ss[0],p,s)
    assert e.raw()==original
    assert any(kind=='markdown' and r'\frac{' in str(text) for kind,text,_ in e.st.outputs)
    q=s['question']
    assert 'answer' not in q and 'explanation' not in q


def test_native_streamlit_radio_uses_math_labels_without_changing_choices():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
from game_core.math_text import markdown
choices=['-1/3','x²','√(x+1)','x≤2']
st.markdown(markdown('유리함수 y=3/(x−2)+1의 점근선은?'))
answer=st.radio('답 선택',range(4),index=None,format_func=lambda i:markdown(choices[i]))
st.session_state['chosen_index']=answer
''').run()
    assert not app.exception
    assert app.radio[0].options[0]==r'$-\frac{1}{3}$'
    assert app.radio[0].options[1]==r'$x^{2}$'
    app.radio[0].set_value(2).run()
    assert app.session_state['chosen_index']==2 and not app.exception
