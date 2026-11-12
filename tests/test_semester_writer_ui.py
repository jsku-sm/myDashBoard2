"""Real Streamlit widget/rerun flows; encrypted fake repository and fake AI."""
import copy
from datetime import datetime
import importlib
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest
from test_student_record_vault import env, review, SID, OTHER
from record_core.semester import SemesterRecords
import storage as db
from record_core.ai import AIConfig


@pytest.fixture
def ui(env,monkeypatch):
    import record_core.writer_view as v
    # Other legacy suites replace Streamlit references; restore real UI modules.
    import streamlit
    monkeypatch.setattr(v,'st',streamlit)
    import record_core.view as old
    monkeypatch.setattr(old,'st',streamlit)
    monkeypatch.setattr(db,'_ready_backend',lambda:env.b)
    monkeypatch.setattr(db,'now',lambda:datetime(2026,11,12,12))
    monkeypatch.setattr(db,'today_str',lambda:'2026-11-12')
    monkeypatch.setattr(v,'values',lambda:{'school_record_ai':{'enabled':True,'api_key':'not-real','model':'test-model'}})
    ai=SimpleNamespace(draft=Mock(side_effect=lambda subject,facts,*args,**kw:{'text':'좌표 관계를 확인함.', 'sentences':[{'text':'좌표 관계를 확인함.','evidence_ids':[facts[0]['evidence_id']]}]}))
    monkeypatch.setattr(v,'RecordAI',lambda config:ai)
    app=AppTest.from_string('from record_core.writer_view import render\nrender()',default_timeout=20)
    app.session_state['user']=copy.deepcopy(env.b.rows['users'][0])
    app.run();assert not app.exception
    pick(app.selectbox,'과목').select('공통수학2').run();assert not app.exception
    return SimpleNamespace(app=app,env=env,v=v,ai=ai,s=SemesterRecords(env.b,lambda:env.actor[0]))


def pick(elements,label):return next(e for e in elements if e.label==label)
def ctx(app):return next(v for k,v in app.session_state.to_dict().items() if k.startswith('rw_') and isinstance(v,dict) and 'buffers' in v and any(b['workspace']['data']['subject']=='공통수학2' for b in v['buffers'].values()))

