"""JavaScript game selector and arcade host in Concept Learning Games."""
from pathlib import Path
import logging
import streamlit as st
from .play_screen import rerun as rerun_game
from . import play_lab_service as svc, play_lab_engine as lab

_component = None


def _frame(user, data, view, *, game_id=None, title=""):
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        _component = components.declare_component("good_math_play_lab", path=str(Path(__file__).with_name("play_lab_frontend")))
    prefix = "_lab_" + user["id"]
    event = _component(data=data, view=view, gameId=game_id, title=title,
                       ack=st.session_state.get(prefix+"_ack"), failed=st.session_state.get(prefix+"_failed"),
                       error=st.session_state.get(prefix+"_error", ""), key="math_play_lab_"+user["id"], default=None)
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or event["id"] == st.session_state.get(prefix+"_handled"):
        return
    st.session_state[prefix+"_handled"] = event["id"]
    if event.get("action") == "navigate":
        target = event.get("target")
        if target in {"hub", "avatar", "quiz", *lab.TITLES}:
            st.session_state[prefix+"_selection"] = target
            rerun_game()
        return
    if event.get("action") != "record":
        return
    try:
        svc.act(user, event.get("revision"), event.get("events"), preview=data["preview"])
        st.session_state[prefix+"_ack"] = event["id"]
        st.session_state.pop(prefix+"_failed", None)
        st.session_state.pop(prefix+"_error", None)
    except (ValueError, PermissionError) as error:
        st.session_state[prefix+"_failed"] = event["id"]
        st.session_state[prefix+"_error"] = str(error)
    except Exception as error:
        logging.getLogger(__name__).warning("Play lab save failed: %s", type(error).__name__)
        st.session_state[prefix+"_failed"] = event["id"]
        st.session_state[prefix+"_error"] = "기록을 반영하지 못했어요. 연결을 확인하고 다시 저장해 주세요."
    rerun_game()


def page(user, avatar_page):
    selection = st.session_state.get("_lab_"+user["id"]+"_selection", "hub")
    # Avatar/quiz have their own authorized snapshots. Do not load arcade history.
    if selection in ('avatar','quiz'):
        from .play_screen import return_bar
        return_bar(user)
        if selection=='avatar': avatar_page()
        else:
            from .function_quiz_view import page as quiz_page
            quiz_page(user)
        return
    data = svc.snapshot(user, preview=user.get("role") == "teacher", history=False)
    if selection in lab.TITLES:
        _frame(user, data, "arena", game_id=selection)
        if data["preview"]:
            st.caption("교사 미리보기 · 학생 기록에 영향을 주지 않습니다.")
        else:
            from .view import _save_panel
            with st.expander('☁ 기록 저장 상태 · 재시도'):
                _save_panel(user)
    else:
        _frame(user, data, "hub")


def summary(user, student_id=None):
    data = svc.snapshot(user, student_id)
    st.markdown("#### 수학 아케이드 기록")
    totals = list(data["games"].values())
    cols = st.columns(4)
    for col, title, value in zip(cols, ["참여한 게임", "완주", "성공한 활동", "다시 도전한 활동"],
                                  [len(totals), sum(g["wins"] for g in totals), sum(g["successes"] for g in totals), sum(g["errors"] for g in totals)]):
        col.metric(title, value)
    st.caption("게임별 활동 기록입니다. 아바타 게임의 별 조각·꾸미기 보상은 기존 방식으로 유지됩니다.")
    rows = []
    for gid, title in lab.TITLES.items():
        g = data["games"].get(gid, {})
        rows.append({"게임": title, "참여": g.get("starts", 0), "완주": g.get("wins", 0), "성공": g.get("successes", 0),
                     "재도전": g.get("errors", 0), "힌트": g.get("hints", 0), "완료 단계": g.get("clears", 0),
                     "학습 포인트": g.get("points", 0), "플레이 시간(초)": round(g.get("seconds", 0)), "최근 활동": g.get("last_at", "")})
    st.dataframe(rows, hide_index=True, width="stretch")
    if data["records"]:
        with st.expander("최근 게임 활동"):
            labels={"start":"시작", "success":"성공", "error":"재도전", "hint":"힌트", "clear":"단계 완료", "win":"완주", "retry":"다시 도전", "pause":"일시정지", "leave":"나가기", "resume":"이어하기", "wait":"다음 단계 대기"}
            st.dataframe([{"게임":lab.TITLES[r["game"]], "활동":labels.get(r["type"],r["type"]), "단계":r["stage"],
                           "문제":r["question"], "안내":r["message"], "기록 시각":r["at"]} for r in reversed(data["records"])], hide_index=True, width="stretch")
