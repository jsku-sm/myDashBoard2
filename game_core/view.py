"""Streamlit UI. Student views receive only authorized, answer-redacted projections."""
from __future__ import annotations
from copy import deepcopy
import logging
import hashlib
import secrets
import streamlit as st
from config import CLASSES
from . import bank, engine, presentation as art, service as svc
from .curriculum import EDITIONS, TOPICS, rows, topic

KINDS={"independent":"처음에 스스로 해결", "retry":"다시 생각해서 해결", "supported":"힌트로 해결", "explained":"해설로 확인"}


def _notice():
    flash=st.session_state.pop("_gg_notice",None)
    if flash:getattr(st,flash[0])(flash[1])


def _change(fn,*args,message="학습 기록에 반영했어요.",flush_user=None,**kwargs):
    try:
        result=fn(*args,**kwargs)
        st.session_state["_gg_notice"]=("success",message)
        if flush_user:
            try:
                status=svc.flush(flush_user)
                if status["local"]:st.session_state["_gg_notice"]=("warning","로컬 시험 저장입니다. 실제 수업에서는 GitHub 저장 모드를 사용하세요.")
            except (engine.GameError,PermissionError) as exc:st.session_state["_gg_notice"]=("warning",str(exc))
    except (ValueError,PermissionError) as exc:
        st.error(str(exc));return None
    except Exception as exc:
        logging.getLogger(__name__).warning("Game operation failed: %s",type(exc).__name__)
        st.error("처리를 완료하지 못했어요. 이 창을 유지하고 다시 시도해 주세요. 토큰이나 학생 정보는 화면으로 보내지 마세요.")
        return None
    st.rerun()
    return result


def _save_panel(user,student_id=None):
    st.caption("Good Math Games · GOOD_GAMES_1.0")
    status=svc.save_status(user,student_id)
    if status["local"]:
        st.warning("현재 로컬 시험 모드입니다. 서버가 다시 시작되면 기록이 사라질 수 있어요. 실제 학생 사용 전 기존 GitHub 저장 설정을 확인하세요.")
    elif status["pending"]:
        st.caption("☁ 서버에는 반영됨 · GitHub 영구 저장 대기 중. 쉬어 가기 전에 저장을 확인해 주세요.")
    else:st.caption("☁ 현재 학습기록의 저장 대기 변경 없음 · 제출한 답·힌트·보상·이어 할 위치를 기록합니다.")
    if status["error"]:st.warning("최근 저장소 연결 오류가 있습니다. 창을 닫기 전에 GitHub 저장을 다시 확인하세요.")
    if st.button("GitHub 저장 확인 · 재시도",key="gg_flush"):
        _change(svc.flush,user,student_id,message="저장 대기 없이 반영된 것을 확인했어요.")


def _pick_topic(prefix,edition=None):
    edition=edition or svc.edition()
    subjects=["공통수학1","공통수학2"]
    sub=st.selectbox("과목",subjects,key=prefix+"_subject")
    data=rows(edition,sub)
    def pick(field,label,values,key):
        opts=list(dict.fromkeys(r[field] for r in values))
        return st.selectbox(label,opts,key=key)
    major=pick("major","대단원",data,prefix+sub+edition+"_major")
    data=[r for r in data if r["major"]==major]
    cols=st.columns(2)
    with cols[0]:middle=pick("middle","중단원",data,prefix+sub+edition+major+"_middle")
    data=[r for r in data if r["middle"]==middle]
    with cols[1]:small=pick("small","소단원",data,prefix+sub+edition+major+middle+"_small")
    data=[r for r in data if r["small"]==small]
    tid=st.selectbox("세부 주제",[r["id"] for r in data],format_func=lambda x:TOPICS[x]["label"],key=prefix+sub+edition+major+middle+small+"_topic")
    st.caption("교과서 대·중·소단원에 맞추고, 세부 주제는 이 앱의 개념 연습을 위해 나누었습니다.")
    return tid


def _mode(prefix):
    return st.radio("학습 분위기",list(engine.MODES),format_func=engine.MODES.get,horizontal=True,key=prefix+"_mode")


