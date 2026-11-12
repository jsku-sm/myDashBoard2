"""Send real Streamlit widget events through the server page, with fake AI only."""
import json
from pathlib import Path
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

APP = '''
import json
import streamlit as st
from types import SimpleNamespace
from quiz_pop import view, api, service, classroom
classroom.history=lambda user: []
service.snapshot=lambda user: {'userId':user['id'],'preview':True,'revision':0,'saved':None}
service.authorize=lambda *args, **kwargs: {'role':'teacher'}
service.storage_info=lambda user: {'ready':True,'repo':'jsku-sm/class-dashboard-data','expected':'jsku-sm/class-dashboard-data'}
def post(url,**kwargs):
    st.session_state.calls=st.session_state.get('calls',0)+1
    st.session_state.called_model=kwargs['json']['model']
    if st.session_state.get('fail'):
        return SimpleNamespace(status_code=401,json=lambda:{'error':{'code':'invalid_api_key','message':'PRIVATE-KEY'}})
    data={'title':'시험 문항','questions':[{'prompt':f'{i}+1은?', 'concept':'덧셈','standardId':'s1','options':['1','2','3','4','5'],'correctIndex':i,'hints':['개념','방법','생각'],'explanation':'덧셈해요.','visual':None} for i in range(3)]}
    return SimpleNamespace(status_code=200,json=lambda:{'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(data)}]}]})
api.requests.post=post
view.page({'id':'test-teacher','role':'teacher'})
'''

def send(app,eid):
    state=WidgetStates();event=state.widgets.add();event.id=app.get('component_instance')[0].proto.id
    event.json_value=json.dumps({'id':eid,'action':'generate','payload':{'settings':{'course':'공통수학1','unit':'다항식','range':'','standards':[{'id':'s1','text':'다항식 연산'}],'count':3,'startStage':0},'difficulty':'기초'}})
    app._run(widget_state=state)
    assert not app.exception
    return json.loads(app.get('component_instance')[0].proto.json_args)

def test_real_streamlit_event_returns_generated_quiz_and_cached_reply(monkeypatch):
    # AppTest executes application code in-process; restore the mocked transport.
    import requests
    original=requests.post
    try:
        app=AppTest.from_string(APP,default_timeout=20)
        app.secrets={'school_record_ai':{'api_key':'PRIVATE-KEY','model':'existing-model'}}
        app.run();assert not app.exception
        result=send(app,'request-1234')
        assert result['enabled'] and result['reply']['ok']
        assert len(json.loads(result['reply']['value']['text'])['questions'])==3
        assert app.session_state['called_model']=='existing-model'
        assert 'PRIVATE-KEY' not in json.dumps(result)
        send(app,'request-1234');assert app.session_state['calls']==1
        app.session_state['fail']=True
        result=send(app,'request-5678')
        assert not result['reply']['ok'] and 'QUIZ_AUTH' in result['reply']['error']
        assert any('QUIZ_AUTH' in e.value for e in app.error)
        assert 'PRIVATE-KEY' not in json.dumps(result)
    finally:
        requests.post=original
