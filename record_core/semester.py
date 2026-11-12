"""Semester-scoped school records, optimistic edits and durable AI request receipts.

Uses the existing encrypted student archive in class-dashboard-data. AI is called
only on an explicit generate action; loading, editing and exporting never call it.
"""
from __future__ import annotations
import calendar
import copy
import csv
import io
import re
import threading
import uuid
from datetime import date
from .archive import ArchiveError, fingerprint, utcnow
from .service import RecordService, check_final, byte_count
from .evidence import project, validate_reviews

_INIT_LOCK = threading.Lock()


class RecordConflict(ArchiveError):
    pass


class RecordPending(ArchiveError):
    def __init__(self, payload=None, draft=None):
        super().__init__('서버에 반영했지만 GitHub 저장 확인이 필요합니다. 입력을 유지하고 ‘저장 다시 확인’을 누르세요. AI를 다시 호출하지 않습니다.')
        self.saved_payload = payload
        self.completed_draft = draft


def term_values(year, semester):
    if type(year) is not int or not 2000 <= year <= 2099 or type(semester) is not int or semester not in (1, 2):
        raise ArchiveError('학년도(2000~2099)와 1·2학기를 확인하세요.')
    return year, semester


def term_dates(year, semester):
    term_values(year, semester)
    return (date(year, 3, 1), date(year, 8, 31)) if semester == 1 else (date(year, 9, 1), date(year + 1, 2, calendar.monthrange(year + 1, 2)[1]))


def term_scope(teacher, sid, subject, year, semester):
    return fingerprint(['semester-record-v1', str(teacher), str(sid), subject, year, semester])


def _range(year, start, end):
    try:
        a, z = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except (ValueError, TypeError):
        raise ArchiveError('자료 시작일과 종료일을 확인하세요.') from None
    if not date(year, 3, 1) <= a <= z <= date(year + 1, 2, calendar.monthrange(year + 1, 2)[1]):
        raise ArchiveError('자료 기간은 선택 학년도 3월부터 다음 해 2월 사이로 지정하세요.')
    return a.isoformat(), z.isoformat()


def _settings(target_chars=400, byte_limit=1500, guidance=''):
    if type(target_chars) is not int or not 100 <= target_chars <= 1000:
        raise ArchiveError('초안 목표 분량은 100~1000자로 지정하세요.')
    if type(byte_limit) is not int or not 100 <= byte_limit <= 6000:
        raise ArchiveError('저장 분량 기준은 100~6000바이트로 지정하세요.')
    if not isinstance(guidance, str) or len(guidance) > 16000:
        raise ArchiveError('교사 제공 작성 기준은 16,000자 이내로 입력하세요.')
    return dict(target_chars=target_chars, byte_limit=byte_limit, guidance=guidance)


def _text(value, limit=30000):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ArchiveError(f'작성 내용은 {limit:,}자 이내의 텍스트로 입력하세요.')
    return value


