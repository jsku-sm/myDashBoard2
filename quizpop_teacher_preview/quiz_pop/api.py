"""Fixed QuizPop requests. API credentials stay on the Streamlit server."""
from copy import deepcopy
from collections.abc import Mapping
import json
import math
import os
from pathlib import Path
import uuid
import requests

PROMPTS = json.loads(Path(__file__).with_name('prompts.json').read_text(encoding='utf-8'))
ENDPOINT = 'https://api.openai.com/v1/responses'


def config(values, environ=None):
    """Resolve the dashboard's existing OpenAI settings without exposing keys.

    Reuse a model from the same section as its credential. A model-only
    quiz_ai setting may deliberately override that model. Credentials for
    another provider must never be sent to the official OpenAI endpoint.
    """
    values = values if isinstance(values, Mapping) else {}
    environ = os.environ if environ is None else environ
    def group(name):
        value = values.get(name, {})
        return value if isinstance(value, Mapping) else {}
    def first(section, *names):
        return next((str(section[n]).strip() for n in names if section.get(n) and str(section[n]).strip()), '')
    def official(section):
        base = first(section, 'base_url', 'OPENAI_BASE_URL', 'openai_base_url')
        return not base or base.rstrip('/') == 'https://api.openai.com/v1'
    own = group('quiz_ai')
    sources = [('[quiz_ai]', own), ('[openai]', group('openai')),
               ('최상위 Secrets', values), ('서버 환경변수', environ),
               ('[school_record_ai]', group('school_record_ai')), ('[snorkl]', group('snorkl'))]
    key = source_model = key_source = ''
    skipped_provider = False
    for label, section in sources:
        candidate = first(section, 'api_key', 'openai_api_key', 'OPENAI_API_KEY')
        if candidate and not official(section):
            skipped_provider = True
            continue
        if candidate:
            key, key_source = candidate, label
            source_model = first(section, 'model', 'openai_model', 'OPENAI_MODEL')
            break
    model = first(own, 'model', 'openai_model', 'OPENAI_MODEL') or source_model or first(values, 'OPENAI_MODEL') or first(environ, 'OPENAI_MODEL') or 'gpt-6-luna'
    allowed = str(own.get('enabled', True)).strip().lower() not in ('false', '0', 'off', 'no')
    reason = ''
    if not official(own): reason = '퀴즈팝의 [quiz_ai] base_url은 공식 OpenAI 주소를 사용해야 합니다. [QUIZ_PROVIDER]'
    elif not allowed: reason = '퀴즈 AI 사용이 꺼져 있습니다. [quiz_ai] enabled = true 설정을 확인해 주세요. [QUIZ_DISABLED]'
    elif not key:
        reason = ('공식 OpenAI용 API 키가 필요합니다. 다른 서비스의 키는 재사용하지 않습니다. [QUIZ_PROVIDER]'
                  if skipped_provider else '퀴즈용 API 키를 찾지 못했습니다. Streamlit Secrets에 OpenAI API 키를 설정해 주세요. [QUIZ_KEY_MISSING]')
    return {'api_key': key, 'model': model, 'enabled': not bool(reason), 'key_source': key_source, 'reason': reason}


def provider_error(response):
    """Only fixed diagnostics leave the server; provider messages may contain secrets."""
    try:
        data = response.json()
        error = data.get('error', {}) if isinstance(data, dict) else {}
        code = error.get('code', '') if isinstance(error, dict) else ''
    except (ValueError, AttributeError): code = ''
    status = response.status_code
    if status == 401: return 'AI 키 인증에 실패했습니다. Streamlit Secrets의 API 키를 확인해 주세요. [QUIZ_AUTH]'
    if status == 403: return '이 API 키로 AI 모델을 사용할 권한이 없습니다. 모델과 프로젝트 권한을 확인해 주세요. [QUIZ_PERMISSION]'
    if status == 404 or code == 'model_not_found': return '설정한 AI 모델을 찾거나 사용할 수 없습니다. [quiz_ai] model을 확인해 주세요. [QUIZ_MODEL]'
    if code in ('insufficient_quota', 'billing_hard_limit_reached', 'billing_not_active'):
        return 'OpenAI API 잔액 또는 프로젝트 사용 한도를 확인해 주세요. [QUIZ_QUOTA]'
    if status == 429: return 'AI 요청이 일시적으로 많습니다. 잠시 뒤 한 번만 다시 눌러 주세요. [QUIZ_RATE_LIMIT]'
    if status == 400:
        return '설정한 AI 모델이 퀴즈 요청 형식을 받지 못했습니다. Responses API와 구조화 출력을 지원하는 모델을 설정해 주세요. [QUIZ_REQUEST]'
    return 'AI 서비스가 응답하지 못했습니다. 잠시 뒤 다시 시도해 주세요. [QUIZ_PROVIDER_ERROR]'


