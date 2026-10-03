"""수다노트: 다섯 가지 질문에 답하는 수업 성찰 게시판.
학생이 쓴 내용은 날짜·시간·학번·이름과 함께 학생별 파일(data/sudanotes/<학번>.csv)로 저장됩니다.
"""
import pandas as pd
import streamlit as st

import auth
import storage as db
import ui
from config import CLASSES, SUBJECTS, SUDANOTE_GUIDE, SUDANOTE_QUESTIONS

QKEYS = [f"q{i}" for i in range(1, len(SUDANOTE_QUESTIONS) + 1)]


def _qa_html(note):
    parts = []
    for i, (k, q) in enumerate(zip(QKEYS, SUDANOTE_QUESTIONS), start=1):
        parts.append(f'<div class="sn-q">질문{i}. {ui.esc(q)}</div>'
                     f'<div class="sn-a">{ui.esc(note.get(k, "")) or "<span class=meta>(답 없음)</span>"}</div>')
    return "".join(parts)


CSS = """<style>
.sn-q{font-weight:700;color:var(--ink);margin:.9rem 0 .25rem;}
.sn-q:first-child{margin-top:0;}
.sn-a{background:var(--soft);color:var(--ink);border-left:3px solid var(--hl);border-radius:0 8px 8px 0;padding:.55rem .8rem;line-height:1.7;}
.st-key-sn_form [data-testid="stTextArea"] label p{font-weight:700;color:var(--ink);font-size:1rem;}
</style>"""


# ---------------------------------------------------------------- 학생 ---
def _sync(key):
    st.session_state.setdefault("_sn_draft", {})[key] = st.session_state.get(f"sn_{key}", "")


def _student(user):
    drafts = st.session_state.setdefault("_sn_draft", {})
    with st.container(border=True, key="sn_form"):
        st.markdown("#### ✍️ 오늘의 수다노트")
        c1, c2 = st.columns(2)
        subject = c1.selectbox("과목", SUBJECTS, key="sn_subject")
        c2.text_input("날짜", value=db.today_str(), disabled=True)
        for i, (k, q) in enumerate(zip(QKEYS, SUDANOTE_QUESTIONS), start=1):
            if f"sn_{k}" not in st.session_state and drafts.get(k):
                st.session_state[f"sn_{k}"] = drafts[k]  # 잠금 등으로 화면이 바뀌어도 쓰던 글 유지
            st.text_area(f"질문{i}. {q}", key=f"sn_{k}", height=100, on_change=_sync, args=(k,),
                         placeholder="무엇이, 왜, 어떻게 그랬는지 나의 말로 적어 보세요.")
        if st.button("제출하기", type="primary", width="stretch"):
            answers = {k: st.session_state.get(f"sn_{k}", "").strip() for k in QKEYS}
            empty = [i for i, k in enumerate(QKEYS, start=1) if not answers[k]]
            if empty:
                st.error("아직 쓰지 않은 질문이 있어요: " + ", ".join(f"질문{i}" for i in empty))
            else:
                now = db.now()
                db.append("sudanotes", {
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"), "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M"), "class": user["class"], "student_id": user["id"],
                    "name": user["name"], "subject": subject, **answers,
                })
                short = [i for i, k in enumerate(QKEYS, start=1) if len(answers[k]) < 15]
                for k in QKEYS:
                    st.session_state.pop(f"sn_{k}", None)
                st.session_state["_sn_draft"] = {}
                st.session_state["_sn_done"] = short
                st.rerun()

    if "_sn_done" in st.session_state:
        short = st.session_state.pop("_sn_done")
        st.balloons()
        msg = "<h4>📬 수다노트를 제출했어요!</h4>오늘 수업을 나의 언어로 정리한 것, 정말 멋져요."
        if short:
            msg += ("<br>다음에는 " + ", ".join(f"질문{i}" for i in short) +
                    "에 '무엇이, 왜, 어떻게'를 조금 더 붙여 써 보면 더 좋아질 거예요.")
        ui.note(msg, "mint")

    mine = [n for n in db.read("sudanotes") if n["student_id"] == user["id"]]
    st.markdown(f"#### 📚 내가 쓴 수다노트 ({len(mine)}개)")
    if not mine:
        st.caption("아직 없어요.")
    for n in mine[::-1]:
        with st.expander(f"{n['date']} {n['time']} · {n['subject']}"):
            st.markdown(_qa_html(n), unsafe_allow_html=True)


# ---------------------------------------------------------------- 교사 ---
def _teacher():
    c1, c2, c3 = st.columns(3)
    cls = c1.selectbox("학급", CLASSES, key="snt_cls")
    subject = c2.selectbox("과목", ["전체"] + SUBJECTS, key="snt_subj")
    day = c3.date_input("날짜", value=db.now().date(), format="YYYY-MM-DD", key="snt_day")
    day_s = day.strftime("%Y-%m-%d")
    roster = auth.students(cls)
    notes = [n for n in db.read("sudanotes") if n["class"] == cls]
    if subject != "전체":
        notes = [n for n in notes if n["subject"] == subject]
    today = [n for n in notes if n["date"] == day_s]

    done = {n["student_id"] for n in today}
    st.markdown(f"**{day_s} 제출 현황** {len(done)}/{len(roster)}명")
    missing = [u["name"] for u in roster if u["id"] not in done]
    if missing:
        st.caption("아직 안 쓴 학생: " + ", ".join(missing))

    view = st.radio("보기", ["이 날짜 전체", "학생별 모아 보기"], horizontal=True, key="snt_view")
    if view == "이 날짜 전체":
        if not today:
            st.info("이 날짜에 제출된 수다노트가 없어요.")
        for n in today[::-1]:
            with st.expander(f"{n['name']} ({n['student_id']}) · {n['time']} · {n['subject']}"):
                st.markdown(_qa_html(n), unsafe_allow_html=True)
    else:
        if not roster:
            st.info("이 학급에 등록된 학생이 없어요.")
            return
        stu = st.selectbox("학생", roster, format_func=lambda u: f"{u['id']} {u['name']}", key="snt_stu")
        theirs = [n for n in notes if n["student_id"] == stu["id"]]
        st.caption(f"{stu['name']} 학생의 수다노트 {len(theirs)}개")
        for n in theirs[::-1]:
            with st.expander(f"{n['date']} {n['time']} · {n['subject']}"):
                st.markdown(_qa_html(n), unsafe_allow_html=True)

    if notes:
        df = pd.DataFrame(notes)[["date", "time", "class", "student_id", "name", "subject"] + QKEYS]
        df.columns = ["날짜", "시간", "학급", "학번", "이름", "과목"] + [f"질문{i}" for i in range(1, len(QKEYS) + 1)]
        st.download_button(f"📄 {cls} 수다노트 전체 CSV 내려받기", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"수다노트_{cls}.csv", mime="text/csv")


def page(user):
    ui.page_title("수다노트", "오늘 수업을 나의 언어로 정리하는 시간")
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(SUDANOTE_GUIDE)
    if user["role"] == "teacher":
        _teacher()
    else:
        _student(user)
