"""6. 교사전용: 관찰기록 / 상점·벌점 / 학생 명단 / 설정"""
import io

import pandas as pd
import streamlit as st

import auth
import realtime as rt
import storage as db
import ui
from config import CLASSES, DEFAULT_UNITS, OBSERVATION_CATEGORIES, POINT_REASONS, SUBJECTS


def _label(u):
    return f"{u['id']} {u['name']}"


# ----------------------------------------------------------- 관찰기록 ---
def tab_observe():
    c1, c2 = st.columns(2)
    cls = c1.selectbox("학급", CLASSES, key="ob_cls")
    roster = auth.students(cls)
    if not roster:
        st.info("이 학급에 등록된 학생이 없어요.")
        return
    stu = c2.selectbox("학생", roster, format_func=_label, key="ob_stu")
    with st.form("ob_form", clear_on_submit=True):
        cat = st.selectbox("영역", OBSERVATION_CATEGORIES)
        content = st.text_area("관찰 내용", height=110, placeholder="구체적인 장면과 행동 위주로 적어 두면 생기부 작성에 도움이 돼요.")
        ok = st.form_submit_button("기록 저장", type="primary")
    if ok and content.strip():
        db.append("observations", {"created_at": db.now_str(), "class": cls, "student_id": stu["id"],
                                   "name": stu["name"], "category": cat, "content": content})
        st.success(f"{stu['name']} 학생 기록을 저장했어요.")

    only = st.toggle("선택한 학생 기록만 보기", value=True)
    rows = [r for r in db.read("observations") if r["class"] == cls]
    if only:
        rows = [r for r in rows if r["student_id"] == stu["id"]]
    if rows:
        df = pd.DataFrame(rows)[["created_at", "student_id", "name", "category", "content"]]
        df.columns = ["일시", "학번", "이름", "영역", "내용"]
        st.download_button("📄 CSV로 내려받기", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"관찰기록_{cls}.csv", mime="text/csv")
    else:
        st.caption("기록이 없어요.")
    for r in rows[::-1]:
        with st.container(border=True):
            a, b = st.columns([6, 1])
            a.markdown(f"**{ui.esc(r['name'])}** <span class='chip'>{ui.esc(r['category'])}</span> "
                       f"<span class='meta'>{r['created_at'][:16]}</span>", unsafe_allow_html=True)
            a.write(r["content"])
            if b.button("삭제", key=f"obd_{r['id']}"):
                db.delete("observations", r["id"])
                st.rerun()


# ------------------------------------------------------------ 상벌점 ---
def _give(students, kind, score, reason, cls):
    rows = []
    for u in students:
        rows.append({"id": db.new_id(), "created_at": db.now_str(), "class": cls, "student_id": u["id"],
                     "name": u["name"], "kind": kind, "score": str(score), "reason": reason})
        rt.push(u["id"], {"kind": kind, "score": score, "reason": reason})
    db.append_many("points", rows)


