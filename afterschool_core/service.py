"""Cohort-scoped after-school board using the app's existing CSV/GitHub store.

Every public operation resolves the logged-in account again. No student-provided
role, class, owner, file path or target student is an authorization source.
Locks/revisions protect this single app server; independent deployments editing
the same GitHub files are NOT a supported multi-writer database.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime
from pathlib import PurePath
from urllib.parse import urlsplit

import streamlit as st
import storage as db
from config import TZ
from afterschool_core.schema import TABLES

SUBJECTS = ('공통수학1', '공통수학2')
LEGACY_SUBJECT = '공통수학2'

STATES = {'draft': '준비 중', 'active': '운영 중', 'archived': '종료 · 읽기 전용', 'closed': '학생 접근 종료'}
KINDS = {'material': '수업자료', 'assignment': '과제', 'question': '질문'}
EXTENSIONS = ('pdf','png','jpg','jpeg','txt','docx','hwp','hwpx','xlsx','pptx')
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_FILES = 3
SAFE_MIMES = {'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg',
              'txt':'text/plain','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              'pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}


class ConflictError(ValueError):
    pass


class SavePendingError(RuntimeError):
    def __init__(self, record_id=''):
        self.record_id = record_id
        super().__init__('서버에 반영했지만 GitHub 영구 저장은 확인되지 않았어요. 반복 등록하지 말고 '
                         '‘저장 다시 확인’을 눌러 주세요. 자동 재시도도 계속되며 취소 버튼으로 되돌아가지 않습니다.')


def _text(value, label, limit=10000, required=False):
    if not isinstance(value, str):
        raise ValueError(f'{label}은(는) 글자로 입력해 주세요.')
    value = value.strip()
    if '\x00' in value or len(value) > limit or (required and not value):
        raise ValueError(f'{label}: {"1~" if required else ""}{limit:,}자 이내로 입력해 주세요.')
    return value


def _date(value, label):
    if value in ('', None):
        return ''
    if isinstance(value, datetime):
        raise ValueError(f'{label}은 날짜만 선택해 주세요.')
    value = value.isoformat() if isinstance(value, date) else value
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        out = date.fromisoformat(value)
        if not 2000 <= out.year <= 2100:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(f'{label}에 올바른 날짜를 입력해 주세요.') from None
    return value


def _due(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        value = value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)
        return value.strftime('%Y-%m-%d %H:%M:%S')
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        if not 2000 <= parsed.year <= 2100:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('마감 시각을 다시 선택해 주세요.') from None
    return value


def _flag(value, label):
    if not isinstance(value, bool):
        raise ValueError(f'{label} 값을 확인해 주세요.')
    return '1' if value else '0'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _array(value):
    try:
        out = json.loads(value or '[]')
        if not isinstance(out, list):
            raise ValueError()
        return out
    except (ValueError, TypeError):
        raise ValueError('방과후 기록 형식을 확인하지 못했어요. 원본 기록을 점검해 주세요.') from None


def _actor(backend, user):
    session = st.session_state.get('user')
    if not isinstance(user, dict) or not isinstance(session, dict) or not user.get('id'):
        raise PermissionError('로그인한 사용자만 이용할 수 있어요.')
    if session.get('id') != user['id'] or session.get('role') != user.get('role'):
        raise PermissionError('로그인 정보를 다시 확인해 주세요.')
    current = next((u for u in backend.read('users') if u.get('id') == user['id']), None)
    if (not current or current.get('role') not in ('teacher','student')
            or current.get('role') != session.get('role') or current.get('must_change') == '1'):
        raise PermissionError('현재 계정 권한을 확인할 수 없어요. 다시 로그인하거나 비밀번호를 변경해 주세요.')
    return current


def _teacher(actor):
    if actor['role'] != 'teacher':
        raise PermissionError('방과후 설정은 교사전용 메뉴에서 선생님만 변경할 수 있어요.')


def require_teacher(user):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(b, user)
        _teacher(actor)
        return actor


def _row(b, table, rid):
    row = next((r for r in b.read(table) if r.get('id') == rid), None)
    if not row:
        raise PermissionError('열 수 있는 기록이 없어요. 배정된 기수와 공개 상태를 확인해 주세요.')
    return dict(row)


def cohort_subject(row):
    # Legacy cohorts were only available in Common Mathematics 2. Do not
    # rewrite data on reads, and do not silently reassign invalid values.
    value = row.get('subject') or LEGACY_SUBJECT
    if value not in SUBJECTS:
        raise ValueError('기수의 과목 정보를 확인해 주세요. 공통수학1 또는 공통수학2만 가능합니다.')
    return value


def _cohort(b, actor, cid, write=False, manage=False):
    c = _row(b, 'as_cohorts', cid)
    c['subject'] = cohort_subject(c)
    if actor['role'] == 'teacher':
        if c['owner_id'] != actor['id']:
            raise PermissionError('본인이 만든 기수만 관리할 수 있어요.')
    else:
        if (manage or c['state'] not in ('active','archived')
                or actor['id'] not in _array(c['members_json'])):
            raise PermissionError('해당 기수에 접근할 수 없어요. 선생님께 배정 상태를 확인해 주세요.')
    if write and c['state'] != 'active':
        raise PermissionError('운영 중인 기수에서만 질문·댓글·과제 제출이 가능해요.')
    return c


def _version(row, expected):
    if not isinstance(expected, str) or expected != row['revision']:
        raise ConflictError('다른 창에서 먼저 변경했어요. 입력 내용을 복사한 뒤 최신 화면에서 다시 확인해 주세요.')


def _bump(row, changes):
    return dict(changes, revision=str(int(row['revision'])+1), updated_at=db.now_str())


def _identity(actor, kind, parent, request_id):
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', request_id):
        raise ValueError('저장 요청을 확인하지 못했어요. 화면을 다시 열어 주세요.')
    return hashlib.sha256(_json([actor['id'],kind,parent,request_id]).encode()).hexdigest()[:32]


def _fingerprint(payload, uploads):
    return hashlib.sha256(_json([payload, [{k:v for k,v in f.items() if k!='data'} for f in uploads]]).encode()).hexdigest()


def _existing(b, table, rid, digest):
    found = next((r for r in b.read(table) if r['id']==rid), None)
    if found and found.get('request_hash') != digest:
        raise ConflictError('이미 저장한 요청과 내용이 달라요. 중복 등록 대신 기존 기록을 확인해 주세요.')
    return found


def _persist(rid=''):
    for table in TABLES:
        db.invalidate(table)
    # Never call flush while holding the backend data lock (lock-order inversion).
    try:
        db.flush_now()
    except Exception:
        raise SavePendingError(rid) from None
    return rid


def retry_save(user):
    b = db._ready_backend()
    with b.lock:
        _actor(b,user)
    _persist()


def has_pending(user):
    b = db._ready_backend()
    with b.lock:
        _actor(b,user)
        return any(p.startswith('data/as_') for p in getattr(b,'dirty',{}))


def _summary(c, actor):
    keys = ('id','year','name','description','start_date','end_date','state','revision')
    out = {k:c[k] for k in keys}
    out['subject'] = cohort_subject(c)
    out['writable'] = c['state']=='active'
    if actor['role']=='teacher':
        out['member_count'] = len(_array(c['members_json']))
    return out


def list_cohorts(user, subject=None):
    if subject is not None and subject not in SUBJECTS:
        raise ValueError('공통수학1 또는 공통수학2를 선택해 주세요.')
    b = db._ready_backend()
    with b.lock:
        actor = _actor(b,user)
        rows=[]
        for c in b.read('as_cohorts'):
            allowed = (c['owner_id']==actor['id']) if actor['role']=='teacher' else (
                c['state'] in ('active','archived') and actor['id'] in _array(c['members_json']))
            if allowed and (subject is None or cohort_subject(c) == subject):
                rows.append(_summary(c,actor))
    def natural(c):
        return (-int(c['year']), tuple((0,int(s)) if s.isdigit() else (1,s) for s in re.split(r'(\d+)', c['name'])))
    return sorted(rows,key=natural)


def has_access(user, subject=None):
    try:
        return bool(list_cohorts(user, subject))
    except PermissionError:
        return False


def get_cohort(user, cid, subject=None):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user)
        c=_cohort(b,a,cid)
        if subject is not None and c['subject'] != subject:
            raise PermissionError('이 과목의 방과후 기수가 아닙니다. 과목과 배정 정보를 다시 확인해 주세요.')
        return _summary(c,a)


def _cohort_payload(payload):
    subject=payload.get('subject', LEGACY_SUBJECT)
    if subject not in SUBJECTS:
        raise ValueError('운영 과목은 공통수학1 또는 공통수학2 중 하나를 선택해 주세요.')
    name=_text(payload.get('name',''),'기수명',80,True)
    year=str(payload.get('year',''))
    if not year.isdigit() or not 2000<=int(year)<=2100:
        raise ValueError('학년도를 확인해 주세요.')
    start=_date(payload.get('start_date',''),'시작일'); end=_date(payload.get('end_date',''),'종료일')
    if start and end and end<start:
        raise ValueError('종료일이 시작일보다 빠를 수 없어요.')
    state=payload.get('state','draft')
    if state not in STATES:
        raise ValueError('기수 상태를 확인해 주세요.')
    return dict(name=name,year=year,subject=subject,description=_text(payload.get('description',''),'안내문',4000),
                start_date=start,end_date=end,state=state)


def create_cohort(user,payload,request_id):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _teacher(a)
        p=_cohort_payload(payload)
        rid=_identity(a,'cohort','',request_id); digest=_fingerprint(p,[])
        if not _existing(b,'as_cohorts',rid,digest):
            if any(r['owner_id']==a['id'] and r['year']==p['year'] and cohort_subject(r)==p['subject'] and r['name'].casefold()==p['name'].casefold()
                   for r in b.read('as_cohorts')):
                raise ValueError('같은 학년도·과목에 같은 기수명이 있어요. 기존 기수를 선택하거나 이름을 바꿔 주세요.')
            b.append('as_cohorts',dict(p,id=rid,owner_id=a['id'],members_json='[]',history_json='[]',revision='1',
                                     created_at=db.now_str(),updated_at=db.now_str(),request_hash=digest))
    return _persist(rid)


def update_cohort(user,cid,payload,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); c=_cohort(b,a,cid,manage=True); _version(c,expected_revision)
        p=_cohort_payload(dict(payload,subject=payload.get('subject',c['subject'])))
        if any(r['id']!=cid and r['owner_id']==a['id'] and r['year']==p['year'] and cohort_subject(r)==p['subject'] and r['name'].casefold()==p['name'].casefold()
               for r in b.read('as_cohorts')):
            raise ValueError('같은 학년도·과목에 같은 기수명이 있어요.')
        history=_array(c['history_json'])
        history.append({'at':db.now_str(),'action':'settings','previous_state':c['state'],'state':p['state'],
                        'previous_subject':c['subject'],'subject':p['subject']})
        b.update('as_cohorts',cid,_bump(c,dict(p,history_json=_json(history))))
    return _persist(cid)


def roster(user,cid):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); c=_cohort(b,a,cid,manage=True)
        selected=set(_array(c['members_json']))
        students=[{'id':u['id'],'name':u['name'],'class':u.get('class',''),'selected':u['id'] in selected}
                  for u in b.read('users') if u['role']=='student']
        known={u['id'] for u in students}
        students.extend({'id':sid,'name':'가입 정보 확인 필요','class':'','selected':True,'unavailable':True}
                        for sid in sorted(selected-known))
    return sorted(students,key=lambda u:(u['class'],u['id']))


def set_members(user,cid,ids,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); c=_cohort(b,a,cid,manage=True); _version(c,expected_revision)
        if not isinstance(ids,(list,tuple)) or any(not isinstance(i,str) for i in ids):
            raise ValueError('배정할 학생을 명단에서 선택해 주세요.')
        known={u['id'] for u in b.read('users') if u['role']=='student'}
        selected=set(ids)
        if not selected.issubset(known):
            raise ValueError('현재 학생 명단에 없는 계정이 있어요. 명단을 다시 확인해 주세요.')
        prev=set(_array(c['members_json']))
        history=_array(c['history_json'])
        history.append({'at':db.now_str(),'action':'members','added':sorted(selected-prev),'removed':sorted(prev-selected)})
        b.update('as_cohorts',cid,_bump(c,{'members_json':_json(sorted(selected)),'history_json':_json(history)}))
    return _persist(cid)



def _membership_delta(user, cid, ids, expected_revision, *, remove=False):
    """Atomic within the app server. Never replace a filtered roster snapshot.

    Only cohort membership/history is updated; user accounts, other cohorts,
    posts and submission versions are not modified. Flush occurs outside lock.
    """
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _teacher(a)
        c=_cohort(b,a,cid,manage=True); _version(c,expected_revision)
        if not isinstance(ids,(list,tuple)) or not ids:
            raise ValueError('학생을 한 명 이상 선택해 주세요.')
        values={_text(sid,'학번',100,True) for sid in ids}
        known={u['id'] for u in b.read('users') if u['role']=='student'}
        if not remove and not values.issubset(known):
            raise ValueError('가입된 학생의 학번과 정확히 일치하지 않습니다. 이름은 검색 후 학생을 선택해 주세요.')
        prev=set(_array(c['members_json']))
        selected=(prev-values) if remove else (prev|values)
        if selected != prev:
            history=_array(c['history_json'])
            history.append({'at':db.now_str(),'action':'members','added':sorted(selected-prev),
                            'removed':sorted(prev-selected)})
            b.update('as_cohorts',cid,_bump(c,{'members_json':_json(sorted(selected)),
                                              'history_json':_json(history)}))
    # Idempotent no-op still confirms any pending durable save.
    return _persist(cid)


def add_members(user, cid, student_ids, expected_revision):
    return _membership_delta(user,cid,student_ids,expected_revision)


def add_member(user, cid, student_id, expected_revision):
    return add_members(user,cid,[student_id],expected_revision)


def remove_member(user, cid, student_id, expected_revision):
    return _membership_delta(user,cid,[student_id],expected_revision,remove=True)

def _uploads(files):
    if not isinstance(files,(list,tuple)) or len(files)>MAX_FILES:
        raise ValueError(f'첨부파일은 최대 {MAX_FILES}개입니다.')
    result=[]; total=0
    for f in files:
        name=_text(str(getattr(f,'name','')),'파일명',180,True)
        if name!=name.replace('\\','/').rsplit('/',1)[-1] or any(ord(ch)<32 for ch in name):
            raise ValueError('파일 이름에 경로나 제어 문자를 사용할 수 없어요.')
        ext=PurePath(name).suffix.lower().lstrip('.')
        if ext not in EXTENSIONS:
            raise ValueError('지원하지 않는 파일 형식이에요. PDF·사진·문서 형식을 사용해 주세요.')
        data=f.getvalue()
        if not isinstance(data,bytes) or not data or len(data)>MAX_FILE_BYTES:
            raise ValueError('빈 파일은 올릴 수 없으며 파일당 최대 10 MiB입니다.')
        total+=len(data)
        if total>MAX_TOTAL_BYTES:
            raise ValueError('첨부파일 합계는 10 MiB 이하여야 해요.')
        signatures={'pdf':b'%PDF-','png':b'\x89PNG\r\n\x1a\n','jpg':b'\xff\xd8','jpeg':b'\xff\xd8',
                    'docx':b'PK','xlsx':b'PK','pptx':b'PK','hwpx':b'PK','hwp':b'\xd0\xcf\x11\xe0'}
        if ext in signatures and not data.startswith(signatures[ext]):
            raise ValueError(f'{name}: 확장자와 파일 내용이 맞지 않아요.')
        result.append(dict(name=name,ext=ext,mime=SAFE_MIMES.get(ext,'application/octet-stream'),
                           size=len(data),sha256=hashlib.sha256(data).hexdigest(),data=data))
    return result


def _save_files(b,uploads):
    result=[]
    try:
        for f in uploads:
            # Opaque path: names/student IDs are not used in the repository tree.
            fid,_=b.save_file(f['data'],f'as_{uuid.uuid4().hex}.{f["ext"]}',f['mime'],False)
            result.append({k:v for k,v in f.items() if k not in ('data','ext') } | {'file_id':fid})
    except Exception:
        for f in result:
            b.delete_file(f['file_id'])
        raise
    return result


def _links(value):
    if not isinstance(value,str):
        raise ValueError('링크는 한 줄에 하나씩 입력해 주세요.')
    urls=[]
    for line in value.splitlines():
        line=line.strip()
        if not line: continue
        try:
            u=urlsplit(line)
            ok=(u.scheme in ('https','http') and u.hostname and not u.username and not u.password)
        except ValueError: ok=False
        if not ok or any(ch.isspace() for ch in line) or len(line)>2000:
            raise ValueError('http 또는 https로 시작하는 올바른 링크만 사용할 수 있어요.')
        urls.append(line)
    if len(urls)>5: raise ValueError('링크는 최대 5개입니다.')
    return list(dict.fromkeys(urls))


def _post(b,a,pid,write=False):
    p=_row(b,'as_posts',pid)
    c=_cohort(b,a,p['cohort_id'],write=write)
    if p.get('deleted_at'):
        raise PermissionError('삭제된 글은 열 수 없어요.')
    if a['role']=='student' and (p['published']!='1' or
            (p['visibility']=='private' and p['author_id']!=a['id'])):
        raise PermissionError('이 글에 접근할 수 없어요.')
    return p,c


def _post_public(p):
    result={k:v for k,v in p.items() if k not in ('owner_id','attachments_json','links_json','request_hash')}
    result['attachments']=[{k:v for k,v in f.items() if k in ('name','size','mime')} for f in _array(p['attachments_json'])]
    result['links']=_array(p['links_json'])
    return result


def list_posts(user,cid,kind=None):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _cohort(b,a,cid)
        rows=[]
        for p in b.read('as_posts'):
            if p['cohort_id']!=cid or p['deleted_at'] or (kind and p['kind']!=kind): continue
            try:
                p,_=_post(b,a,p['id'])
            except PermissionError: continue
            rows.append(_post_public(p))
    return sorted(rows,key=lambda p:(p['pinned']=='1',p['created_at'],p['id']),reverse=True)


def get_post(user,pid):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); p,_=_post(b,a,pid)
        return _post_public(p)


def _post_payload(a,payload):
    kind=payload.get('kind')
    if kind not in KINDS or (a['role']=='student' and kind!='question'):
        raise PermissionError('자료와 과제는 선생님만 등록할 수 있어요.')
    visibility=payload.get('visibility','private' if kind=='question' else 'cohort')
    if visibility not in ('cohort','private') or (kind!='question' and visibility!='cohort'):
        raise ValueError('공개 범위를 확인해 주세요.')
    p=dict(kind=kind,title=_text(payload.get('title',''),'제목',160,True),
           body=_text(payload.get('body',''),'내용',10000),visibility=visibility,
           published='1' if a['role']=='student' else _flag(payload.get('published',False),'공개'),
           pinned='0' if a['role']=='student' else _flag(payload.get('pinned',False),'상단 고정'),
           comments_enabled=_flag(payload.get('comments_enabled',True),'댓글'),
           lesson_date=_date(payload.get('lesson_date',''),'수업일'),
           due_at=_due(payload.get('due_at','')) if kind=='assignment' else '',
           allow_late=_flag(payload.get('allow_late',False),'기한 후 제출') if kind=='assignment' else '0')
    if a['role']=='student':
        p.update(comments_enabled='1',lesson_date='')
    return p


def create_post(user,cid,payload,files,request_id):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); c=_cohort(b,a,cid,write=a['role']=='student')
        if a['role']=='teacher' and c['state'] not in ('draft','active'):
            raise PermissionError('자료와 과제 등록은 준비 중 또는 운영 중에 가능해요.')
        p=_post_payload(a,payload); uploads=_uploads(files)
        links=[] if a['role']=='student' else _links(payload.get('links',''))
        if not p['body'] and not uploads and not links:
            raise ValueError('내용, 파일, 링크 중 하나 이상 입력해 주세요.')
        rid=_identity(a,'post',cid,request_id); digest=_fingerprint(p|{'links':links},uploads)
        if not _existing(b,'as_posts',rid,digest):
            attached=_save_files(b,uploads)
            try:
                b.append('as_posts',dict(p,id=rid,cohort_id=cid,owner_id=c['owner_id'],author_id=a['id'],author_name=a['name'],
                                        attachments_json=_json(attached),links_json=_json(links),revision='1',resolved='0',
                                        created_at=db.now_str(),updated_at=db.now_str(),deleted_at='',request_hash=digest))
            except Exception:
                for f in attached: b.delete_file(f['file_id'])
                raise
    return _persist(rid)


def update_post(user,pid,payload,expected_revision):
    """Teacher changes metadata/text only; attachments remain unchanged."""
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _teacher(a); p,c=_post(b,a,pid)
        if c['state'] not in ('draft','active'):
            raise PermissionError('종료한 기수는 읽기 전용이에요. 운영 중으로 변경한 뒤 수정하세요.')
        _version(p,expected_revision)
        if p['kind']=='question':
            raise ValueError('학생 질문의 원문은 바꾸지 않아요. 댓글로 답변해 주세요.')
        changes=_post_payload(a,dict(payload,kind=p['kind']))
        changes['links_json']=_json(_links(payload.get('links','')))
        b.update('as_posts',pid,_bump(p,changes))
    return _persist(pid)


def delete_post(user,pid,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); p,c=_post(b,a,pid)
        if a['role']=='student':
            _cohort(b,a,c['id'],write=True)
            if p['kind']!='question' or p['author_id']!=a['id']:
                raise PermissionError('본인이 작성한 질문만 삭제할 수 있어요.')
            if any(r['post_id']==pid and not r['deleted_at'] for r in b.read('as_comments')):
                raise ValueError('답변이 있는 질문은 삭제하지 않아요. 선생님께 문의하세요.')
        elif c['state'] not in ('draft','active'):
            raise PermissionError('종료한 기수는 읽기 전용이에요.')
        _version(p,expected_revision)
        if p['kind']=='assignment' and any(r['post_id']==pid for r in b.read('as_submissions')):
            raise ValueError('제출물이 있는 과제는 삭제할 수 없어요. 필요하면 비공개로 전환하세요.')
        b.update('as_posts',pid,_bump(p,{'deleted_at':db.now_str()}))
    return _persist(pid)


def resolve_question(user,pid,resolved,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _teacher(a); p,_=_post(b,a,pid,write=True); _version(p,expected_revision)
        if p['kind']!='question': raise ValueError('질문을 선택해 주세요.')
        b.update('as_posts',pid,_bump(p,{'resolved':_flag(resolved,'해결 상태')}))
    return _persist(pid)


def comments(user,pid):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _post(b,a,pid)
        return [{k:r[k] for k in ('id','author_id','author_name','body','created_at','revision')}
                for r in sorted(b.read('as_comments'),key=lambda r:(r['created_at'],r['id']))
                if r['post_id']==pid and not r['deleted_at']]


def add_comment(user,pid,body,request_id):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); p,c=_post(b,a,pid,write=True)
        if p['comments_enabled']!='1': raise PermissionError('댓글이 닫힌 글이에요.')
        body=_text(body,'댓글',3000,True)
        rid=_identity(a,'comment',pid,request_id); digest=_fingerprint({'body':body},[])
        if not _existing(b,'as_comments',rid,digest):
            b.append('as_comments',dict(id=rid,cohort_id=c['id'],owner_id=c['owner_id'],post_id=pid,author_id=a['id'],
                                       author_name=a['name'],body=body,created_at=db.now_str(),updated_at=db.now_str(),
                                       revision='1',deleted_at='',request_hash=digest))
    return _persist(rid)


def delete_comment(user,rid,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); r=_row(b,'as_comments',rid); _post(b,a,r['post_id'],write=True); _version(r,expected_revision)
        if a['role']!='teacher' and a['id']!=r['author_id']:
            raise PermissionError('본인의 댓글만 삭제할 수 있어요.')
        b.update('as_comments',rid,_bump(r,{'deleted_at':db.now_str()}))
    return _persist(rid)


def _submission(b,a,rid):
    r=_row(b,'as_submissions',rid)
    p,c=_post(b,a,r['post_id'])
    if a['role']=='student' and r['student_id']!=a['id']:
        raise PermissionError('자신의 제출물만 확인할 수 있어요.')
    return r,p,c


def _submission_public(r):
    result={k:v for k,v in r.items() if k not in ('owner_id','attachments_json','request_hash')}
    result['attachments']=[{k:v for k,v in f.items() if k in ('name','size','mime')} for f in _array(r['attachments_json'])]
    return result


def submissions(user,pid):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); p,_=_post(b,a,pid)
        if p['kind']!='assignment': raise ValueError('과제를 선택해 주세요.')
        rows=[r for r in b.read('as_submissions') if r['post_id']==pid and
              (a['role']=='teacher' or r['student_id']==a['id'])]
        return [_submission_public(r) for r in sorted(rows,key=lambda r:(r['student_id'],-int(r['attempt'])))]


def submit(user,pid,body,files,request_id):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user)
        if a['role']!='student': raise PermissionError('과제는 배정된 학생 본인만 제출할 수 있어요.')
        p,c=_post(b,a,pid,write=True)
        if p['kind']!='assignment': raise ValueError('과제를 선택해 주세요.')
        body=_text(body,'답안',20000); uploads=_uploads(files)
        if not body and not uploads: raise ValueError('답안 또는 첨부파일을 입력해 주세요.')
        rid=_identity(a,'submission',pid,request_id); digest=_fingerprint({'body':body},uploads)
        found=_existing(b,'as_submissions',rid,digest)
        if not found:
            late=bool(p['due_at'] and db.now_str()>p['due_at'])
            if late and p['allow_late']!='1':
                raise PermissionError('제출 마감이 지났어요. 선생님께 기한 연장을 요청하세요.')
            attempts=[int(r['attempt']) for r in b.read('as_submissions') if r['post_id']==pid and r['student_id']==a['id']]
            attached=_save_files(b,uploads)
            try:
                b.append('as_submissions',dict(id=rid,cohort_id=c['id'],owner_id=c['owner_id'],post_id=pid,
                                              student_id=a['id'],student_name=a['name'],attempt=str(max(attempts,default=0)+1),
                                              body=body,attachments_json=_json(attached),assignment_revision=p['revision'],late='1' if late else '0',
                                              created_at=db.now_str(),feedback='',feedback_at='',revision='1',request_hash=digest))
            except Exception:
                for f in attached: b.delete_file(f['file_id'])
                raise
    return _persist(rid)


def feedback(user,rid,body,expected_revision):
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user); _teacher(a); r,p,c=_submission(b,a,rid); _version(r,expected_revision)
        if c['state']!='active': raise PermissionError('운영 중인 기수에서만 피드백을 수정할 수 있어요.')
        b.update('as_submissions',rid,{'feedback':_text(body,'피드백',5000),'feedback_at':db.now_str(),
                                       'revision':str(int(r['revision'])+1)})
    return _persist(rid)


def download_attachment(user,kind,rid,index):
    """No raw file ID accepted. Recheck membership, parent visibility and owner."""
    b=db._ready_backend()
    with b.lock:
        a=_actor(b,user)
        if kind=='post': r,_=_post(b,a,rid)
        elif kind=='submission': r,_,_=_submission(b,a,rid)
        else: raise PermissionError('파일 경로를 확인할 수 없어요.')
        fs=_array(r['attachments_json'])
        if not isinstance(index,int) or isinstance(index,bool) or index<0 or index>=len(fs):
            raise PermissionError('파일을 확인할 수 없어요.')
        f=fs[index]
        data=b.load_file(f['file_id'])
        if data is None or hashlib.sha256(data).hexdigest()!=f['sha256']:
            raise ValueError('파일을 불러오지 못했거나 원본과 달라요. 선생님께 확인해 주세요.')
        # Authorization is still serialized with membership changes on this server.
        return data,f['name'],f['mime']


def export_roster(user,cid):
    rows=[r for r in roster(user,cid) if r['selected']]
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(['학급','학번','이름'])
    for r in rows:
        def safe(s): return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
        w.writerow([safe(r['class']),safe(r['id']),safe(r['name'])])
    return buf.getvalue().encode('utf-8-sig')
