"""Authorization, immutable papers, marking, grading and per-student records.

One Streamlit backend process is the live authority. Answers enter its locked
store immediately; GitHubBackend batches commits. No per-student GitHub polling.
Only this module reads raw quiz tables. Student responses are allowlisted.
"""
from __future__ import annotations
from copy import deepcopy
import csv
import hashlib
import io
import json
import secrets
import uuid
import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS, DEFAULT_UNITS
from . import bank


class QuizError(ValueError): pass
class Conflict(QuizError): pass
class PendingSave(RuntimeError):
    def __init__(self):
        super().__init__("서버에는 반영되었지만 GitHub 영구 저장은 확인되지 않았어요. 입력을 유지하고 ‘저장 확인·재시도’를 눌러 주세요. 자동 저장도 재시도합니다.")


def _json(x): return json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
def _parse(v, default): return json.loads(v) if v else deepcopy(default)
def _stamp(): return db.now().isoformat(timespec="microseconds")
def _id(): return uuid.uuid4().hex


def _actor(user, backend, role=None):
    session = st.session_state.get("user") or {}
    if not isinstance(user, dict) or not user.get("id") or session.get("id") != user["id"]:
        raise PermissionError("로그인한 계정으로 다시 접속해 주세요.")
    u = next((x for x in backend.read("users") if x["id"] == user["id"]), None)
    if not u or u.get("role") not in ("teacher", "student") or u.get("must_change") == "1":
        raise PermissionError("계정과 비밀번호 변경 여부를 확인해 주세요.")
    if role and u["role"] != role:
        raise PermissionError("이 기능을 사용할 권한이 없습니다.")
    return u


def current_actor(user):
    backend = db._ready_backend()
    with backend.lock: return dict(_actor(user, backend))


def _quiz(backend, qid):
    row = next((x for x in backend.read("quiz_sets") if x["id"] == qid), None)
    if not row: raise QuizError("퀴즈를 찾을 수 없어요. 목록에서 다시 선택하세요.")
    return row


def _owner(user, backend, row):
    actor = _actor(user, backend, "teacher")
    if row["teacher_id"] != actor["id"]:
        raise PermissionError("담당 교사만 이 퀴즈를 관리할 수 있습니다.")
    return actor


def _target(actor, row):
    return next((x for x in _parse(row["targets_json"], [])
                 if x["id"] == actor["id"] and x["class"] == actor.get("class")), None)


def _student(user, backend, row):
    actor = _actor(user, backend, "student")
    if row["state"] not in ("open", "closed") or not _target(actor, row):
        raise PermissionError("내 반에 배포된 퀴즈만 열 수 있어요.")
    return actor


def _attempt(backend, quiz_id, student_id):
    return next((a for a in backend.read("quiz_attempts")
                 if a["quiz_id"] == quiz_id and a["student_id"] == student_id), None)


def _new_attempt(row, target):
    t = _stamp()
    return db._norm({"id": hashlib.sha256(f'{row["id"]}:{target["id"]}'.encode()).hexdigest(),
        "quiz_id": row["id"], "student_id": target["id"], "name": target["name"], "class": target["class"],
        "state": "working", "answers_json": "{}", "revision": "0", "started_at": t,
        "updated_at": t, "marks_json": "{}"}, "quiz_attempts")


def _put(backend, table, row):
    if not backend.update(table, row["id"], row): backend.append(table, row)
    db.invalidate(table)


def _durable(backend, table, row):
    if getattr(backend, "is_local", True): return True
    path = db.GitHubBackend._path(table, row)
    return path not in getattr(backend, "dirty", {})


def save_state(user, quiz_id):
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend, quiz_id); actor = _actor(user, backend)
        if actor["role"] == "teacher": _owner(user, backend, row)
        else: _student(user, backend, row)
        attempts = [a for a in backend.read("quiz_attempts") if a["quiz_id"] == quiz_id
                    and (actor["role"] == "teacher" or a["student_id"] == actor["id"])]
        ready = _durable(backend, "quiz_sets", row) and all(_durable(backend, "quiz_attempts", a) for a in attempts)
    return {"durable": ready, "local": getattr(backend, "is_local", True),
            "error": bool(getattr(backend, "last_error", "")), "last_saved": getattr(backend, "last_saved", "")}


