"""Function concept quiz within Games; existing accounts and save pipeline."""
from pathlib import Path
import logging
import streamlit as st
from . import function_quiz_service as svc, service as games

_component=None


def summary(user,student_id=None):
    data=svc.snapshot(user,student_id)
    st.markdown("#### 함수 개념퀴즈 기록")
    totals=data["totals"]
    columns=st.columns(4)
    for col,label,value in zip(columns,["제출한 답","정답","다시 생각한 오답","해결한 개념"],
                               [totals["answered"],totals["correct"],totals["wrong"],sum(len(s["passed"]) for s in data["stages"].values())]):
        col.metric(label,value)
    st.caption(f"학습 포인트 {data['points']} · 단계별 6개 주제, 총 5단계. 재도전 응답도 횟수에 포함됩니다.")
    rows=[]
    for i,t in enumerate(data["topics"]):
        count=data["skills"].get(str(i),{})
        rows.append({"주제":t["title"],"정답":count.get("correct",0),"오답":count.get("wrong",0),
                     "해결 단계":", ".join(k for k,s in data["stages"].items() if str(i) in s["passed"]) or "아직 없음"})
    st.dataframe(rows,hide_index=True,width="stretch")
    if data["records"]:
        with st.expander("최근 함수 퀴즈 응답 30개"):
            for r in reversed(data["records"]):
                st.write(f"**{r['level']}단계 · {'정답' if r['correct'] else '오답'}** — {r['prompt']}")
                st.caption(f"내 선택: {r['selected']} / 정답: {r['answer']} · {r['at']}")


def page(user):
    preview=user.get("role")=="teacher"
    if preview:
        games.roster(user)  # Server-side teacher validation, even for preview.
        mode=st.radio("함수 퀴즈 교사 메뉴",["퀴즈 미리보기","학생 기록"],horizontal=True,key="function_teacher_tab")
        if mode=="학생 기록":
            roster=games.roster(user)
            if not roster:st.info("등록된 학생이 없습니다.");return
            classes=sorted({s["class"] for s in roster})
            cls=st.selectbox("학급",classes,key="function_class")
            targets={s["id"]:s for s in roster if s["class"]==cls}
            sid=st.selectbox("학생",list(targets),format_func=lambda x:f"{x} · {targets[x]['name']}",key="function_student")
            summary(user,sid)
            return
        st.caption("교사 미리보기 · 5단계를 자유롭게 체험하며 학생 기록에 저장되지 않습니다.")
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        _component=components.declare_component("good_function_quiz",path=str(Path(__file__).with_name("function_quiz_frontend")))
    data=svc.snapshot(user,preview=preview)
    event=_component(data=data,error=st.session_state.get("_function_error",""),key="function_quiz_"+user["id"],default=None)
    if isinstance(event,dict) and event.get("id")!=st.session_state.get("_function_last_event"):
        st.session_state["_function_last_event"]=event.get("id")
        st.session_state.pop("_function_error",None)
        try:svc.act(user,event.get("revision"),event,preview=preview)
        except (ValueError,PermissionError) as error:st.session_state["_function_error"]=str(error)
        except Exception as error:
            logging.getLogger(__name__).warning("Function quiz action failed: %s",type(error).__name__)
            st.session_state["_function_error"]="기록을 반영하지 못했어요. 연결을 확인하고 다시 시도해 주세요."
        st.rerun()
    if not preview:
        from .view import _save_panel
        _save_panel(user)
