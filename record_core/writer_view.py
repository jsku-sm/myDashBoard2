"""Teacher-facing semester writer. No hidden AI button; editable single/bulk views."""
from __future__ import annotations
import copy
import hashlib
import uuid
from datetime import date
import pandas as pd
import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS
from .archive import ArchiveError, EXPECTED_REPO, fingerprint
from .ai import AIConfig, RecordAI
from .service import byte_count
from .semester import SemesterRecords, RecordPending, RecordConflict, term_dates
from .view import values, _files

CSS = '''<style>
.record-writer-steps{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 18px}.record-writer-steps span{padding:7px 13px;border-radius:20px;background:#f5f1e8;color:#756c57;font-size:.82rem;border:1px solid #e3dfd4}
.st-key-school_record_writer button[kind="primary"]{background:#52715c;border-color:#52715c;border-radius:12px;min-height:44px}
.st-key-school_record_writer textarea{line-height:1.9!important;font-size:1rem!important}
.st-key-school_record_writer [data-testid="stExpander"]{border-color:#dce3d8;border-radius:14px}
.st-key-school_record_writer [data-testid="stTabs"] button{font-weight:650}
</style>'''


def _error(exc):
    st.error(str(exc) if isinstance(exc, (ArchiveError, PermissionError, db.SetupError)) else '처리 결과를 확인하지 못했어요. 입력 내용은 유지했습니다. 저장소 연결을 확인해 주세요.')


def _prefix(ctx, sid, buf):
    return ctx['key'] + '_' + hashlib.sha256(sid.encode()).hexdigest()[:12] + '_' + str(buf['epoch']) + '_'


def _install(ctx, sid, workspace, preserve_backup=True):
    old = ctx['buffers'].get(sid, {})
    current = workspace['data'].get('current') or {}
    backups = old.get('backups', [])
    if preserve_backup and old.get('text', '').strip() and old.get('text') != current.get('text', ''):
        backups = (backups + [old['text']])[-5:]
    table_text = ctx['table_edits'].get(sid, {}).get('text', '')
    if preserve_backup and table_text.strip() and table_text != current.get('text', '') and table_text not in backups:
        backups = (backups + [table_text])[-5:]
    ctx['buffers'][sid] = dict(workspace=workspace, text=current.get('text', ''), reviews=copy.deepcopy(current.get('reviews', [])),
                              ai_draft=copy.deepcopy(current.get('ai_draft')), analyses=copy.deepcopy(current.get('analyses', [])),
                              review_note=current.get('review_note', ''), epoch=old.get('epoch', 0) + 1, backups=backups,
                              candidate=old.get('candidate'))
    ctx['table_epoch'] += 1
    ctx['table_edits'].pop(sid, None)
    return ctx['buffers'][sid]


def _capture(ctx, sid):
    b = ctx['buffers'][sid]; p = _prefix(ctx, sid, b); data = b['workspace']['data']
    known = {e['id']: e for e in data['evidence'] if e['eligible']}
    old = {r['evidence_id']: r for r in b['reviews']}
    selected = st.session_state.get(p + 'selected', [k for k in old if k in known])
    reviews = []
    for eid in selected:
        if eid not in known:
            continue
        r = old.get(eid, {}); item = known[eid]
        unchanged = r.get('evidence_hash', item['evidence_hash']) == item['evidence_hash']
        reviews.append(dict(evidence_id=eid, evidence_hash=item['evidence_hash'], subject=data['subject'],
                            fact=st.session_state.get(p + eid + '_fact', r.get('fact', '')),
                            context=st.session_state.get(p + eid + '_context', r.get('context', '확인 필요')),
                            teacher_confirmed=st.session_state.get(p + eid + '_confirm', r.get('teacher_confirmed', False) and unchanged)))
    b.update(reviews=reviews, text=st.session_state.get(p + 'text', b['text']),
             review_note=st.session_state.get(p + 'review_note', b['review_note']))
    if p + 'analyses' in st.session_state:
        b['analyses'] = st.session_state[p + 'analyses']
    return b


