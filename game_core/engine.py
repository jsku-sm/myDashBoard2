"""Pure learning state transitions. No score/points table is accessed here."""
from __future__ import annotations
from copy import deepcopy
import uuid

MODES={"puzzle":"퍼즐형 · 개념 블록", "adventure":"모험형 · 개념 탐험"}
# Original small puzzle shapes, no speed requirement or game-over.
SHAPES=[[(0,0),(1,0),(2,0),(3,0)],[(0,0),(0,1),(1,1),(2,1)],[(0,0),(1,0),(0,1),(1,1)],[(0,0),(1,0),(2,0),(1,1)],[(1,0),(2,0),(0,1),(1,1)]]
ITEMS={
 "coat_ink":dict(name="잉크 재킷",slot="coat",cost=0,value="#526886"),
 "coat_mint":dict(name="세이지 재킷",slot="coat",cost=8,value="#477D70"),
 "coat_lilac":dict(name="라일락 재킷",slot="coat",cost=12,value="#8174A7"),
 "coat_sun":dict(name="앰버 재킷",slot="coat",cost=16,value="#B67B32"),
 "coat_rose":dict(name="로즈 재킷",slot="coat",cost=20,value="#A56B7C"),
 "cap_none":dict(name="기본 헤어",slot="cap",cost=0,value="none"),
 "cap_beanie":dict(name="니트 비니",slot="cap",cost=8,value="beanie"),
 "cap_headphones":dict(name="헤드폰",slot="cap",cost=14,value="headphones"),
 "pin_none":dict(name="기본 배지",slot="pin",cost=0,value="none"),
 "pin_star":dict(name="작은 별 배지",slot="pin",cost=6,value="star"),
 "pin_math":dict(name="무한 가능성 배지",slot="pin",cost=12,value="math"),
 "back_city":dict(name="밤의 좌표도시",slot="background",cost=0,value="#202D43"),
 "back_forest":dict(name="조용한 숲",slot="background",cost=18,value="#24473E"),
 "back_sky":dict(name="새벽 하늘",slot="background",cost=24,value="#3F4167"),
}
FREE=[k for k,v in ITEMS.items() if v["cost"]==0]

class GameError(ValueError): pass
class Conflict(GameError): pass


def new_profile():
    return dict(version=1,earned=0,spent=0,owned=list(FREE),equipped={v["slot"]:k for k,v in ITEMS.items() if k in FREE},
                sessions=[],active_id="",point_requests={},feedback=[])


def wallet(p): return p["earned"]-p["spent"]

def active(p,sid):
    found=next((s for s in p["sessions"] if s["id"]==sid),None)
    if not found: raise GameError("학습 기록이 없습니다. 목록을 다시 열어 주세요.")
    return found


def start(p,topic_id,mode,questions,now,mission_id="",level="천천히"):
    if mode not in MODES or len(questions)!=5: raise GameError("게임 종류와 5문항 구성을 확인해 주세요.")
    for old in p["sessions"]:
        if old["topic_id"]==topic_id and old["mission_id"]==mission_id and old["status"]!="done":
            p["active_id"]=old["id"];old["status"]="working";switch(old,mode);return old["id"]
        if mission_id and old["mission_id"]==mission_id and old["status"]=="done":
            raise GameError("완료한 미션입니다. 같은 개념은 자유 학습에서 다시 연습할 수 있어요.")
    if sum(s["status"]!="done" for s in p["sessions"])>=5:
        raise GameError("이어 할 학습이 5개 있습니다. 진행 중인 학습 하나를 마친 뒤 새로 시작해 주세요.")
    sid=uuid.uuid4().hex
    p["sessions"].append(dict(id=sid,topic_id=topic_id,mode=mode,mission_id=mission_id,level=level,
        status="working",created_at=now,updated_at=now,index=0,questions=deepcopy(questions),
        answers=[dict(choices=[],hints=0,revealed=False,solved=False,kind="",reflection="",rewarded=False) for _ in questions],
        board=[[0]*6 for _ in range(6)],boards_cleared=0,lines_cleared=0,path=[[0,0]],modes_used=[mode],reflection=""))
    p["active_id"]=sid
    return sid


def current(s,index):
    if s["status"]=="done" or type(index) is not int or index!=s["index"]:
        raise Conflict("문제 진행 상태가 바뀌었습니다. 현재 문제를 확인해 주세요.")
    return s["questions"][index],s["answers"][index]


def submit(s,index,choice):
    q,a=current(s,index)
    if type(choice) is not int or choice not in range(4): raise GameError("보기 하나를 선택해 주세요.")
    if a["solved"]: return True
    if len(a["choices"])>=30: raise GameError("이번에는 해설을 함께 확인하고 다음 문제로 이어 가요.")
    a["choices"].append(choice)
    if choice==q["answer"]:
        a["solved"]=True
        a["kind"]="explained" if a["revealed"] else "supported" if a["hints"] else "retry" if len(a["choices"])>1 else "independent"
        return True
    return False


def hint(s,index):
    q,a=current(s,index)
    if not a["solved"]: a["hints"]=min(len(q["hints"]),a["hints"]+1)


def reveal(s,index):
    q,a=current(s,index)
    if not a["solved"]: a["revealed"]=True


def reflect_solution(s,index,text):
    q,a=current(s,index)
    if not a["revealed"]: raise GameError("해설을 먼저 확인해 주세요.")
    text=str(text).strip()
    if not 5<=len(text)<=1000: raise GameError("해설에서 확인한 규칙을 5자 이상 자신의 말로 남겨 주세요.")
    a.update(solved=True,kind="explained",reflection=text)