class SemesterRecords(RecordService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with _INIT_LOCK:
            if not hasattr(self.backend, '_semester_lock'):
                self.backend._semester_lock = threading.RLock()
                self.backend._semester_pending = {}
        self.lock = self.backend._semester_lock

    def _bundles(self, sid):
        self.student(sid)
        values = {b.get('_path', fingerprint(b)): b for b in self.backend.archive_read_student(sid)}
        # Include queued current files when a remote commit has not yet succeeded.
        prefix = self.backend.archive_crypto.student_dir(sid) + '/'
        with getattr(self.backend, 'lock', self.lock):
            queued = dict(getattr(self.backend, 'archive_pending', getattr(self.backend, 'pending', {})))
        for path, raw in queued.items():
            if path.startswith(prefix) and path.endswith('/current.json.enc'):
                b = self.backend.archive_crypto.open_bundle(raw, sid, path)
                b['_path'] = path
                values[path] = b
        return list(values.values())

    def _latest(self, bundles, scope, teacher):
        items = [b['payload'] for b in bundles if b['category'] == 'drafts'
                 and b['payload'].get('format') == 'semester-record-v1'
                 and b['payload'].get('scope_id') == scope and b['payload'].get('teacher_id') == teacher]
        return max(items, key=lambda p: int(p.get('revision', 0)), default=None)

    def pending(self):
        teacher = self.actor()['id']
        return any(v == teacher for v in self.backend._semester_pending.values())

    def retry(self):
        teacher = self.actor()['id']
        self.backend.flush()
        with self.lock:
            self.backend._semester_pending = {k: v for k, v in self.backend._semester_pending.items() if v != teacher}

    def _flush(self, scope, teacher, payload=None, draft=None):
        try:
            self.backend.flush()
        except Exception:
            with self.lock:
                self.backend._semester_pending[scope] = teacher
            raise RecordPending(payload, draft) from None

    def load_term(self, sid, subject, year, semester, start=None, end=None):
        actor = self.actor(); self.student(sid); term_values(year, semester)
        if subject not in ('공통수학1', '공통수학2'):
            raise ArchiveError('과목을 확인하세요.')
        defaults = term_dates(year, semester)
        start, end = _range(year, start or defaults[0], end or defaults[1])
        bundles = self._bundles(sid)
        scope = term_scope(actor['id'], sid, subject, year, semester)
        current = self._latest(bundles, scope, actor['id'])
        evidence = project(bundles, sid=sid, teacher_id=actor['id'], legacy_teacher_id=self.legacy_teacher_id,
                           subject=subject, start=start, end=end)
        saved = [b['payload'] for b in bundles if b['payload'].get('teacher_id') == actor['id']
                 and b['payload'].get('scope_id') == scope and b['payload'].get('kind') == 'file_analysis']
        data = dict(teacher_id=actor['id'], student_id=str(sid), subject=subject, academic_year=year, semester=semester,
                    start=start, end=end, scope_id=scope, evidence=evidence, saved=saved, current=current,
                    revision=int((current or {}).get('revision', 0)), loaded_at=utcnow())
        return self._seal(data)

    def refresh(self, workspace):
        d = self.validate(workspace)
        return self.load_term(d['student_id'], d['subject'], d['academic_year'], d['semester'], d['start'], d['end'])

    def with_saved(self, workspace, payload):
        d = copy.deepcopy(self.validate(workspace))
        if payload.get('scope_id') != d['scope_id'] or payload.get('teacher_id') != d['teacher_id']:
            raise ArchiveError('저장 결과의 소유자와 작성 범위를 확인하세요.')
        d.update(current=copy.deepcopy(payload), revision=payload['revision'])
        return self._seal(d)

    def sync_sources(self, sid, assessment_store=None):
        self.student(sid)
        self.backend.archive_student_tables(sid)
        self.backend.flush()
        if assessment_store is not None:
            super().sync(sid, assessment_store)

    def add_observation(self, workspace, text, observed_on):
        d = self.validate(workspace); _text(text, 6000)
        if len(text.strip()) < 5:
            raise ArchiveError('관찰 사실을 5자 이상 구체적으로 입력하세요.')
        day, _ = _range(d['academic_year'], observed_on, observed_on)
        if not d['start'] <= day <= d['end']:
            raise ArchiveError('선택한 자료 기간 안의 관찰일을 지정하세요.')
        import storage as db
        if day > db.today_str():
            raise ArchiveError('미래 날짜를 실제 관찰일로 기록할 수 없습니다.')
        student = self.student(d['student_id'])
        row = dict(id=uuid.uuid4().hex, created_at=day + ' 12:00:00', student_id=d['student_id'],
                   name=student.get('name', ''), category='교과세특 수업 관찰', content=text.strip(),
                   author_id=d['teacher_id'], subject=d['subject'], **{'class': student.get('class', '')})
        self.backend.append('observations', row)
        self._flush(d['scope_id'], d['teacher_id'])
        return self.refresh(workspace)

    def _reviews(self, d, reviews):
        if not isinstance(reviews, list) or len(reviews) > 30:
            raise ArchiveError('근거 자료는 최대 30개입니다.')
        known = {e['id']: e for e in d['evidence'] if e['eligible']}
        clean = []
        for r in reviews:
            if not isinstance(r, dict) or r.get('evidence_id') not in known:
                raise ArchiveError('선택한 학생의 근거 목록을 다시 확인하세요.')
            fact = _text(r.get('fact', ''), 10000)
            e = known[r['evidence_id']]
            clean.append(dict(evidence_id=e['id'], evidence_hash=r.get('evidence_hash', ''), fact=fact,
                              context=r.get('context', '확인 필요'), subject=d['subject'],
                              teacher_confirmed=r.get('teacher_confirmed') is True))
        if len({r['evidence_id'] for r in clean}) != len(clean):
            raise ArchiveError('같은 근거가 중복 선택되었습니다.')
        return clean

    def save_term(self, workspace, reviews, text, ai_draft=None, analyses=None, *, final=False, confirmed=False,
                  review_note='', target_chars=400, byte_limit=1500, guidance='', generation_id=''):
        d = self.validate(workspace); _text(text); _text(review_note, 4000)
        settings = _settings(target_chars, byte_limit, guidance)
        reviews = self._reviews(d, reviews)
        if self.pending():
            raise RecordPending()
        facts = []
        if final:
            facts = validate_reviews(d['evidence'], reviews, d['subject'])
            check_final(text, (ai_draft or {}).get('text', ''), confirmed=confirmed, review_note=review_note, byte_limit=byte_limit)
            if ai_draft and ai_draft.get('evidence_hashes') != {r['evidence_id']: r['evidence_hash'] for r in reviews}:
                raise ArchiveError('초안 작성 후 근거가 바뀌었어요. 재생성하거나 교사 직접 작성으로 전환하세요.')
            fresh = self.refresh(workspace)
            validate_reviews(fresh['data']['evidence'], reviews, d['subject'])
        with self.lock:
            self.actor()
            current = self._latest(self._bundles(d['student_id']), d['scope_id'], d['teacher_id'])
            if int((current or {}).get('revision', 0)) != d['revision']:
                raise RecordConflict('다른 화면에서 더 최근에 저장했어요. 입력 내용은 유지했습니다. 최신 기록을 불러온 뒤 내용을 합쳐 주세요.')
            payload = {k: d[k] for k in ('scope_id', 'teacher_id', 'student_id', 'subject', 'academic_year', 'semester', 'start', 'end')}
            payload.update(format='semester-record-v1', kind='final' if final else 'working_draft',
                           revision=d['revision'] + 1, text=text, reviews=copy.deepcopy(reviews), ai_draft=copy.deepcopy(ai_draft),
                           analyses=copy.deepcopy(analyses or []), sources=facts, review_note=review_note,
                           teacher_confirmed=bool(final and confirmed), saved_at=utcnow(), settings=settings,
                           generation_id=generation_id,
                           previous_final_text=text if final else (current or {}).get('previous_final_text', (current or {}).get('text', '') if (current or {}).get('kind') == 'final' else ''))
            # Keep a searchable latest-state index, including drafts. No other teacher's row changes.
            rid = d['scope_id'][:32]
            student = self.student(d['student_id'])
            fields = dict(id=rid, updated_at=payload['saved_at'], period=f"{d['academic_year']}학년도 {d['semester']}학기",
                          subject=d['subject'], student_id=d['student_id'], name=student.get('name', ''),
                          author_id=d['teacher_id'], text=text, **{'class': student.get('class', '')})
            import json
            fields['sources'] = json.dumps(dict(kind='teacher_confirmed' if final else 'working_draft', scope_id=d['scope_id'],
                                                academic_year=d['academic_year'], semester=d['semester'], revision=payload['revision']), ensure_ascii=False)
            old = next((r for r in self.backend.read('records') if r['id'] == rid), None)
            if old and old.get('author_id') != d['teacher_id']:
                raise PermissionError('기록 소유자가 일치하지 않습니다.')
            self.backend.queue_archive(d['student_id'], 'drafts', d['scope_id'], payload)
            if final:
                self.backend.queue_archive(d['student_id'], 'school_records', d['scope_id'], payload)
            if old:
                self.backend.update('records', rid, fields)
            else:
                self.backend.append('records', fields)
        self._flush(d['scope_id'], d['teacher_id'], payload, ai_draft)
        return payload

    def _job(self, d, request_id):
        return next((b['payload'] for b in self._bundles(d['student_id']) if b['payload'].get('kind') == 'semester_generation'
                     and b['payload'].get('teacher_id') == d['teacher_id'] and b['payload'].get('scope_id') == d['scope_id']
                     and b['payload'].get('request_id') == request_id), None)

    def _put_job(self, d, job):
        self.backend.queue_archive(d['student_id'], 'drafts', 'generation:' + d['scope_id'] + ':' + job['request_id'], job)
        self._flush(d['scope_id'], d['teacher_id'], draft=job.get('result'))

    def generate(self, workspace, reviews, ai, request_id, *, consent=False, target_chars=400, byte_limit=1500, guidance=''):
        d = self.validate(workspace); _settings(target_chars, byte_limit, guidance)
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}', request_id):
            raise ArchiveError('AI 생성 요청을 다시 준비하세요.')
        if not consent:
            raise ArchiveError('전송할 근거를 확인한 뒤 AI 생성 버튼을 눌러 주세요.')
        if self.pending():
            raise RecordPending()
        reviews = self._reviews(d, reviews)
        facts = validate_reviews(d['evidence'], reviews, d['subject'])
        fingerprint_input = fingerprint([reviews, target_chars, byte_limit, guidance, d['revision']])
        with self.lock:
            job = self._job(d, request_id)
            if job and job.get('input_hash') != fingerprint_input:
                raise RecordConflict('같은 AI 요청의 입력이 바뀌었습니다. 새 작업으로 시작하세요.')
            current = self._latest(self._bundles(d['student_id']), d['scope_id'], d['teacher_id'])
            if current and current.get('generation_id') == request_id:
                return current  # An interrupted acknowledgement must not call AI again.
            if job and job['state'] in ('running', 'failed'):
                raise ArchiveError('이 요청은 처리 중이거나 결과가 불확실하여 자동 재호출하지 않습니다. 저장 기록과 오류를 확인한 뒤 필요한 경우 새 작업을 시작하세요.')
            if int((current or {}).get('revision', 0)) != d['revision']:
                raise RecordConflict('저장된 글이 바뀌었습니다. 최신 기록을 불러온 뒤 생성하세요.')
            if not job:
                fresh = self.refresh(workspace)
                validate_reviews(fresh['data']['evidence'], reviews, d['subject'])
                job = dict(kind='semester_generation', teacher_id=d['teacher_id'], student_id=d['student_id'], scope_id=d['scope_id'],
                           request_id=request_id, input_hash=fingerprint_input, state='running', started_at=utcnow())
                # Queued receipt is visible to other threads before leaving this lock.
                self.backend.queue_archive(d['student_id'], 'drafts', 'generation:' + d['scope_id'] + ':' + request_id, job)
                new = True
            else:
                new = False
        if new:
            self._flush(d['scope_id'], d['teacher_id'])  # Do not charge before the request receipt is durable.
            try:
                result = ai.draft(d['subject'], facts, self.identities(), target_chars, consent=True, guidance=guidance)
                self.actor()
            except Exception:
                job.update(state='failed', finished_at=utcnow())
                self._put_job(d, job)
                raise
            result['evidence_hashes'] = {r['evidence_id']: r['evidence_hash'] for r in reviews}
            job.update(state='generated', result=result, finished_at=utcnow())
            self._put_job(d, job)
        result = job['result']
        try:
            payload = self.save_term(workspace, reviews, result['text'], result,
                                     (d.get('current') or {}).get('analyses', []), target_chars=target_chars,
                                     byte_limit=byte_limit, guidance=guidance, generation_id=request_id)
        except Exception as error:
            error.completed_draft = result
            raise
        # Canonical payload includes the request receipt; replay can return it even
        # if this final ledger flush fails after the draft was already committed.
        job.update(state='saved', saved_revision=payload['revision'])
        self._put_job(d, job)
        return payload

    def previous_texts(self, workspace):
        d = self.validate(workspace)
        rows = [r for r in self.backend.read('records') if r.get('student_id') == d['student_id']
                and r.get('subject') == d['subject'] and (r.get('author_id') or self.legacy_teacher_id) == d['teacher_id']
                and r.get('id') != d['scope_id'][:32]]
        return sorted(rows, key=lambda r: r.get('updated_at', ''), reverse=True)

    def export_csv(self, workspaces, *, final_only=False):
        fields = ['학년도', '학기', '학급', '학번', '이름', '과목', '작성상태', '교과세특', '글자수', '참고바이트', '자료시작일', '자료종료일', '저장일', '교사확인메모']
        buffer = io.StringIO(newline=''); writer = csv.DictWriter(buffer, fieldnames=fields); writer.writeheader()
        for w in workspaces:
            d = self.validate(w); p = d.get('current') or {}
            if not p or (final_only and p['kind'] != 'final'):
                continue
            student = self.student(d['student_id'])
            row = dict(zip(fields, [d['academic_year'], d['semester'], student.get('class', ''), d['student_id'], student.get('name', ''),
                       d['subject'], '완성본' if p['kind'] == 'final' else '초안', p['text'], len(p['text']), byte_count(p['text']),
                       p['start'], p['end'], p['saved_at'], p.get('review_note', '')]))
            for k,v in row.items():
                if isinstance(v, str) and (v.lstrip().startswith(('=', '+', '-', '@')) or v.startswith(('\t', '\r', '\n'))):
                    row[k] = "'" + v
            writer.writerow(row)
        return buffer.getvalue().encode('utf-8-sig')