def _load(service, ctx, student, year, term, subject, start, end, sync=False):
    warning = ''
    # Confirm source updates/migration before reading encrypted evidence. Loading
    # never calls AI and failure leaves the previous writing buffer untouched.
    service.backend.flush()
    if sync:
        service.sync_sources(student)
        # A separate assessment store error must not hide already saved notes.
        try:
            from think_app.embedded import get_store
            from think_app.integration import load_embedded_settings
            service.sync_sources(student, get_store(load_embedded_settings()))
        except Exception:
            warning = '수다노트 등 기본 자료는 불러왔지만 수행평가 별도 저장소의 동기화는 확인하지 못했어요. 기존 자료를 표시합니다.'
    workspace = service.load_term(student, subject, year, term, start, end)
    _install(ctx, student, workspace)
    return warning


def _readiness(service, b, config, target):
    if not config.enabled:
        return False, 'AI 설정에서 enabled=true가 필요해요.'
    if not config.api_key or not config.model:
        return False, 'AI API 키와 모델 설정을 확인해 주세요.'
    try:
        preview = service.input_preview(b['workspace'], b['reviews'], target)
    except (ArchiveError, PermissionError) as exc:
        return False, str(exc)
    return True, preview


def _save(service, ctx, sid, settings, final=False, confirmed=False):
    b = _capture(ctx, sid)
    payload = service.save_term(b['workspace'], b['reviews'], b['text'], b['ai_draft'], b['analyses'],
                                final=final, confirmed=confirmed, review_note=b['review_note'], **settings)
    _install(ctx, sid, service.with_saved(b['workspace'], payload), preserve_backup=False)
    return payload


def _batch_fingerprint(b):
    return fingerprint([b['workspace']['data']['revision'], b['reviews'], b['text'], b['review_note'], b['ai_draft'], b['analyses']])


def _generate(service, ctx, sid, config, settings, token, item=None):
    b = _capture(ctx, sid)
    edit = ctx['table_edits'].get(sid)
    if edit and edit.get('dirty') and (edit['text'] != b['text'] or edit['review_note'] != b['review_note']):
        raise RecordConflict('전체 편집 표에 저장하지 않은 수정 내용이 있습니다. 먼저 표의 수정 내용을 저장한 뒤 생성해 주세요.')
    if item is not None and item['input_hash'] != _batch_fingerprint(b):
        raise RecordConflict('일괄 생성을 시작한 뒤 근거 또는 작성 내용이 바뀌었습니다. 해당 학생을 다시 확인해 주세요.')
    current = b['workspace']['data'].get('current') or {}
    # Preserve unsaved teacher prose before replacing the editor with a new draft.
    if b['text'].strip() and b['text'] != current.get('text', ''):
        payload = service.save_term(b['workspace'], b['reviews'], b['text'], b['ai_draft'], b['analyses'],
                                    review_note=b['review_note'], **settings)
        b['workspace'] = service.with_saved(b['workspace'], payload)
        if item is not None:
            item['input_hash'] = _batch_fingerprint(b)
    payload = service.generate(b['workspace'], b['reviews'], RecordAI(config), token, consent=True, **settings)
    _install(ctx, sid, service.with_saved(b['workspace'], payload), preserve_backup=False)