def rotated(index,rotation):
    cells=SHAPES[index%5]
    for _ in range(rotation%4): cells=[(-y,x) for x,y in cells]
    mx,my=min(x for x,y in cells),min(y for x,y in cells)
    return [(x-mx,y-my) for x,y in cells]


def puzzle_moves(board,index):
    out=[];seen=set()
    for rot in range(4):
        shape=rotated(index,rot)
        for y in range(6):
            for x in range(6):
                cells=tuple(sorted((x+dx,y+dy) for dx,dy in shape))
                if cells in seen: continue
                if all(cx<6 and cy<6 and not board[cy][cx] for cx,cy in cells):
                    out.append((x,y,rot));seen.add(cells)
    return out


def ensure_space(s):
    if not puzzle_moves(s["board"],s["index"]):
        s["board"]=[[0]*6 for _ in range(6)];s["boards_cleared"]+=1


def advance(p,s,index,now,placement=None,direction="east"):
    q,a=current(s,index)
    if not a["solved"]: raise GameError("정답을 확인하거나 해설을 자신의 말로 정리한 뒤 이어 갈 수 있어요.")
    if direction not in ("east","north"): raise GameError("이동 방향을 선택하세요.")
    ensure_space(s);moves=puzzle_moves(s["board"],index)
    chosen=tuple(placement) if placement is not None else moves[0]
    if chosen not in moves: raise GameError("블록이 겹치지 않는 자리를 선택해 주세요.")
    x,y,rot=chosen
    for dx,dy in rotated(index,rot):s["board"][y+dy][x+dx]=index+1
    full_rows={r for r in range(6) if all(s["board"][r])}
    full_cols={c for c in range(6) if all(s["board"][r][c] for r in range(6))}
    s["lines_cleared"]=s.get("lines_cleared",0)+len(full_rows)+len(full_cols)
    for r in range(6):
        for c in range(6):
            if r in full_rows or c in full_cols:s["board"][r][c]=0
    px,py=s["path"][-1];s["path"].append([px+(direction=="east"),py+(direction=="north")])
    if not a["rewarded"]: p["earned"]+=2;a["rewarded"]=True;a["completed_at"]=now
    s["index"]+=1;s["updated_at"]=now
    if s["index"]==5:
        s["status"]="done";s["completed_at"]=now;p["earned"]+=2
    else: ensure_space(s)


def switch(s,mode):
    if mode not in MODES: raise GameError("게임 종류를 확인하세요.")
    s["mode"]=mode
    if mode not in s["modes_used"]:s["modes_used"].append(mode)


def buy(p,item_id):
    if item_id not in ITEMS:raise GameError("없는 꾸미기 아이템입니다.")
    item=ITEMS[item_id]
    if item_id not in p["owned"]:
        if wallet(p)<item["cost"]:raise GameError("아직 별 조각이 부족해요. 가진 아이템도 언제든 바꿔 입을 수 있어요.")
        p["spent"]+=item["cost"];p["owned"].append(item_id)
    p["equipped"][item["slot"]]=item_id


def public_session(s):
    # Never send future questions, answer keys, seeds or private teacher metadata.
    v={k:deepcopy(s[k]) for k in ("id","topic_id","mode","mission_id","level","status","index","board","path","modes_used","created_at","updated_at","reflection")}
    v["lines_cleared"]=s.get("lines_cleared",0)
    v["answers"]=[{k:deepcopy(a[k]) for k in ("choices","hints","revealed","solved","kind","reflection","rewarded")} for a in s["answers"]]
    if s["status"]!="done":
        q=s["questions"][s["index"]];a=s["answers"][s["index"]]
        v["question"]={k:deepcopy(q[k]) for k in ("id","prompt","options","concept","source","source_note")}
        v["question"]["hints"]=q["hints"][:a["hints"]]
        if a["solved"] or a["revealed"]:
            v["question"].update(answer=q["answer"],explanation=q["explanation"])
        v["question"]["hint_count"]=len(q["hints"])
    else:
        v["review"]=[dict(prompt=q["prompt"],answer=q["options"][q["answer"]],explanation=q["explanation"],kind=a["kind"]) for q,a in zip(s["questions"],s["answers"])]
    return v


def growth(p):
    topics={}
    for s in p["sessions"]:
        entry=topics.setdefault(s["topic_id"],dict(topic_id=s["topic_id"],independent=0,retry=0,supported=0,explained=0,completed=0,visits=0,last_at="",trajectory=[],_timeline=[]))
        entry["visits"]+=1;entry["last_at"]=max(entry["last_at"],s["updated_at"])
        for a in s["answers"]:
            if a["rewarded"]:
                entry[a["kind"]]+=1;entry["completed"]+=1;entry["_timeline"].append((a.get("completed_at",s["updated_at"]),a["kind"]))
    for entry in topics.values():
        entry["trajectory"]=[kind for _,kind in sorted(entry.pop("_timeline"),key=lambda item:item[0])]
        recent=entry["trajectory"][-5:]
        entry["message"]="다시 만나 볼 개념" if not recent else "도움을 활용해 확인 중"
        if recent and recent[-1]=="independent":
            entry["message"]="최근 문항을 스스로 해결했어요"
            if any(k!="independent" for k in entry["trajectory"][:-1]):entry["message"]="도움을 받던 개념을 스스로 해결했어요"
        if len(recent)>=3 and all(x=="independent" for x in recent[-3:]):entry["message"]="최근 3문항을 스스로 해결했어요"
    return list(topics.values())
