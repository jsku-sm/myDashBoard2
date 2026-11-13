"""Semester writer persistence and request lifecycle, all data/providers are fake."""
import copy
import csv
import io
import threading
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_student_record_vault import env, review, SID, OTHER, api, api_response
from record_core.archive import ArchiveError
from record_core.semester import SemesterRecords, RecordConflict, RecordPending, term_dates


@pytest.fixture
def term(env):
    env.s = SemesterRecords(env.b, lambda: env.actor[0])
    env.load = lambda: env.s.load_term(SID, '공통수학2', 2026, 2)
    return env


def reviews(w):
    return [review(next(e for e in w['data']['evidence'] if e['category']=='sudanotes'))]


def fake_ai(action=None):
    def draft(subject, facts, *args, **kwargs):
        if action: action()
        return {'text':'대칭이동에서 좌표의 부호를 확인함.', 'sentences':[{'text':'대칭이동에서 좌표의 부호를 확인함.','evidence_ids':[facts[0]['evidence_id']]}]}
    return SimpleNamespace(draft=Mock(side_effect=draft))


def test_scope_partitions_and_date_window_keeps_same_record(term):
    w=term.load();term.s.save_term(w, [], '2학기 작성 내용')
    assert term.load()['data']['current']['text']=='2학기 작성 내용'
    for y,s,subject in [(2026,1,'공통수학2'),(2025,2,'공통수학2'),(2026,2,'공통수학1')]:
        assert term.s.load_term(SID,subject,y,s)['data']['current'] is None
    resized=term.s.load_term(SID,'공통수학2',2026,2,'2026-10-01','2026-12-31')
    assert resized['data']['scope_id']==w['data']['scope_id']
    assert resized['data']['current']['text']=='2학기 작성 내용'
    assert term.s.load_term(OTHER,'공통수학2',2026,2)['data']['current'] is None


@pytest.mark.parametrize('year,sem',[(1999,1),(2100,1),(2026,0),(2026,3),('2026',2),(True,1)])
def test_invalid_terms(term,year,sem):
    with pytest.raises(ArchiveError):term.s.load_term(SID,'공통수학2',year,sem)


def test_dates_and_leap_year(term):
    assert term_dates(2027,2)==(date(2027,9,1),date(2028,2,29))
    for start,end in [('2026-02-28','2026-10-24'),('2026-11-01','2026-10-24'),('invalid','2026-10-24')]:
        with pytest.raises(ArchiveError):term.s.load_term(SID,'공통수학2',2026,2,start,end)


def test_all_sources_notes_period_subject_and_observations(term,monkeypatch):
    monkeypatch.setattr('storage.today_str',lambda:'2026-11-12')
    w=term.load()
    assert {'sudanotes','assessments','games','quizzes'} <= {e['category'] for e in w['data']['evidence']}
    assert all(not e['eligible'] for e in w['data']['evidence'] if e['category']=='points')
    fresh=term.s.add_observation(w,'학생이 두 좌표의 부호를 비교하고 오류를 수정하는 과정을 관찰함.','2026-10-25')
    assert any(e['category']=='observations' and e['subject']=='공통수학2' for e in fresh['data']['evidence'])
    assert not any(e['category']=='observations' for e in term.s.load_term(SID,'공통수학1',2026,2)['data']['evidence'])
    assert not any(e['category']=='sudanotes' for e in term.s.load_term(SID,'공통수학2',2026,1)['data']['evidence'])
    term.actor[0]='teacher2'
    assert not any(e['category']=='observations' for e in term.load()['data']['evidence'])


def test_draft_save_requires_no_ai_or_submissions(term):
    w=term.s.load_term(OTHER,'공통수학1',2026,1)
    p=term.s.save_term(w,[],'교사가 직접 작성 중인 초안입니다.')
    assert p['kind']=='working_draft' and p['revision']==1
    assert term.b.rows['records'][0]['period']=='2026학년도 1학기'


