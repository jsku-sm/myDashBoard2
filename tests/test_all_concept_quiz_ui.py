"""Production Streamlit selectors and component events; local fake accounts."""
import importlib
import json
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

APP='''
import streamlit as st
import storage as db
import realtime
from game_core import function_quiz_view as view
backend=db.LocalBackend(TEST_ROOT)
db._ready_backend=lambda:backend
db.get_backend=lambda:backend
realtime.is_locked=lambda _:False
user={'id':'10101','name':'가상학생','role':'student','class':'1-1','must_change':'0'}
if not backend.read('users'):backend.append('users',user)
st.session_state.user=user
view.page(user)
'''


def props(app):
    return json.loads(app.get('component_instance')[0].proto.json_args)


def emit(app,action,**extra):
    current=props(app)['data']
    state=WidgetStates();item=state.widgets.add();item.id=app.get('component_instance')[0].proto.id
    item.json_value=json.dumps(dict(id=action+str(current['revision']),action=action,unit=current['unit'],revision=current['revision'],**extra))
    app._run(widget_state=state)
    assert not app.exception
    return props(app)['data']


def test_course_unit_picker_opens_correct_bank_and_preserves_returned_problem(tmp_path,monkeypatch):
    import storage,realtime,game_core.service,game_core.view
    from game_core import function_quiz_service,function_quiz_view
    for module in (game_core.service,game_core.view,function_quiz_service,function_quiz_view):importlib.reload(module)
    for obj,name in [(storage,'_ready_backend'),(storage,'get_backend'),(realtime,'is_locked')]:
        monkeypatch.setattr(obj,name,getattr(obj,name))
    # Only omit the transport-status panel; selectors, roles, records and RPC are real.
    monkeypatch.setattr(game_core.view,'_save_panel',lambda _:None)
    app=AppTest.from_string('TEST_ROOT='+repr(str(tmp_path/'store'))+'\n'+APP,default_timeout=20).run()
    assert not app.exception
    assert props(app)['data']['unit']=='polynomials'
    app.selectbox(key='concept_picker_10101_unit_공통수학1').set_value('matrices').run()
    data=emit(app,'open',level=1,topic=2)
    assert data['unit']=='matrices' and data['topic_count']==3 and data['question']['topic']==2
    backend=storage.LocalBackend(str(tmp_path/'store'))
    row=json.loads(backend.read('game_profiles')[0]['state_json'])
    answer=row['concept_quizzes']['matrices']['active']['question']['answer']
    submitted=emit(app,'answer',question_id=data['question']['id'],turn=0,choice=answer,seconds=0)
    assert submitted['totals']['correct']==1
    app.selectbox(key='concept_picker_10101_subject').set_value('공통수학2').run()
    app.selectbox(key='concept_picker_10101_unit_공통수학2').set_value('sets').run()
    data=emit(app,'open',level=1,topic=8)
    assert data['topics'][8]['id']=='logic.absolute' and data['topic_count']==9
    assert data['totals']['correct']==0
    app.selectbox(key='concept_picker_10101_unit_공통수학2').set_value('functions').run()
    assert props(app)['data']['topic_count']==6
    app.selectbox(key='concept_picker_10101_subject').set_value('공통수학1').run()
    restored=props(app)['data']
    assert restored['unit']=='matrices' and restored['totals']['correct']==1
    assert restored['question']['id']==submitted['question']['id']
