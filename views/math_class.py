"""3. 수업 (공통수학1, 공통수학2)
평가계획 / 단원별 학습지 / 학급 게시판(결과물 제출 + 자동 피드백) / 질문 게시판
"""
import random

import streamlit as st

import auth
import storage as db
import ui
from config import CLASSES, DEFAULT_UNITS


def units(subject):
    raw = db.get_setting(f"units_{subject}")
    lst = [u.strip() for u in raw.splitlines() if u.strip()] if raw else list(DEFAULT_UNITS[subject])
    return lst + ["기타"]


def _upload(f, public):
    try:
        return db.save_upload(f, public=public)
    except Exception as e:
        st.error(f"'{f.name}' 파일을 올리지 못했어요: {e}")
        return None


def make_feedback(name, content, has_file):
    msgs = [m.strip() for m in db.get_setting("feedback_messages").splitlines() if m.strip()]
    fb = (random.choice(msgs) if msgs else "{name}님, 잘 받았어요!").replace("{name}", name)
    if len(content.strip()) < 30 and not has_file:
        fb += " " + db.get_setting("short_feedback")
    return fb


# ------------------------------------------------------------- 평가계획 ---
def tab_plan(user, subject):
    is_t = user["role"] == "teacher"
    if is_t:
        with st.expander("➕ 평가계획 올리기", expanded=False):
            with st.form(f"plan_up_{subject}", clear_on_submit=True):
                title = st.text_input("제목", value=f"{subject} 평가계획")
                desc = st.text_area("설명 (선택)", height=80)
                f = st.file_uploader("파일", key=f"plan_file_{subject}")
                ok = st.form_submit_button("올리기", type="primary")
            if ok:
                if not f:
                    st.error("파일을 골라 주세요.")
                else:
                    with st.spinner("올리는 중..."):
                        res = _upload(f, True)
                    if res:
                        fid, url = res
                        db.append("materials", {
                            "uploaded_at": db.now_str(), "subject": subject, "category": "평가계획",
                            "unit": "", "title": title, "description": desc, "file_id": fid,
                            "file_name": f.name, "file_url": url, "mime": f.type or "",
                        })
                        st.success("올렸어요.")
                        st.rerun()
    rows = [m for m in db.read("materials") if m["subject"] == subject and m["category"] == "평가계획"]
    if not rows:
        st.info("아직 올라온 평가계획이 없어요.")
    for m in rows[::-1]:
        _material_card(user, m)


def _material_card(user, m):
    with st.container(border=True):
        st.markdown(f"**{m['title']}**  \n<span class='meta'>{m['uploaded_at'][:10]}</span>",
                    unsafe_allow_html=True)
        if m["description"]:
            st.write(m["description"])
        c1, c2 = st.columns([4, 1])
        with c1:
            ui.file_widget(m, m["id"])
        if user["role"] == "teacher":
            with c2:
                if st.button("삭제", key=f"del_m_{m['id']}"):
                    db.delete_file(m["file_id"])
                    db.delete("materials", m["id"])
                    st.rerun()


# --------------------------------------------------------------- 학습지 ---
def tab_sheets(user, subject):
    us = units(subject)
    if user["role"] == "teacher":
        with st.expander("➕ 학습지 올리기", expanded=False):
            with st.form(f"ws_up_{subject}", clear_on_submit=True):
                unit = st.selectbox("단원", us)
                title = st.text_input("제목", placeholder="예: 3차시 나머지정리 학습지")
                desc = st.text_area("설명 (선택)", height=70)
                files = st.file_uploader("파일 (여러 개 가능)", accept_multiple_files=True,
                                         key=f"ws_files_{subject}")
                ok = st.form_submit_button("올리기", type="primary")
            if ok:
                if not files:
                    st.error("파일을 골라 주세요.")
                else:
                    done = 0
                    with st.spinner("올리는 중..."):
                        for f in files:
                            res = _upload(f, True)
                            if not res:
                                continue
                            done += 1
                            fid, url = res
                            db.append("materials", {
                                "uploaded_at": db.now_str(), "subject": subject, "category": "학습지",
                                "unit": unit, "title": title or f.name, "description": desc,
                                "file_id": fid, "file_name": f.name, "file_url": url, "mime": f.type or "",
                            })
                    if done == len(files):
                        st.rerun()
                    st.success(f"{done}개 올렸어요. 나머지는 위 오류를 확인해 주세요.")

    rows = [m for m in db.read("materials") if m["subject"] == subject and m["category"] == "학습지"]
    if not rows:
        st.info("아직 올라온 학습지가 없어요.")
        return
    for u in us:
        items = [m for m in rows if m["unit"] == u]
        if not items:
            continue
        with st.expander(f"{u}  ({len(items)})"):
            for m in items[::-1]:
                _material_card(user, m)


