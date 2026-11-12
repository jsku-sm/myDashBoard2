"""Real Streamlit RPC -> real classroom -> student code-entry integration.

Only AI/network and persistence transport are fake; no live student accounts.
"""
import importlib
import json
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from test_quiz_pop import saved, chosen


APP = '''
import json
import streamlit as st
import storage as db
import realtime
from types import SimpleNamespace
from quiz_pop import view, api
backend=db.LocalBackend(TEST_ROOT)
backend.is_local=False;backend.repo='jsku-sm/class-dashboard-data'
db._ready_backend=lambda:backend
db.flush_now=lambda:None
realtime.is_locked=lambda _:False
teacher={'id':'teacher','name':'시험교사','role':'teacher','class':'','must_change':'0'}
student={'id':'10101','name':'가상학생','role':'student','class':'1-1','must_change':'0'}
if not backend.read('users'):
    backend.append('users',teacher);backend.append('users',student)
st.session_state.user=student if st.session_state.get('test_role')=='student' else teacher
def post(url,**kwargs):
    st.session_state.calls=st.session_state.get('calls',0)+1
    paper={'title':'다항식 퀴즈','questions':[{'prompt':f'{i}+1은?', 'concept':'덧셈','standardId':'s1','options':['1','2','3','4','5'],'correctIndex':i,'hints':['개념','방법','생각'],'explanation':'덧셈해요.','visual':None} for i in range(3)]}
    return SimpleNamespace(status_code=200,json=lambda:{'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(paper)}]}]})
api.requests.post=post
view.page(st.session_state.user)
'''


def learning_component(app):
    return next(c for c in app.get('component_instance')
                if 'teacherPaper' not in json.loads(c.proto.json_args)['data'])


def props(app):
    return json.loads(learning_component(app).proto.json_args)


def teacher_paper(app):
    return next(json.loads(c.proto.json_args)['data']['teacherPaper']
                for c in app.get('component_instance')
                if 'teacherPaper' in json.loads(c.proto.json_args)['data'])


def event(app,action,payload,eid):
    current=props(app)
    state=WidgetStates();item=state.widgets.add();item.id=learning_component(app).proto.id
    item.json_value=json.dumps({'id':eid,'action':action,'payload':payload,'revision':current['data']['revision']})
    app._run(widget_state=state)
    assert not app.exception
    return props(app)


def test_generate_autocode_student_form_join_and_answer_roundtrip(tmp_path,monkeypatch):
    # Restore production functions if another AppTest replaced them in-process.
    import storage,realtime,requests,game_core.service
    from quiz_pop import service,classroom,view
    for module in (game_core.service,service,classroom,view):importlib.reload(module)
    for obj,name in [(storage,'_ready_backend'),(storage,'flush_now'),(realtime,'is_locked'),(requests,'post')]:
        monkeypatch.setattr(obj,name,getattr(obj,name))
    app=AppTest.from_string('TEST_ROOT='+repr(str(tmp_path/'store'))+'\n'+APP,default_timeout=20)
    app.secrets={'quiz_ai':{'api_key':'fake-test-key','model':'test-model'}}
    app.run();assert not app.exception and not props(app)['data']['publication']
    generated=event(app,'generate',{'settings':chosen(),'difficulty':'기초'},'generate-001')
    assert generated['reply']['ok'] and app.session_state['calls']==1
    value=saved();value['session']['questions']=json.loads(generated['reply']['value']['text'])['questions']
    value['session']['progress']=[{'attempts':[],'solved':False,'hintsUsed':0} for _ in range(3)]
    published=event(app,'save',value,'save-teacher-001')
    assert published['reply']['ok']
    code=published['data']['publication']['code']
    assert len(code)==6 and code.isdigit()
    assert any(code in m.value for m in app.markdown)
    assert teacher_paper(app)['questions']==value['session']['questions']
    assert app.session_state['calls']==1
    assert not any(b.label=='참여코드 만들기' for b in app.button)
    app.session_state['test_role']='student';app.run()
    assert not app.exception and not app.get('component_instance')
    app.text_input(key='quizpop_join_input').set_value(code)
    next(b for b in app.button if b.label=='퀴즈 참여').click().run()
    mine=props(app)['data']
    assert mine['assignment']['code']==code and mine['role']=='student'
    assert len(app.get('component_instance'))==1
    assert 'teacherPaper' not in mine
    assert mine['saved']['session']['questions']==value['session']['questions']
    blocked=event(app,'generate',{'settings':chosen(),'difficulty':'기초'},'student-forged-001')
    assert not blocked['reply']['ok'] and app.session_state['calls']==1
    answer=mine['saved']
    for q,p in zip(answer['session']['questions'],answer['session']['progress']):
        p.update(attempts=[q['correctIndex']],solved=True)
    answer['showingSummary']=True
    done=event(app,'save',answer,'student-save-001')
    assert done['reply']['ok'] and done['data']['saved']['showingSummary']
    app.session_state['test_role']='teacher';app.session_state['_quizpop_teacher_room']=code;app.run()
    assert not app.exception
    assert next(m for m in app.metric if m.label=='완료 학생').value=='1'
    assert teacher_paper(app)['questions']==value['session']['questions']
    assert teacher_paper(app)['code']==code
    next(b for b in app.button if b.label=='이 퀴즈 참여 종료').click().run()
    assert not app.exception
    assert teacher_paper(app)['questions']==value['session']['questions']
    assert app.session_state['calls']==1
