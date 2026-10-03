"""교사전용 > 생기부 생성기 (교과 세부능력 및 특기사항 초안 작성)

기초자료: 수다노트 + 교사 관찰기록 + 질문 게시판 질문
초안: ChatGPT(OpenAI API). API 키가 없으면 '프롬프트 복사' 후 ChatGPT 웹사이트에 붙여 넣어 쓸 수 있음.
학생 이름·학번은 AI에 보내지 않습니다(학급 학생 이름은 모두 '학생'/'친구'로 바꿔서 전송).
"""
import difflib
import re
from datetime import date

import pandas as pd
import requests
import streamlit as st

import auth
import storage as db
import ui
from config import CLASSES, SUBJECTS, SUDANOTE_QUESTIONS

MIN_LEN, MAX_LEN = 300, 400
MAX_SOURCE_CHARS = 7000  # AI에 보내는 자료 길이 제한(비용 조절)


# ------------------------------------------------------------- 도구 ---
def neis_bytes(text: str) -> int:
    """나이스 기준 바이트: 한글 3, 줄바꿈 2, 그 밖(영문·숫자·공백·기호) 1."""
    n = 0
    for ch in text:
        if ch == "\n":
            n += 2
        elif ord(ch) > 127:
            n += 3
        else:
            n += 1
    return n


def default_period():
    t = db.now().date()
    if 3 <= t.month <= 8:
        return date(t.year, 3, 1), date(t.year, 8, 31)
    y = t.year if t.month >= 9 else t.year - 1
    return date(y, 9, 1), date(y + 1, 2, 28)


def _in(day: str, start: date, end: date) -> bool:
    return start.strftime("%Y-%m-%d") <= (day or "")[:10] <= end.strftime("%Y-%m-%d")


def gather(stu, subject, start, end):
    notes = [n for n in db.read("sudanotes") if n["student_id"] == stu["id"]
             and n["subject"] == subject and _in(n["date"], start, end)]
    obs = [o for o in db.read("observations") if o["student_id"] == stu["id"]
           and _in(o["created_at"], start, end)]
    qs = [q for q in db.read("questions") if q["student_id"] == stu["id"]
          and q["subject"] == subject and _in(q["created_at"], start, end)]
    return notes, obs, qs


def anonymize(text: str, names: list[str]) -> str:
    for nm in sorted(names, key=len, reverse=True):
        if nm and len(nm) >= 2:
            text = text.replace(nm, "친구")
    return text


def source_text(stu, notes, obs, qs, roster_names):
    parts = []
    if notes:
        parts.append(f"[수다노트: 학생이 수업 후 직접 쓴 성찰 기록 {len(notes)}회]")
        for n in notes[::-1]:  # 최신부터
            lines = [f"- {n['date']}"]
            for i, q in enumerate(SUDANOTE_QUESTIONS, start=1):
                a = n.get(f"q{i}", "").strip()
                if a:
                    lines.append(f"  질문{i}({q[:18]}…): {a}")
            parts.append("\n".join(lines))
    if obs:
        parts.append(f"[교사 관찰기록 {len(obs)}건]")
        parts += [f"- {o['created_at'][:10]} ({o['category']}) {o['content']}" for o in obs[::-1]]
    if qs:
        parts.append(f"[학생이 질문 게시판에 올린 질문 {len(qs)}건]")
        parts += [f"- {q['created_at'][:10]} {q['title']}: {q['content']}" for q in qs[::-1]]
    text = "\n".join(parts)
    names = list(roster_names) + [stu["name"]]
    text = anonymize(text, [n for n in names if n != stu["name"]])
    text = text.replace(stu["name"], "학생")
    return text[:MAX_SOURCE_CHARS]


