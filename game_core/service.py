"""Permission-checked game persistence through the existing GitHub backend.

Raw keys never go through student projections. A single profile row contains
lesson progress and its reward ledger: a retry cannot mint a second reward.
The existing backend is single-server, batched GitHub storage, not a database.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import PurePath
import secrets
import uuid
import streamlit as st
import storage as db
import realtime as rt
from config import CLASSES
from . import bank, engine
from .curriculum import EDITIONS, DEFAULT_EDITION, topic
from .schema import TABLES

GameError=engine.GameError
Conflict=engine.Conflict

def _json(v):return json.dumps(v,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def _load(v,default):return json.loads(v) if v else deepcopy(default)
def _stamp():return db.now().isoformat(timespec="microseconds")
def _id():return uuid.uuid4().hex

def _actor(user,b,role=None,write=False):
    session=st.session_state.get("user") or {}
    if not isinstance(user,dict) or session.get("id")!=user.get("id"):
        raise PermissionError("현재 로그인한 계정으로 다시 열어 주세요.")
    u=next((r for r in b.read("users") if r["id"]==user.get("id")),None)
    if not u or u.get("role") not in ("teacher","student") or u.get("must_change")=="1":
        raise PermissionError("계정과 비밀번호 변경 여부를 확인해 주세요.")
    if role and u["role"]!=role:raise PermissionError("이 기능을 사용할 권한이 없습니다.")
    if u["role"]=="student" and u.get("class") not in CLASSES:raise PermissionError("학급 배정을 확인해 주세요.")
    if write and u["role"]=="student" and rt.is_locked(u.get("class","")):
        raise PermissionError("지금은 선생님 설명 시간입니다. 화면 잠금 해제 후 이어 가세요.")
    return u


def _target(user,b,student_id=None,write=False):
    u=_actor(user,b,write=write)
    sid=student_id or u["id"]
    if u["role"]=="student" and sid!=u["id"]:raise PermissionError("다른 학생의 성장 기록은 열 수 없습니다.")
    target=next((r for r in b.read("users") if r["id"]==sid and r["role"]=="student"),None)
    if not target:raise GameError("학생 계정을 선택해 주세요. 교사는 미리보기로 게임을 확인할 수 있습니다.")
    return target


def _row(b,u):
    row=next((r for r in b.read("game_profiles") if r["student_id"]==u["id"]),None)
    if row:return deepcopy(row)
    return dict(id=hashlib.sha256(u["id"].encode()).hexdigest(),student_id=u["id"],name=u.get("name",""),
                **{"class":u.get("class","")},state_json=_json(engine.new_profile()),revision="0",updated_at="")


def _put(b,table,row):
    row=db._norm(row,table)
    if not b.update(table,row["id"],row):b.append(table,row)
    db.invalidate(table)


def _mutate(user,revision,fn):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"student",write=True);row=_row(b,u)
        if type(revision) is not int or revision!=int(row["revision"]):
            raise Conflict("다른 창에서 학습 기록이 바뀌었습니다. 새로고침 후 이어 가세요.")
        p=_load(row["state_json"],engine.new_profile());result=fn(p,b,u)
        row.update(state_json=_json(p),revision=str(revision+1),updated_at=_stamp(),name=u.get("name",""))
        row["class"]=u.get("class","");_put(b,"game_profiles",row)
    return result


def profile(user,student_id=None):
    b=db._ready_backend()
    with b.lock:
        u=_target(user,b,student_id);row=_row(b,u);p=_load(row["state_json"],engine.new_profile())
        return dict(student={k:u.get(k,"") for k in ("id","name","class")},revision=int(row["revision"]),
                    coins=engine.wallet(p),earned=p["earned"],owned=p["owned"],equipped=p["equipped"],
                    sessions=[engine.public_session(s) for s in p["sessions"]],active_id=p["active_id"],
                    growth=engine.growth(p),feedback=p.get("feedback",[]),point_requests=p.get("point_requests",{}))


def roster(user):
    b=db._ready_backend()
    with b.lock:
        _actor(user,b,"teacher")
        return sorted([{k:u.get(k,"") for k in ("id","name","class")} for u in b.read("users") if u["role"]=="student"],key=lambda u:(u["class"],u["id"]))


def edition():
    value=db.get_setting("game_textbook_edition")
    return value if value in EDITIONS else DEFAULT_EDITION


def set_edition(user,value):
    b=db._ready_backend()
    with b.lock:
        _actor(user,b,"teacher",write=True)
        if value not in EDITIONS:raise GameError("교과서 대표저자를 선택해 주세요.")
        db.set_setting("game_textbook_edition",value)


def _mission(b,mid):
    m=next((r for r in b.read("game_missions") if r["id"]==mid),None)
    if not m:raise GameError("미션을 찾을 수 없습니다.")
    return m


def _mission_target(u,m):
    return any(t["id"]==u["id"] and t["class"]==u.get("class") for t in _load(m["targets_json"],[]))


def start(user,topic_id,mode,revision,mission_id="",level="천천히"):
    topic(topic_id)
    def action(p,b,u):
        if mission_id:
            m=_mission(b,mission_id)
            if m["active"]!="1" or not _mission_target(u,m):raise PermissionError("현재 내 반에 배포된 미션만 시작할 수 있습니다.")
            if m["topic_id"]!=topic_id:raise GameError("선생님이 지정한 주제로 시작해 주세요.")
        custom=[_load(r["question_json"],{}) for r in b.read("game_questions") if r["published"]=="1" and r["topic_id"]==topic_id]
        # Numbers are selected on the server; seeds and answer keys stay server-side.
        questions=bank.generate(topic_id,secrets.randbits(64),custom=custom,level=level)
        return engine.start(p,topic_id,mode,questions,_stamp(),mission_id,level)
    return _mutate(user,revision,action)


def resume(user,sid,revision):
    def action(p,b,u):
        s=engine.active(p,sid)
        if s["status"]!="done":s["status"]="working"
        p["active_id"]=sid
    _mutate(user,revision,action)


def lesson_action(user,sid,index,revision,kind,**args):
    def action(p,b,u):
        s=engine.active(p,sid)
        if s.get("mission_id"):
            m=_mission(b,s["mission_id"])
            if not _mission_target(u,m):raise PermissionError("학급 배정이 바뀌어 이 미션을 이어 갈 수 없습니다.")
            # Closing a mission hides new starts, but preserves the learner's existing session.
        if kind=="answer":result=engine.submit(s,index,args.get("choice"))
        elif kind=="hint":result=engine.hint(s,index)
        elif kind=="reveal":result=engine.reveal(s,index)
        elif kind=="reflect_solution":result=engine.reflect_solution(s,index,args.get("text",""))
        elif kind=="advance":result=engine.advance(p,s,index,_stamp(),args.get("placement"),args.get("direction","east"))
        elif kind=="switch":result=engine.switch(s,args.get("mode"))
        elif kind=="pause":
            if s["status"]!="done":s["status"]="paused"
            p["active_id"]="";result=None
        elif kind=="reflection":
            if s["status"]!="done":raise GameError("5문제를 마친 뒤 한 줄 기록을 남길 수 있어요.")
            text=str(args.get("text","")).strip()
            if len(text)>1500:raise GameError("한 줄 기록은 1500자 이하로 적어 주세요.")
            s["reflection"]=text;result=None
        else:raise GameError("알 수 없는 학습 동작입니다.")
        s["updated_at"]=_stamp()
        return result
    return _mutate(user,revision,action)


def buy(user,item_id,revision):
    return _mutate(user,revision,lambda p,b,u:engine.buy(p,item_id))


def create_mission(user,title,topic_id,classes,allow_points=False):
    topic(topic_id);title=str(title).strip()
    if not 1<=len(title)<=120:raise GameError("미션 제목은 1~120자로 입력하세요.")
    if not classes or any(c not in CLASSES for c in classes):raise GameError("대상 학급을 선택해 주세요.")
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True)
        targets=[{k:s.get(k,"") for k in ("id","name","class")} for s in b.read("users") if s["role"]=="student" and s["class"] in classes]
        if not targets:raise GameError("선택한 학급에 등록된 학생이 없습니다.")
        row=dict(id=_id(),owner_id=u["id"],title=title,topic_id=topic_id,targets_json=_json(targets),active="1",allow_points="1" if allow_points else "0",created_at=_stamp())
        _put(b,"game_missions",row);return row["id"]


def missions(user):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b);rows=b.read("game_missions")
        if u["role"]=="teacher":rows=[m for m in rows if m["owner_id"]==u["id"]]
        else:rows=[m for m in rows if m["active"]=="1" and _mission_target(u,m)]
        return [dict({k:m[k] for k in ("id","title","topic_id","active","allow_points","created_at")},count=len(_load(m["targets_json"],[]))) for m in rows]


def close_mission(user,mid):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True);m=_mission(b,mid)
        if m["owner_id"]!=u["id"]:raise PermissionError("미션 작성 교사만 변경할 수 있습니다.")
        m["active"]="0";_put(b,"game_missions",m)


def teacher_questions(user,topic_id):
    topic(topic_id);b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher")
        return [dict(id=r["id"],published=r["published"]=="1",revision=int(r["revision"]),question=_load(r["question_json"],{})) for r in b.read("game_questions") if r["owner_id"]==u["id"] and r["topic_id"]==topic_id]


def save_question(user,question,*,qid="",revision=0,published=False,reviewed=False):
    q=bank.validate(question)
    if published and not reviewed:raise GameError("정답과 해설을 직접 검토한 뒤 공개해 주세요.")
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True)
        old=next((r for r in b.read("game_questions") if r["id"]==qid),None) if qid else None
        if qid and (not old or old["owner_id"]!=u["id"]):raise PermissionError("작성 교사만 문항을 수정할 수 있습니다.")
        if old and int(old["revision"])!=revision:raise Conflict("문항이 다른 창에서 변경되었습니다. 다시 열어 주세요.")
        q["source"]="교사 검토 문항" if published else "교사 작성 초안"
        row=dict(id=qid or _id(),owner_id=u["id"],topic_id=q["topic_id"],question_json=_json(q),published="1" if published else "0",revision=str(revision+1),updated_at=_stamp())
        _put(b,"game_questions",row);return row["id"]


def import_questions(user,questions):
    validated=[bank.validate(q) for q in questions]
    if not 1<=len(validated)<=100:raise GameError("1~100문제를 등록해 주세요.")
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True)
        rows=[dict(id=_id(),owner_id=u["id"],topic_id=q["topic_id"],question_json=_json(q),published="0",revision="1",updated_at=_stamp()) for q in validated]
        b.append_many("game_questions",rows);db.invalidate("game_questions")
        return len(rows)


ALLOWED={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",
         ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",".hwp":"application/x-hwp",".hwpx":"application/zip"}

def upload_resource(user,topic_id,title,classes,name,data,confirmed=False):
    topic(topic_id)
    if not confirmed:raise GameError("학생에게 공개할 수 있는 자료인지 확인해 주세요.")
    ext=PurePath(name).suffix.lower()
    if ext not in ALLOWED or not 0<len(data)<=8*1024*1024:raise GameError("PDF·이미지·DOCX·HWP·HWPX 파일을 8MB 이하로 올려 주세요.")
    if not classes or any(c not in CLASSES for c in classes):raise GameError("공개 학급을 선택해 주세요.")
    if not 1<=len(title.strip())<=150:raise GameError("자료 제목을 1~150자로 입력하세요.")
    signatures={".pdf":b"%PDF", ".png":b"\x89PNG", ".jpg":b"\xff\xd8", ".jpeg":b"\xff\xd8", ".docx":b"PK", ".hwpx":b"PK", ".hwp":b"\xd0\xcf\x11\xe0", ".webp":b"RIFF"}
    if not data.startswith(signatures[ext]):raise GameError("파일 내용과 확장자가 맞지 않습니다.")
    b=db._ready_backend()
    with b.lock:u=_actor(user,b,"teacher",write=True)
    safe_name=PurePath(name.replace("\\","/")).name[:150]
    fid,_=b.save_file(data,safe_name,ALLOWED[ext],False)
    with b.lock:
        _actor(user,b,"teacher",write=True)
        row=dict(id=_id(),owner_id=u["id"],topic_id=topic_id,title=title.strip(),file_id=fid,file_name=safe_name,mime=ALLOWED[ext],classes_json=_json(classes),created_at=_stamp())
        _put(b,"game_resources",row);return row["id"]


def resources(user,topic_id):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b)
        rows=[r for r in b.read("game_resources") if r["topic_id"]==topic_id and
              ((u["role"]=="teacher" and r["owner_id"]==u["id"]) or (u["role"]=="student" and u["class"] in _load(r["classes_json"],[])))]
        return [{k:r[k] for k in ("id","title","file_name","mime","created_at")} for r in rows]


def download_resource(user,rid):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,write=True)
        r=next((r for r in b.read("game_resources") if r["id"]==rid),None)
        if not r or not ((u["role"]=="teacher" and r["owner_id"]==u["id"]) or (u["role"]=="student" and u["class"] in _load(r["classes_json"],[]))):
            raise PermissionError("이 자료를 열람할 수 없습니다.")
    data=b.load_file(r["file_id"])
    if data is None:raise GameError("첨부파일을 찾지 못했습니다. 교사에게 확인을 요청해 주세요.")
    return data,r["file_name"],r["mime"]


def remove_resource(user,rid):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True)
        r=next((r for r in b.read("game_resources") if r["id"]==rid),None)
        if not r or r["owner_id"]!=u["id"]:raise PermissionError("작성 교사만 자료를 숨길 수 있습니다.")
        r["classes_json"]="[]";_put(b,"game_resources",r)


def save_feedback(user,student_id,text):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True);target=_target(user,b,student_id);row=_row(b,target);p=_load(row["state_json"],{})
        text=str(text).strip()
        if not 1<=len(text)<=1000:raise GameError("피드백은 1~1000자로 적어 주세요.")
        p.setdefault("feedback",[]).append(dict(id=_id(),text=text,teacher_id=u["id"],created_at=_stamp()))
        row.update(state_json=_json(p),revision=str(int(row["revision"])+1),updated_at=_stamp());_put(b,"game_profiles",row)


def request_points(user,sid,revision):
    def action(p,b,u):
        s=engine.active(p,sid)
        if s["status"]!="done" or not s["mission_id"]:raise GameError("교사가 상점 검토를 허용한 완료 미션만 요청할 수 있어요.")
        m=_mission(b,s["mission_id"])
        if m["allow_points"]!="1" or not _mission_target(u,m):raise PermissionError("이 미션은 상점 연동을 사용하지 않습니다.")
        p["point_requests"].setdefault(sid,dict(status="pending",mission_id=m["id"],created_at=_stamp(),score=0))
    return _mutate(user,revision,action)


def approve_points(user,student_id,sid,score,reason,approve=True):
    if approve and (type(score) is not int or not 1<=score<=10):raise GameError("승인 상점은 1~10점으로 입력하세요.")
    if not 1<=len(str(reason).strip())<=300:raise GameError("검토 사유를 입력하세요.")
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b,"teacher",write=True);target=_target(user,b,student_id);row=_row(b,target);p=_load(row["state_json"],{})
        req=p.get("point_requests",{}).get(sid)
        if not req:raise GameError("검토 요청이 없습니다.")
        m=_mission(b,req["mission_id"])
        if m["owner_id"]!=u["id"]:raise PermissionError("미션 작성 교사만 승인할 수 있습니다.")
        if req["status"]!="pending":return False
        point_id="game_"+hashlib.sha256(f"{student_id}:{sid}".encode()).hexdigest()
        existing=next((r for r in b.read("points") if r["id"]==point_id),None)
        if approve:
            if not existing:
                b.append("points",dict(id=point_id,created_at=db.now_str(),student_id=student_id,name=target["name"],
                    **{"class":target["class"]},kind="상점",score=str(score),reason=f"[학습게임 교사 승인] {reason}"))
                db.invalidate("points")
            req.update(status="approved",score=int(existing["score"]) if existing else score,reason=reason,teacher_id=u["id"])
        else:
            if existing:raise GameError("이미 상점이 저장되어 승인 상태를 복구해야 합니다.")
            req.update(status="declined",score=0,reason=reason,teacher_id=u["id"])
        row.update(state_json=_json(p),revision=str(int(row["revision"])+1),updated_at=_stamp());_put(b,"game_profiles",row)
    if approve and not existing:rt.push(student_id,dict(kind="상점",score=score,reason=reason))
    return True


def save_status(user,student_id=None):
    b=db._ready_backend()
    with b.lock:
        u=_actor(user,b)
        paths=[]
        if u["role"]=="student" or student_id:
            target=_target(user,b,student_id);r=_row(b,target);paths=[db.GitHubBackend._path("game_profiles",r)]
        else:
            for table in TABLES-{"game_profiles"}:
                paths.extend(db.GitHubBackend._path(table,r) for r in b.read(table) if r.get("owner_id")==u["id"])
        pending=any(path in getattr(b,"dirty",{}) for path in paths)
        if u["role"]=="teacher" and not student_id:
            pending=pending or any(path.split("/")[1].split(".")[0] in TABLES for path in getattr(b,"dirty",{}) if path.startswith("data/"))
        return dict(local=getattr(b,"is_local",True),pending=pending,error=bool(getattr(b,"last_error","")))


def flush(user,student_id=None):
    save_status(user,student_id) # authorize before touching the remote store
    try:db.flush_now()
    except Exception:raise GameError("GitHub 영구 저장을 확인하지 못했습니다. 이 창을 유지하고 저장 확인을 다시 눌러 주세요.") from None
    status=save_status(user,student_id)
    if status["pending"]:raise GameError("서버에 반영되었지만 GitHub 저장 대기 중입니다. 저장 확인을 다시 눌러 주세요.")
    return status
