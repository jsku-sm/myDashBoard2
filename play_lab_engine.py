"""Additive arcade activity records. No changes to avatar rewards or quiz grades."""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

CATALOG = json.loads(Path(__file__).with_name("play_lab_catalog.json").read_text(encoding="utf-8"))
TITLES = {row["id"]: row["title"] for row in CATALOG}
EVENT_TYPES = {"start", "pause", "leave", "resume", "heartbeat", "success", "error", "hint", "clear", "win", "retry", "wait"}


def initial():
    return dict(version=1, games={}, runs={}, records=[])


def number(value, maximum, *, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum or (integer and type(value) is not int):
        raise ValueError("게임 기록의 숫자 범위를 확인해 주세요.")
    return value


def validate(raw):
    if not isinstance(raw, dict) or raw.get("game") not in TITLES or raw.get("type") not in EVENT_TYPES:
        raise ValueError("지원하지 않는 게임 기록입니다.")
    run = raw.get("runId")
    if not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", run):
        raise ValueError("게임 실행 기록을 확인해 주세요.")
    clean = {"game": raw["game"], "runId": run, "type": raw["type"]}
    for key, maximum, integer in [("seq", 1000000, True), ("elapsed", 86400, False), ("stage", 30, True), ("stageCount", 30, True), ("score", 10000000, False)]:
        clean[key] = number(raw.get(key), maximum, integer=integer)
    if clean["seq"] < 1 or clean["stage"] < 1 or clean["stageCount"] < clean["stage"]:
        raise ValueError("게임 순서와 단계를 확인해 주세요.")
    if raw.get("mode") not in ("relaxed", "challenge"):
        raise ValueError("게임 모드를 확인해 주세요.")
    clean["mode"] = raw["mode"]
    for key in ("question", "message", "skill"):
        value = raw.get(key, "")
        if not isinstance(value, str):
            raise ValueError("게임 기록 형식이 올바르지 않습니다.")
        clean[key] = value[:500]
    return clean


def apply(state, events, at):
    if not isinstance(events, list) or not 1 <= len(events) <= 40:
        raise ValueError("한 번에 저장할 게임 기록은 1~40개입니다.")
    clean = [validate(e) for e in events]  # Reject an invalid batch before any mutation.
    for e in clean:
        gid, rid, kind = e["game"], e["runId"], e["type"]
        run = state["runs"].get(rid)
        if not run:
            if kind != "start":
                raise ValueError("게임 시작 기록부터 순서대로 저장해 주세요.")
            run = dict(game=gid, seq=0, elapsed=0, finished=False, stages=[])
            state["runs"][rid] = run
        if run["game"] != gid:
            raise ValueError("게임 실행 ID가 다른 게임과 겹칩니다.")
        if e["seq"] <= run["seq"]:
            continue
        if run["finished"]:
            run["seq"] = e["seq"]
            continue
        g = state["games"].setdefault(gid, dict(starts=0, wins=0, successes=0, errors=0, hints=0, clears=0, points=0, seconds=0, best_score=0, status="ready", last_at=""))
        if not run["seq"]:
            g["starts"] += 1
        g["seconds"] += max(0, e["elapsed"] - run["elapsed"])
        run["elapsed"] = max(run["elapsed"], e["elapsed"])
        run["seq"] = e["seq"]
        g["best_score"] = max(g["best_score"], e["score"])
        g.update(last_at=at, stage=e["stage"])
        counter = {"success": "successes", "error": "errors", "hint": "hints"}.get(kind)
        if counter:
            g[counter] += 1
        if kind == "clear" and e["stage"] not in run["stages"]:
            run["stages"].append(e["stage"])
            g["clears"] += 1
            g["points"] = g.get("points", 0) + math.floor(300 / e["stageCount"] * (1.2 if e["mode"] == "challenge" else 1) + .5)
        if kind == "win":
            g["wins"] += 1
        if kind in {"win", "retry"}:
            run["finished"] = True
        g["status"] = {"start": "playing", "resume": "playing", "heartbeat": "playing", "pause": "paused", "leave": "paused", "wait": "between", "win": "complete", "retry": "retry"}.get(kind, g["status"])
        if kind != "heartbeat":
            state["records"].append({**e, "at": at})
    state["records"] = state["records"][-150:]
    # Keep active runs; prune the oldest completed runs only.
    if len(state["runs"]) > 400:
        for rid in list(state["runs"]):
            if len(state["runs"]) <= 400:
                break
            if state["runs"][rid]["finished"]:
                del state["runs"][rid]


def public(state):
    return {"games": deepcopy(state["games"]), "records": deepcopy(state["records"][-30:])}