def text(value, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('입력한 학습 내용의 길이와 형식을 확인해 주세요.')
    return value.strip()


def standards(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 30:
        raise ValueError('성취기준을 1~30개 선택해 주세요.')
    if any(not isinstance(x, dict) for x in value): raise ValueError('성취기준 형식을 확인해 주세요.')
    return [{'id': text(x.get('id'), 80), 'text': text(x.get('text'), 1500)} for x in value]


def settings(value):
    if not isinstance(value, dict): raise ValueError('학습 설정을 확인해 주세요.')
    if value.get('course') not in ('공통수학1', '공통수학2'): raise ValueError('과목을 확인해 주세요.')
    if type(value.get('count')) is not int or value['count'] not in (3, 5, 7): raise ValueError('문항 수를 확인해 주세요.')
    if type(value.get('startStage')) is not int or not 0 <= value['startStage'] <= 4: raise ValueError('시작 단계를 확인해 주세요.')
    result = {k: value[k] for k in ('course', 'count', 'startStage')}
    result.update(unit=text(value.get('unit', ''), 100, empty=True), range=text(value.get('range', ''), 700, empty=True), standards=standards(value.get('standards')))
    if not (result['unit'] or result['range']) or not result['standards']: raise ValueError('단원과 성취기준을 입력해 주세요.')
    return result


def validate_schema(value, schema):
    """Validate the source app's closed JSON schema before storing/rendering it."""
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try: validate_schema(value, option); return
            except ValueError: pass
        raise ValueError('문항의 시각 자료 형식을 확인하지 못했어요.')
    kind = schema.get('type')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str),
             'integer': type(value) is int, 'number': type(value) in (int, float) and math.isfinite(value), 'null': value is None}.get(kind, False)
    if not valid: raise ValueError('문항 데이터의 형식을 확인하지 못했어요.')
    if 'enum' in schema and value not in schema['enum']: raise ValueError('문항 데이터의 범위를 확인해 주세요.')
    if kind == 'object':
        if any(k not in value for k in schema.get('required', [])) or (schema.get('additionalProperties') is False and set(value) - set(schema.get('properties', {}))):
            raise ValueError('문항 데이터의 항목을 확인하지 못했어요.')
        for k, v in value.items(): validate_schema(v, schema['properties'][k])
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 100): raise ValueError('문항 데이터의 개수를 확인해 주세요.')
        for item in value: validate_schema(item, schema['items'])
    if kind == 'string' and len(value) > 5000: raise ValueError('문항 내용이 너무 길어요.')
    if kind in ('integer', 'number') and not schema.get('minimum', -1e9) <= value <= schema.get('maximum', 1e9):
        raise ValueError('문항 수치의 범위를 확인해 주세요.')