def flush(user, quiz_id):
    # Always release store.lock before flush_lock; avoids writer deadlocks.
    save_state(user, quiz_id)
    try: db.flush_now()
    except Exception: raise PendingSave() from None
    if not save_state(user, quiz_id)["durable"]: raise PendingSave()


def _metadata(row):
    return {k: row[k] for k in ("id", "subject", "unit", "title", "state", "created_at", "parent_id", "round")}


def list_quizzes(user):
    backend = db._ready_backend()
    with backend.lock:
        actor = _actor(user, backend)
        rows = backend.read("quiz_sets")
        if actor["role"] == "teacher": rows = [q for q in rows if q["teacher_id"] == actor["id"]]
        else: rows = [q for q in rows if q["state"] in ("open", "closed") and _target(actor, q)]
        return sorted([_metadata(q) for q in rows], key=lambda q: (q["created_at"], q["id"]), reverse=True)


def roster(user):
    backend = db._ready_backend()
    with backend.lock:
        _actor(user, backend, "teacher")
        return sorted([{k:u.get(k, "") for k in ("id", "name", "class")} for u in backend.read("users")
                       if u["role"] == "student" and u.get("class") in CLASSES],
                      key=lambda u: (u["class"], u["id"]))


def units(subject):
    if subject not in SUBJECTS: return []
    raw = db.get_setting(f"units_{subject}")
    return [x.strip() for x in raw.splitlines() if x.strip()] if raw.strip() else bank.units(subject)


def revision(row):
    return hashlib.sha256(_json(row).encode()).hexdigest()


def teacher_paper(user, quiz_id):
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend, quiz_id); _owner(user, backend, row)
        return dict(_metadata(row), questions=_parse(row["question_json"], []),
                    targets=_parse(row["targets_json"], []), classes=_parse(row["classes_json"], []),
                    bank_unit=row["bank_unit"], revision=revision(row), generator=row["generator"])


def create_draft(user, subject, unit, *, bank_unit=None, parent_id="", focus=()):
    if subject not in SUBJECTS or unit not in units(subject): raise QuizError("과목과 단원을 선택하세요.")
    source_unit = bank_unit or unit
    backend = db._ready_backend()
    with backend.lock:
        actor = _actor(user, backend, "teacher")
        round_no = 1
        if parent_id:
            parent = _quiz(backend, parent_id); _owner(user, backend, parent)
            if parent["subject"] != subject or parent["unit"] != unit: raise QuizError("추가 퀴즈는 같은 과목·단원으로 만드세요.")
            round_no = int(parent["round"] or 1) + 1
        previous = [x for x in backend.read("quiz_sets") if x["teacher_id"] == actor["id"]
                    and x["subject"] == subject and x["unit"] == unit]
        exclude = {bank.fingerprint(q) for x in previous for q in _parse(x["question_json"], [])}
    questions = bank.generate(subject, source_unit, secrets.randbits(64), exclude=exclude, focus=focus)
    t, qid = _stamp(), _id()
    row = {"id": qid, "teacher_id": actor["id"], "subject": subject, "unit": unit, "bank_unit": source_unit,
           "title": f"{subject} · {unit} · {round_no}차 개념퀴즈", "state": "draft", "created_at": t, "updated_at": t,
           "parent_id": parent_id, "round": str(round_no), "question_json": _json(questions),
           "targets_json": "[]", "classes_json": "[]", "generator": bank.VERSION}
    with backend.lock:
        _actor(user, backend, "teacher"); _put(backend, "quiz_sets", row)
    # No remote call is needed merely to preview; publication has a flush gate.
    return qid


def edit_draft(user, quiz_id, title, questions, expected_revision):
    if not isinstance(title,str) or not title.strip() or len(title)>200: raise QuizError("제목은 1~200자로 입력하세요.")
    questions = bank.validate_questions(questions)
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend, quiz_id); _owner(user, backend, row)
        if row["state"] != "draft": raise QuizError("배포한 문제는 수정할 수 없어요. 새 퀴즈를 만들어 주세요.")
        if revision(row) != expected_revision: raise Conflict("다른 창에서 초안이 바뀌었어요. 다시 열어 확인하세요.")
        row.update(title=title.strip(), question_json=_json(questions), updated_at=_stamp())
        _put(backend,"quiz_sets",row)
    flush(user, quiz_id)