def prepare_student(ui):
    app=ui.app
    multi=pick(app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임')
    evidence=next(e for e in ctx(app)['buffers'][SID]['workspace']['data']['evidence'] if e['category']=='sudanotes')
    multi.select(evidence['id']).run()
    pick(app.text_area,'AI에 반영할 사실 · 필요할 때만 수정').set_value('좌표의 부호 오류를 찾아 수정하는 과정을 관찰함.')
    pick(app.selectbox,'활동 맥락').select('정규 교과수업')
    app.run()
    assert not app.exception


def test_visible_generate_and_editor_before_evidence(ui):
    app=ui.app
    assert pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    assert pick(app.text_area,'교과세특 작성 내용') is not None
    assert not ui.ai.draft.called
    assert any('근거' in e.value for e in app.info)


def test_individual_draft_reload_and_csv(ui):
    app=ui.app
    pick(app.text_area,'교과세특 작성 내용').set_value('직접 작성한 학생 기록')
    pick(app.button,'초안 저장').click().run()
    assert not app.exception and not app.error
    assert ui.s.load_term(SID,'공통수학2',2026,2)['data']['current']['text']=='직접 작성한 학생 기록'
    assert pick(app.text_area,'교과세특 작성 내용').value=='직접 작성한 학생 기록'
    assert not ui.ai.draft.called
    assert any(e.label=='이 학생 저장본 CSV' for e in app.get('download_button'))


def test_generate_then_edit_and_finalize(ui):
    app=ui.app;prepare_student(ui)
    assert not pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    pick(app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not app.exception and not app.error
    assert ui.ai.draft.call_count==1 and pick(app.text_area,'교과세특 작성 내용').value=='좌표 관계를 확인함.'
    pick(app.text_area,'교과세특 작성 내용').set_value('대칭이동에 따른 좌표의 부호 변화를 비교하며 자신의 풀이를 점검함.')
    pick(app.text_input,'교사 확인·수정 메모').set_value('수다노트와 풀이를 대조하여 문장을 수정함.')
    pick(app.checkbox,'내용과 근거를 검토했으며, 이 문장을 완성본으로 확정합니다.').check().run()
    pick(app.button,'완성본 저장').click().run()
    assert not app.exception and not app.error
    assert ui.s.load_term(SID,'공통수학2',2026,2)['data']['current']['kind']=='final'
    assert ui.ai.draft.call_count==1


def test_all_load_preserves_unsaved_single_text_and_no_ai(ui):
    app=ui.app
    pick(app.text_area,'교과세특 작성 내용').set_value('아직 저장하지 않은 수정 중 문장').run()
    pick(app.button,'📂 전체 불러오기 · 저장된 초안과 완성본').click().run()
    assert not app.exception
    assert OTHER in ctx(app)['buffers']
    assert '아직 저장하지 않은 수정 중 문장' in ctx(app)['buffers'][SID]['backups']
    assert not ui.ai.draft.called


def test_student_denied_and_backend_missing_still_explains_button(ui,monkeypatch):
    ui.app.session_state['user']=ui.env.b.rows['users'][2];ui.app.run()
    assert ui.app.error and not ui.app.button and not ui.app.text_area
    ui.app.session_state['user']=ui.env.b.rows['users'][0]
    monkeypatch.setattr(db,'_ready_backend',lambda: (_ for _ in ()).throw(db.SetupError('저장소 연결 필요')))
    ui.app.run()
    assert not ui.app.exception and pick(ui.app.button,'✨ AI 교과세특 초안 생성').disabled


def test_bulk_table_edits_save_and_unchanged_final_is_preserved(ui):
    app=ui.app;w=ui.s.load_term(SID,'공통수학2',2026,2)
    r=review(next(e for e in w['data']['evidence'] if e['category']=='sudanotes'))
    ui.s.save_term(w,[r],'저장된 완성본',final=True,confirmed=True,review_note='근거 자료를 확인함.')
    pick(app.button,'📂 전체 불러오기 · 저장된 초안과 완성본').click().run()
    c=ctx(app)
    # AppTest has no DataEditor element; submit its actual widget delta schema.
    key=next(k for k in app.session_state.to_dict() if k.startswith(c['key']+'_grid_'))
    app.session_state[key]={'edited_rows':{'1':{'교과세특':'두 번째 학생 수정 문장'}},'added_rows':[],'deleted_rows':[]}
    app.run();pick(app.button,'표의 수정 내용 저장').click().run()
    assert not app.exception and not app.error
    assert ui.s.load_term(OTHER,'공통수학2',2026,2)['data']['current']['text']=='두 번째 학생 수정 문장'
    current=ui.s.load_term(SID,'공통수학2',2026,2)['data']['current']
    assert current['kind']=='final' and current['revision']==1
    assert not ui.ai.draft.called


def test_batch_students_separate_results_and_no_recall(ui):
    app=ui.app;ui.s.sync_sources(OTHER)
    for sid in (SID,OTHER):
        w=ui.s.load_term(sid,'공통수학2',2026,2)
        r=review(next(e for e in w['data']['evidence'] if e['category']=='sudanotes'))
        ui.s.save_term(w,[r],'')
    pick(app.button,'📂 전체 불러오기 · 저장된 초안과 완성본').click().run()
    pick(app.multiselect,'AI 초안을 생성할 학생').select(SID).select(OTHER)
    pick(app.checkbox,'선택한 학생들의 확인 근거를 AI에 전송합니다. 학생 수만큼 요청이 진행됩니다.').check().run()
    pick(app.button,'✨ 선택 학생 AI 초안 일괄 생성').click().run()
    assert not app.exception and not app.error
    assert ui.ai.draft.call_count==2
    assert all(x['state']=='done' for x in ctx(app)['job']['items'])
    assert all(ui.s.load_term(sid,'공통수학2',2026,2)['data']['current']['text'] for sid in (SID,OTHER))
    app.run();assert ui.ai.draft.call_count==2


def test_batch_changed_buffer_rejected_before_ai(ui):
    app=ui.app;prepare_student(ui);c=ctx(app);b=c['buffers'][SID]
    item={'input_hash':ui.v._batch_fingerprint(b)}
    pick(app.text_area,'교과세특 작성 내용').set_value('교사가 나중에 수정한 내용').run()
    with pytest.raises(Exception,match='내용이 바뀌었습니다'):
        ui.v._generate(ui.s,c,SID,AIConfig(api_key='fake'),{'target_chars':400,'byte_limit':1500,'guidance':''},'batch_changed',item)
    assert not ui.ai.draft.called


def test_batch_failure_keeps_done_and_resumes_only_unstarted(ui):
    app=ui.app;third='1103'
    ui.env.b.rows['users'].append({'id':third,'name':'가상학생다','role':'student','class':'1-1'})
    ui.env.b.rows['sudanotes'].append({'id':'note3','student_id':third,'date':'2026-10-25','subject':'공통수학2','q1':'좌표를 직접 비교함.'})
    for sid in (SID,OTHER,third):
        ui.s.sync_sources(sid)
        w=ui.s.load_term(sid,'공통수학2',2026,2)
        r=review(next(e for e in w['data']['evidence'] if e['category']=='sudanotes'))
        ui.s.save_term(w,[r],'')
    original=ui.ai.draft.side_effect;calls=[0]
    def sometimes_fails(*args,**kwargs):
        calls[0]+=1
        if calls[0]==2:raise RuntimeError('mock provider failure')
        return original(*args,**kwargs)
    ui.ai.draft.side_effect=sometimes_fails
    pick(app.button,'📂 전체 불러오기 · 저장된 초안과 완성본').click().run()
    pick(app.multiselect,'AI 초안을 생성할 학생').select(SID).select(OTHER).select(third)
    pick(app.checkbox,'선택한 학생들의 확인 근거를 AI에 전송합니다. 학생 수만큼 요청이 진행됩니다.').check().run()
    pick(app.button,'✨ 선택 학생 AI 초안 일괄 생성').click().run()
    assert not app.exception
    assert [x['state'] for x in ctx(app)['job']['items']]==['done','failed','waiting']
    assert ui.ai.draft.call_count==2
    pick(app.button,'아직 시작하지 않은 학생 계속').click().run()
    assert not app.exception
    assert [x['state'] for x in ctx(app)['job']['items']]==['done','failed','done']
    assert ui.ai.draft.call_count==3


def test_observation_add_keeps_teacher_prose(ui):
    app=ui.app
    pick(app.text_area,'교과세특 작성 내용').set_value('관찰 추가 전 작성한 문장')
    pick(app.text_area,'관찰한 사실').set_value('칠판에 좌표를 표시하며 대칭 관계를 설명함.')
    pick(app.button,'관찰 근거 저장·불러오기').click().run()
    assert not app.exception and not app.error
    assert pick(app.text_area,'교과세특 작성 내용').value=='관찰 추가 전 작성한 문장'
    assert any(e['category']=='observations' for e in ctx(app)['buffers'][SID]['workspace']['data']['evidence'])


def test_points_are_visible_separately_and_not_offered_as_ai_evidence(ui):
    app=ui.app
    assert any('상점·벌점 확인' in e.label for e in app.expander)
    options=pick(app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').options
    assert not any('상점·벌점' in str(x) for x in options)
    assert not ui.ai.draft.called


def test_select_generate_and_accept_unchanged_without_typing_or_extra_approvals(ui):
    app=ui.app
    evidence=next(e for e in ctx(app)['buffers'][SID]['workspace']['data']['evidence'] if e['category']=='sudanotes')
    pick(app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').select(evidence['id']).run()
    assert not ui.ai.draft.called
    assert not pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    assert any('대칭의 부호를 확인함' in m.value for m in app.markdown)
    assert not ctx(app)['buffers'][SID]['reviews'][0]['teacher_confirmed']
    pick(app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not app.exception and not app.error
    assert ui.ai.draft.call_count==1
    facts=ui.ai.draft.call_args.args[1]
    assert len(facts)==1 and facts[0]['evidence_id']==evidence['id']
    assert '학생이 설명한 핵심 개념' in facts[0]['confirmed_fact']
    assert '교사 관찰 아님' in facts[0]['confirmed_fact']
    generated=pick(app.text_area,'교과세특 작성 내용').value
    assert generated=='좌표 관계를 확인함.'
    assert pick(app.button,'완성본 저장').disabled
    pick(app.checkbox,'내용과 근거를 검토했으며, 이 문장을 완성본으로 확정합니다.').check().run()
    pick(app.button,'완성본 저장').click().run()
    assert not app.exception and not app.error
    saved=ui.s.load_term(SID,'공통수학2',2026,2)['data']['current']
    assert saved['kind']=='final' and saved['text']==generated
    assert saved['teacher_confirmed'] and saved['ai_draft']
    assert saved['review_note']==''
    app.run();assert ui.ai.draft.call_count==1


def test_selection_removal_and_nonclass_context_disable_generation(ui):
    app=ui.app
    evidence=next(e for e in ctx(app)['buffers'][SID]['workspace']['data']['evidence'] if e['category']=='sudanotes')
    pick(app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').select(evidence['id']).run()
    pick(app.selectbox,'활동 맥락').select('방과후·자유 학습').run()
    assert pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    pick(app.selectbox,'활동 맥락').select('정규 교과수업').run()
    assert not pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    pick(app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').unselect(evidence['id']).run()
    assert pick(app.button,'✨ AI 교과세특 초안 생성').disabled
    assert not ui.ai.draft.called


def test_arcade_card_renders_math_and_generation_uses_readable_event(ui):
    import json
    profile={'play_lab':{'records':[{'game':'function-factory','runId':'lesson-run','seq':1,
        'type':'success','at':'2026-11-12 10:00:00','stage':1,
        'question':r'$f(x)=3x+1,\quad g(x)=x+3$에 입력 $-2$를 처리하시오.',
        'skill':'합성함수', 'message':r'출력 $4$예요.'}]}}
    ui.env.b.rows['game_profiles'].append({'id':'arcade-test','student_id':SID,'state_json':json.dumps(profile)})
    ui.s.sync_sources(SID)
    w=ui.s.load_term(SID,'공통수학2',2026,2)
    ui.v._install(ctx(ui.app),SID,w)
    ui.app.run()
    e=next(e for e in w['data']['evidence'] if e.get('extra',{}).get('source_kind')=='arcade_event')
    pick(ui.app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').select(e['id']).run()
    assert not ui.app.exception
    assert any(r'$f(x)=3x+1,\quad g(x)=x+3$' in m.value for m in ui.app.markdown)
    assert not pick(ui.app.button,'✨ AI 교과세특 초안 생성').disabled
    pick(ui.app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not ui.app.exception and not ui.app.error
    fact=ui.ai.draft.call_args.args[1][0]['confirmed_fact']
    assert '실제 학생 답과 풀이 과정은 이 기록에 없어' in fact
    assert '학생에게 표시된 피드백' in fact
