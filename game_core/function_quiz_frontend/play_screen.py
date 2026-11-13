"""Viewport play space and fragment-scoped navigation; no student data cache."""
import streamlit as st
from pathlib import Path

_viewport_component = None

CSS = '''<style>
.st-key-good_game_stage {
 position:fixed!important; inset:62px 12px 12px!important; z-index:900;
 width:auto!important; max-width:none!important; height:auto!important;
 padding:0; overflow:hidden; box-sizing:border-box;
 background:#f8f7ff; color:#20203a; border:3px solid #282342;
 border-radius:24px; box-shadow:0 0 0 100vmax rgba(28,24,50,.42),0 14px 50px #201d3540;
}
.st-key-good_game_content {position:absolute!important;left:0;top:0;max-width:none!important;
 transform-origin:top left;box-sizing:border-box;gap:8px!important;}
.st-key-good_game_stage h1,.st-key-good_game_stage h2,.st-key-good_game_stage h3 {color:#20203a;}
.st-key-game_return_bar {position:sticky!important;top:-14px;z-index:15;background:#f8f7ff;
 padding:10px 0 12px;border-bottom:2px solid #d4cbee;}
.st-key-game_return_bar button {background:#d9ff4b!important;color:#20203a!important;
 border:3px solid #20203a!important;border-radius:15px!important;min-height:52px;
 box-shadow:4px 4px #20203a;font-size:1.05rem;font-weight:900;}
.st-key-game_return_bar button:hover {background:#e7ff8c!important;}
@media(max-width:600px){.st-key-good_game_stage{inset:54px 4px 4px!important;padding:0;border-radius:16px;}
 .st-key-game_return_bar{top:-8px}.st-key-game_return_bar button{min-height:48px;font-size:.95rem}}
</style>'''


def fit_viewport():
    global _viewport_component
    if _viewport_component is None:
        import streamlit.components.v1 as components
        _viewport_component=components.declare_component('good_game_viewport',path=str(Path(__file__).with_name('play_viewport_frontend')))
    _viewport_component(key='good_game_viewport',default=None)


def rerun():
    # Full reruns (first entry/reconnect) cannot request a fragment-only rerun.
    try:
        st.rerun(scope='fragment')
    except st.errors.StreamlitAPIException:
        st.rerun()


def return_bar(user):
    with st.container(key='game_return_bar'):
        if st.button('← 모든 게임 목록으로 돌아가기', type='primary', key='game_return_'+user['id']):
            st.session_state['_lab_'+user['id']+'_selection']='hub'
            st.session_state['_gg_nav_next']='개념 학습게임'
            rerun()


def active(user, child):
    if child=='개념 학습게임':
        return st.session_state.get('_lab_'+user['id']+'_selection','hub')!='hub'
    if child=='단원 마무리 챌린지':
        key='_reward_teacher_' if user.get('role')=='teacher' else '_reward_student_'
        return bool(st.session_state.get(key+user['id']))
    return False