def _resources(user,tid,manage=False):
    material=svc.resources(user,tid)
    if not material:return
    with st.expander("이 개념의 수업 학습지 · 참고자료"):
        for item in material:
            st.write(item["title"])
            key=f"_gg_file_{user['id']}_{item['id']}"
            if st.button("자료 내려받기 준비",key=key+"_prepare"):
                try:st.session_state[key]=svc.download_resource(user,item["id"])
                except (ValueError,PermissionError) as exc:st.error(str(exc))
            if key in st.session_state:
                data,name,mime=st.session_state[key]
                st.download_button("자료 내려받기",data,file_name=name,mime=mime,key=key+"_download")
            if manage and st.button("학생에게 숨기기",key=key+"_hide"):
                st.session_state.pop(key,None)
                _change(svc.remove_resource,user,item["id"],message="학생 자료 목록에서 숨겼습니다. 저장 이력은 삭제하지 않습니다.")


def _landing(user,p):
    unfinished=[s for s in p["sessions"] if s["status"]!="done"]
    if unfinished:
        with st.expander(f"이어 할 학습 {len(unfinished)}개",expanded=True):
            for s in reversed(unfinished):
                st.write(f"{TOPICS[s['topic_id']]['label']} · {s['index']}/5문제 · {engine.MODES[s['mode']]}")
                if st.button("이 자리부터 이어 하기",key="resume_"+s["id"]):
                    _change(svc.resume,user,s["id"],p["revision"],message="지난번 자리부터 천천히 이어 가요.")
    missions=svc.missions(user)
    if missions:
        with st.expander("선생님이 보낸 5문제 미션",expanded=True):
            for m in missions:
                already=next((s for s in p["sessions"] if s["mission_id"]==m["id"]),None)
                st.write(f"**{m['title']}** · {TOPICS[m['topic_id']]['label']}")
                if already and already["status"]=="done":st.caption("완료했어요. 나의 성장기록에서 다시 살펴볼 수 있어요.");continue
                mode=_mode("mission_"+m["id"])
                if st.button("미션 시작 · 이어 하기",key="mission_start_"+m["id"]):
                    _change(svc.start,user,m["topic_id"],mode,p["revision"],mission_id=m["id"],message="선생님 미션을 열었어요. 속도보다 생각에 집중해요.")
    st.subheader("오늘 내가 골라 배우는 개념")
    tid=_pick_topic("gg_free");t=topic(tid)
    st.markdown(art.note(t["concept"]),unsafe_allow_html=True)
    st.caption("생활·전공과의 연결 · "+t["usefulness"])
    mode=_mode("gg_free")
    level=st.selectbox("숫자의 복잡도",["천천히","기본","한 걸음 더"],key="gg_level",help="점수나 등급이 아닙니다. 같은 개념을 작은 수부터 연습하는 선택입니다.")
    if st.button("5문제, 나의 속도로 시작하기",key="gg_start",type="primary",width="stretch"):
        _change(svc.start,user,tid,mode,p["revision"],level=level,message="첫 문제를 만났어요. 필요하면 힌트를 이용해요.")
    _resources(user,tid)