def build_prompt(subject, src):
    guide = db.get_setting("record_guide")
    examples = db.get_setting("record_examples").strip()
    banned = db.get_setting("record_banned")
    system = (
        "너는 한국 고등학교 수학 교사가 학교생활기록부의 '교과학습발달상황 세부능력 및 특기사항(세특)'을 "
        "작성하도록 돕는 보조자다. 아래 규칙을 반드시 지킨다.\n"
        "1. 제공된 자료에 근거한 사실만 쓴다. 자료에 없는 활동, 능력, 성과를 지어내지 않는다.\n"
        "2. 교사가 수업에서 관찰한 관점으로 쓴다. 학생의 자기 기록을 '~라고 함'처럼 나열하지 말고, "
        "학생이 보인 이해·과정·변화를 관찰 문장으로 서술한다.\n"
        "3. 한 문단으로 쓰고, 문장 끝은 '~함', '~임', '~보임', '~을 보여 줌' 같은 명사형 종결을 쓴다.\n"
        f"4. 분량은 공백 포함 {MIN_LEN}~{MAX_LEN}자로 한다.\n"
        "5. 학생 이름, 학번, 학교명, 특정 대학·기관·업체명, 대회·수상·자격증, 사교육, 부모 관련 내용, "
        "영문 약어를 쓰지 않는다. 주어로 '학생'이나 이름을 쓰지 않고 바로 서술한다.\n"
        "6. 구체적인 수학 개념명과 활동을 포함한다. 근거 없는 최상급 칭찬(탁월한, 독보적인 등)을 피한다.\n"
        f"7. 다음 표현은 쓰지 않는다: {banned}\n"
        f"8. 교사의 추가 지침: {guide}\n"
        + (f"9. 아래는 문체만 참고할 예시다. 내용은 절대 따라 하지 않는다.\n{examples}\n" if examples else "")
        + "출력은 세특 본문 한 문단만 쓴다. 제목, 설명, 따옴표를 붙이지 않는다."
    )
    user = f"과목: {subject}\n\n아래 자료를 바탕으로 세특 초안을 작성해 줘.\n\n{src}"
    return system, user


def openai_cfg():
    try:
        o = st.secrets["openai"]
        return o.get("api_key", "").strip(), o.get("model", "gpt-4o-mini").strip() or "gpt-4o-mini"
    except Exception:
        return "", ""


def _base_url():
    try:
        return st.secrets["openai"].get("base_url", "https://api.openai.com/v1").rstrip("/")
    except Exception:
        return "https://api.openai.com/v1"


