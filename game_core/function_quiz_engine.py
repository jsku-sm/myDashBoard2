"""Five-stage, unit-scoped concept progression with legacy function records."""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import secrets
import time
import uuid
from .concept_quiz_catalog import unit_info


@lru_cache(maxsize=7)
def bank(unit="functions"):
    unit_info(unit)
    if unit != "functions":
        from .concept_quiz_bank import bank as common_bank
        return common_bank(unit)
    return json.loads(Path(__file__).with_name("function_quiz_bank.json").read_text(encoding="utf-8"))


def initial():
    return dict(version=1, stages={}, awards={}, totals=dict(answered=0, correct=0, wrong=0, seconds=0),
                skills={}, records=[], active=None, previous={}, events=[], mastered_at="")


def unlocked(state):
    return next((level for level in range(1, 6) if not state["stages"].get(str(level), {}).get("completed_at")), 5)


def open_question(state, level, topic, *, preview=False, unit="functions"):
    content=bank(unit)
    count=len(content["topics"])
    if type(level) is not int or not 1 <= level <= (5 if preview else unlocked(state)):
        raise ValueError(f"현재 단원의 {count}개 주제를 해결한 뒤 다음 단계에 도전해요.")
    if type(topic) is not int or not 0 <= topic < count:
        raise ValueError("주제를 다시 선택해 주세요.")
    key=f"{level}:{topic}"
    candidates=[q for q in content["questions"] if q["level"]==level and q["topic"]==topic
                and q["id"]!=state["previous"].get(key)]
    q=deepcopy(secrets.choice(candidates))
    q["unit"]=unit
    answer=q["options"][q["answer"]]
    secrets.SystemRandom().shuffle(q["options"])
    q["answer"]=q["options"].index(answer)
    state["previous"][key]=q["id"]
    state["active"]=dict(id=uuid.uuid4().hex, question=q, started=time.time(), elapsed=0,
                         turn=0, tries=0, result=None)


def answer(state, event, now, *, unit="functions"):
    active=state.get("active")
    if not active or event.get("question_id")!=active["id"] or event.get("turn")!=active["turn"]:
        raise ValueError("문제가 바뀌었습니다. 현재 문제에서 다시 답해 주세요.")
    if active["result"] is not None:
        return  # Duplicate submissions cannot change an answer or earn points.
    q=active["question"];choice=event.get("choice")
    if q.get("unit","functions") != unit: raise ValueError("단원이 바뀌었습니다. 현재 단원의 문제에서 답해 주세요.")
    if type(choice) is not int or not 0 <= choice < len(q["options"]):
        raise ValueError("보기 하나를 선택해 주세요.")
    value=event.get("seconds",0)
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError("풀이 시간이 올바르지 않습니다. 문제를 다시 열어 주세요.")
    # Time is a learning aid, not an award or a rank criterion.
    elapsed=max(active["elapsed"],min(float(value),max(0,time.time()-active["started"]),86400))
    delta=round(elapsed-active["elapsed"],2);active["elapsed"]=elapsed;active["tries"]+=1
    correct=choice==q["answer"]
    stage=state["stages"].setdefault(str(q["level"]),dict(passed={},completed_at=""))
    if correct and str(q["topic"]) not in stage["passed"]:
        stage["passed"][str(q["topic"])]=dict(at=now,tries=active["tries"])
    for counts in (state["totals"],state["skills"].setdefault(str(q["topic"]),dict(answered=0,correct=0,wrong=0,seconds=0))):
        counts["answered"]+=1;counts["correct"]+=int(correct);counts["wrong"]+=int(not correct)
        counts["seconds"]=round(counts["seconds"]+delta,2)
    earned=0;completed=False
    if len(stage["passed"])==len(bank(unit)["topics"]) and not stage["completed_at"]:
        stage["completed_at"]=now;completed=True
        earned=q["level"]*100;state["awards"][str(q["level"])]=earned
        if q["level"]==5 and not state["mastered_at"]:
            state["mastered_at"]=now;state["awards"]["master"]=300;earned+=300
    active["result"]=dict(correct=correct,choice=choice,answer=q["answer"],explanation=q["explanation"],
                          earned=earned,completed=completed)
    state["records"].append(dict(id=uuid.uuid4().hex,level=q["level"],topic=q["topic"],prompt=q["prompt"],
                                 selected=q["options"][choice],answer=q["options"][q["answer"]],
                                 correct=correct,seconds=delta,at=now))
    state["records"]=state["records"][-300:]


def apply(state,event,now,*,preview=False,unit="functions"):
    unit_info(unit)
    if not isinstance(event,dict) or not isinstance(event.get("id"),str) or not 1<=len(event["id"])<=100:
        raise ValueError("화면을 새로고침한 뒤 다시 시도해 주세요.")
    if event.get("unit",unit) != unit: raise ValueError("단원이 바뀌었습니다. 새로 선택한 단원에서 다시 시작해 주세요.")
    if event["id"] in state["events"]:return
    action=event.get("action")
    if action=="open":open_question(state,event.get("level"),event.get("topic"),preview=preview,unit=unit)
    elif action=="answer":answer(state,event,now,unit=unit)
    elif action=="retry":
        active=state.get("active")
        if not active or event.get("question_id")!=active["id"] or event.get("turn")!=active["turn"]:
            raise ValueError("현재 문제에서 다시 생각하기를 눌러 주세요.")
        if active["result"] and not active["result"]["correct"]:
            active["result"]=None;active["turn"]+=1
    else:raise ValueError("지원하지 않는 퀴즈 동작입니다.")
    state["events"]=(state["events"]+[event["id"]])[-40:]


def public(state,*,preview=False,unit="functions",history=True):
    info=unit_info(unit);content=bank(unit)
    active=state.get("active");q=None
    if active:
        source=active["question"]
        q={k:source[k] for k in ("level","topic","prompt","options")}
        q.update(id=active["id"],turn=active["turn"],elapsed=active["elapsed"],result=deepcopy(active["result"]))
    return dict(unit=unit,unit_title=info["title"],subject=info["subject"],topic_count=len(content["topics"]),
                topics=content["topics"],levels=content["levels"],unlocked=5 if preview else unlocked(state),
                stages=deepcopy(state["stages"]),points=sum(state["awards"].values()),
                totals=deepcopy(state["totals"]),skills=deepcopy(state["skills"]),
        mastered_at=state["mastered_at"],question=q,preview=preview,records=deepcopy(state["records"][-30:]) if history else [])