def _lesson(user,p,s,preview=False):
    sid=s["id"];ix=s["index"];prefix=("demo_" if preview else "learn_")+sid+"_"+str(ix)
    def act(kind,**args):
        if preview:
            dp=deepcopy(st.session_state["_gg_demo"]);ds=engine.active(dp,sid)
            if kind=="answer":engine.submit(ds,ix,args["choice"])
            elif kind=="hint":engine.hint(ds,ix)
            elif kind=="reveal":engine.reveal(ds,ix)
            elif kind=="reflect_solution":engine.reflect_solution(ds,ix,args["text"])
            elif kind=="advance":engine.advance(dp,ds,ix,"preview",args.get("placement"),args.get("direction","east"))
            elif kind=="switch":engine.switch(ds,args["mode"])
            elif kind=="pause":dp["active_id"]=""
            elif kind=="reflection":ds["reflection"]=args["text"]
            st.session_state["_gg_demo"]=dp;st.rerun()
        else:
            done=(kind=="advance" and ix==4) or kind=="pause"
            _change(svc.lesson_action,user,sid,ix,p["revision"],kind,**args,
                    message="기록했어요. 다시 돌아오면 여기서 이어 갈 수 있어요." if kind=="pause" else "한 걸음이 기록되었어요.",flush_user=user if done else None)
    st.subheader(topic(s["topic_id"])["label"])
    st.markdown(art.progress(ix),unsafe_allow_html=True)
    st.caption("게임 결과는 성적이 아닙니다. 힌트 사용과 재도전도 의미 있는 학습으로 남아요.")
    left,right=st.columns([1,2])
    placement=None;direction="east"
    with left:
        st.markdown(art.avatar(p["equipped"],p["coins"]),unsafe_allow_html=True)
        if s["status"]!="done":
            alt="adventure" if s["mode"]=="puzzle" else "puzzle"
            if st.button(engine.MODES[alt]+"으로 바꾸기",key=prefix+"_switch",width="stretch"):act("switch",mode=alt)
            if st.button("저장하고 쉬어 가기",key=prefix+"_pause",width="stretch"):act("pause")
        else:
            if st.button("다른 개념 만나기",key=prefix+"_back",width="stretch"):act("pause")
    with right:
        if s["mode"]=="puzzle":
            if ix<5 and s["answers"][ix]["solved"]:
                moves=engine.puzzle_moves(s["board"],ix)
                placement=st.selectbox("얻은 블록을 놓을 자리",moves,format_func=lambda a:f"{a[1]+1}행 {a[0]+1}열 · {a[2]*90}° 회전",key=prefix+"_placement")
            st.markdown(art.puzzle(s["board"],min(ix,4),placement),unsafe_allow_html=True)
            st.caption("문제를 확인하면 블록 1개. 자리를 고르면 점선으로 미리 보여요. 한 줄을 채우면 비워져요. 시간제한·게임오버는 없어요.")
            st.caption(f"완성한 줄 {s.get('lines_cleared',0)}개 · 줄 수와 관계없이 학습 보상은 같아요.")
        else:
            st.markdown(art.adventure(s["path"]),unsafe_allow_html=True)
            st.caption("문제 한 개마다 길 한 칸. 경로는 내가 정해요. 다섯 번의 생각이 나만의 지도가 됩니다.")
            if ix<5 and s["answers"][ix]["solved"]:
                direction=st.radio("이번에는 어느 방향으로 갈까요?",["east","north"],format_func=lambda x:"동쪽 →" if x=="east" else "북쪽 ↑",horizontal=True,key=prefix+"_direction")
    if s["status"]=="done":
        _completed(user,p,s,act,preview);return
    q=s["question"];a=s["answers"][ix]
    with st.expander("이 문제의 개념 한 줄",expanded=False):st.write(topic(s["topic_id"])["concept"])
    st.markdown(f"### {ix+1}. {q['prompt']}")
    if q.get("source_note"):st.caption("문항 출처 · "+q["source_note"])
    if a["solved"]:
        st.success({"independent":"이번 규칙을 스스로 적용했어요.","retry":"다시 생각해서 해결했어요. 바꾼 생각이 오늘의 배움이에요.","supported":"힌트를 활용해 끝까지 해결했어요. 도움을 쓰는 것도 학습의 힘이에요.","explained":"해설에서 규칙을 확인했어요. 비슷한 문제에서 다시 사용해 봐요."}[a["kind"]])
        st.write("**정답** · "+q["options"][q["answer"]]);st.write(q["explanation"])
        if st.button("블록 놓기 · 별 조각 2개" if s["mode"]=="puzzle" else "한 칸 이동 · 별 조각 2개",type="primary",key=prefix+"_next",width="stretch"):
            act("advance",placement=placement,direction=direction)
        st.caption("모든 해결 경로의 보상은 같습니다. 다음 문제에서 혼자 적용해 볼 기회를 드려요.")
        return
    with st.form(prefix+"_answer_form"):
        choice=st.radio("나의 생각과 가장 가까운 답",range(4),format_func=lambda i:f"{i+1}  ·  {q['options'][i]}",index=None,key=prefix+"_choice")
        if st.form_submit_button("내 생각 확인하기",type="primary",width="stretch"):
            if choice is None:st.info("답 하나를 골라 주세요. 모르겠다면 아래 힌트부터 만나도 괜찮아요.")
            else:act("answer",choice=choice)
    if a["choices"]:
        st.info("아직 답과 만나지 않았어요. 어떤 조건을 놓쳤는지 한 번 더 살펴볼까요? 오답으로 별 조각을 잃지 않아요.")
    for number,h in enumerate(q["hints"],1):st.markdown(art.note(f"힌트 {number} · {h}"),unsafe_allow_html=True)
    cols=st.columns(2)
    if cols[0].button("한 단계 힌트",key=prefix+"_hint",disabled=a["hints"]>=q["hint_count"]):act("hint")
    if cols[1].button("해설과 함께 배우기",key=prefix+"_reveal",disabled=a["revealed"]):act("reveal")
    if a["revealed"]:
        st.write("**정답** · "+q["options"][q["answer"]]);st.write(q["explanation"])
        st.caption("이 과정은 ‘해설로 확인’으로 기록됩니다. 정답을 본 것과 혼자 해결한 것을 구분해요.")
        with st.form(prefix+"_explain_form"):
            text=st.text_area("해설에서 확인한 규칙 한 가지를 나의 말로",key=prefix+"_explain",max_chars=1000,placeholder="예: x축 대칭에서는 y좌표의 부호만 바뀐다.")
            if st.form_submit_button("규칙을 남기고 다음 단계로"):act("reflect_solution",text=text)
    st.caption("선택만 한 답이나 아직 제출하지 않은 글은 저장되지 않습니다. ‘내 생각 확인하기’ 또는 기록 버튼을 눌러 주세요.")


