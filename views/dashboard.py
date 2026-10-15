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


CSS = """<style>
.st-key-pastel_dashboard {
  --dash-surface:light-dark(#FFFFFF,#19243B);
  --dash-muted:light-dark(#66728A,#B4BED2);
  --dash-mint:light-dark(#EAF7F0,#20382F);
  --dash-mint-line:light-dark(#A9CFB9,#527A64);
  --dash-mint-ink:light-dark(#356D50,#B2E1C4);
  --dash-purple:light-dark(#F2ECFB,#30283F);
  --dash-purple-line:light-dark(#CBB9E4,#765E8E);
  --dash-purple-ink:light-dark(#705193,#DCC4F2);
  --dash-blue:light-dark(#ECF4FE,#23354A);
  --dash-blue-line:light-dark(#B6CDE8,#53779B);
  --dash-blue-ink:light-dark(#426C99,#B6D7F8);
  --dash-peach:light-dark(#FFF2E8,#3E3027);
  --dash-peach-line:light-dark(#E8C5A9,#946D4D);
  --dash-peach-ink:light-dark(#92613B,#F4CFAC);
  gap:.85rem;
}
.st-key-pastel_dashboard [data-testid="stMarkdownContainer"] {
  font-family:'Pretendard',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
.st-key-pastel_dashboard .pg-sub {margin-bottom:.3rem;}
.st-key-pastel_dashboard :is(.st-key-dashboard_filters,.st-key-dashboard_emotions,
  .st-key-dashboard_care,.st-key-dashboard_classes,.st-key-dashboard_students,.st-key-dashboard_trend) {
  border:1.5px solid var(--dash-line); border-radius:19px; padding:1rem 1.1rem;
  background:var(--dash-surface); gap:.6rem; min-width:0;
  box-shadow:0 3px 0 color-mix(in srgb,var(--dash-line) 24%,transparent);
}
.st-key-pastel_dashboard .st-key-dashboard_filters {
  --dash-line:var(--dash-mint-line); --dash-accent:var(--dash-mint-ink);
  background:linear-gradient(110deg,var(--dash-mint),light-dark(#F4F9FD,#253343));
}
.st-key-dashboard_filters .dash-filter-title {
  display:flex; align-items:center; gap:.5rem; color:var(--dash-mint-ink);
  font-size:.9rem; font-weight:800; margin:0 0 .15rem;
}
.st-key-dashboard_filters .dash-filter-title::before {
  content:""; width:9px; height:9px; border-radius:3px; background:var(--dash-mint-ink);
  box-shadow:4px 4px 0 color-mix(in srgb,var(--dash-mint-ink) 20%,transparent);
}
.st-key-dashboard_filters [data-testid="stHorizontalBlock"] {gap:.85rem; align-items:end;}
.st-key-dashboard_filters :is([data-testid="stDateInput"],[data-testid="stSelectbox"]) label p {
  color:var(--dash-mint-ink); font-weight:800; font-size:.9rem;
}
.st-key-dashboard_filters :is([data-testid="stDateInput"],[data-testid="stSelectbox"])
  :is([data-baseweb="input"],[data-baseweb="select"] > div,
    .react-aria-ComboBox > [role="group"],.react-aria-DatePicker > [role="group"],
    [data-testid="stDateInputField"]:not(input)) {
  min-height:44px; border:1.5px solid var(--dash-mint-line); border-radius:12px;
  background:var(--dash-surface); color:var(--ink); cursor:pointer;
  box-shadow:0 2px 0 color-mix(in srgb,var(--dash-mint-line) 30%,transparent);
}
.st-key-dashboard_filters :is([data-testid="stDateInput"],[data-testid="stSelectbox"])
  :is([data-baseweb="input"],[data-baseweb="select"] > div,
    .react-aria-ComboBox > [role="group"],.react-aria-DatePicker > [role="group"],
    [data-testid="stDateInputField"]:not(input)):focus-within {
  border-color:var(--dash-mint-ink); outline:2px solid var(--dash-mint-line); outline-offset:2px;
}
.st-key-dashboard_filters [data-testid="stCheckbox"] {
  padding:.65rem .75rem; border:1.5px solid var(--dash-mint-line); border-radius:12px;
  background:var(--dash-surface); min-height:44px;
}
.st-key-dashboard_filters [data-testid="stCheckbox"] label {cursor:pointer;}
.st-key-dashboard_filters [data-testid="stCheckbox"] label p {font-size:.86rem; font-weight:750; color:var(--dash-mint-ink);}
.st-key-dashboard_filters [data-testid="stCheckbox"]:has(input:checked) {
  border-color:var(--dash-mint-ink); box-shadow:inset 0 -2px 0 var(--dash-mint-line);
}
.st-key-dashboard_filters [data-testid="stCheckbox"]:has(input:focus-visible) {
  outline:3px solid var(--dash-mint-ink); outline-offset:3px;
}
body:has(.st-key-pastel_dashboard) [role="listbox"] [role="option"]:is([aria-selected="true"],[data-selected="true"]) {
  background:light-dark(#E3F2E9,#244437); color:light-dark(#28583F,#D1EEDB);
  box-shadow:inset 3px 0 0 light-dark(#397357,#A1D9B8); font-weight:750;
}
.st-key-dashboard_metrics {gap:0;}
.st-key-dashboard_metrics > [data-testid="stHorizontalBlock"],
.st-key-dashboard_metrics > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {gap:.8rem;}
.st-key-dashboard_metrics :is(.st-key-dashboard_metric_students,.st-key-dashboard_metric_logins,
  .st-key-dashboard_metric_online,.st-key-dashboard_metric_emotions) {
  padding:.85rem .95rem; border:1.5px solid var(--metric-line); border-radius:17px;
  background:var(--metric-bg); min-width:0; position:relative; overflow:hidden;
  box-shadow:0 3px 0 color-mix(in srgb,var(--metric-line) 28%,transparent);
}
.st-key-dashboard_metric_students {--metric-bg:var(--dash-mint); --metric-line:var(--dash-mint-line); --metric-ink:var(--dash-mint-ink);}
.st-key-dashboard_metric_logins {--metric-bg:var(--dash-purple); --metric-line:var(--dash-purple-line); --metric-ink:var(--dash-purple-ink);}
.st-key-dashboard_metric_online {--metric-bg:var(--dash-blue); --metric-line:var(--dash-blue-line); --metric-ink:var(--dash-blue-ink);}
.st-key-dashboard_metric_emotions {--metric-bg:var(--dash-peach); --metric-line:var(--dash-peach-line); --metric-ink:var(--dash-peach-ink);}
.st-key-dashboard_metrics [data-testid="stMetric"] {padding:0; border:none; background:transparent;}
.st-key-dashboard_metrics [data-testid="stMetricLabel"] {color:var(--metric-ink); font-size:.88rem; font-weight:750;}
.st-key-dashboard_metrics [data-testid="stMetricLabel"] p {color:inherit; font-weight:750;}
.st-key-dashboard_metrics [data-testid="stMetricValue"] {color:var(--metric-ink); font-weight:800; font-size:2rem; line-height:1.25;}
.st-key-pastel_dashboard .st-key-dashboard_overview > [data-testid="stHorizontalBlock"] {gap:.85rem;}
.st-key-pastel_dashboard .st-key-dashboard_emotions {--dash-line:var(--dash-mint-line); --dash-accent:var(--dash-mint-ink);}
.st-key-pastel_dashboard .st-key-dashboard_care {--dash-line:var(--dash-peach-line); --dash-accent:var(--dash-peach-ink); background:light-dark(#FFFCF8,#2A282D);}
.st-key-pastel_dashboard .st-key-dashboard_classes {--dash-line:var(--dash-purple-line); --dash-accent:var(--dash-purple-ink);}
.st-key-pastel_dashboard .st-key-dashboard_students {--dash-line:var(--dash-blue-line); --dash-accent:var(--dash-blue-ink);}
.st-key-pastel_dashboard .st-key-dashboard_trend {--dash-line:var(--dash-purple-line); --dash-accent:var(--dash-purple-ink);}
.st-key-pastel_dashboard :is(.st-key-dashboard_emotions,.st-key-dashboard_care,
  .st-key-dashboard_classes,.st-key-dashboard_students,.st-key-dashboard_trend) h4 {
  color:var(--dash-accent); font-size:1.18rem; padding:0 0 .5rem; margin:0;
  border-bottom:1px solid color-mix(in srgb,var(--dash-line) 65%,transparent);
}
.st-key-pastel_dashboard :is(.st-key-dashboard_classes,.st-key-dashboard_students) [data-testid="stDataFrame"] {
  border:1px solid var(--dash-line); border-radius:12px; overflow:hidden;
}
.st-key-dashboard_care .dash-care-student {
  border:1px solid var(--dash-peach-line); border-left:3px solid var(--dash-peach-line);
  border-radius:12px; background:var(--dash-surface); padding:.65rem .75rem; margin:.2rem 0;
  color:var(--ink); font-size:.92rem; line-height:1.65; overflow-wrap:anywhere;
}
.st-key-dashboard_care .dash-care-student strong {font-weight:800;}
.st-key-dashboard_care .dash-care-student small {color:var(--dash-muted); font-size:.85rem;}
@media (max-width:640px) {
  .st-key-dashboard_metrics > [data-testid="stHorizontalBlock"],
  .st-key-dashboard_metrics > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem;
  }
  .st-key-dashboard_metrics > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
  .st-key-dashboard_metrics > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {width:100%; min-width:0;}
  .st-key-dashboard_metrics :is(.st-key-dashboard_metric_students,.st-key-dashboard_metric_logins,
    .st-key-dashboard_metric_online,.st-key-dashboard_metric_emotions) {padding:.7rem .8rem; border-radius:14px;}
  .st-key-dashboard_metrics [data-testid="stMetricValue"] {font-size:1.75rem;}
  .st-key-pastel_dashboard :is(.st-key-dashboard_filters,.st-key-dashboard_emotions,
    .st-key-dashboard_care,.st-key-dashboard_classes,.st-key-dashboard_students,.st-key-dashboard_trend) {
    padding:.85rem .8rem; border-radius:16px;
  }
}
</style>"""


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
    text = bars.mark_text(align="left", dx=6, fontSize=13).encode(text="학생 수:Q", color=alt.value("#8A96AD"))
    return ((bars + text).properties(height=300)
            .configure_axis(labelFont="Pretendard", titleFont="Pretendard")
            .configure_text(font="Pretendard"))


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

    with st.container(key="dashboard_metrics"):
        metrics = st.columns(4, gap="small")
        metric_values = [
            ("students", "학생 수", f"{len(roster)}명"),
            ("logins", "로그인", f"{len(first_login)}명"),
            ("online", "지금 접속 중", f"{len(online)}명" if is_today else "—"),
            ("emotions", "감정 응답", f"{len(emos)}명"),
        ]
        for col, (key, label, value) in zip(metrics, metric_values):
            with col, st.container(border=True, key=f"dashboard_metric_{key}"):
                st.metric(label, value)

    with st.container(key="dashboard_overview"):
        left, right = st.columns([3, 2], gap="small")
        with left, st.container(border=True, key="dashboard_emotions"):
            st.markdown("#### 감정별 통계")
            counts = {}
            for r in emos.values():
                counts[r["emotion"]] = counts.get(r["emotion"], 0) + 1
            st.altair_chart(_emotion_chart(counts), width="stretch")
        with right, st.container(border=True, key="dashboard_care"):
            st.markdown("#### 관심이 필요한 학생")
            care = [r for r in emos.values() if r["emotion"] in CARE_EMOTIONS]
            if not care:
                st.caption("오늘은 힘든 감정을 고른 학생이 없어요.")
            for r in sorted(care, key=lambda r: r["class"]):
                e = EMOTION_MAP[r["emotion"]]
                st.markdown(
                    f'<div class="dash-care-student">{ui.esc(e[1])} '
                    f'<strong>{ui.esc(r["name"])}</strong> '
                    f'<small>({ui.esc(r["class"])})</small><br>{ui.esc(e[2])}</div>',
                    unsafe_allow_html=True,
                )

    if cls == "전체":
        with st.container(border=True, key="dashboard_classes"):
            st.markdown("#### 학급별 감정 분포")
            table = pd.DataFrame(0, index=CLASSES, columns=[f"{e[1]} {e[2]}" for e in EMOTIONS])
            for r in emos.values():
                e = EMOTION_MAP.get(r["emotion"])
                if e and r["class"] in table.index:
                    table.loc[r["class"], f"{e[1]} {e[2]}"] += 1
            st.dataframe(table, width="stretch")

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
    with st.container(border=True, key="dashboard_students"):
        st.markdown("#### 학생별 상태")
        st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")


def _trend(cls: str):
    with st.container(border=True, key="dashboard_trend"):
        _trend_body(cls)


def _trend_body(cls: str):
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
    ).properties(height=260).configure_axis(labelFont="Pretendard", titleFont="Pretendard").configure_legend(
        labelFont="Pretendard", titleFont="Pretendard")
    st.altair_chart(chart, width="stretch")


def page(user):
    if user["role"] != "teacher":
        st.error("선생님만 볼 수 있는 화면이에요.")
        return
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="pastel_dashboard"):
        ui.page_title("대시보드", "감정 상태와 접속 상태는 선생님만 볼 수 있어요.")
        with st.container(border=True, key="dashboard_filters"):
            st.markdown('<p class="dash-filter-title">우리 반의 하루 살펴보기</p>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2, 2, 1.5], gap="small")
            today = db.now().date()
            day = c1.date_input("날짜", value=today, max_value=today, format="YYYY-MM-DD")
            cls = c2.selectbox("학급", ["전체"] + CLASSES)
            auto = c3.toggle("자동 새로고침", value=True, help="10초마다 접속 상태를 다시 불러와요.")
        st.fragment(_body, run_every=10 if auto else None)(day.strftime("%Y-%m-%d"), cls)
        _trend(cls)