# ---------------------------------------------------------- 학급 게시판 ---
def tab_board(user, subject):
    if user["role"] == "teacher":
        return _board_teacher(subject)
    us = units(subject)
    st.markdown(f"**{user['class']}반 게시판** · 내가 올린 결과물은 나와 선생님만 볼 수 있어요.")
    with st.form(f"sub_{subject}", clear_on_submit=True):
        unit = st.selectbox("단원", us)
        title = st.text_input("제목", placeholder="예: 인수분해 활동지")
        content = st.text_area("내용", height=140,
                               placeholder="오늘 활동에서 내가 생각한 것, 풀이 과정을 적어 주세요.")
        f = st.file_uploader("파일 첨부 (사진, PDF 등 · 선택 · 10MB 이하)", key=f"sub_file_{subject}")
        ok = st.form_submit_button("올리기", type="primary")
    if ok:
        if not title.strip() or (not content.strip() and not f):
            st.error("제목과 함께 내용이나 파일 중 하나는 꼭 넣어 주세요.")
        else:
            with st.spinner("올리는 중..."):
                fid, url, fname, mime = "", "", "", ""
                if f:
                    res = _upload(f, False)
                    if not res:
                        st.stop()
                    fid, url = res
                    fname, mime = f.name, f.type or ""
                fb = make_feedback(user["name"], content, bool(f))
                db.append("submissions", {
                    "created_at": db.now_str(), "subject": subject, "class": user["class"],
                    "student_id": user["id"], "name": user["name"], "unit": unit, "title": title,
                    "content": content, "file_id": fid, "file_name": fname, "file_url": url,
                    "mime": mime, "feedback": fb, "teacher_comment": "",
                })
            st.session_state[f"_fb_{subject}"] = fb
            st.rerun()

    fb = st.session_state.pop(f"_fb_{subject}", None)
    if fb:
        st.balloons()
        ui.note(f"<h4>📬 피드백이 도착했어요</h4>{ui.esc(fb)}", "mint")

    mine = [s for s in db.read("submissions") if s["subject"] == subject and s["student_id"] == user["id"]]
    st.markdown("#### 내가 올린 결과물")
    if not mine:
        st.caption("아직 없어요.")
    for s in mine[::-1]:
        with st.container(border=True):
            st.markdown(f"<span class='chip'>{ui.esc(s['unit'])}</span> **{ui.esc(s['title'])}** "
                        f"<span class='meta'>{s['created_at'][:16]}</span>", unsafe_allow_html=True)
            if s["content"]:
                st.write(s["content"])
            ui.file_widget(s, s["id"])
            st.markdown(f"💬 {s['feedback']}")
            if s["teacher_comment"]:
                st.markdown(f"🧑‍🏫 **선생님:** {s['teacher_comment']}")


def _board_teacher(subject):
    c1, c2 = st.columns([3, 2])
    cls = c1.radio("학급", CLASSES, horizontal=True, key=f"tb_cls_{subject}")
    unit = c2.selectbox("단원", ["전체"] + units(subject), key=f"tb_unit_{subject}")
    rows = [s for s in db.read("submissions") if s["subject"] == subject and s["class"] == cls]
    if unit != "전체":
        rows = [s for s in rows if s["unit"] == unit]
        roster = auth.students(cls)
        done = {s["student_id"] for s in rows}
        missing = [u["name"] for u in roster if u["id"] not in done]
        st.markdown(f"**제출 현황** {len(done)}/{len(roster)}명")
        if missing:
            st.caption("아직 안 올린 학생: " + ", ".join(missing))
    if not rows:
        st.info("올라온 결과물이 없어요.")
    for s in rows[::-1]:
        with st.container(border=True):
            st.markdown(f"**{ui.esc(s['name'])}** ({s['student_id']}) · <span class='chip'>{ui.esc(s['unit'])}</span> "
                        f"**{ui.esc(s['title'])}** <span class='meta'>{s['created_at'][:16]}</span>",
                        unsafe_allow_html=True)
            if s["content"]:
                st.write(s["content"])
            ui.file_widget(s, s["id"])
            st.caption(f"자동 피드백: {s['feedback']}")
            cc1, cc2, cc3 = st.columns([5, 1, 1])
            cm = cc1.text_input("선생님 한마디", value=s["teacher_comment"], key=f"cm_{s['id']}",
                                label_visibility="collapsed", placeholder="선생님 한마디 (학생에게 보여요)")
            if cc2.button("저장", key=f"cms_{s['id']}"):
                db.update("submissions", s["id"], {"teacher_comment": cm})
                st.toast("저장했어요.")
            if cc3.button("삭제", key=f"cmd_{s['id']}"):
                db.delete_file(s["file_id"])
                db.delete("submissions", s["id"])
                st.rerun()