def test_teacher_and_student_permissions_and_signed_scope(term):
    w=term.load();term.s.save_term(w,[],'교사1 전용 기록')
    term.actor[0]='teacher2'
    assert term.load()['data']['current'] is None
    with pytest.raises(PermissionError):term.s.save_term(w,[],'다른 교사의 글')
    term.actor[0]=SID
    with pytest.raises(PermissionError):term.load()
    term.actor[0]='teacher';w['data']['semester']=1
    with pytest.raises(ArchiveError):term.s.save_term(w,[],'변조')


def test_stale_edit_conflict_preserves_newer_text(term):
    a=term.load();b=term.load()
    term.s.save_term(a,[],'새로 저장된 글')
    with pytest.raises(RecordConflict):term.s.save_term(b,[],'오래된 화면의 글')
    assert term.load()['data']['current']['text']=='새로 저장된 글'
    assert len(term.b.rows['records'])==1


def test_final_can_reopen_edit_and_keeps_previous_final(term):
    w=term.load();r=reviews(w)
    p=term.s.save_term(w,r,'대칭이동의 좌표 관계를 설명함.',final=True,confirmed=True,review_note='풀이와 관찰 기록을 확인함.')
    assert p['kind']=='final'
    term.s.save_term(term.load(),r,'후속 수정 중인 글')
    current=term.load()['data']['current']
    assert current['kind']=='working_draft' and current['previous_final_text']==p['text']
    assert len([k for k in term.b.files if '/history/' in k and '/drafts/' in k])>=2
    assert term.s.export_csv([term.load()],final_only=True).decode('utf-8-sig').count('\n')==1


def test_final_accepts_reviewed_unchanged_ai_but_rejects_unverified_and_stale_evidence(term):
    w=term.load();r=reviews(w)
    with pytest.raises(ArchiveError):term.s.save_term(w,r,'완성 문장',final=True)
    a={'text':'동일한 AI 초안','evidence_hashes':{r[0]['evidence_id']:r[0]['evidence_hash']}}
    saved=term.s.save_term(w,r,'동일한 AI 초안',a,final=True,confirmed=True)
    assert saved['kind']=='final' and saved['ai_draft']==a
    w=term.load()
    term.b.rows['sudanotes'][0]['q1']='원본이 나중에 바뀜';term.s.sync_sources(SID)
    with pytest.raises(ArchiveError):term.s.save_term(w,r,'교사가 고친 문장',final=True,confirmed=True,review_note='교사 확인 기록')


def test_csv_bom_quoting_and_formula_escape(term):
    term.b.rows['users'][2]['name']='=HYPERLINK("example")'
    w=term.load();term.s.save_term(w,[],'=악성수식\n두번째 줄,쉼표')
    raw=term.s.export_csv([term.load()]);assert raw.startswith(b'\xef\xbb\xbf')
    row=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))[0]
    assert row['교과세특'].startswith("'=") and row['이름'].startswith("'=")
    assert row['학년도']=='2026' and row['학기']=='2' and row['작성상태']=='초안'
    assert '\n두번째 줄,쉼표' in row['교과세특']


def test_save_failure_visible_pending_and_retry_without_loss(term):
    w=term.load();term.b.fail=True
    with pytest.raises(RecordPending):term.s.save_term(w,[],'저장 확인 중인 내용')
    assert term.s.pending() and term.load()['data']['current']['text']=='저장 확인 중인 내용'
    with pytest.raises(RecordPending):term.s.save_term(term.load(),[],'중복 저장')
    term.b.fail=False;term.s.retry()
    assert not term.s.pending() and term.load()['data']['revision']==1


def test_generate_saves_request_before_ai_and_replay_is_free(term):
    w=term.load();r=reviews(w)
    def receipt_exists():
        jobs=[b['payload'] for b in term.b.archive_read_student(SID) if b['payload'].get('request_id')=='request_1']
        assert jobs[0]['state']=='running'
    ai=fake_ai(receipt_exists)
    p=term.s.generate(w,r,ai,'request_1',consent=True,guidance='사실만 간결하게 기록')
    again=term.s.generate(w,r,ai,'request_1',consent=True,guidance='사실만 간결하게 기록')
    assert p==again and ai.draft.call_count==1
    assert term.load()['data']['current']['kind']=='working_draft'
    assert ai.draft.call_args.kwargs['guidance']=='사실만 간결하게 기록'