def render():
    user = st.session_state.get('user') or {}
    if user.get('role') != 'teacher':
        st.error('생기부 작성기는 교사만 사용할 수 있어요.'); return
    with st.container(key='school_record_writer'):
        st.markdown(CSS, unsafe_allow_html=True)
        st.markdown('<div class="record-writer-steps"><span>01 자료 확인</span><span>02 AI 초안</span><span>03 교사 수정</span><span>04 저장 · CSV</span></div>', unsafe_allow_html=True)
        try:
            backend = db._ready_backend()
            secrets = values()
            legacy = str(secrets.get('app', {}).get('teacher_id', secrets.get('TEACHER_ID', 'teacher')))
            service = SemesterRecords(backend, lambda: (st.session_state.get('user') or {}).get('id'), legacy)
            actor = service.actor()
        except Exception as exc:
            _error(exc)
            st.button('✨ AI 교과세특 초안 생성', disabled=True, key='rw_unavailable_generate')
            st.caption('학생 자료 저장소와 암호화키 연결을 먼저 확인해 주세요. 학생 자료나 작성 중 글을 임시 파일로 옮기지 않습니다.')
            return
        config = AIConfig.from_values(secrets)
        root = 'rw_' + hashlib.sha256(actor['id'].encode()).hexdigest()[:12]
        t = db.now().date(); academic = t.year if t.month >= 3 else t.year - 1
        a, b, c, d = st.columns([1, 1, 1.3, 1.2])
        year = int(a.number_input('학년도', min_value=2000, max_value=2099, value=academic, step=1, key=root+'_year'))
        term = b.selectbox('학기', [1, 2], index=0 if 3 <= t.month <= 8 else 1, format_func=lambda n:f'{n}학기', key=root+'_term')
        subject = c.selectbox('과목', SUBJECTS, key=root+'_subject')
        cls = d.selectbox('학급', list(CLASSES) + ['전체 학급'], key=root+'_class')
        with st.expander('자료 기간 · 초안 분량 · 교사 제공 작성 기준', expanded=False):
            period = st.date_input('근거 자료를 불러올 기간', value=term_dates(year, term), format='YYYY-MM-DD', key=f'{root}_range_{year}_{term}')
            st.caption('기본값: 1학기 3~8월, 2학기 9~다음 해 2월. 학교 일정에 맞게 자료 기간을 조정하세요. 저장 구분은 학년도·학기·과목으로 유지됩니다.')
            c1, c2 = st.columns(2)
            target = int(c1.number_input('AI 목표 글자 수', min_value=100, max_value=1000, value=400, step=50, key=root+'_target'))
            limit = int(c2.number_input('완성본 저장 분량 기준(참고 바이트)', min_value=100, max_value=6000, value=1500, step=100, key=root+'_limit'))
            guidance = st.text_area('교사 제공 작성 기준 · 기재 지침 발췌(선택)', max_chars=16000, height=130, key=root+'_guidance',
                                    placeholder='추후 제공할 기재 지침의 관련 내용을 여기에 입력할 수 있어요.')
            st.caption('공식 기재 지침 파일은 아직 반영되지 않았습니다. 위 분량은 앱의 조정 가능한 작업 기준이며, 공식 입력 한도를 판정하는 값이 아닙니다.')
        if len(period) != 2:
            st.info('자료 시작일과 종료일을 모두 선택해 주세요.'); return
        start, end = period
        key = root + '_' + hashlib.sha256(f'{year}|{term}|{subject}|{start}|{end}'.encode()).hexdigest()[:16]
        ctx = st.session_state.setdefault(key, dict(key=key, buffers={}, table_epoch=0, table_edits={}, job=None))
        settings = dict(target_chars=target, byte_limit=limit, guidance=guidance)
        roster = sorted([r for r in backend.read('users') if r.get('role') == 'student' and (cls == '전체 학급' or r.get('class') == cls)], key=lambda r:r['id'])
        names = {r['id']:f"{r.get('class','')} · {r['id']} · {r.get('name','')}" for r in roster}
        if service.pending():
            st.warning('저장 확인이 필요한 변경이 있습니다. AI 생성과 추가 저장 전에 아래 버튼으로 확인하세요.')
        if st.button('저장 다시 확인 · AI 호출 없음', key=root+'_retry'):
            try:
                service.retry(); st.success('저장을 확인했습니다. 최신 글을 다시 불러올 수 있어요.')
            except Exception as exc: _error(exc)
        notice = ctx.pop('notice', None)
        if notice: st.success(notice)
        if not roster:
            st.info('이 학급에 등록된 학생이 없습니다.'); st.button('✨ AI 교과세특 초안 생성', disabled=True, key=root+'_empty'); return
        single, whole, batch, help_tab = st.tabs(['학생별 작성', '전체 불러오기 · 수정 · CSV', '선택 학생 AI 일괄 생성', '저장·AI 연결 안내'])
        with single:
            sid = st.selectbox('학생 선택', list(names), format_func=names.get, key=key+'_student_'+cls)
            if sid not in ctx['buffers']:
                try: _load(service, ctx, sid, year, term, subject, start, end)
                except Exception as exc:
                    _error(exc); st.button('✨ AI 교과세특 초안 생성', disabled=True, key=key+'_load_failed')
            if sid in ctx['buffers']:
                _student(service, ctx, sid, config, settings, year, term, subject, start, end)
        with whole:
            _whole(service, ctx, names, settings, year, term, subject, start, end)
        with batch:
            _batch_controls(service, ctx, names, config, settings)
        with help_tab:
            st.markdown('**관찰기록:** `data/observations/` · **상점·벌점:** `data/points/` · **생기부 작성 목록:** `data/school_records/` — 각 폴더 안에서 학생별로 나누어 저장합니다.')
            st.markdown('**수다노트 원본:** `jsku-sm/class-dashboard-data/data/sudanotes/<학번>.csv`')
            st.markdown('**작성 초안·완성본:** 같은 저장소의 학생별 암호화 자료함에 학년도·학기·과목별로 저장합니다. 원본 자료와 이전 수정 이력을 보존합니다.')
            st.markdown('**불러오기와 CSV:** 자료를 불러오거나 CSV를 내려받는 동작은 AI를 호출하지 않습니다. CSV는 내려받는 별도 파일이며 학생 자료를 공개하지 않습니다.')
            st.markdown('**일괄 생성:** 학생별로 먼저 근거를 선택·확인합니다. 선택한 학생을 한 명씩 처리하고, 실패 시 나머지 작업을 일시 정지합니다. 이미 완료한 학생은 다시 호출하지 않습니다.')
            st.code('[school_record_ai]\nenabled = true\napi_key = "기존 OpenAI API 키"\nmodel = "사용 가능한 모델 이름"', language='toml')
            st.caption(f'현재 AI 설정: {"사용 가능" if config.enabled and config.api_key and config.model else "설정 확인 필요"} · API 키는 화면에 표시하지 않습니다. 기존 학생 자료함 암호화키는 유지하세요.')
        _batch_step(service, ctx, config)