# ---------------------------------------------------------- 질문 게시판 ---
def tab_questions(user, subject):
    is_t = user["role"] == "teacher"
    if not is_t:
        with st.expander("✋ 질문하기", expanded=False):
            with st.form(f"q_{subject}", clear_on_submit=True):
                unit = st.selectbox("단원", units(subject))
                title = st.text_input("질문 제목")
                content = st.text_area("자세한 내용", height=120,
                                       placeholder="어디까지 이해했고, 어디서 막혔는지 적어 주면 더 잘 도와줄 수 있어요.")
                anon = st.checkbox("친구들에게는 이름 숨기기 (선생님은 볼 수 있어요)")
                ok = st.form_submit_button("질문 올리기", type="primary")
            if ok:
                if not title.strip() or not content.strip():
                    st.error("제목과 내용을 모두 적어 주세요.")
                else:
                    db.append("questions", {
                        "created_at": db.now_str(), "subject": subject, "class": user["class"],
                        "student_id": user["id"], "name": user["name"], "anonymous": "1" if anon else "0",
                        "unit": unit, "title": title, "content": content, "answer": "", "answered_at": "",
                    })
                    st.success("질문을 올렸어요. 답변이 달리면 여기에서 볼 수 있어요.")
                    st.rerun()

    flt = st.radio("보기", ["전체", "답변 대기", "답변 완료"] + ([] if is_t else ["내 질문"]),
                   horizontal=True, key=f"qf_{subject}")
    rows = [q for q in db.read("questions") if q["subject"] == subject]
    if flt == "답변 대기":
        rows = [q for q in rows if not q["answer"]]
    elif flt == "답변 완료":
        rows = [q for q in rows if q["answer"]]
    elif flt == "내 질문":
        rows = [q for q in rows if q["student_id"] == user["id"]]
    if not rows:
        st.info("질문이 없어요.")
    for q in rows[::-1][:60]:
        if q["anonymous"] == "1":
            who = f"익명 ({q['name']}, {q['class']})" if is_t else "익명"
        else:
            who = f"{q['name']} ({q['class']})"
        badge = "✅ 답변 완료" if q["answer"] else "⏳ 답변 대기"
        with st.container(border=True):
            st.markdown(f"<span class='chip'>{ui.esc(q['unit'])}</span> **{ui.esc(q['title'])}** · {badge}  \n"
                        f"<span class='meta'>{ui.esc(who)} · {q['created_at'][:16]}</span>",
                        unsafe_allow_html=True)
            st.write(q["content"])
            if q["answer"]:
                ui.note(f"<b>🧑‍🏫 선생님 답변</b><br>{ui.esc(q['answer'])}", "yellow")
            if is_t:
                ans = st.text_area("답변", value=q["answer"], key=f"ans_{q['id']}", height=90)
                a1, a2, _ = st.columns([1, 1, 4])
                if a1.button("답변 저장", key=f"ansb_{q['id']}", type="primary"):
                    db.update("questions", q["id"], {"answer": ans, "answered_at": db.now_str()})
                    st.rerun()
                if a2.button("삭제", key=f"qd_{q['id']}"):
                    db.delete("questions", q["id"])
                    st.rerun()
            elif q["student_id"] == user["id"] and not q["answer"]:
                if st.button("내 질문 삭제", key=f"qd_{q['id']}"):
                    db.delete("questions", q["id"])
                    st.rerun()


def page(user, subject):
    ui.page_title(subject, "평가계획 · 단원별 학습지 · 학급 게시판 · 질문 게시판")
    t1, t2, t3, t4 = st.tabs(["📋 평가계획", "📚 학습지", "📤 학급 게시판", "❓ 질문 게시판"])
    with t1:
        tab_plan(user, subject)
    with t2:
        tab_sheets(user, subject)
    with t3:
        tab_board(user, subject)
    with t4:
        tab_questions(user, subject)
