"""Authoritative multiplayer state on the dashboard's shared, locked backend.

A single Streamlit server is required, as for the existing dashboard. Durable
GitHub commits are batched by storage.py; no browser polls GitHub directly.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
import secrets
import time
import uuid

import streamlit as st
import storage as db
import realtime as rt
from . import engine

ReviewError = engine.ReviewError


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _actor(user, backend, role=None, write=False):
    session = st.session_state.get("user") or {}
    if not isinstance(user, dict) or session.get("id") != user.get("id"):
        raise PermissionError("로그인한 계정으로 다시 접속해 주세요.")
    actor = next((u for u in backend.read("users") if u["id"] == user.get("id")), None)
    if not actor or actor.get("role") not in ("student", "teacher") or actor.get("must_change") == "1":
        raise PermissionError("계정과 비밀번호 변경 여부를 확인해 주세요.")
    if role and actor["role"] != role:
        raise PermissionError("교사만 게임을 설정하고 전체 결과를 볼 수 있습니다.")
    if actor["role"] == "student" and rt.is_locked(actor.get("class", "")):
        raise PermissionError("선생님 설명 시간이에요. 잠금 해제 후 이어 가세요.")
    return actor


def teacher(user):
    backend = db._ready_backend()
    with backend.lock:
        return _actor(user, backend, "teacher")


def _put(b, table, row):
    row = db._norm(row, table)
    if not b.update(table, row["id"], row):
        b.append(table, row)
    db.invalidate(table)


def _room(b, code):
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ReviewError("6자리 참여코드를 입력해 주세요.")
    row = next((r for r in b.read("review_rooms") if r["code"] == code), None)
    if not row:
        raise ReviewError("게임방을 찾을 수 없어요. 참여코드를 확인해 주세요.")
    return row


def _owner(actor, room):
    if actor["role"] != "teacher" or actor["id"] != room["owner_id"]:
        raise PermissionError("이 게임을 만든 교사만 관리할 수 있습니다.")


def _target(actor, room):
    if not any(t["id"] == actor["id"] and t["class"] == actor.get("class") for t in json.loads(room["targets_json"])):
        raise PermissionError("선생님이 지정한 반의 학생만 참여할 수 있습니다.")


def _attempts(b, room):
    rows = [deepcopy(a) for a in b.read("review_attempts") if a["room_id"] == room["id"]]
    for row in rows:
        row["answers"] = json.loads(row["answers_json"])
    return rows


def _save_attempt(b, a):
    a["answers_json"] = _json(a["answers"])
    a["updated_at"] = db.now_str()
    a["revision"] = str(int(a["revision"])+1)
    _put(b, "review_attempts", a)


def _finish(b, room):
    # Unclaimed end-of-round rewards use the first option, once, on the server.
    for a in _attempts(b, room):
        if a["answers"] and engine.claim_reward(a["answers"][-1], 0):
            _save_attempt(b, a)
    room.update(status="ended", ended_at=str(time.time()))
    _put(b, "review_rooms", room)


def _expire(b, room):
    if room["status"] != "running":
        return
    attempts = _attempts(b, room)
    count = len(json.loads(room["questions_json"]))
    finished = attempts and all(len(a["answers"]) == count and not a["answers"][-1].get("reward_pending") for a in attempts)
    if time.time() >= float(room["started_at"])+int(room["duration"]) or finished:
        _finish(b, room)


def create(user, *, title, questions, mode, classes, duration, source=None):
    questions = engine.validate_questions(questions)
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
        raise ReviewError("제목을 1~160자로 입력해 주세요.")
    if mode not in engine.MODES or type(duration) is not int or not 60 <= duration <= 1800:
        raise ReviewError("게임 모드와 제한시간(1~30분)을 확인해 주세요.")
    if not classes or not isinstance(classes, list):
        raise ReviewError("참여할 반을 선택해 주세요.")
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, "teacher")
        targets = [{k: u.get(k, "") for k in ("id", "name", "class")} for u in b.read("users")
                   if u["role"] == "student" and u.get("class") in classes]
        if not targets:
            raise ReviewError("선택한 반에 등록된 학생이 없습니다. 학생관리에서 확인해 주세요.")
        codes = {r["code"] for table in ("review_rooms", "quizpop_rooms", "reward_rooms") for r in b.read(table)}
        for _ in range(100):
            code = str(secrets.randbelow(900000)+100000)
            if code not in codes:
                break
        else:
            raise ReviewError("참여코드를 만들지 못했습니다. 다시 시도해 주세요.")
        row = dict(id=uuid.uuid4().hex, owner_id=actor["id"], code=code, title=title.strip(), mode=mode,
                   classes_json=_json(classes), targets_json=_json(targets), questions_json=_json(questions),
                   source_json=_json(source or {}), status="lobby", duration=str(duration),
                   created_at=db.now_str(), started_at="", ended_at="", review_qid="", reveal="0")
        _put(b, "review_rooms", row)
        return code


def history(user):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, "teacher")
        return sorted([{k: r[k] for k in ("code", "title", "mode", "status", "created_at")}
                       for r in b.read("review_rooms") if r["owner_id"] == actor["id"]],
                      key=lambda r: r["created_at"], reverse=True)


def paper(user, code):
    b = db._ready_backend()
    with b.lock:
        room = _room(b, code)
        _owner(_actor(user, b, "teacher"), room)
        return {"title": room["title"], "questions": json.loads(room["questions_json"]), "source": json.loads(room["source_json"])}


def join(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, "student")
        room = _room(b, code)
        _target(actor, room)
        _expire(b, room)
        existing = next((a for a in _attempts(b, room) if a["student_id"] == actor["id"]), None)
        if existing:
            return existing["id"]
        if room["status"] != "lobby":
            raise ReviewError("이미 시작한 게임이에요. 참여했던 학생은 다시 접속할 수 있어요.")
        attempts = _attempts(b, room)
        teams = ["핑크 팀", "민트 팀"]
        team = min(teams, key=lambda t: sum(a["team"] == t for a in attempts)) if room["mode"] == "team" else ""
        a = dict(id=hashlib.sha256(f'{room["id"]}:{actor["id"]}'.encode()).hexdigest(), room_id=room["id"],
                 student_id=actor["id"], name=actor["name"], **{"class": actor["class"]},
                 alias=f"플레이어 {len(attempts)+1:02}", team=team, answers_json="[]", joined_at=db.now_str(),
                 updated_at=db.now_str(), revision="0")
        _put(b, "review_attempts", a)
        return a["id"]


def control(user, code, action, qid="", reveal=False):
    b = db._ready_backend()
    with b.lock:
        room = _room(b, code)
        _owner(_actor(user, b, "teacher"), room)
        _expire(b, room)
        if action == "start":
            if room["status"] != "lobby":
                return
            if not _attempts(b, room):
                raise ReviewError("학생이 한 명 이상 입장하면 시작할 수 있어요.")
            room.update(status="running", started_at=str(time.time()))
            _put(b, "review_rooms", room)
        elif action == "end":
            if room["status"] != "ended":
                _finish(b, room)
        elif action == "review":
            if room["status"] != "ended":
                raise ReviewError("게임 종료 후 함께 풀기를 열 수 있어요.")
            if qid and qid not in [q["id"] for q in json.loads(room["questions_json"])]:
                raise ReviewError("문제를 찾을 수 없어요.")
            room.update(review_qid=qid, reveal="1" if reveal else "0")
            _put(b, "review_rooms", room)
        else:
            raise ReviewError("지원하지 않는 동작입니다.")


def submit(user, code, index, choice, kind="answer"):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b, "student", write=True)
        room = _room(b, code)
        _target(actor, room)
        _expire(b, room)
        if room["status"] != "running":
            raise ReviewError("게임이 끝났거나 아직 시작하지 않았어요.")
        a = next((x for x in _attempts(b, room) if x["student_id"] == actor["id"]), None)
        if a is None:
            raise ReviewError("먼저 게임에 입장해 주세요.")
        if type(index) is not int:
            raise ReviewError("문제 번호를 확인해 주세요.")
        if kind == "answer":
            if 0 <= index < len(a["answers"]) and a["answers"][index]["choice"] == choice:
                return  # same request after reconnect: no duplicate answer/reward
            record = engine.answer_record(room["mode"], json.loads(room["questions_json"]), a["answers"],
                                          index, choice, time.time(), secrets.SystemRandom())
            a["answers"].append(record)
        elif kind == "reward":
            if index != len(a["answers"])-1 or index < 0:
                raise ReviewError("현재 보상을 선택해 주세요.")
            if not engine.claim_reward(a["answers"][index], choice):
                return
        else:
            raise ReviewError("지원하지 않는 동작입니다.")
        _save_attempt(b, a)
        _expire(b, room)


def _public_question(q, reveal=False):
    keys = ["id", "prompt", "options", "concept"]
    if reveal:
        keys += ["answer", "explanation"]
    return {k: deepcopy(q[k]) for k in keys}


def snapshot(user, code):
    b = db._ready_backend()
    with b.lock:
        actor = _actor(user, b)
        room = _room(b, code)
        if actor["role"] == "teacher":
            _owner(actor, room)
        else:
            _target(actor, room)
        _expire(b, room)
        qs, attempts = json.loads(room["questions_json"]), _attempts(b, room)
        stats = engine.report(qs, attempts)
        view = {k: room[k] for k in ("code", "title", "mode", "status", "created_at")}
        view.update(role=actor["role"], duration=int(room["duration"]), total=len(qs), participants=len(attempts),
                    remaining=max(0, math_ceil(float(room["started_at"])+int(room["duration"])-time.time())) if room["started_at"] else int(room["duration"]),
                    mode_info=engine.MODES[room["mode"]], server_time=time.time(), teams=stats["teams"],
                    leaderboard=[{k: r[k] for k in ("alias", "team", "score", "correct", "answered", "rank")}
                                 for r in stats["rows"]] if room["mode"] != "practice" else [])
        if room["review_qid"]:
            q = next(q for q in qs if q["id"] == room["review_qid"])
            view["review"] = _public_question(q, reveal=room["reveal"] == "1")
            view["review"]["number"] = qs.index(q)+1
        if actor["role"] == "teacher":
            view["report"] = stats
            view["expected"] = len(json.loads(room["targets_json"]))
            # Answers/solutions enter the teacher component only after the round.
            if room["status"] == "ended":
                view["paper"] = qs
                view["individuals"] = [{"student_id": a["student_id"], "answers": [
                    {k: x[k] for k in ("qid", "choice", "correct", "points")} for x in a["answers"]]} for a in attempts]
        else:
            a = next((x for x in attempts if x["student_id"] == actor["id"]), None)
            if a is None:
                raise ReviewError("먼저 게임에 입장해 주세요.")
            view.update(alias=a["alias"], team=a["team"], revision=int(a["revision"]), **engine.summary(a, qs))
            rank_row = next(r for r in stats["rows"] if r["student_id"] == actor["id"])
            view["rank"] = rank_row["rank"]
            if a["answers"]:
                last = a["answers"][-1]
                view["feedback"] = {k: last[k] for k in ("index", "choice", "correct", "points", "reward_pending", "bonus")}
                view["feedback"]["question"] = _public_question(qs[last["index"]], reveal=True)
            if room["status"] == "running" and len(a["answers"]) < len(qs):
                view["question"] = _public_question(qs[len(a["answers"])])
                view["index"] = len(a["answers"])
            if room["status"] == "ended":
                view["answers"] = [{**_public_question(q, reveal=True), "choice": a["answers"][i]["choice"] if i < len(a["answers"]) else None}
                                   for i, q in enumerate(qs)]
        return view


def math_ceil(number):
    import math
    return math.ceil(number)


def save_status(user, code):
    b = db._ready_backend()
    with b.lock:
        actor, room = _actor(user, b), _room(b, code)
        if actor["role"] == "teacher":
            _owner(actor, room)
        else:
            _target(actor, room)
        attempts = [a for a in _attempts(b, room) if actor["role"] == "teacher" or a["student_id"] == actor["id"]]
        paths = [db.GitHubBackend._path("review_rooms", room)] + [db.GitHubBackend._path("review_attempts", a) for a in attempts]
        dirty = getattr(b, "dirty", {})
        sids = {a["student_id"] for a in attempts}
        archive_dirty = any(t == "review_attempts" and sid in sids for t, sid in getattr(b, "archive_dirty", {}))
        pending = any(p in dirty for p in paths) or archive_dirty
        # A queued encrypted archive is not yet durable either.
        if getattr(b, "archive_crypto", None):
            prefixes = [b.archive_crypto.student_dir(sid)+"/" for sid in sids]
            pending |= any(any(p.startswith(prefix) for prefix in prefixes) for p in getattr(b, "archive_pending", {}))
        return dict(local=b.is_local, durable=not pending, error=bool(getattr(b, "last_error", "")))


def flush(user, code):
    save_status(user, code)  # authorize before requesting a flush
    try:
        db.flush_now()  # outside backend.lock to preserve the existing lock order
    except Exception:
        status = save_status(user, code)
        status.update(error=True, durable=False)
        return status
    return save_status(user, code)


def csv_export(user, code):
    teacher(user)
    view = snapshot(user, code)
    rows = view["report"]["rows"]
    out = io.StringIO()
    keys = ["rank", "student_id", "name", "class", "team", "answered", "correct", "wrong", "unanswered", "accuracy", "score"]
    writer = csv.writer(out)
    writer.writerow(["등수", "학번", "이름", "반", "팀", "푼 문제", "정답", "오답", "미응답", "정답률(응답 기준)", "게임점수"])
    def cell(x):
        text = str(x)
        return "'"+text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text
    for r in rows:
        writer.writerow([cell(r[k]) for k in keys])
    return out.getvalue().encode("utf-8-sig")