def test_request_receipt_must_commit_before_call(term):
    w=term.load();ai=fake_ai();term.b.fail=True
    with pytest.raises(RecordPending):term.s.generate(w,reviews(w),ai,'request_2',consent=True)
    assert ai.draft.call_count==0


def test_failed_ai_never_automatically_recalled(term):
    w=term.load();ai=fake_ai(lambda: (_ for _ in ()).throw(RuntimeError('timeout')))
    with pytest.raises(ArchiveError, match='AI 초안 생성 중'):term.s.generate(w,reviews(w),ai,'request_3',consent=True)
    with pytest.raises(ArchiveError):term.s.generate(w,reviews(w),ai,'request_3',consent=True)
    assert ai.draft.call_count==1


def test_generated_result_commit_failure_retains_candidate_then_recovers_without_call(term):
    w=term.load();ai=fake_ai(lambda:setattr(term.b,'fail',True))
    with pytest.raises(RecordPending) as exc:term.s.generate(w,reviews(w),ai,'request_4',consent=True)
    assert exc.value.completed_draft['text']
    term.b.fail=False;term.s.retry()
    p=term.s.generate(w,reviews(w),ai,'request_4',consent=True)
    assert p['text'] and ai.draft.call_count==1


def test_draft_commit_failure_recovers_canonical_request(term,monkeypatch):
    w=term.load();ai=fake_ai();original=term.b.flush;failed=[False]
    def flush():
        payloads=[term.b.archive_crypto.decrypt(raw).get('payload',{}) for raw in term.b.pending.values()]
        if not failed[0] and any(p.get('generation_id')=='request_5' and p.get('kind')=='working_draft' for p in payloads):
            failed[0]=True
            raise RuntimeError('draft commit failure')
        original()
    monkeypatch.setattr(term.b,'flush',flush)
    with pytest.raises(RecordPending) as exc:term.s.generate(w,reviews(w),ai,'request_5',consent=True)
    assert exc.value.saved_payload['text']
    term.s.retry();p=term.s.generate(w,reviews(w),ai,'request_5',consent=True)
    assert p['revision']==1 and ai.draft.call_count==1


def test_concurrent_teacher_save_keeps_ai_result_for_manual_merge(term):
    w=term.load();ai=fake_ai(lambda:term.s.save_term(term.load(),[],'다른 창에서 작성한 문장'))
    with pytest.raises(RecordConflict) as exc:term.s.generate(w,reviews(w),ai,'request_6',consent=True)
    assert exc.value.completed_draft['text']
    assert term.load()['data']['current']['text']=='다른 창에서 작성한 문장'


def test_same_request_concurrent_threads_only_calls_ai_once(term):
    w=term.load();started=threading.Event();release=threading.Event();errors=[]
    ai=fake_ai(lambda:(started.set(),release.wait(5)))
    def run():
        try:term.s.generate(w,reviews(w),ai,'request_7',consent=True)
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=run);thread.start();assert started.wait(5)
    with pytest.raises(ArchiveError):term.s.generate(w,reviews(w),ai,'request_7',consent=True)
    release.set();thread.join(5)
    assert not thread.is_alive() and not errors and ai.draft.call_count==1


def test_generation_without_consent_does_not_call(term):
    w=term.load();ai=fake_ai()
    with pytest.raises(ArchiveError):term.s.generate(w,reviews(w),ai,'request_8')
    assert not ai.draft.called


def test_guidance_is_sent_with_schema_and_only_selected_anonymous_facts(term):
    w=term.load();r=reviews(w);eid=r[0]['evidence_id']
    post=Mock(return_value=api_response({'sentences':[{'text':'좌표를 점검함.','evidence_ids':[eid]}],'cautions':[]}))
    term.s.generate(w,r,api(post),'request_9',consent=True,guidance='교사 제공 문장 작성 기준')
    body=post.call_args.kwargs['json']
    assert '교사 제공 문장 작성 기준' in body['instructions']
    assert body['store'] is False
    import json
    encoded=json.dumps(body,ensure_ascii=False)
    assert '가상학생가' not in encoded and '다른 학생 비공개' not in encoded and 'AI에 보내지 말아야 할 사유' not in encoded