def publish(user, quiz_id, classes, student_ids=None, *, reviewed=False):
    if reviewed is not True: raise QuizError("문제·보기·정답을 검토한 뒤 확인란을 선택해 주세요.")
    if not classes or not set(classes).issubset(CLASSES): raise QuizError("배포할 학급을 선택하세요.")
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend,quiz_id); _owner(user,backend,row)
        if row["state"] == "open":
            # Retry after a failed flush must not reset answers or target lists.
            pass
        elif row["state"] != "draft": raise QuizError("이 퀴즈는 이미 종료되었습니다.")
        else:
            eligible = [u for u in backend.read("users") if u["role"] == "student" and u["class"] in classes]
            if student_ids is not None:
                if not student_ids or not set(student_ids).issubset({u["id"] for u in eligible}):
                    raise QuizError("선택한 반에 등록된 배포 대상 학생을 확인하세요.")
                eligible = [u for u in eligible if u["id"] in student_ids]
            if not eligible: raise QuizError("배포할 반에 등록된 학생이 없습니다. 교사전용에서 학생을 먼저 등록하세요.")
            bank.validate_questions(_parse(row["question_json"],[]))
            targets = [{k:u[k] for k in ("id","name","class")} for u in sorted(eligible,key=lambda u:(u['class'],u['id']))]
            row.update(state="open", targets_json=_json(targets), classes_json=_json(sorted({u["class"] for u in targets})), updated_at=_stamp())
            _put(backend,"quiz_sets",row)
    flush(user,quiz_id)


def student_paper(user, quiz_id):
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend,quiz_id); actor = _student(user,backend,row)
        a = _attempt(backend,quiz_id,actor["id"])
        ready = _durable(backend,"quiz_sets",row)
        if not ready: raise QuizError("선생님의 퀴즈 배포를 저장 중입니다. 잠시 뒤 새로고침해 주세요.")
        questions = _parse(row["question_json"],[])
        out = dict(_metadata(row), questions=[{k:q[k] for k in ("id","prompt","options")} for q in questions],
                   answers=_parse(a["answers_json"],{}) if a else {}, revision=int(a["revision"]) if a else 0,
                   attempt_state=a["state"] if a else "working", started=bool(a),
                   saved=bool(a and _durable(backend,"quiz_attempts",a)), editable=(row["state"]=="open" and (not a or a["state"]=="working")),
                   released=False, submitted_at=a["submitted_at"] if a else "")
        if a and a["state"] == "graded" and a["released_at"] and _durable(backend,"quiz_attempts",a):
            out.update(released=True, score=int(a["score"]), marks=_parse(a["marks_json"],{}),
                       solutions=[{k:q[k] for k in ("id","answer","explanation")} for q in questions])
        return out


def save_answer(user, quiz_id, question_id, choice, expected_revision):
    if choice is not None and (type(choice) is not int or not 0<=choice<4): raise QuizError("보기 번호를 확인하세요.")
    backend = db._ready_backend()
    with backend.lock:
        row = _quiz(backend,quiz_id); actor = _student(user,backend,row)
        import realtime
        if realtime.is_locked(actor["class"]): raise QuizError("선생님 설명 시간에는 답을 바꿀 수 없어요.")
        if not _durable(backend,"quiz_sets",row): raise QuizError("배포 저장이 끝난 뒤 답을 선택하세요.")
        qids = {q["id"] for q in _parse(row["question_json"],[])}
        if question_id not in qids: raise QuizError("문항을 확인하세요.")
        a = _attempt(backend,quiz_id,actor["id"]) or _new_attempt(row,actor)
        if row["state"] != "open" or a["state"] != "working": raise QuizError("제출·채점·종료된 퀴즈의 답은 변경할 수 없어요.")
        if type(expected_revision) is not int or expected_revision != int(a["revision"]):
            raise Conflict("다른 창에서 답이 바뀌었어요. 저장된 답을 다시 불러온 뒤 선택하세요.")
        answers = _parse(a["answers_json"],{})
        if answers.get(question_id) == choice: return int(a["revision"])
        if choice is None: answers.pop(question_id, None)
        else: answers[question_id] = choice
        a.update(answers_json=_json(answers), revision=str(int(a['revision'])+1), updated_at=_stamp())
        _put(backend,"quiz_attempts",a)
        return int(a["revision"])


