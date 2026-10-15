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
        parts.append(f'<div class="sn-qa sn-qa-{i}"><div class="sn-q">질문{i}. {ui.esc(q)}</div>'
                     f'<div class="sn-a">{ui.esc(note.get(k, "")) or "<span class=meta>(답 없음)</span>"}</div></div>')
    return "".join(parts)


CSS = """<style>
.st-key-pastel_sudanote {
  --sn-ink:var(--ink,light-dark(#263553,#E6ECF7));
  --sn-surface:light-dark(#FFFFFF,#19243B);
  --sn-muted:light-dark(#66728A,#B4BED2);
  --sn-purple:light-dark(#725294,#D6BDEC);
  --sn-purple-line:light-dark(#C9B4E2,#765E8E);
  --sn-purple-bg:light-dark(#F2ECFB,#30283F);
}
.st-key-pastel_sudanote :is(.st-key-sn_guide,.st-key-sn_form,.st-key-sn_filters,.st-key-sn_history) {
  border:1.5px solid var(--sn-purple-line); border-radius:20px;
  padding:1.1rem 1.2rem; gap:.8rem; color:var(--sn-ink);
  box-shadow:0 4px 0 light-dark(#E7E3F1,#131C2D);
}
.st-key-pastel_sudanote .st-key-sn_guide {
  background:linear-gradient(110deg,var(--sn-purple-bg),light-dark(#FFFBED,#352F26));
  border-left:5px solid var(--sn-purple-line);
}
.st-key-sn_guide .sn-eyebrow {
  display:inline-flex; align-items:center; padding:.2rem .65rem; margin:0;
  border-radius:99px; background:var(--sn-surface); color:var(--sn-purple);
  border:1px solid var(--sn-purple-line); font-size:.77rem; font-weight:800; letter-spacing:.06em;
}
.st-key-sn_guide [data-testid="stMarkdownContainer"] p {
  line-height:1.7; margin-bottom:.45rem; color:var(--sn-ink);
}
.st-key-sn_guide [data-testid="stMarkdownContainer"] p:first-child strong {
  font-size:1.1rem; color:var(--sn-purple);
}
.st-key-pastel_sudanote .st-key-sn_form {background:var(--sn-surface);}
.st-key-pastel_sudanote .st-key-sn_filters {
  background:light-dark(#EAF7F1,#20382F); border-color:light-dark(#A6CCB9,#527A64);
}
.st-key-pastel_sudanote .st-key-sn_history {
  background:light-dark(#F8F5FD,#242237); margin-top:.35rem;
}
.st-key-pastel_sudanote :is(.st-key-sn_form,.st-key-sn_history,.st-key-sn_filters) h4 {
  margin:0; padding:0; font-size:1.25rem; color:var(--sn-ink);
}
.st-key-pastel_sudanote :is(.st-key-sn_question_1,.sn-qa-1) {
  --sn-panel:light-dark(#ECF8F1,#203A30); --sn-edge:light-dark(#B3D7C1,#527A64);
  --sn-accent:light-dark(#3D7458,#B2E1C4); --sn-number:"01";
}
.st-key-pastel_sudanote :is(.st-key-sn_question_2,.sn-qa-2) {
  --sn-panel:light-dark(#F3EDFC,#322A43); --sn-edge:light-dark(#D0BFE8,#775D92);
  --sn-accent:light-dark(#78559D,#DEC7F4); --sn-number:"02";
}
.st-key-pastel_sudanote :is(.st-key-sn_question_3,.sn-qa-3) {
  --sn-panel:light-dark(#ECF4FD,#23354A); --sn-edge:light-dark(#B5CFEA,#53779B);
  --sn-accent:light-dark(#456F9B,#B6D7F8); --sn-number:"03";
}
.st-key-pastel_sudanote :is(.st-key-sn_question_4,.sn-qa-4) {
  --sn-panel:light-dark(#FFF2E8,#3E3027); --sn-edge:light-dark(#E6C3A5,#946D4D);
  --sn-accent:light-dark(#94633C,#F4CFAC); --sn-number:"04";
}
.st-key-pastel_sudanote :is(.st-key-sn_question_5,.sn-qa-5) {
  --sn-panel:light-dark(#FDEEF2,#3D2935); --sn-edge:light-dark(#E6B9C7,#8D5E71);
  --sn-accent:light-dark(#9A5771,#F1BED2); --sn-number:"05";
}
.st-key-sn_form :is(.st-key-sn_question_1,.st-key-sn_question_2,.st-key-sn_question_3,.st-key-sn_question_4,.st-key-sn_question_5) {
  padding:.85rem 1rem; border:1.5px solid var(--sn-edge); border-left:4px solid var(--sn-edge);
  border-radius:16px; background:var(--sn-panel); gap:.35rem;
}
.st-key-sn_form [data-testid="stTextArea"] label p {
  font-weight:750; color:var(--sn-ink); font-size:.98rem; line-height:1.6;
}
.st-key-sn_form [data-testid="stTextArea"] label p::before {
  content:var(--sn-number); display:inline-grid; place-items:center; vertical-align:middle;
  min-width:1.9rem; height:1.9rem; margin-right:.5rem; border-radius:10px;
  border:1px solid var(--sn-edge); color:var(--sn-accent); background:var(--sn-surface);
  font-size:.78rem; font-weight:800;
}
.st-key-sn_form [data-testid="stTextArea"] textarea {
  border:1px solid var(--sn-edge); border-radius:11px; background:var(--sn-surface);
  color:var(--sn-ink); line-height:1.7; padding:.7rem .8rem;
}
.st-key-sn_form [data-testid="stTextArea"] textarea:focus {
  border-color:var(--sn-accent); outline:2px solid var(--sn-edge); outline-offset:1px;
}
.st-key-pastel_sudanote :is(.st-key-sn_form,.st-key-sn_filters,.st-key-sn_history)
  :is([data-testid="stSelectbox"],[data-testid="stDateInput"],[data-testid="stTextInput"],[data-testid="stRadio"]) label p {
  color:var(--sn-purple); font-weight:800;
}
.st-key-pastel_sudanote :is([data-testid="stSelectbox"],[data-testid="stDateInput"],[data-testid="stTextInput"])
  :is([data-baseweb="select"] > div,[data-baseweb="input"],.react-aria-ComboBox > [role="group"],.react-aria-DatePicker > [role="group"]) {
  background:var(--sn-surface); border:1.5px solid var(--sn-purple-line); border-radius:12px;
  min-height:44px; box-shadow:0 2px 0 light-dark(#E5DEF0,#1C1726);
}
.st-key-sn_form button[kind="primary"] {
  min-height:46px; background:light-dark(#D6EFDF,#294D3A); color:light-dark(#2C6142,#D4F4DF);
  border:1.5px solid light-dark(#75A888,#75AD8B); border-radius:12px; font-weight:800;
  box-shadow:0 3px 0 light-dark(#B4D6C0,#172F22);
}
.st-key-sn_form button[kind="primary"]:hover:not(:disabled) {
  background:light-dark(#C4E7D1,#365E47); border-color:light-dark(#386B4B,#A9D6B8);
}
.st-key-sn_form button[kind="primary"]:focus-visible {outline:3px solid var(--sn-purple); outline-offset:3px;}
.sn-status {
  display:flex; justify-content:space-between; align-items:center; gap:.65rem; flex-wrap:wrap;
  padding:.65rem .85rem; border:1px solid light-dark(#A6CCB9,#527A64); border-radius:12px;
  background:var(--sn-surface); color:var(--sn-ink); font-size:.92rem;
}
.sn-status strong {color:light-dark(#35694E,#B9E2C8);}
.sn-status-count {padding:.25rem .65rem; border-radius:99px; background:light-dark(#D9EFE2,#2C4E3B); font-weight:800; white-space:nowrap;}
.st-key-sn_history [data-testid="stRadio"] :is(label[data-testid="stRadioOption"],label[data-baseweb="radio"]) {
  padding:.55rem .8rem; border:1.5px solid var(--sn-purple-line); border-radius:12px;
  background:var(--sn-surface); box-shadow:0 2px 0 light-dark(#E4DAF0,#191622); cursor:pointer;
}
.st-key-sn_history [data-testid="stRadio"] :is(label[data-testid="stRadioOption"],label[data-baseweb="radio"]):has(input:checked) {
  background:var(--sn-purple-bg); border-color:var(--sn-purple); box-shadow:inset 0 -3px 0 var(--sn-purple);
}
.st-key-sn_history [data-testid="stRadio"] :is(label[data-testid="stRadioOption"],label[data-baseweb="radio"]):has(input:checked) p::after {
  content:" ✓"; color:var(--sn-purple); font-weight:800;
}
.st-key-sn_history [data-testid="stRadio"] :is(label[data-testid="stRadioOption"],label[data-baseweb="radio"]):has(input:focus-visible) {
  outline:3px solid var(--sn-purple); outline-offset:3px;
}
.st-key-sn_history [data-testid="stExpander"] details {
  border:1.5px solid var(--sn-purple-line); border-radius:13px; background:var(--sn-surface); overflow:hidden;
}
.st-key-sn_history [data-testid="stExpander"] summary {
  padding:.7rem .85rem; background:light-dark(#EBE5F8,#342B48); color:var(--sn-ink); font-weight:750;
}
.st-key-sn_history [data-testid="stExpander"] summary:hover {background:light-dark(#E2D8F3,#413552);}
.st-key-sn_history [data-testid="stExpander"] details[open] summary {border-bottom:1px solid var(--sn-purple-line);}
.st-key-sn_history [data-testid="stDownloadButton"] button {
  min-height:44px; border:1.5px solid var(--sn-purple-line); border-radius:12px;
  background:var(--sn-purple-bg); color:var(--sn-purple); font-weight:800;
}
.st-key-pastel_sudanote .sn-qa {border:1px solid var(--sn-edge); border-radius:12px; overflow:hidden; margin:.65rem 0;}
.st-key-pastel_sudanote .sn-q {font-weight:750; color:var(--sn-accent); background:var(--sn-panel); padding:.65rem .8rem; line-height:1.6;}
.st-key-pastel_sudanote .sn-a {background:var(--sn-surface); color:var(--sn-ink); padding:.65rem .8rem; line-height:1.7; overflow-wrap:anywhere;}
@media (max-width:640px) {
  .st-key-pastel_sudanote :is(.st-key-sn_guide,.st-key-sn_form,.st-key-sn_filters,.st-key-sn_history) {padding:.85rem .8rem; border-radius:16px;}
  .st-key-sn_form :is(.st-key-sn_question_1,.st-key-sn_question_2,.st-key-sn_question_3,.st-key-sn_question_4,.st-key-sn_question_5) {padding:.7rem .65rem;}
}
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
            with st.container(border=True, key=f"sn_question_{i}"):
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
    with st.container(border=True, key="sn_history"):
        st.markdown(f"#### 📚 내가 쓴 수다노트 ({len(mine)}개)")
        if not mine:
            st.caption("아직 없어요.")
        for n in mine[::-1]:
            with st.expander(f"{n['date']} {n['time']} · {n['subject']}"):
                st.markdown(_qa_html(n), unsafe_allow_html=True)


# ---------------------------------------------------------------- 교사 ---
def _teacher():
    with st.container(border=True, key="sn_filters"):
        st.markdown("#### 🗂️ 수다노트 모아 보기")
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
        st.markdown(f'<div class="sn-status"><strong>{ui.esc(day_s)} 제출 현황</strong>'
                    f'<span class="sn-status-count">{len(done)}/{len(roster)}명</span></div>',
                    unsafe_allow_html=True)
        missing = [u["name"] for u in roster if u["id"] not in done]
        if missing:
            st.caption("아직 안 쓴 학생: " + ", ".join(missing))

    with st.container(border=True, key="sn_history"):
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
    with st.container(key="pastel_sudanote"):
        ui.page_title("수다노트", "오늘 수업을 나의 언어로 정리하는 시간")
        st.markdown(CSS, unsafe_allow_html=True)
        with st.container(border=True, key="sn_guide"):
            st.markdown('<p class="sn-eyebrow">나의 배움 기록</p>', unsafe_allow_html=True)
            st.markdown(SUDANOTE_GUIDE)
        if user["role"] == "teacher":
            _teacher()
        else:
            _student(user)
