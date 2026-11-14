"""In-flow game content and fragment-scoped navigation; no viewport takeover."""
import streamlit as st

CSS = '''<style>
/* The panel stays AFTER the tool picker and game navigation in document flow. */
.st-key-good_game_panel {
 position:relative; inset:auto; z-index:auto;
 width:100%; max-width:100%; min-width:0; height:auto;
 padding:12px; box-sizing:border-box; overflow:visible;
 background:#f8f7ff; color:#20203a; border:2px solid #ded8f0;
 border-radius:20px;
}
.st-key-good_game_panel iframe {max-width:100%;}
.st-key-good_game_panel h1,.st-key-good_game_panel h2,.st-key-good_game_panel h3 {color:#20203a;}
.st-key-game_return_bar {position:static;z-index:auto;background:#f8f7ff;
 padding:6px 0 12px;border-bottom:2px solid #d4cbee;}
.st-key-game_return_bar button {background:#d9ff4b!important;color:#20203a!important;
 border:3px solid #20203a!important;border-radius:15px!important;min-height:48px;
 box-shadow:4px 4px #20203a;font-size:1.05rem;font-weight:900;}
.st-key-game_return_bar button:hover {background:#e7ff8c!important;}
@media(max-width:600px){.st-key-good_game_panel{padding:8px;border-radius:16px;}
 .st-key-game_return_bar button{font-size:.95rem}}
</style>'''


def fit_viewport():
    """Compatibility only: older callers must never overlay or scale the dashboard."""
    return None


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
