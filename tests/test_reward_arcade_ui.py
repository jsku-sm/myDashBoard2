"""Real Streamlit reruns and component RPC, fake users in temporary local files."""
import importlib
import json
import uuid
from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates

APP='''
import streamlit as st
import storage as db
import realtime
from reward_core import view, service
from types import SimpleNamespace
b=db.LocalBackend(TEST_ROOT)
b.is_local=False;b.repo='jsku-sm/class-dashboard-data'
db._ready_backend=lambda:b
db.flush_now=lambda:None
realtime.is_locked=lambda _:False
teacher=dict(id='teacher',name='검증교사',role='teacher',must_change='0',**{'class':''})
student=dict(id='10101',name='검증학생',role='student',must_change='0',**{'class':'1-1'})
if not b.read('users'):
    b.append('users',teacher);b.append('users',student)
st.session_state.user=student if st.session_state.get('test_role')=='student' else teacher
service.time=SimpleNamespace(time=lambda:st.session_state.get('test_now',1000.0))
if st.session_state.user['role']=='teacher':view.page(st.session_state.user)
else:
    from quiz_pop.entry import student_entry
    student_entry(st.session_state.user,st.session_state.get('_quizpop_student_code','join'),standalone=False)
'''


def component(app):return app.get('component_instance')[0]
def props(app):return json.loads(component(app).proto.json_args)
def rpc(app,action,**values):
    state=WidgetStates();item=state.widgets.add();item.id=component(app).proto.id
    item.json_value=json.dumps(dict(id=uuid.uuid4().hex,action=action,**values))
    app._run(widget_state=state)
    assert not app.exception
    return props(app)['view']


def test_teacher_setup_preview_code_student_entry_and_timed_return(tmp_path,monkeypatch):
    import storage,realtime,game_core.service
    from reward_core import service,view
    from quiz_pop import service as quizsvc,classroom,entry
    for module in (game_core.service,service,view,quizsvc,classroom,entry):importlib.reload(module)
    for obj,name in ((storage,'_ready_backend'),(storage,'flush_now'),(realtime,'is_locked'),(service,'time')):
        monkeypatch.setattr(obj,name,getattr(obj,name))
    path=str(tmp_path/'data')
    app=AppTest.from_string('TEST_ROOT='+repr(path)+'\n'+APP,default_timeout=20)
    app.run();assert not app.exception
    app.selectbox(key='reward_unit_공통수학1').set_value('matrices').run()
    app.multiselect(key='reward_topics_matrices').set_value(['matrix.meaning']).run()
    next(b for b in app.button if b.label=='이 단원으로 문제 준비').click().run()
    assert not app.exception
    assert any('해설' in m.value for m in app.markdown)
    assert len([c for c in app.checkbox if c.label=='이 문제 출제'])>=3
    next(c for c in app.checkbox if c.label=='문제·정답과 출제 범위를 확인했습니다.').check().run()
    next(b for b in app.button if b.label=='참여코드 만들기').click().run()
    assert not app.exception
    v=props(app)['view'];assert v['status']=='lobby' and len(v['code'])==6
    code=v['code'];b=storage.LocalBackend(path);paper=json.loads(b.read('reward_rooms')[0]['questions_json'])
    app.session_state['test_role']='student';app.run()
    assert not app.exception and not app.get('component_instance')
    assert not app.error, [e.value for e in app.error]
    app.text_input(key='quizpop_join_input').set_value(code)
    next(b for b in app.button if b.label=='퀴즈 참여').click().run()
    assert not app.exception and props(app)['view']['role']=='student' and props(app)['view']['participants']==1
    app.session_state['test_role']='teacher';app.run();rpc(app,'start')
    app.session_state['test_role']='student';app.run()
    for i in range(3):
        v=props(app)['view'];assert 'answer' not in v['question']
        if i==0:rpc(app,'hint',index=i,turn=v['turn'])
        v=rpc(app,'answer',index=i,turn=v['turn'],choice=paper[i]['answer'])
        assert v['feedback']['correct']
        rpc(app,'next',index=i,turn=v['turn'])
    v=props(app)['view'];assert v['ticket'] and v['correct']==3 and v['hints']==1
    v=rpc(app,'play',game='blocks');run=v['run'];assert run['game']=='blocks'
    app.session_state['test_now']=1090.0
    v=rpc(app,'progress',run=run['id'],start=0,inputs=[0]*1800,final=True)
    assert not v['run'] and v['question'] and len(v['runs'])==1 and v['coins']>=2
    app.session_state['test_role']='teacher';app.run()
    assert props(app)['view']['students'][0]['correct']==3
    rpc(app,'end');assert any('CSV' in e.proto.label for e in app.get('download_button'))
