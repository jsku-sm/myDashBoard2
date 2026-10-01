"""교사 대시보드: 접속 상태 + 감정 현황/통계 (교사만)."""
from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

import auth
import realtime as rt
import storage as db
import ui
from config import CARE_EMOTIONS, CLASSES, EMOTION_MAP, EMOTIONS


def _latest_emotions(rows):
    latest = {}
    for r in rows:  # 시간순으로 쌓이므로 마지막 값이 최신
        latest[r["student_id"]] = r
    return latest


def _emotion_chart(counts: dict):
    df = pd.DataFrame([
        {"감정": f"{e[1]} {e[2]}", "학생 수": counts.get(e[0], 0), "색": e[3]} for e in EMOTIONS
    ])
    bars = alt.Chart(df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, height=22).encode(
        y=alt.Y("감정:N", sort=None, axis=alt.Axis(labelFontSize=13, title=None, labelLimit=140)),
        x=alt.X("학생 수:Q", axis=alt.Axis(tickMinStep=1, format="d")),
        color=alt.Color("색:N", scale=None),
        tooltip=["감정", "학생 수"],
    )
    text = bars.mark_text(align="left", dx=6, fontSize=13).encode(text="학생 수:Q", color=alt.value("#1E2A4A"))
    return (bars + text).properties(height=300)


def _body(day: str, cls: str):
    is_today = day == db.today_str()
    roster = auth.students(cls)
    ids = {u["id"] for u in roster}
    if not roster:
        st.info("등록된 학생이 없어요. '교사전용 > 학생 명단'에서 학생을 등록해 주세요.")
        return

    logins = [r for r in db.read("logins") if r["date"] == day and r["student_id"] in ids]
    first_login, last_login = {}, {}
    for r in logins:
        first_login.setdefault(r["student_id"], r["created_at"][11:16])
        last_login[r["student_id"]] = r["created_at"][11:16]
    emos = _latest_emotions([r for r in db.read("emotions")
                             if r["date"] == day and r["student_id"] in ids])
    online = [u for u in roster if rt.is_online(u["id"])] if is_today else []

    m = st.columns(4)
    m[0].metric("학생 수", f"{len(roster)}명")
    m[1].metric("로그인", f"{len(first_login)}명")
    m[2].metric("지금 접속 중", f"{len(online)}명" if is_today else "—")
    m[3].metric("감정 응답", f"{len(emos)}명")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### 감정별 통계")
        counts = {}
        for r in emos.values():
            counts[r["emotion"]] = counts.get(r["emotion"], 0) + 1
        st.altair_chart(_emotion_chart(counts), width="stretch")
    with right:
        st.markdown("#### 관심이 필요한 학생")
        care = [r for r in emos.values() if r["emotion"] in CARE_EMOTIONS]
        if not care:
            st.caption("오늘은 힘든 감정을 고른 학생이 없어요.")
        for r in sorted(care, key=lambda r: r["class"]):
            e = EMOTION_MAP[r["emotion"]]
            st.markdown(f"{e[1]} **{r['name']}** ({r['class']}) · {e[2]}")

    if cls == "전체":
        st.markdown("#### 학급별 감정 분포")
        table = pd.DataFrame(0, index=CLASSES, columns=[f"{e[1]} {e[2]}" for e in EMOTIONS])
        for r in emos.values():
            e = EMOTION_MAP.get(r["emotion"])
            if e and r["class"] in table.index:
                table.loc[r["class"], f"{e[1]} {e[2]}"] += 1
        st.dataframe(table, width="stretch")

    st.markdown("#### 학생별 상태")
    data = []
    for u in roster:
        if is_today:
            if rt.is_online(u["id"]):
                state = "🟢 접속 중"
            elif u["id"] in first_login:
                state = "🟡 로그인함 (지금은 미접속)"
            else:
                state = "⚪ 오늘 미로그인"
        else:
            state = "✅ 로그인" if u["id"] in first_login else "⚪ 미로그인"
        e = EMOTION_MAP.get(emos.get(u["id"], {}).get("emotion", ""))
        data.append({
            "학급": u["class"], "학번": u["id"], "이름": u["name"], "접속 상태": state,
            "첫 로그인": first_login.get(u["id"], ""), "마지막 로그인": last_login.get(u["id"], ""),
            "감정": f"{e[1]} {e[2]}" if e else "",
        })
    st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")


def _trend(cls: str):
    st.markdown("#### 최근 7일 감정 흐름")
    ids = {u["id"] for u in auth.students(cls)}
    end = db.now().date()
    days = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    rows = []
    all_emo = db.read("emotions")
    for d in days:
        latest = _latest_emotions([r for r in all_emo if r["date"] == d and r["student_id"] in ids])
        for r in latest.values():
            e = EMOTION_MAP.get(r["emotion"])
            if e:
                rows.append({"날짜": d[5:], "감정": f"{e[1]} {e[2]}", "색": e[3]})
    if not rows:
        st.caption("최근 7일 동안 기록이 없어요.")
        return
    df = pd.DataFrame(rows).groupby(["날짜", "감정", "색"]).size().reset_index(name="학생 수")
    order = [f"{e[1]} {e[2]}" for e in EMOTIONS]
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("날짜:N", axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y("학생 수:Q", stack="zero"),
        color=alt.Color("감정:N", sort=order,
                        scale=alt.Scale(domain=order, range=[e[3] for e in EMOTIONS])),
        order=alt.Order("감정:N"),
        tooltip=["날짜", "감정", "학생 수"],
    ).properties(height=260)
    st.altair_chart(chart, width="stretch")


def page(user):
    if user["role"] != "teacher":
        st.error("선생님만 볼 수 있는 화면이에요.")
        return
    ui.page_title("대시보드", "감정 상태와 접속 상태는 선생님만 볼 수 있어요.")
    c1, c2, c3 = st.columns([2, 2, 1])
    today = db.now().date()
    day = c1.date_input("날짜", value=today, max_value=today, format="YYYY-MM-DD")
    cls = c2.selectbox("학급", ["전체"] + CLASSES)
    auto = c3.toggle("자동 새로고침", value=True, help="10초마다 접속 상태를 다시 불러와요.")
    st.fragment(_body, run_every=10 if auto else None)(day.strftime("%Y-%m-%d"), cls)
    _trend(cls)
