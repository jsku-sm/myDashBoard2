"""Real config/Responses/UI integration with fake HTTP and encrypted fake storage."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from record_core.ai import AIConfig, RecordAI
from record_core.archive import ArchiveError
from test_semester_writer_ui import ui, pick, ctx, prepare_student
from test_student_record_vault import env, SID


@pytest.mark.parametrize('values,environ,source,model', [
    ({'openai': {'api_key':'fake', 'model':'gpt-4o-mini'}}, {}, 'openai', 'gpt-4o-mini'),
    ({'OPENAI_API_KEY':'fake', 'OPENAI_MODEL':'gpt-4.1-mini'}, {}, 'OPENAI_API_KEY', 'gpt-4.1-mini'),
    ({}, {'OPENAI_API_KEY':'fake', 'OPENAI_MODEL':'gpt-4o'}, '서버 환경변수', 'gpt-4o'),
    ({'quiz_ai': {'api_key':'fake', 'model':'gpt-5.4-mini'}}, {}, 'quiz_ai', 'gpt-5.4-mini'),
    ({'snorkl': {'openai_api_key':'fake', 'openai_model':'gpt-4.1-mini', 'ai_enabled':False}}, {}, 'snorkl', 'gpt-4.1-mini'),
    ({'school_record_ai': {'api_key':'', 'model':''}, 'openai': {'api_key':'fake','model':'gpt-4o-mini'}}, {}, 'openai', 'gpt-4o-mini'),
])
def test_existing_settings_enable_explicit_teacher_generation(values, environ, source, model):
    config=AIConfig.from_values(values, environ)
    assert config.enabled and not config.problem()
    assert config.api_key=='fake' and config.key_source==source and config.model==model
    assert 'fake' not in repr(config)


def test_explicit_disable_and_dedicated_override_and_invalid_flags():
    base={'openai': {'api_key':'shared', 'model':'gpt-4o-mini'}}
    for flag in (False, ' false ', 'OFF', '0'):
        c=AIConfig.from_values(dict(base,school_record_ai={'enabled':flag}), {})
        assert not c.enabled and '사용 안 함' in c.problem()
    c=AIConfig.from_values(dict(base,school_record_ai={'enabled':'TRUE','model':'gpt-4.1-mini'}), {})
    assert c.enabled and c.model=='gpt-4.1-mini' and c.api_key=='shared'
    assert AIConfig.from_values(dict(base,school_record_ai={'enabled':'typo'}), {}).config_error
    assert '모델 이름' in AIConfig.from_values(dict(base,school_record_ai={'model':'사용 가능한 모델 이름'}), {}).problem()


def test_custom_provider_keys_never_sent_to_official_openai():
    for section in ('openai','quiz_ai','snorkl'):
        c=AIConfig.from_values({section:{'api_key':'foreign', 'base_url':'https://other.example/v1'}}, {})
        assert not c.api_key
    c=AIConfig.from_values({'school_record_ai':{'api_key':'foreign','base_url':'https://other.example/v1'},
                            'openai':{'api_key':'official'}}, {})
    assert c.config_error and not c.api_key
    assert not AIConfig.from_values({}, {'OPENAI_API_KEY':'foreign','OPENAI_BASE_URL':'https://other.example/v1'}).api_key


def post_client(body, status=200):
    post=Mock(return_value=SimpleNamespace(status_code=status,json=lambda:body))
    return RecordAI(AIConfig('fake',model='test-model',enabled=True), SimpleNamespace(post=post)),post


FACTS=[{'evidence_id':'E'+'a'*16,'confirmed_fact':'대칭이동에서 좌표의 부호를 비교함.','source':'교사 관찰'}]


@pytest.mark.parametrize('status,code,expected', [
    (401,'invalid_api_key','API 키가 유효하지'),
    (403,'permission_denied','사용 권한'),
    (404,'model_not_found','모델을 찾지'),
    (429,'insufficient_quota','잔액·결제'),
    (429,'rate_limit_exceeded','요청이 몰렸'),
    (400,'context_length_exceeded','입력 한도'),
    (503,'server_error','일시적인 오류'),
])
def test_actionable_errors_without_key_student_or_provider_text(status, code, expected):
    client,post=post_client({'error':{'code':code,'message':'sk-private 학생 개인정보'}},status)
    with pytest.raises(ArchiveError,match=expected) as error:
        client.draft('공통수학2',FACTS,consent=True)
    assert 'sk-private' not in str(error.value) and '학생 개인정보' not in str(error.value)
    assert post.call_count==1


def test_incomplete_refusal_timeout_and_malformed_reply_are_distinct():
    for reply,match in [
        ({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}},'출력 한도'),
        ({'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'private'}]}]},'해당 자료'),
        ([], '응답 형식'),
        ({'status':'completed','output':None},'응답 형식'),
    ]:
        client,post=post_client(reply)
        with pytest.raises(ArchiveError,match=match):client.draft('공통수학2',FACTS,consent=True)
        assert post.call_count==1
    client,post=post_client({});post.side_effect=requests.Timeout('private')
    with pytest.raises(ArchiveError,match='대기 시간이 초과'):client.draft('공통수학2',FACTS,consent=True)
    assert post.call_count==1


def test_ui_legacy_openai_config_to_real_responses_adapter(ui,monkeypatch):
    monkeypatch.setattr(ui.v,'values',lambda:{'openai':{'api_key':'fake','model':'gpt-4o-mini'}})
    post=Mock()
    def respond(*args,**kwargs):
        body=kwargs['json']; facts=json.loads(body['input'][0]['content'][0]['text'])['facts']
        assert body['model']=='gpt-4o-mini' and body['store'] is False
        assert '가상학생가' not in str(body)
        result={'sentences':[{'text':'대칭이동의 좌표 관계를 설명함.','evidence_ids':[facts[0]['evidence_id']]}],'cautions':[]}
        return SimpleNamespace(status_code=200,json=lambda:{'status':'completed','output':[{'type':'message','content':[
            {'type':'output_text','text':json.dumps(result,ensure_ascii=False)}]}]})
    post.side_effect=respond
    monkeypatch.setattr(ui.v,'RecordAI',lambda config:RecordAI(config,SimpleNamespace(post=post)))
    prepare_student(ui)
    assert not post.called
    button=pick(ui.app.button,'✨ AI 교과세특 초안 생성');assert not button.disabled
    button.click().run()
    assert not ui.app.exception and not ui.app.error
    assert post.call_count==1
    assert pick(ui.app.text_area,'교과세특 작성 내용').value=='대칭이동의 좌표 관계를 설명함.'
    ui.app.run();assert post.call_count==1


def test_ui_disabled_setting_explains_before_network(ui,monkeypatch):
    monkeypatch.setattr(ui.v,'values',lambda:{'openai':{'api_key':'fake'},'school_record_ai':{'enabled':False}})
    prepare_student(ui)
    assert pick(ui.app.button,'✨ AI 교과세특 초안 생성').disabled
    assert any('사용 안 함' in i.value for i in ui.app.info)
    assert not ui.ai.draft.called


def test_ui_http_error_keeps_selection_and_survives_rerun(ui,monkeypatch):
    client,post=post_client({'error':{'code':'insufficient_quota'}},429)
    monkeypatch.setattr(ui.v,'RecordAI',lambda config:client)
    prepare_student(ui)
    selected=list(pick(ui.app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').value)
    pick(ui.app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not ui.app.exception and any('잔액·결제' in e.value for e in ui.app.error)
    ui.app.run()
    assert post.call_count==1 and any('잔액·결제' in e.value for e in ui.app.error)
    assert pick(ui.app.multiselect,'활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임').value==selected


def test_ui_generated_draft_visible_after_save_failure_and_recovery_is_free(ui):
    prepare_student(ui);original=ui.ai.draft.side_effect
    def break_save(*args,**kwargs):
        result=original(*args,**kwargs);ui.env.b.fail=True;return result
    ui.ai.draft.side_effect=break_save
    pick(ui.app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not ui.app.exception
    assert pick(ui.app.text_area,'교과세특 작성 내용').value=='좌표 관계를 확인함.'
    assert pick(ui.app.button,'✨ AI 교과세특 초안 생성').disabled
    pick(ui.app.text_area,'교과세특 작성 내용').set_value('교사가 검토한 수정 문장').run()
    ui.env.b.fail=False
    pick(ui.app.button,'생성된 초안 저장 다시 확인 · AI 호출 없음').click().run()
    assert not ui.app.exception and not ui.app.error
    assert ui.ai.draft.call_count==1
    assert pick(ui.app.text_area,'교과세특 작성 내용').value=='교사가 검토한 수정 문장'
    pick(ui.app.button,'초안 저장').click().run()
    assert not ui.app.exception and not ui.app.error
    assert ui.s.load_term(SID,'공통수학2',2026,2)['data']['current']['text']=='교사가 검토한 수정 문장'
    assert ui.ai.draft.call_count==1


def test_resume_only_never_starts_a_new_request(ui):
    workspace=ui.s.load_term(SID,'공통수학2',2026,2)
    from test_semester_records import reviews
    with pytest.raises(ArchiveError,match='저장할 생성 결과'):
        ui.s.generate(workspace,reviews(workspace),None,'never_called',consent=True,resume_only=True)


def test_ai_error_is_not_hidden_by_failed_failure_receipt(ui):
    prepare_student(ui)
    def fail(*args,**kwargs):
        ui.env.b.fail=True
        raise ArchiveError('AI 요청 실패(401). API 키를 확인하세요.')
    ui.ai.draft.side_effect=fail
    pick(ui.app.button,'✨ AI 교과세특 초안 생성').click().run()
    assert not ui.app.exception and any('401' in e.value for e in ui.app.error)
    assert ui.ai.draft.call_count==1 and ui.s.pending()