def _completed(user,p,s,act,preview):
    counts={v:sum(a["kind"]==k for a in s["answers"]) for k,v in KINDS.items()}
    st.success("다섯 번의 도전을 마쳤어요. 문제별 10개 + 마무리 2개, 총 별 조각 12개가 쌓였어요.")
    st.markdown(art.note("오늘의 정답 수가 나의 가치를 정하지는 않아요. 새로 이해한 한 가지는 내 안에 남아 있어요."),unsafe_allow_html=True)
    st.write(" · ".join(f"{label} {n}개" for label,n in counts.items()))
    with st.form("finish_"+s["id"]):
        text=st.text_area("오늘 새로 이해한 한 가지 · 다음에 확인할 것",value=s.get("reflection",""),max_chars=1500,key="finishtext_"+s["id"])
        if st.form_submit_button("나의 말로 기록하기"):act("reflection",text=text)
    with st.expander("5문제 다시 살펴보기"):
        for i,r in enumerate(s["review"],1):
            st.write(f"**{i}. {r['prompt']}**");st.write(f"정답: {r['answer']} · {KINDS[r['kind']]}");st.write(r["explanation"])
    if not preview and s["mission_id"]:
        m=next((m for m in svc.missions(user) if m["id"]==s["mission_id"]),None)
        req=p["point_requests"].get(s["id"])
        if req:st.caption("교사 상점 검토 · "+{"pending":"검토 대기","approved":"승인됨","declined":"보류됨"}.get(req["status"],req["status"]))
        elif m and m["allow_points"]=="1":
            st.caption("이 미션은 교사가 상점 검토를 허용했습니다. 자동 상점·자동 성적 반영은 하지 않습니다.")
            if st.button("선생님께 상점 검토 요청",key="request_"+s["id"]):_change(svc.request_points,user,s["id"],p["revision"])


