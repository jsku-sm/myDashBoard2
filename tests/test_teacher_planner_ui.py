"""Real Streamlit rerun/component RPC integration with isolated fake accounts."""
import importlib
import json
import uuid
from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates

APP='''
import streamlit as st
import storage as db
from teacher_planner import view
b=db.LocalBackend(TEST_ROOT)
db._ready_backend=lambda:b
db.flush_now=lambda:None
teacher=dict(id='test-teacher',name='검증교사',role='teacher',must_change='0')
student=dict(id='test-student',name='검증학생',role='student',must_change='0')
if not b.read('users'):
    b.append('users',teacher);b.append('users',student)
st.session_state.user=student if st.session_state.get('student') else teacher
view.page(st.session_state.user,st.session_state.get('mode','progress'))
'''

def props(app):return json.loads(app.get('component_instance')[0].proto.json_args)
def rpc(app,action,payload,token=None):
    state=WidgetStates();item=state.widgets.add();item.id=app.get('component_instance')[0].proto.id
    item.json_value=json.dumps(dict(token=token or uuid.uuid4().hex,action=action,payload=payload))
    app._run(widget_state=state)
    assert not app.exception
    return props(app)


def test_streamlit_create_move_both_views_conflict_replay_and_student_denial(tmp_path,monkeypatch):
    import storage,teaching_progress_service
    from teacher_planner import service,view
    for module in (teaching_progress_service,service,view):importlib.reload(module)
    for name in ('_ready_backend','flush_now'):monkeypatch.setattr(storage,name,getattr(storage,name))
    app=AppTest.from_string('TEST_ROOT='+repr(str(tmp_path/'data'))+'\n'+APP,default_timeout=20).run()
    assert not app.exception and not app.error
    assert props(app)['mode']=='progress'
    p=dict(date='2026-10-20',classes=['1-1'],subject='공통수학2',period='2교시',content='합성함수',status='예정',assessment_title='함수 수행평가',assessment_date='2026-11-20')
    first=rpc(app,'save_lesson',p,'create-one-lesson')
    assert first['ack']['ok'] and len(first['data']['lessons'])==1
    rpc(app,'save_lesson',p,'create-one-lesson');assert len(props(app)['data']['lessons'])==1
    r=first['data']['lessons'][0]
    moved=rpc(app,'move',dict(id=r['id'],kind='lesson',revision=r['revision'],date='2026-10-21',period='3교시'))
    assert moved['ack']['ok']
    app.session_state['mode']='diary';app.run();assert not app.exception
    r=props(app)['data']['lessons'][0];assert r['date']=='2026-10-21' and r['assessment_date']=='2026-11-20'
    moved=rpc(app,'move',dict(id=r['id'],kind='assessment',revision=r['revision'],date='2026-11-21'))
    assert moved['data']['lessons'][0]['date']=='2026-10-21'
    stale=rpc(app,'move',dict(id=r['id'],kind='lesson',revision='1',date='2026-10-22'))
    assert not stale['ack']['ok'] and stale['data']['lessons'][0]['date']=='2026-10-21'
    result=rpc(app,'save_diary',dict(kind='task',title='업무 준비',date='2026-10-20',deadline='2026-10-23',important='1'))
    assert result['ack']['ok'] and result['data']['diary'][0]['title']=='업무 준비'
    app.session_state['mode']='progress';app.run()
    assert len(props(app)['data']['diary'])==1
    app.session_state['student']=True;app.run()
    assert app.error and not app.exception and not app.get('component_instance')