def _student(service, ctx, sid, config, settings, year, term, subject, start, end):
    b = _capture(ctx, sid); p = _prefix(ctx, sid, b); w = b['workspace']; data = w['data']
    current = data.get('current') or {}
    st.caption(f"{year}학년도 {term}학기 · {subject} · {'완성본' if current.get('kind')=='final' else '초안' if current else '작성 전'} · 저장 버전 {data['revision']}")
    if st.button('📂 학습 자료 다시 불러오기 · 저장본 열기', key=p+'reload', help='입력 중인 글은 이전 수정 내용에 남겨 둡니다.'):
        try:
            with st.spinner('수다노트와 학습 기록을 확인하고 있어요.'):
                warning = _load(service, ctx, sid, year, term, subject, start, end, sync=True)
            ctx['notice'] = warning or '학습 자료와 저장본을 불러왔습니다.'; st.rerun()
        except Exception as exc: _error(exc)
    ready, preview = _readiness(service, b, config, settings['target_chars'])
    consent = st.checkbox('선택한 근거와 전송 내용을 확인했으며 이 학생의 AI 초안 생성을 진행합니다.', key=p+'consent')
    replace = st.checkbox('이미 작성한 글도 보관한 뒤 새 초안으로 바꾸기', key=p+'replace') if b['text'].strip() else True
    if st.button('✨ AI 교과세특 초안 생성', type='primary', key=p+'generate', disabled=not(ready and consent and replace) or service.pending()):
        try:
            with st.spinner('확인한 근거로 초안을 작성하고 저장합니다.'):
                _generate(service, ctx, sid, config, settings, uuid.uuid4().hex)
            ctx['notice'] = 'AI 초안을 저장했습니다. 아래 수정란에서 교사의 문장으로 다듬어 주세요.'; st.rerun()
        except Exception as exc:
            if getattr(exc, 'completed_draft', None): b['candidate'] = exc.completed_draft
            _error(exc)
    if not ready: st.info('생성 준비: ' + preview)
    elif not consent: st.caption('근거가 준비되었습니다. 위 확인 항목을 체크하면 AI 생성 버튼을 사용할 수 있어요.')
    with st.expander('AI에 보낼 근거 미리보기', expanded=False):
        st.text(preview)
        if settings['guidance']: st.text('교사 제공 작성 기준:\n' + settings['guidance'])
    _evidence(service, ctx, sid, p)
    # Text editor always exists, including students with no submitted evidence.
    st.markdown('#### 교사 작성·수정')
    b['text'] = st.text_area('교과세특 작성 내용', value=b['text'], height=240, key=p+'text')
    st.caption(f"{len(b['text'])}자 · UTF-8/CRLF 참고 {byte_count(b['text'])}B / 설정 기준 {settings['byte_limit']}B")
    b['review_note'] = st.text_input('교사 확인·수정 메모', value=b['review_note'], key=p+'review_note', placeholder='예: 학생 풀이와 대조하고 개념 설명을 수정함.')
    verified = st.checkbox('원본과 기재 기준을 확인하고 교사가 직접 작성 또는 수정한 완성본입니다.', key=p+'verified')
    a, c = st.columns(2)
    if a.button('초안 저장', key=p+'save', width='stretch', disabled=service.pending()):
        try: _save(service, ctx, sid, settings); ctx['notice']='작성 중 내용을 저장했습니다.'; st.rerun()
        except Exception as exc: _error(exc)
    if c.button('완성본 저장', key=p+'final', type='primary', width='stretch', disabled=not verified or service.pending()):
        try: _save(service, ctx, sid, settings, True, True); ctx['notice']='교사 확인 완성본을 저장했습니다. 다시 열어 수정할 수 있어요.'; st.rerun()
        except Exception as exc: _error(exc)
    if current:
        st.download_button('이 학생 저장본 CSV', service.export_csv([w]), file_name=f'교과세특_{year}_{term}학기_{subject}_{sid}.csv', mime='text/csv', key=p+'csv')
    if b['ai_draft']:
        with st.expander('AI 원문 · 문장별 근거 · 직접 작성 전환'):
            st.text(b['ai_draft'].get('text', ''))
            for s in b['ai_draft'].get('sentences', []): st.write({'문장':s['text'],'근거':s['evidence_ids']})
            for caution in b['ai_draft'].get('cautions', []): st.info(caution)
            if st.button('AI 연결 해제 · 교사 직접 작성', key=p+'manual'):
                b['ai_draft']=None; st.rerun()
    if b.get('candidate'):
        with st.expander('저장 확인이 필요한 AI 생성 결과', expanded=True):
            st.text(b['candidate']['text'])
            st.caption('기존 수정 내용과 충돌하거나 저장이 중단된 결과입니다. 최신 저장본을 확인한 뒤 필요한 내용을 옮겨 적을 수 있어요.')
    if b['backups']:
        with st.expander('다시 불러오기 전 수정 중이던 내용'):
            for text in b['backups'][::-1]: st.text(text)
    with st.expander('이전 기간·학기의 저장 문장 참고'):
        if st.button('이전 저장 문장 조회', key=p+'legacy'):
            ctx.setdefault('previous', {})[sid] = service.previous_texts(w)
        for i, old in enumerate(ctx.get('previous', {}).get(sid, [])):
            st.caption(old.get('period', '') + ' · ' + old.get('updated_at', ''))
            st.text(old.get('text', ''))
            if st.button('이 문장을 현재 초안으로 가져오기', key=p+'import_'+str(i)):
                if b['text']: b['backups']=(b['backups']+[b['text']])[-5:]
                b.update(text=old.get('text', ''), ai_draft=None, epoch=b['epoch']+1); st.rerun()


