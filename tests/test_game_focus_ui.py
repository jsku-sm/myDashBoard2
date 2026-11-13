"""Real Streamlit routing/events with local synthetic student records."""
import importlib
import json
import uuid
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates

APP='''
import streamlit as st
import storage as db
import realtime
from game_core import view
b=db.LocalBackend(TEST_ROOT)
db._ready_backend=lambda:b
db.get_backend=lambda:b
realtime.is_locked=lambda _:False
user=dict(id='10101',name='가상학생',role='student',must_change='0',**{'class':'1-1'})
if not b.read('users'):b.append('users',user)
st.session_state.user=user
st.session_state['outside_runs']=st.session_state.get('outside_runs',0)+1
view.page(user)
'''

def emit(app,**event):
    item=app.get('component_instance')[0]
    widgets=WidgetStates();w=widgets.widgets.add();w.id=item.proto.id
    w.json_value=json.dumps(dict(id=uuid.uuid4().hex,**event))
    app._run(widget_state=widgets)
    assert not app.exception and not app.error


def test_all_games_open_in_play_stage_and_native_back_returns_to_hub(tmp_path,monkeypatch):
    import storage,realtime
    from game_core import play_lab_engine
    for name in ('play_screen','service','play_lab_service','play_lab_view','function_quiz_service','function_quiz_view','view'):
        importlib.reload(importlib.import_module('game_core.'+name))
    for obj,name in ((storage,'_ready_backend'),(storage,'get_backend'),(realtime,'is_locked')):
        monkeypatch.setattr(obj,name,getattr(obj,name))
    app=AppTest.from_string('TEST_ROOT='+repr(str(tmp_path/'db'))+'\n'+APP,default_timeout=15).run()
    import streamlit.testing.v1.local_script_runner as runner
    from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
    # Match the browser's component-event request: rerun only its enclosing fragment.
    fragment_id=next(iter(app._fragment_storage._fragments))
    monkeypatch.setattr(runner,'RerunData',lambda **kwargs:RerunData(**kwargs,fragment_id_queue=[fragment_id]))
    def props():return json.loads(app.get('component_instance')[0].proto.json_args)
    assert props()['view']=='hub'
    for gid in play_lab_engine.TITLES:
        emit(app,action='navigate',target=gid)
        assert props()['view']=='arena' and props()['gameId']==gid
        assert any(b.proto.id.endswith('-good_game_stage') for b in app.get('flex_container'))
        assert props()['data']['records']==[]
        emit(app,action='navigate',target='hub')
        assert props()['view']=='hub'
    for gid in ('avatar','quiz'):
        emit(app,action='navigate',target=gid)
        button=app.button(key='game_return_10101')
        assert '모든 게임 목록' in button.label
        button.click().run()
        assert not app.exception and not app.error and props()['view']=='hub'
    assert app.session_state['outside_runs']==1


@pytest.mark.parametrize('game',['jump','kart','space','blocks','maze'])
def test_reward_games_exit_to_list_and_keep_participation(tmp_path,monkeypatch,game):
    import storage,realtime
    for package,names in [('game_core',('play_screen','service','play_lab_service','play_lab_view','view')),
                          ('reward_core',('service','view'))]:
        for name in names:importlib.reload(importlib.import_module(package+'.'+name))
    for obj,name in ((storage,'_ready_backend'),(storage,'get_backend'),(realtime,'is_locked')):
        monkeypatch.setattr(obj,name,getattr(obj,name))
    setup='''
from reward_core import service as reward
import uuid
if 'reward_ready' not in st.session_state:
    teacher=dict(id='teacher',name='가상교사',role='teacher',must_change='0',**{'class':''})
    b.append('users',teacher);st.session_state.user=teacher
    paper=reward.prepare(teacher,'functions',['function.meaning'],'easy')
    code=reward.create(teacher,unit='functions',topics=['function.meaning'],difficulty='easy',paper=paper,game=TEST_GAME,mode='solo',classes=['1-1'],duration=600)
    st.session_state.user=user;reward.join(user,code)
    st.session_state.user=teacher;reward.control(teacher,code,'start')
    st.session_state.user=user
    for i in range(3):
        v=reward.snapshot(user,code)
        reward.act(user,code,dict(id=uuid.uuid4().hex,action='answer',index=i,turn=v['turn'],choice=paper[i]['answer']))
        v=reward.snapshot(user,code)
        reward.act(user,code,dict(id=uuid.uuid4().hex,action='next',index=i,turn=v['turn']))
    reward.act(user,code,dict(id=uuid.uuid4().hex,action='play',game=TEST_GAME))
    st.session_state['_reward_student_10101']=code
    st.session_state['_gg_child']='단원 마무리 챌린지'
    st.session_state['reward_ready']=True
'''
    script=APP.replace('view.page(user)',setup+'\nview.page(user)')
    app=AppTest.from_string('TEST_ROOT='+repr(str(tmp_path/'db'))+'\nTEST_GAME='+repr(game)+'\n'+script,default_timeout=20).run()
    assert not app.exception and not app.error
    args=json.loads(app.get('component_instance')[0].proto.json_args)
    assert args['returnToGames'] is True and args['view']['run']['game']==game
    code=app.session_state['_reward_student_10101']
    emit(app,action='game_list')
    assert app.session_state['_gg_child']=='개념 학습게임'
    assert app.session_state['_reward_student_10101']==code
    assert json.loads(app.get('component_instance')[0].proto.json_args)['view']=='hub'