def _wardrobe(user,p):
    st.subheader("나의 캐릭터 작업실")
    st.markdown(art.avatar(p["equipped"],p["coins"]),unsafe_allow_html=True)
    st.caption("별 조각은 꾸미기에만 사용합니다. 실제 돈·성적·상점으로 자동 환산되지 않습니다. 출석이 끊겨도 사라지지 않아요.")
    slot=st.radio("꾸밀 부분",["coat","cap","pin","background"],format_func=lambda k:{"coat":"재킷","cap":"헤어·소품","pin":"배지","background":"배경"}[k],horizontal=True,key="wardrobe_slot")
    for key,item in engine.ITEMS.items():
        if item["slot"]!=slot:continue
        owned=key in p["owned"];equipped=p["equipped"].get(slot)==key
        title=f"{item['name']} · "+("착용 중" if equipped else "보유" if owned else f"별 조각 {item['cost']}개")
        if st.button(title,key="item_"+key,disabled=equipped or (not owned and p["coins"]<item["cost"])):
            _change(svc.buy,user,key,p["revision"],message="나만의 캐릭터에 반영했어요.")


def _growth(user,p,teacher=False):
    if teacher:st.subheader(f"{p['student']['class']} · {p['student']['name']}의 성장 기록")
    else:st.subheader("어제보다 넓어진 나의 가능성")
    totals=sum(t["completed"] for t in p["growth"])
    c=st.columns(3);c[0].metric("확인한 문제",totals);c[1].metric("만난 개념",len(p["growth"]));c[2].metric("완료한 5문제 학습",sum(s["status"]=="done" for s in p["sessions"]))
    st.caption("두 게임의 기록을 개념별로 합칩니다. 아래 수치는 관찰 자료이며 성적·완전한 개념 숙달 판정이 아닙니다.")
    data=[{"세부 주제":TOPICS[t["topic_id"]]["label"],**{label:t[k] for k,label in KINDS.items()},"최근 변화":t["message"]} for t in p["growth"]]
    if data:st.dataframe(data,hide_index=True,width="stretch")
    else:st.markdown(art.note("아직 빈 기록은 앞으로의 가능성이에요. 첫 한 문제부터 채워 보아요."),unsafe_allow_html=True)
    with st.expander("나의 학습 발자국",expanded=False):
        for s in reversed(p["sessions"][-40:]):
            label=TOPICS[s["topic_id"]]["label"]
            st.write(f"**{label}** · {s['index']}/5문제 · "+" + ".join(engine.MODES[m] for m in s["modes_used"]))
            st.caption(s["updated_at"].split(".")[0]+" · "+("완료" if s["status"]=="done" else "이어 하기 가능"))
            if s["reflection"]:st.write(s["reflection"])
            for i,a in enumerate(s["answers"]):
                if a["choices"] or a["hints"] or a["revealed"]:
                    st.caption(f"{i+1}번 · 답 확인 {len(a['choices'])}회 · 힌트 {a['hints']}회 · {KINDS.get(a['kind'],'생각 중')}")
                    if a["reflection"]:st.write("확인한 규칙: "+a["reflection"])
            if not teacher and st.button("이 학습 열기",key="history_"+s["id"]):
                st.session_state["_gg_nav_next"]="개념 학습게임"
                _change(svc.resume,user,s["id"],p["revision"])
    if p["feedback"]:
        st.subheader("선생님이 남긴 응원")
        for f in reversed(p["feedback"][-20:]):st.markdown(art.note(f["text"]),unsafe_allow_html=True)
    if not teacher:_wardrobe(user,p)


def _teacher_preview(user):
    st.info("교사 미리보기입니다. 가상 캐릭터로 체험하며 학생 기록·상점에는 저장하지 않습니다.")
    p=st.session_state.get("_gg_demo")
    if p and p.get("active_id"):
        s=engine.public_session(engine.active(p,p["active_id"]))
        projected=dict(coins=engine.wallet(p),equipped=p["equipped"],point_requests={})
        _lesson(user,projected,s,preview=True)
        return
    tid=_pick_topic("gg_preview")
    mode=_mode("gg_preview")
    level=st.selectbox("숫자의 복잡도",["천천히","기본","한 걸음 더"],key="gg_preview_level")
    if st.button("5문제 미리보기 시작",key="gg_demo_start",type="primary"):
        dp=engine.new_profile();engine.start(dp,tid,mode,bank.generate(tid,secrets.randbits(64),level=level),"preview")
        st.session_state["_gg_demo"]=dp;st.rerun()