def _evidence(service, ctx, sid, p):
    b=ctx['buffers'][sid]; data=b['workspace']['data']; items={e['id']:e for e in data['evidence'] if e['eligible']}
    st.markdown('#### 사용할 자료와 교사 확인 근거')
    counts={label:sum(e['label']==label for e in items.values()) for label in dict.fromkeys(e['label'] for e in items.values())}
    st.caption(' · '.join(f'{k} {v}건' for k,v in counts.items()) or '선택 기간에 제출된 자료가 없습니다. 직접 작성하거나 교사 관찰을 추가할 수 있어요.')
    points = [e for e in data['evidence'] if e['category'] == 'points']
    with st.expander(f'상점·벌점 확인 · {len(points)}건 (조회 전용)'):
        st.caption('상점·벌점은 별도로 확인하며 AI 교과세특 근거에 자동으로 넣지 않습니다.')
        if points:
            st.dataframe(pd.DataFrame([{'일자': e['date'], '구분·점수': e['title'], '사유': e['text']} for e in points]), hide_index=True, width='stretch')
        else:
            st.caption('선택 기간의 상점·벌점 기록이 없습니다.')
    if any(e['category'] == 'observations' and not e['subject'] for e in items.values()):
        st.caption('과목 미지정 관찰기록은 이전 기록입니다. 선택한 과목의 수업에서 확인한 내용인지 검토한 뒤 근거로 선택하세요.')
    with st.expander('교사가 직접 관찰한 수업 내용 추가'):
        observed=st.date_input('관찰일', value=min(db.now().date(),date.fromisoformat(data['end'])), key=p+'observed')
        fact=st.text_area('관찰한 사실', key=p+'new_observation', placeholder='수업에서 실제로 확인한 개념 설명, 풀이 수정, 질문 등을 적어 주세요.')
        if st.button('관찰 근거 저장·불러오기', key=p+'add_observation', disabled=service.pending()):
            try:
                fresh=service.add_observation(b['workspace'],fact,observed)
                if fresh['data']['revision'] != b['workspace']['data']['revision']:
                    raise RecordConflict('관찰은 저장했지만 다른 화면에서 글이 수정되었습니다. 현재 입력은 유지했습니다. 최신 저장본을 다시 불러와 주세요.')
                # Reload evidence without discarding the writing buffer.
                b['workspace']=fresh; b['epoch']+=1; st.rerun()
            except Exception as exc: _error(exc)
    old={r['evidence_id']:r for r in b['reviews']}
    selected=st.multiselect('활용할 자료 선택 · 수다노트/관찰/수행평가/퀴즈/게임',list(items),default=[x for x in old if x in items],
                            format_func=lambda k:f"{items[k]['date']} · {items[k]['label']} · {items[k]['title']}" + (' · 과목 미지정' if items[k]['category']=='observations' and not items[k]['subject'] else ''),max_selections=30,key=p+'selected')
    for eid in selected:
        e=items[eid]; r=old.get(eid,{})
        with st.expander(f"{e['label']} · {e['date']} · {e['title']}",expanded=not r.get('teacher_confirmed',False)):
            st.caption(e['origin']); st.text(e['text'])
            st.text_area('교사가 확인한 구체적 사실', value=r.get('fact',''), key=p+eid+'_fact', height=100)
            context=st.selectbox('활동 맥락',['확인 필요','정규 교과수업','방과후·자유 학습','기타'],
                                 index=['확인 필요','정규 교과수업','방과후·자유 학습','기타'].index(r.get('context','확인 필요')),key=p+eid+'_context')
            unchanged=r.get('evidence_hash',e['evidence_hash'])==e['evidence_hash']
            st.checkbox('선택 과목의 정규 수업에서 확인한 사실입니다.',value=r.get('teacher_confirmed',False) and unchanged,key=p+eid+'_confirm')
            for i,f in enumerate(e['attachments']):
                if st.button('원본 첨부 열기 · '+f['name'],key=p+eid+'_file_'+str(i)):
                    st.session_state[p+eid+'_raw_'+str(i)]=service.file(b['workspace'],eid,i)
                raw=st.session_state.get(p+eid+'_raw_'+str(i))
                if raw: st.download_button('첨부 내려받기',raw,file_name=f['name'],mime=f['mime'],key=p+eid+'_download_'+str(i))
    _capture(ctx,sid)
    if selected:
        with st.expander('선택 자료의 PDF·손글씨 분석(선택)'):
            st.session_state.setdefault(p+'analyses',b['analyses'])
            _files(service,b['workspace'],p,[items[x] for x in selected],AIConfig.from_values(values()))
            b['analyses']=st.session_state.get(p+'analyses',[])