def call_gpt(system, user):
    key, model = openai_cfg()
    r = requests.post(
        f"{_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]},
        timeout=120,
    )
    if r.status_code == 401:
        raise RuntimeError("OpenAI API 키가 올바르지 않아요. secrets 의 [openai] api_key 를 확인해 주세요.")
    if r.status_code == 404:
        raise RuntimeError(f"'{model}' 모델을 쓸 수 없어요. secrets 의 [openai] model 이름을 확인해 주세요.")
    if r.status_code == 429:
        raise RuntimeError("OpenAI 사용 한도를 넘었거나 결제 잔액이 없어요. platform.openai.com 의 Billing 을 확인해 주세요.")
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI 오류 ({r.status_code}): {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')


def check(text, others):
    """경고 목록: 분량, 금지 표현, 영문, 다른 학생과의 유사 문장."""
    warns = []
    n = len(text)
    if n and not (MIN_LEN <= n <= MAX_LEN):
        warns.append(f"분량이 {n}자예요. 목표는 {MIN_LEN}~{MAX_LEN}자예요.")
    banned = [w.strip() for w in db.get_setting("record_banned").split(",") if w.strip()]
    hit = [w for w in banned if w in text]
    if hit:
        warns.append("기재 금지·주의 표현이 있어요: " + ", ".join(hit))
    eng = sorted(set(re.findall(r"[A-Za-z]{2,}", text)))
    if eng:
        warns.append("영문 표기가 있어요(우리말로 바꿀 수 있는지 확인): " + ", ".join(eng))
    sents = [s.strip() for s in re.split(r"(?<=[.。])\s+", text) if len(s.strip()) > 15]
    for other_name, other in others:
        osents = [s.strip() for s in re.split(r"(?<=[.。])\s+", other) if len(s.strip()) > 15]
        for s in sents:
            for o in osents:
                if difflib.SequenceMatcher(None, s, o).ratio() > 0.8:
                    warns.append(f"{other_name} 학생 세특과 매우 비슷한 문장이 있어요: “{s[:40]}…”")
                    break
    return warns


def find_record(stu, subject, period):
    for r in db.read("records"):
        if r["student_id"] == stu["id"] and r["subject"] == subject and r["period"] == period:
            return r
    return None


def save_record(stu, subject, period, text, sources):
    cur = find_record(stu, subject, period)
    data = {"updated_at": db.now_str(), "text": text, "sources": sources}
    if cur:
        db.update("records", cur["id"], data)
    else:
        db.append("records", {"period": period, "subject": subject, "class": stu["class"],
                              "student_id": stu["id"], "name": stu["name"], **data})


# ------------------------------------------------------------- 화면 ---
def tab_record():
    st.caption("수다노트·관찰기록·질문을 모아 교과세특 초안을 만들어요. "
               "초안은 참고용이며, 사실 확인과 최종 문장은 반드시 선생님이 결정해 주세요.")
    key, model = openai_cfg()

    c1, c2, c3 = st.columns([1, 1, 2])
    cls = c1.selectbox("학급", CLASSES, key="rec_cls")
    subject = c2.selectbox("과목", SUBJECTS, key="rec_subj")
    ds, de = default_period()
    period_in = c3.date_input("기간", value=(ds, de), format="YYYY-MM-DD", key="rec_period")
    if not isinstance(period_in, (list, tuple)) or len(period_in) != 2:
        st.info("기간의 시작일과 종료일을 모두 골라 주세요.")
        return
    start, end = period_in
    period = f"{start}~{end}"
    roster = auth.students(cls)
    if not roster:
        st.info("이 학급에 등록된 학생이 없어요.")
        return
    names = [u["name"] for u in roster]

    with st.expander("⚙️ 작성 규칙 · 문체 예시 · 금지 표현"):
        g = st.text_area("추가 지침", value=db.get_setting("record_guide"), height=90)
        ex = st.text_area("문체 참고 예시 (선생님이 좋아하는 세특 문장 1~2개. 내용은 따라 하지 않고 말투만 참고해요)",
                          value=db.get_setting("record_examples"), height=110)
        bn = st.text_area("금지·주의 표현 (쉼표로 구분)", value=db.get_setting("record_banned"), height=80)
        if st.button("규칙 저장", key="rec_rule_save"):
            db.set_setting("record_guide", g)
            db.set_setting("record_examples", ex)
            db.set_setting("record_banned", bn)
            st.success("저장했어요.")

    # 학급 현황 + 일괄 생성
    recs = {r["student_id"]: r for r in db.read("records")
            if r["class"] == cls and r["subject"] == subject and r["period"] == period}
    rows = []
    for u in roster:
        notes, obs, qs = gather(u, subject, start, end)
        r = recs.get(u["id"])
        rows.append({"학번": u["id"], "이름": u["name"], "수다노트": len(notes), "관찰기록": len(obs),
                     "질문": len(qs), "세특": f"{len(r['text'])}자 · {neis_bytes(r['text'])}B" if r else "—"})
    st.markdown("#### 학급 현황")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=240)

    b1, b2 = st.columns(2)
    todo = [u for u in roster if u["id"] not in recs]
    if b1.button(f"🤖 초안 없는 학생 {len(todo)}명 한꺼번에 만들기", disabled=not key or not todo,
                 width="stretch", help=None if key else "OpenAI API 키가 있어야 해요."):
        bar = st.progress(0.0, text="초안을 만드는 중...")
        made, skipped = 0, []
        todo = [u for u in todo if not find_record(u, subject, period)]  # 이미 저장된 세특은 절대 덮어쓰지 않음
        for i, u in enumerate(todo, start=1):
            notes, obs, qs = gather(u, subject, start, end)
            if not (notes or obs or qs):
                skipped.append(u["name"])
            else:
                try:
                    sysm, usr = build_prompt(subject, source_text(u, notes, obs, qs, names))
                    save_record(u, subject, period, call_gpt(sysm, usr), f"수다노트{len(notes)}·관찰{len(obs)}·질문{len(qs)}")
                    made += 1
                except Exception as e:
                    st.error(f"{u['name']}: {e}")
                    break
            bar.progress(i / len(todo), text=f"{i}/{len(todo)}명 처리")
        st.session_state["_rec_msg"] = (f"{made}명 초안을 만들었어요." +
                                        (f" 기초자료가 없어 건너뜀: {', '.join(skipped)}" if skipped else ""))
        st.rerun()
    if "_rec_msg" in st.session_state:
        st.success(st.session_state.pop("_rec_msg"))
    if recs:
        df = pd.DataFrame([{"학번": r["student_id"], "이름": r["name"], "과목": r["subject"],
                            "세특": r["text"], "글자수": len(r["text"]), "바이트": neis_bytes(r["text"])}
                           for r in sorted(recs.values(), key=lambda r: r["student_id"])])
        b2.download_button("📄 학급 세특 CSV 내려받기 (나이스 붙여넣기용)", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"세특_{cls}_{subject}.csv", mime="text/csv", width="stretch")

    # 학생 한 명씩
    st.markdown("#### 학생별 작성")
    stu = st.selectbox("학생", roster, format_func=lambda u: f"{u['id']} {u['name']}", key="rec_stu")
    notes, obs, qs = gather(stu, subject, start, end)
    st.caption(f"기초자료: 수다노트 {len(notes)}회 · 관찰기록 {len(obs)}건 · 질문 {len(qs)}건")
    if not (notes or obs or qs):
        st.warning("이 기간에 기초자료가 없어요. 기간이나 과목을 확인해 주세요.")
        return
    src = source_text(stu, notes, obs, qs, names)
    with st.expander("📂 AI에 보내는 기초자료 보기 (이름은 '학생'·'친구'로 바뀌어 있어요)"):
        st.text(src)

    box_key = f"rec_text_{stu['id']}_{subject}_{period}"
    saved = find_record(stu, subject, period)
    if box_key not in st.session_state:
        st.session_state[box_key] = saved["text"] if saved else ""

    sysm, usr = build_prompt(subject, src)
    g1, g2 = st.columns(2)
    if g1.button("🤖 ChatGPT로 초안 만들기", type="primary", disabled=not key, width="stretch"):
        with st.spinner("초안을 쓰는 중... (10~30초)"):
            try:
                st.session_state[box_key] = call_gpt(sysm, usr)
                st.rerun()
            except Exception as e:
                st.error(str(e))
    with g2.popover("📋 API 없이: 프롬프트 복사해서 ChatGPT에 붙여 넣기", width="stretch"):
        st.caption("오른쪽 위 복사 버튼을 눌러 chatgpt.com 에 붙여 넣고, 받은 결과를 아래 칸에 붙여 넣으세요.")
        st.code(sysm + "\n\n" + usr, language=None, wrap_lines=True)
    if not key:
        st.caption("ℹ️ secrets 에 [openai] api_key 를 넣으면 버튼 한 번으로 초안을 만들 수 있어요.")

    text = st.text_area("세특 (직접 고칠 수 있어요)", key=box_key, height=200)
    n, b = len(text), neis_bytes(text)
    ok_len = MIN_LEN <= n <= MAX_LEN
    st.markdown(f"**{n}자** · **{b}바이트** (나이스 기준) {'✅' if ok_len else '⚠️ 목표 ' + str(MIN_LEN) + '~' + str(MAX_LEN) + '자'}")
    others = [(r["name"], r["text"]) for r in db.read("records")
              if r["class"] == cls and r["subject"] == subject and r["student_id"] != stu["id"]]
    for w in check(text, others):
        st.warning(w)
    if st.button("💾 저장", disabled=not text.strip()):
        save_record(stu, subject, period, text.strip(), f"수다노트{len(notes)}·관찰{len(obs)}·질문{len(qs)}")
        st.session_state["_rec_saved"] = stu["name"]
        st.rerun()
    if st.session_state.get("_rec_saved"):
        st.success(f"{st.session_state.pop('_rec_saved')} 학생 세특을 저장했어요. (교사만 볼 수 있어요)")
    if saved:
        st.caption(f"마지막 저장: {saved['updated_at']}")