def tab_points():
    cls = st.radio("학급", CLASSES, horizontal=True, key="pt_cls")
    roster = auth.students(cls)
    if not roster:
        st.info("이 학급에 등록된 학생이 없어요.")
        return

    with st.container(border=True):
        st.markdown("#### ⚡ 한 번에 상점 +1")
        st.caption("이름을 누르면 바로 상점 1점이 들어가고, 그 학생 화면에 폭죽이 터져요.")
        cols = st.columns(6)
        for i, u in enumerate(roster):
            if cols[i % 6].button(f"⭐ {u['name']}", key=f"qp_{u['id']}", width="stretch"):
                _give([u], "상점", 1, "칭찬해요", cls)
                st.toast(f"🎉 {u['name']} 상점 +1")

    with st.container(border=True):
        st.markdown("#### 상점·벌점 주기")
        targets = st.multiselect("학생", roster, format_func=_label, key="pt_targets", placeholder="학생을 고르세요 (여러 명 가능)")
        c1, c2 = st.columns(2)
        kind = c1.radio("종류", ["상점", "벌점"], horizontal=True, key="pt_kind")
        score = c2.number_input("점수", 1, 10, 1, key="pt_score")
        reason = st.selectbox("사유", POINT_REASONS[kind] + ["직접 입력"], key=f"pt_reason_{kind}")
        if reason == "직접 입력":
            reason = st.text_input("사유 직접 입력", key="pt_reason_txt")
        if st.button(f"{kind} 주기", type="primary", disabled=not targets or not reason):
            _give(targets, kind, int(score), reason, cls)
            st.success(f"{len(targets)}명에게 {kind} {score}점을 줬어요. 학생 화면에 곧 표시돼요.")

    pts = [p for p in db.read("points") if p["class"] == cls]
    st.markdown("#### 학급 현황")
    summary = []
    for u in roster:
        mine = [p for p in pts if p["student_id"] == u["id"]]
        plus = sum(int(p["score"] or 0) for p in mine if p["kind"] == "상점")
        minus = sum(int(p["score"] or 0) for p in mine if p["kind"] == "벌점")
        summary.append({"학번": u["id"], "이름": u["name"], "상점": plus, "벌점": minus, "합계": plus - minus})
    st.dataframe(pd.DataFrame(summary).sort_values("합계", ascending=False),
                 hide_index=True, width="stretch")

    with st.expander("최근 기록 (잘못 준 점수 삭제)"):
        for p in pts[::-1][:40]:
            a, b = st.columns([6, 1])
            icon = "⭐" if p["kind"] == "상점" else "⚠️"
            a.markdown(f"{icon} **{p['name']}** {p['kind']} {p['score']}점 · {p['reason']} "
                       f"<span class='meta'>{p['created_at'][5:16]}</span>", unsafe_allow_html=True)
            if b.button("삭제", key=f"ptd_{p['id']}"):
                db.delete("points", p["id"])
                st.rerun()


# ---------------------------------------------------------- 학생 명단 ---
def _read_roster(f):
    if f.name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(f, dtype=str)
    else:
        raw = f.getvalue()
        for enc in ("utf-8-sig", "cp949"):
            try:
                df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
    df.columns = [c.strip() for c in df.columns]
    need = {"학번", "이름", "학급"}
    if not need.issubset(df.columns):
        raise ValueError("첫 줄에 '학번, 이름, 학급' 열 이름이 있어야 해요.")
    df = df.fillna("")
    return [{"id": r["학번"].strip(), "name": r["이름"].strip(), "class": r["학급"].strip(),
             "pw": r.get("초기비밀번호", "")} for _, r in df.iterrows() if r["학번"].strip()]