def _whole(service, ctx, names, settings, year, term, subject, start, end):
    st.caption('현재 선택한 학급(또는 전체 학급)의 초안·완성본을 함께 불러옵니다. 표의 문장은 직접 수정할 수 있습니다.')
    if st.button('📂 전체 불러오기 · 저장된 초안과 완성본',key=ctx['key']+'_all_load',type='primary'):
        failures=[];bar=st.progress(0)
        for i,sid in enumerate(names):
            try:
                _load(service,ctx,sid,year,term,subject,start,end)
            except Exception: failures.append(names[sid])
            bar.progress((i+1)/len(names))
        ctx['notice']=f'{len(names)-len(failures)}명 기록을 불러왔습니다.'+(' 불러오기 실패: '+', '.join(failures) if failures else '')
        st.rerun()
    loaded=[sid for sid in names if sid in ctx['buffers']]
    if not loaded:
        st.info('전체 불러오기를 누르면 편집 표가 열립니다.');return
    selected=st.multiselect('표에서 편집할 학생',loaded,default=loaded,format_func=names.get,key=ctx['key']+'_table_students_'+str(ctx['table_epoch']))
    rows=[]
    for sid in selected:
        b=_capture(ctx,sid); d=b['workspace']['data']; current=d.get('current') or {}; edit=ctx['table_edits'].get(sid,{})
        if not edit.get('dirty') and not edit.get('final'):edit={}
        rows.append({'학번':sid,'학생':names[sid],'상태':'완성본' if current.get('kind')=='final' else '초안' if current else '작성 전',
                     '교과세특':edit.get('text',b['text']),'교사 확인·수정 메모':edit.get('review_note',b['review_note']),
                     '완성본으로 저장':edit.get('final',False)})
    if not rows:return
    table_key=ctx['key']+'_grid_'+str(ctx['table_epoch'])+'_'+fingerprint(rows)[:10]
    frame=st.data_editor(pd.DataFrame(rows),hide_index=True,width='stretch',disabled=['학번','학생','상태'],num_rows='fixed',
                         column_config={'교과세특':st.column_config.TextColumn(width='large'), '완성본으로 저장':st.column_config.CheckboxColumn()},key=table_key)
    for row in frame.to_dict('records'):
        b=ctx['buffers'][row['학번']]
        ctx['table_edits'][row['학번']]={'text':row['교과세특'] or '', 'review_note':row['교사 확인·수정 메모'] or '', 'final':bool(row['완성본으로 저장']),
                                     'dirty':row['교과세특']!=b['text'] or row['교사 확인·수정 메모']!=b['review_note']}
    verified=st.checkbox('완성본으로 표시한 학생의 근거·내용·분량을 모두 확인했습니다.',key=ctx['key']+'_bulk_confirm')
    if st.button('표의 수정 내용 저장',key=ctx['key']+'_bulk_save',type='primary',disabled=service.pending()):
        errors=[];saved=0
        if any(ctx['table_edits'][sid]['final'] for sid in selected) and not verified:
            st.error('완성본으로 저장할 행은 교사 확인 항목을 체크해 주세요.')
        else:
            for sid in selected:
                b=_capture(ctx,sid); edit=ctx['table_edits'][sid]
                current=b['workspace']['data'].get('current') or {}
                if (edit['text']==current.get('text','') and edit['review_note']==current.get('review_note','')
                        and b['reviews']==current.get('reviews',[]) and b['ai_draft']==current.get('ai_draft')
                        and b['analyses']==current.get('analyses',[]) and not edit['final']):
                    continue
                try:
                    payload=service.save_term(b['workspace'],b['reviews'],edit['text'],b['ai_draft'],b['analyses'],
                                              final=edit['final'],confirmed=verified,review_note=edit['review_note'],**settings)
                    _install(ctx,sid,service.with_saved(b['workspace'],payload));saved+=1
                except Exception as exc: errors.append(names[sid]+' · '+str(exc))
                if service.pending():break
            ctx['bulk_result']=(saved,errors);st.rerun()
    if ctx.get('bulk_result'):
        saved,errors=ctx['bulk_result'];st.caption(f'저장 완료 {saved}명')
        for error in errors:st.error(error)
    works=[ctx['buffers'][sid]['workspace'] for sid in selected]
    a,b=st.columns(2)
    a.download_button('선택 학생 저장본 CSV · 초안 포함',service.export_csv(works),file_name=f'교과세특_{year}_{term}학기_{subject}_전체.csv',mime='text/csv',key=ctx['key']+'_csv_all')
    b.download_button('완성본만 CSV',service.export_csv(works,final_only=True),file_name=f'교과세특_{year}_{term}학기_{subject}_완성본.csv',mime='text/csv',key=ctx['key']+'_csv_final')
    st.caption('CSV에는 저장이 끝난 내용이 들어갑니다. 표에서 고친 내용은 먼저 저장하세요. 수정하지 않은 행은 유지합니다. 변경한 행은 완성본 체크가 없으면 초안으로 저장하며 이전 완성본 이력을 보관합니다.')