def submit(user, quiz_id, *, allow_blank=False):
    backend = db._ready_backend()
    with backend.lock:
        row=_quiz(backend,quiz_id); actor=_student(user,backend,row)
        import realtime
        if realtime.is_locked(actor['class']): raise QuizError("선생님 설명 시간이 끝나면 제출하세요.")
        a = _attempt(backend,quiz_id,actor['id']) or _new_attempt(row,actor)
        if a['state']=='graded': raise QuizError("이미 선생님이 채점한 답안입니다.")
        if a['state']=='working':
            if row['state']!='open': raise QuizError("퀴즈가 종료되었습니다.")
            if len(_parse(a['answers_json'],{}))<10 and allow_blank is not True: raise QuizError("아직 선택하지 않은 문항이 있어요.")
            a.update(state='submitted', submitted_at=_stamp(), updated_at=_stamp(), revision=str(int(a['revision'])+1))
            _put(backend,'quiz_attempts',a)
    flush(user,quiz_id)


def _grade(backend,row,target,teacher,include_incomplete):
    a=_attempt(backend,row['id'],target['id'])
    if a and a['state']=='graded': return 'already'
    if not a: a=_new_attempt(row,target)
    answers=_parse(a['answers_json'],{})
    if not include_incomplete and a['state']!='submitted' and len(answers)<10: return 'skipped'
    marks={q['id']: (answers.get(q['id'])==q['answer']) for q in _parse(row['question_json'],[])}
    a.update(state='graded', graded_at=_stamp(), graded_by=teacher['id'], marks_json=_json(marks),
             score=str(sum(marks.values())*10), updated_at=_stamp(), revision=str(int(a['revision'])+1))
    _put(backend,'quiz_attempts',a)
    return 'graded'


def grade(user, quiz_id, student_ids=None, *, include_incomplete=False):
    backend=db._ready_backend()
    with backend.lock:
        row=_quiz(backend,quiz_id); teacher=_owner(user,backend,row)
        if row['state'] not in ('open','closed'): raise QuizError("배포한 퀴즈만 채점할 수 있어요.")
        targets=_parse(row['targets_json'],[])
        if student_ids is not None:
            if not student_ids or not set(student_ids).issubset({t['id'] for t in targets}): raise QuizError("채점 대상 학생을 확인하세요.")
            targets=[t for t in targets if t['id'] in student_ids]
        result={'graded':0,'skipped':0,'already':0}
        for target in targets: result[_grade(backend,row,target,teacher,include_incomplete)] += 1
    flush(user,quiz_id)
    return result


def release(user, quiz_id, student_ids=None):
    backend=db._ready_backend()
    with backend.lock:
        row=_quiz(backend,quiz_id); _owner(user,backend,row)
        targets={t['id'] for t in _parse(row['targets_json'],[])}
        if student_ids is not None and not set(student_ids).issubset(targets): raise QuizError("공개할 학생을 확인하세요.")
        count=0
        for a in backend.read('quiz_attempts'):
            if a['quiz_id']!=quiz_id or (student_ids is not None and a['student_id'] not in student_ids): continue
            if a['state']=='graded' and not a['released_at']:
                a.update(released_at=_stamp(),updated_at=_stamp()); _put(backend,'quiz_attempts',a); count+=1
    flush(user,quiz_id)
    return count


def close(user, quiz_id):
    backend=db._ready_backend()
    with backend.lock:
        row=_quiz(backend,quiz_id); _owner(user,backend,row)
        if row['state'] not in ('open','closed'): raise QuizError("배포한 퀴즈만 종료할 수 있어요.")
        row.update(state='closed',updated_at=_stamp()); _put(backend,'quiz_sets',row)
    flush(user,quiz_id)