def _question_form(user,tid,base,qid="",revision=0,published=False):
    content_key=qid or base["id"]+hashlib.sha256(repr(base).encode("utf-8")).hexdigest()[:10]
    formkey=f"gg_editor_{tid}_{content_key}_{revision}"
    with st.form(formkey):
        st.caption("객관식 4지선다 · 수식은 텍스트 또는 $...$ LaTeX를 사용할 수 있습니다. 현재 학습 중인 학생의 문항은 수정되지 않고 새 학습에 반영됩니다.")
        prompt=st.text_area("문제",value=base["prompt"],max_chars=3000,key=formkey+"_prompt")
        options=[st.text_input(f"보기 {i+1}",value=base["options"][i],max_chars=500,key=formkey+f"_option{i}") for i in range(4)]
        answer=st.selectbox("정답 번호",range(4),index=base["answer"],format_func=lambda x:f"{x+1}번",key=formkey+"_answer")
        explanation=st.text_area("풀이·해설",value=base["explanation"],max_chars=4000,key=formkey+"_explanation")
        hints=st.text_area("단계별 힌트 · 한 줄에 하나, 최대 3개",value="\n".join(base["hints"]),max_chars=4500,key=formkey+"_hints")
        source=st.text_input("출처·교사 메모 (학생에게도 표시 가능)",value=base.get("source_note",""),max_chars=300,key=formkey+"_source")
        publish=st.checkbox("학생 문제에 공개",value=published,key=formkey+"_publish")
        reviewed=st.checkbox("정답이 하나이며 해설·단원 적합성·이용 권한을 직접 확인했습니다",key=formkey+"_reviewed")
        if st.form_submit_button("검토 문항 저장",type="primary"):
            q=dict(base,topic_id=tid,prompt=prompt,options=options,answer=answer,explanation=explanation,hints=[x.strip() for x in hints.splitlines() if x.strip()],source_note=source)
            _change(svc.save_question,user,q,qid=qid,revision=revision,published=publish,reviewed=reviewed,message="문항을 저장했습니다. 공개 문항은 새 5문제 학습에 최대 2개씩 반영됩니다.")


def _content_manager(user):
    tid=_pick_topic("gg_manage")
    tab=st.radio("관리할 내용",["기본 문제·직접 추가","내 문항 수정","CSV 일괄 등록","학습지 업로드"],horizontal=True,key="gg_content_tab")
    if tab=="기본 문제·직접 추가":
        key="_gg_sample_"+tid
        if key not in st.session_state:st.session_state[key]=bank.generate(tid,1729)
        if st.button("다른 숫자로 예시 보기",key="gg_regenerate"):
            st.session_state[key]=bank.generate(tid,secrets.randbits(64));st.rerun()
        sample=st.session_state[key]
        idx=st.selectbox("수정할 기본 문항",range(5),format_func=lambda x:f"{x+1}. {sample[x]['prompt'][:55]}",key="gg_sample_index_"+tid)
        st.caption("기본 출제는 제작 시 구성한 문항 틀입니다. 실행 중 AI에 학생 정보나 학습지를 보내지 않습니다.")
        _question_form(user,tid,sample[idx])
    elif tab=="내 문항 수정":
        items=svc.teacher_questions(user,tid)
        if not items:st.info("이 주제에 직접 등록한 문항이 없습니다. 기본 문제를 수정하거나 CSV로 초안을 등록하세요.");return
        idx=st.selectbox("내 문항",range(len(items)),format_func=lambda i:("공개 · " if items[i]["published"] else "초안 · ")+items[i]["question"]["prompt"][:60],key="gg_owned_"+tid)
        item=items[idx]
        _question_form(user,tid,item["question"],item["id"],item["revision"],item["published"])
    elif tab=="CSV 일괄 등록":
        st.download_button("문항 CSV 양식 내려받기",bank.csv_template(),file_name="게임문항_등록양식.csv",mime="text/csv",key="gg_csv_template")
        st.caption("양식의 예시는 대칭이동 문제입니다. 현재 선택한 세부 주제에 맞게 내용을 바꾸세요. 파일은 1MB 이하, 1~100문항입니다. 등록 후 ‘내 문항 수정’에서 검토·공개합니다.")
        file=st.file_uploader("문항 CSV",type=["csv"],key="gg_csv_upload_"+tid)
        if file:
            try:
                parsed=bank.parse_csv(file.getvalue(),tid)
                st.dataframe([{"문제":q["prompt"],"정답":q["options"][q["answer"]]} for q in parsed],hide_index=True,width="stretch")
                if st.button(f"{len(parsed)}문항을 비공개 초안으로 등록",key="gg_csv_import"):
                    _change(svc.import_questions,user,parsed,message="초안을 등록했습니다. 각 문항을 검토하고 공개해 주세요.")
            except ValueError as exc:st.error(str(exc))
    else:
        st.info("학습지는 학생 참고자료로 올립니다. PDF·사진에서 문제를 자동 추출하지 않습니다. 게임으로 출제할 문항은 직접 입력하거나 CSV로 등록해 주세요.")
        with st.form("gg_resource_form"):
            title=st.text_input("학습지 제목",max_chars=150,key="gg_resource_title")
            classes=st.multiselect("공개 학급",CLASSES,key="gg_resource_classes")
            file=st.file_uploader("학습지 파일 · 8MB 이하",type=["pdf","png","jpg","jpeg","webp","docx","hwp","hwpx"],key="gg_resource_upload")
            confirm=st.checkbox("배포 권한이 있으며 학생 개인정보·비공개 정답을 제거한 자료입니다",key="gg_resource_rights")
            if st.form_submit_button("이 주제에 학습지 등록"):
                if file is None:st.error("파일을 선택해 주세요.")
                else:_change(svc.upload_resource,user,tid,title,classes,file.name,file.getvalue(),confirmed=confirm,message="선택한 학급에 학습지를 연결했습니다.",flush_user=user)
        _resources(user,tid,manage=True)