def _batch_controls(service,ctx,names,config,settings):
    st.caption('학생별 작성에서 근거를 선택하고 확인한 뒤, 준비된 학생들을 한 번에 생성합니다. 저장된 글의 불러오기는 AI 호출과 별개입니다.')
    rows=[];ready_ids=[]
    for sid in names:
        if sid not in ctx['buffers']:
            rows.append({'학생':names[sid],'생성 준비':'자료 불러오기 필요'});continue
        b=_capture(ctx,sid);ready,message=_readiness(service,b,config,settings['target_chars'])
        if ready:ready_ids.append(sid)
        rows.append({'학생':names[sid],'생성 준비':'준비 완료' if ready else message})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    selected=st.multiselect('AI 초안을 생성할 학생',list(names),format_func=names.get,key=ctx['key']+'_batch_students')
    consent=st.checkbox('선택한 학생들의 확인 근거를 AI에 전송합니다. 학생 수만큼 요청이 진행됩니다.',key=ctx['key']+'_batch_consent')
    replace=st.checkbox('작성된 내용이 있는 학생도 이전 내용을 보관하고 새 초안 생성',key=ctx['key']+'_batch_replace')
    job=ctx.get('job');active=job and job['active']
    if st.button('✨ 선택 학생 AI 초안 일괄 생성',type='primary',key=ctx['key']+'_batch_start',disabled=not(selected and consent) or active or service.pending()):
        missing=[names[s] for s in selected if s not in ready_ids]
        existing=[names[s] for s in selected if s in ctx['buffers'] and _capture(ctx,s)['text'].strip()]
        if missing:st.error('먼저 근거를 확인해 주세요: '+', '.join(missing))
        elif existing and not replace:st.error('이미 작성된 내용이 있습니다. 재생성 여부를 확인해 주세요: '+', '.join(existing))
        else:
            ctx['job']={'active':True,'settings':copy.deepcopy(settings),'items':[{'sid':s,'token':uuid.uuid4().hex,'state':'waiting','message':'',
                         'input_hash':_batch_fingerprint(_capture(ctx,s))} for s in selected]}
            st.rerun()
    if job:
        done=sum(x['state']=='done' for x in job['items'])
        st.progress(done/len(job['items']),text=f"저장 완료 {done}/{len(job['items'])}명")
        st.dataframe(pd.DataFrame([{'학생':names.get(x['sid'],x['sid']),'상태':{'waiting':'대기','running':'처리 중','done':'저장 완료','failed':'확인 필요'}.get(x['state'],x['state']),'안내':x['message']} for x in job['items']]),hide_index=True,width='stretch')
        a,b=st.columns(2)
        if a.button('일괄 생성 일시 정지',key=ctx['key']+'_pause',disabled=not job['active']):job['active']=False;st.rerun()
        if b.button('아직 시작하지 않은 학생 계속',key=ctx['key']+'_resume',disabled=job['active'] or not any(x['state']=='waiting' for x in job['items']) or service.pending()):job['active']=True;st.rerun()
        st.caption('실패한 요청을 자동 재호출하지 않습니다. 이미 저장된 학생은 그대로 유지하며 남은 학생만 계속할 수 있어요.')


def _batch_step(service,ctx,config):
    job=ctx.get('job')
    if not job or not job['active']:return
    if service.pending():job['active']=False;return
    item=next((x for x in job['items'] if x['state'] in ('waiting','running')),None)
    if not item:job['active']=False;return
    item['state']='running'
    try:
        with st.spinner('일괄 생성 중 · '+item['sid']+' 학생의 초안을 저장하고 있어요.'):
            _generate(service,ctx,item['sid'],config,job['settings'],item['token'],item)
        item.update(state='done',message='초안 저장 완료')
    except Exception as exc:
        b=ctx['buffers'][item['sid']]
        if getattr(exc,'completed_draft',None):b['candidate']=exc.completed_draft
        item.update(state='failed',message=str(exc) if isinstance(exc,(ArchiveError,PermissionError)) else '처리 확인 필요. 입력을 유지했습니다.')
        job['active']=False
    st.rerun()