def dashboard(user, quiz_id, class_filter='전체'):
    backend=db._ready_backend()
    with backend.lock:
        row=_quiz(backend,quiz_id); _owner(user,backend,row)
        targets=[t for t in _parse(row['targets_json'],[]) if class_filter=='전체' or t['class']==class_filter]
        attempts={a['student_id']:a for a in backend.read('quiz_attempts') if a['quiz_id']==quiz_id}
        paper=_parse(row['question_json'],[])
        students=[]
        for t in targets:
            a=attempts.get(t['id'])
            answers=_parse(a['answers_json'],{}) if a else {}
            students.append(dict(t, answers=answers, count=len(answers), state=a['state'] if a else 'not_started',
                score=int(a['score']) if a and a['state']=='graded' else None,
                marks=_parse(a['marks_json'],{}) if a and a['state']=='graded' else {},
                released=bool(a and a['released_at']), saved=bool(a and _durable(backend,'quiz_attempts',a)),
                updated_at=a['updated_at'] if a else '', revision=int(a['revision']) if a else 0))
        graded=[s for s in students if s['state']=='graded']
        stats=[]
        for q in paper:
            wrong=sum(not s['marks'][q['id']] for s in graded)
            blank=sum(q['id'] not in s['answers'] for s in graded)
            stats.append({'question':q['id'],'concept':q['concept'],'graded':len(graded),'wrong':wrong,
                          'wrong_choice':wrong-blank,'blank':blank,'correct':len(graded)-wrong,
                          'ungraded':len(students)-len(graded)})
        return {'quiz':_metadata(row), 'students':students, 'stats':stats,
                'questions':paper, 'graded':len(graded), 'responding':sum(s['count']>0 for s in students),
                'mean':sum(s['score'] for s in graded)/len(graded) if graded else None,
                'refreshed_at':_stamp()}


def recommend(user, quiz_id, threshold=60):
    if type(threshold) is not int or not 0<=threshold<=100: raise QuizError("점수 기준을 확인하세요.")
    board=dashboard(user,quiz_id)
    ids=[s['id'] for s in board['students'] if s['score'] is not None and s['score']<threshold]
    concepts=list(dict.fromkeys(s['concept'] for s in sorted(board['stats'],key=lambda x:x['wrong'],reverse=True) if s['wrong']>0))[:3]
    return ids, concepts


def history(user, student_id):
    backend=db._ready_backend()
    with backend.lock:
        actor=_actor(user,backend)
        if actor['role']=='student' and actor['id']!=student_id: raise PermissionError("본인의 퀴즈 기록만 볼 수 있어요.")
        quizzes={q['id']:q for q in backend.read('quiz_sets') if actor['role']=='student' or q['teacher_id']==actor['id']}
        out=[]
        for a in backend.read('quiz_attempts'):
            q=quizzes.get(a['quiz_id'])
            if a['student_id']!=student_id or not q: continue
            if actor['role']=='student' and not _target(actor,q): continue
            released=bool(a['state']=='graded' and a['released_at'] and _durable(backend,'quiz_attempts',a))
            x=dict(_metadata(q),student_id=student_id,name=a['name'],class_name=a['class'],
                   attempt_state=a['state'],answers=_parse(a['answers_json'],{}),updated_at=a['updated_at'],
                   submitted_at=a['submitted_at'],graded_at=a['graded_at'],released=released,
                   storage_path=db.GitHubBackend._path('quiz_attempts',a) if actor['role']=='teacher' else '')
            if actor['role']=='teacher' or released:
                x.update(score=int(a['score']) if a['score'] else None,marks=_parse(a['marks_json'],{}))
            out.append(x)
        return sorted(out,key=lambda x:x['updated_at'],reverse=True)


def _csv_safe(v):
    s=str(v)
    return "'"+s if s and s[0] in '=+-@\t\r' else s


def export_dashboard(user,quiz_id):
    board=dashboard(user,quiz_id)
    f=io.StringIO(newline=''); w=csv.writer(f)
    w.writerow(['학급','학번','이름','응답수','상태','점수']+[f'{i}번' for i in range(1,11)])
    for s in board['students']:
        cells=[]
        for q in board['questions']:
            v=s['answers'].get(q['id']); label=str(v+1) if v is not None else '미응답'
            if s['state']=='graded': label+=(' O' if s['marks'][q['id']] else ' X')
            cells.append(label)
        w.writerow([_csv_safe(v) for v in [s['class'],s['id'],s['name'],s['count'],s['state'],s['score'] if s['score'] is not None else '',*cells]])
    return f.getvalue().encode('utf-8-sig')