def _mission_manager(user):
    tid=_pick_topic("gg_mission")
    with st.form("gg_mission_form"):
        title=st.text_input("미션 제목",value=topic(tid)["label"]+" · 한 걸음 5문제",max_chars=120,key="gg_mission_title_"+tid)
        classes=st.multiselect("배포 학급",CLASSES,key="gg_mission_classes")
        points=st.checkbox("완료 학생의 상점 검토 요청 허용 (자동 부여하지 않음)",value=False,key="gg_mission_points")
        st.caption("현재 해당 학급에 등록된 학생에게 배포합니다. 시간제한·마감 벌점은 없으며 학생이 두 게임 중 하나를 고릅니다.")
        if st.form_submit_button("5문제 미션 배포",type="primary"):
            _change(svc.create_mission,user,title,tid,classes,allow_points=points,message="미션을 배포했습니다.",flush_user=user)
    st.subheader("내가 배포한 미션")
    for m in reversed(svc.missions(user)):
        st.write(f"**{m['title']}** · 대상 {m['count']}명 · "+("열림" if m["active"]=="1" else "새 시작 종료"))
        st.caption(TOPICS[m["topic_id"]]["label"]+" · "+("교사 승인 상점 가능" if m["allow_points"]=="1" else "캐릭터 보상만"))
        if m["active"]=="1" and st.button("새 미션 시작 종료",key="close_"+m["id"]):
            _change(svc.close_mission,user,m["id"],message="새 시작을 종료했습니다. 이미 시작한 학생은 계속 학습할 수 있습니다.")