def request_body(kind, payload, model):
    if not isinstance(payload, dict): raise ValueError('요청 내용을 확인해 주세요.')
    body = {'model': model, 'store': False}
    if kind == 'generate':
        chosen = settings(payload.get('settings'))
        names = [s['name'] for s in PROMPTS['stages']]
        if payload.get('difficulty') not in names: raise ValueError('난이도를 확인해 주세요.')
        stage = names.index(payload['difficulty'])
        previous = payload.get('avoidRepeating', [])
        if not isinstance(previous, list) or len(previous) > 120: raise ValueError('출제 이력의 크기를 확인해 주세요.')
        previous = [text(p, 3000) for p in previous]
        data = dict(settings=chosen, difficulty=names[stage], questionCount=chosen['count'], variationId=uuid.uuid4().hex, avoidRepeating=previous)
        body.update(instructions=PROMPTS['generate'][stage], max_output_tokens=10000,
                    input=[{'role':'user', 'content':json.dumps(data, ensure_ascii=False)}],
                    text={'format':{'type':'json_schema', 'name':'math_quiz', 'strict':True, 'schema':deepcopy(PROMPTS['schemas'][str(chosen['count'])])}})
    elif kind == 'guide':
        context = payload.get('context', {})
        if not isinstance(context, dict): raise ValueError('학습 맥락을 확인해 주세요.')
        safe = {k: text(context.get(k, ''), limit, empty=True) for k, limit in [('unit',100),('range',700),('concept',1000),('question',5000)]}
        safe['standards'] = standards(context.get('standards'))
        if context.get('visual') is not None:
            visual_schema = PROMPTS['schemas']['3']['properties']['questions']['items']['properties']['visual']
            validate_schema(context['visual'], visual_schema)
            safe['visual'] = context['visual']
        history = payload.get('history', [])
        if not isinstance(history, list) or len(history) > 8: raise ValueError('대화 이력의 크기를 확인해 주세요.')
        messages = []
        for m in history:
            if not isinstance(m, dict) or m.get('role') not in ('user', 'assistant'): raise ValueError('대화 형식을 확인해 주세요.')
            messages.append({'role':m['role'], 'content':text(m.get('content'), 5000)})
        # Learning context is data, never a client-supplied developer instruction.
        body.update(instructions=PROMPTS['guide'], max_output_tokens=4096,
                    input=[{'role':'user', 'content':'현재 학습 맥락(자료): '+json.dumps(safe,ensure_ascii=False)}, *messages,
                           {'role':'user', 'content':text(payload.get('text'),1200)}])
    else: raise ValueError('지원하지 않는 퀴즈 요청입니다.')
    return body


def call(kind, payload, cfg, transport=None):
    if not cfg['enabled']: raise ValueError(cfg.get('reason') or 'AI 연결이 아직 준비되지 않았어요. 선생님에게 알려 주세요. [QUIZ_KEY_MISSING]')
    body = request_body(kind, payload, cfg['model'])
    transport = transport or requests
    try:
        response = transport.post(ENDPOINT, headers={'Authorization':'Bearer '+cfg['api_key'], 'Content-Type':'application/json'}, json=body, timeout=(10, 150))
        if response.status_code != 200:
            raise ValueError(provider_error(response))
        result = response.json()
    except requests.Timeout:
        raise ValueError('AI 문항 생성 시간이 초과되었습니다. 문항 수를 3개로 줄여 다시 시도해 주세요. [QUIZ_TIMEOUT]') from None
    except requests.RequestException:
        raise ValueError('AI 서버와 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요. [QUIZ_NETWORK]') from None
    except (TypeError, json.JSONDecodeError):
        raise ValueError('AI 응답을 읽지 못했어요. 다시 시도해 주세요.') from None
    if not isinstance(result, dict): raise ValueError('AI 응답 형식을 읽지 못했습니다. [QUIZ_RESPONSE]')
    if result.get('status') != 'completed': raise ValueError('AI 응답이 끝나기 전에 출력 한도에 도달했거나 처리가 중단되었습니다. 문항 수를 3개로 줄여 다시 시도해 주세요. [QUIZ_INCOMPLETE]')
    texts = [p.get('text','') for m in result.get('output',[]) if m.get('type')=='message' and m.get('role')=='assistant'
             for p in m.get('content',[]) if p.get('type')=='output_text']
    answer = '\n\n'.join(texts).strip()
    if not answer: raise ValueError('표시할 AI 답변이 없어요. 질문을 바꿔 다시 시도해 주세요.')
    if kind == 'generate':
        try:
            quiz = json.loads(answer)
            validate_schema(quiz, body['text']['format']['schema'])
            ids = {s['id'] for s in payload['settings']['standards']}
            if any(q['standardId'] not in ids or len(set(q['options'])) != 5 for q in quiz['questions']): raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('문항 구성을 확인하지 못했어요. 같은 설정으로 다시 생성해 주세요.') from None
    return {'text':answer}