def tab_roster():
    st.markdown("#### 명단 파일로 한 번에 등록")
    tmpl = "학번,이름,학급,초기비밀번호\n10101,김수학,1-1,\n10102,이함수,1-1,\n10201,박방정,1-2,\n"
    st.download_button("📄 명단 양식 내려받기 (CSV)", tmpl.encode("utf-8-sig"),
                       file_name="학생명단_양식.csv", mime="text/csv")
    st.caption("초기비밀번호 칸을 비워 두면 학번이 초기 비밀번호가 돼요. 학생은 첫 로그인 때 비밀번호를 꼭 바꿔야 해요.")
    f = st.file_uploader("명단 파일 (CSV 또는 엑셀)", type=["csv", "xlsx"], key="roster_file")
    if f:
        try:
            rows = _read_roster(f)
            bad = [r for r in rows if r["class"] not in CLASSES]
            st.dataframe(pd.DataFrame(rows).drop(columns=["pw"]).rename(
                columns={"id": "학번", "name": "이름", "class": "학급"}), hide_index=True, height=220)
            if bad:
                st.warning(f"학급 이름이 {', '.join(CLASSES)} 중 하나가 아닌 학생이 {len(bad)}명 있어요. 확인해 주세요.")
            overwrite = st.checkbox("이미 있는 학번은 이름·학급을 새 값으로 바꾸기")
            if st.button(f"{len(rows)}명 등록", type="primary"):
                with st.spinner("등록 중..."):
                    a, u, s = auth.add_students(rows, overwrite)
                st.success(f"새로 등록 {a}명 · 정보 수정 {u}명 · 건너뜀 {s}명")
        except Exception as e:
            st.error(f"파일을 읽지 못했어요: {e}")

    st.markdown("#### 한 명 추가")
    with st.form("add_one", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        sid = c1.text_input("학번")
        name = c2.text_input("이름")
        cls = c3.selectbox("학급", CLASSES)
        ok = st.form_submit_button("추가")
    if ok and sid.strip() and name.strip():
        a, _, s = auth.add_students([{"id": sid, "name": name, "class": cls}], False)
        if a:
            st.success("추가했어요. 초기 비밀번호는 학번과 같아요.")
        else:
            st.error("이미 있는 학번이에요.")

    st.markdown("#### 등록된 학생")
    cls = st.selectbox("학급", ["전체"] + CLASSES, key="ro_cls")
    roster = auth.students(cls)
    st.caption(f"{len(roster)}명")
    if roster:
        st.dataframe(pd.DataFrame([{"학급": u["class"], "학번": u["id"], "이름": u["name"],
                                    "비밀번호 변경 필요": "예" if u["must_change"] == "1" else ""}
                                   for u in roster]), hide_index=True, width="stretch", height=260)
        stu = st.selectbox("학생 선택", roster, format_func=_label, key="ro_stu")
        c1, c2 = st.columns(2)
        if c1.button("🔑 비밀번호 초기화 (학번으로)", width="stretch"):
            auth.reset_password(stu["id"])
            st.success(f"{stu['name']} 학생의 비밀번호를 학번으로 초기화했어요.")
        if c2.button("🗑️ 학생 삭제", width="stretch"):
            st.session_state["_confirm_del"] = stu["id"]
        if st.session_state.get("_confirm_del") == stu["id"]:
            st.warning(f"{stu['name']} 학생을 명단에서 지울까요? (기록은 남아요)")
            if st.button("네, 지울게요", type="primary"):
                db.delete("users", stu["id"])
                st.session_state.pop("_confirm_del")
                st.rerun()


# --------------------------------------------------------------- 설정 ---
def tab_settings():
    st.markdown("#### 자동 피드백 문구")
    st.caption("한 줄에 하나씩. 학생이 결과물을 올리면 이 중 하나가 무작위로 전송돼요. `{name}` 자리에 학생 이름이 들어가요.")
    fb = st.text_area("격려 메시지", value=db.get_setting("feedback_messages"), height=180)
    short = st.text_area("내용이 짧을 때 덧붙이는 문구", value=db.get_setting("short_feedback"), height=70)

    st.markdown("#### 단원 목록")
    unit_vals = {}
    cols = st.columns(2)
    for i, s in enumerate(SUBJECTS):
        cur = db.get_setting(f"units_{s}") or "\n".join(DEFAULT_UNITS[s])
        unit_vals[s] = cols[i].text_area(s, value=cur, height=230)

    st.markdown("#### 학생에게 보이는 것")
    show = st.toggle("학생이 자기 상점·벌점 합계를 홈에서 볼 수 있게 하기",
                     value=db.get_setting("show_points_to_students") == "1")

    if st.button("설정 저장", type="primary"):
        db.set_setting("feedback_messages", fb)
        db.set_setting("short_feedback", short)
        for s, v in unit_vals.items():
            db.set_setting(f"units_{s}", v)
        db.set_setting("show_points_to_students", "1" if show else "0")
        st.success("저장했어요.")

    st.markdown("#### 백업")
    st.caption("모든 표 데이터를 CSV로 내려받아요. 같은 데이터가 깃허브 데이터 저장소에도 자동으로 쌓여요.")
    table = st.selectbox("표", sorted(db.SCHEMAS.keys() - {"users", "settings"}))
    rows = db.read(table)
    st.download_button(f"📄 {table}.csv 내려받기",
                       pd.DataFrame(rows, columns=db.SCHEMAS[table]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{table}_{db.today_str()}.csv", mime="text/csv")
    st.caption(db.backend_status())
    if not db.get_backend().is_local and st.button("💾 지금 바로 저장하기"):
        with st.spinner("깃허브에 저장 중..."):
            try:
                db.flush_now()
                st.success("저장했어요.")
            except Exception as e:
                st.error(f"저장하지 못했어요: {e}")


def page(user):
    if user["role"] != "teacher":
        st.error("선생님만 볼 수 있는 화면이에요.")
        return
    ui.page_title("교사전용", "관찰기록, 상점·벌점, 학생 명단, 설정")
    t1, t2, t3, t4 = st.tabs(["📒 관찰기록", "⭐ 상점·벌점", "👥 학생 명단", "⚙️ 설정"])
    with t1:
        tab_observe()
    with t2:
        tab_points()
    with t3:
        tab_roster()
    with t4:
        tab_settings()