def _teacher_growth(user):
    roster=svc.roster(user)
    clas=st.selectbox("학급",CLASSES,key="gg_growth_class")
    roster=[s for s in roster if s["class"]==clas]
    if not roster:st.info("이 학급에 등록된 학생이 없습니다.");return
    student=st.selectbox("학생",[s["id"] for s in roster],format_func=lambda sid:next(f"{s['name']} · {sid}" for s in roster if s["id"]==sid),key="gg_growth_student_"+clas)
    p=svc.profile(user,student);_growth(user,p,teacher=True)
    with st.form("gg_feedback_"+student):
        feedback=st.text_area("구체적인 변화에 대한 교사 피드백",max_chars=1000,key="gg_feedback_text_"+student,placeholder="예: 지난번에는 힌트로 찾았던 대칭 규칙을 이번에는 혼자 적용했네요.")
        if st.form_submit_button("학생에게 피드백 남기기"):
            _change(svc.save_feedback,user,student,feedback,message="학생의 성장기록에 피드백을 남겼습니다.")
    for sid,req in p["point_requests"].items():
        if req["status"]!="pending":continue
        own={m["id"] for m in svc.missions(user)}
        if req["mission_id"] not in own:continue
        with st.expander("완료 미션의 상점 검토 요청"):
            st.caption("이 조작만 기존 상점을 부여합니다. 별 조각은 차감·변환하지 않습니다.")
            with st.form("approve_"+student+sid):
                score=st.number_input("승인 상점",min_value=1,max_value=10,value=1,step=1,key="score_"+sid)
                reason=st.text_input("검토 사유",max_chars=300,key="reason_"+sid)
                decision=st.radio("검토 결과",["승인","보류"],key="decision_"+sid,horizontal=True)
                confirmed=st.checkbox("학습 내용을 확인했으며 이 결과로 처리합니다",key="confirm_"+sid)
                if st.form_submit_button("교사 검토 확정"):
                    if not confirmed:st.error("검토 확인란을 선택해 주세요.")
                    else:_change(svc.approve_points,user,student,sid,int(score),reason,approve=decision=="승인",message="교사 검토를 반영했습니다.",flush_user=user)


def page(user):
    st.markdown(art.CSS,unsafe_allow_html=True)
    st.markdown(art.hero(),unsafe_allow_html=True)
    if "_gg_nav_next" in st.session_state:
        st.session_state["_gg_child"]=st.session_state.pop("_gg_nav_next")
    _notice()
    child=st.radio("게임으로 배우기 하위 메뉴",["개념 학습게임","나의 성장기록"],horizontal=True,key="_gg_child")
    teacher=user.get("role")=="teacher"
    try:
        st.caption("현재 교과서 목차 · "+EDITIONS[svc.edition()]+" · 2022 개정")
        if teacher:
            if child=="나의 성장기록":_teacher_growth(user)
            else:
                action=st.radio("교사 도구",["학생 화면 미리보기","문항·학습지 관리","미션 배포","교과서 설정"],horizontal=True,key="_gg_teacher_action")
                if action=="학생 화면 미리보기":_teacher_preview(user)
                elif action=="문항·학습지 관리":_content_manager(user)
                elif action=="미션 배포":_mission_manager(user)
                else:
                    st.info("학교 교과서의 대표저자를 확인해 선택하세요. 처음에는 홍진곤 판본을 표시합니다. 판본을 바꿔도 동일 개념의 학습 기록은 유지됩니다.")
                    ed=st.selectbox("학교 교과서 대표저자",list(EDITIONS),index=list(EDITIONS).index(svc.edition()),format_func=EDITIONS.get,key="gg_edition_select")
                    if st.button("교과서 목차 저장",key="gg_edition_save"):_change(svc.set_edition,user,ed,message="교과서 목차를 반영했습니다.",flush_user=user)
                    st.caption("근거: 천재교과서·천재교육 공식 고등 교과서 소개의 목차. 세부 주제는 앱에서 별도로 나눈 학습 범위입니다.")
            _save_panel(user)
        else:
            p=svc.profile(user)
            if child=="나의 성장기록":_growth(user,p)
            else:
                s=next((s for s in p["sessions"] if s["id"]==p["active_id"]),None)
                if s:_lesson(user,p,s)
                else:_landing(user,p)
            _save_panel(user)
    except (ValueError,PermissionError) as exc:
        st.error(str(exc))
        if st.button("학습 상태 다시 읽기",key="gg_reload"):st.rerun()
    except Exception as exc:
        logging.getLogger(__name__).warning("Game page failed: %s",type(exc).__name__)
        st.error("학습 화면을 열지 못했습니다. 저장 연결을 확인하고 다시 열어 주세요. 기존 학생 자료를 삭제하거나 암호화키를 바꾸지 마세요.")
