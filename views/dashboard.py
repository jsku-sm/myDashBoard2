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
  --dash-mint:light-dark(#E2F5EC,#20382F);
  --dash-mint-line:light-dark(#A9CFB9,#527A64);
  --dash-mint-ink:light-dark(#356D50,#B2E1C4);
  --dash-purple:light-dark(#EEE6FB,#30283F);
  --dash-purple-line:light-dark(#CBB9E4,#765E8E);
  --dash-purple-ink:light-dark(#705193,#DCC4F2);
  --dash-blue:light-dark(#E5F1FF,#23354A);
  --dash-blue-line:light-dark(#B6CDE8,#53779B);
  --dash-blue-ink:light-dark(#426C99,#B6D7F8);
  --dash-peach:light-dark(#FFEDE0,#3E3027);
  --dash-peach-line:light-dark(#E8C5A9,#946D4D);
  --dash-peach-ink:light-dark(#92613B,#F4CFAC);
  gap:.85rem;
}
.st-key-pastel_dashboard [data-testid="stMarkdownContainer"] {
  font-family:'Pretendard',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
.st-key-pastel_dashboard .dash-hero {
  display:flex; align-items:center; justify-content:space-between; gap:1rem;
  position:relative; overflow:hidden; padding:1.4rem 1.6rem; border-radius:24px;
  border:1.5px solid var(--dash-purple-line);
  background:linear-gradient(115deg,var(--dash-purple) 0%,light-dark(#EAF2FF,#263448) 58%,var(--dash-mint) 100%);
  box-shadow:0 4px 0 color-mix(in srgb,var(--dash-purple-line) 23%,transparent);
}
.st-key-pastel_dashboard .dash-hero-copy {position:relative; z-index:1;}
.st-key-pastel_dashboard .dash-hero-label {
  display:inline-flex; align-items:center; gap:.4rem; border-radius:99px; padding:.27rem .65rem;
  border:1px solid var(--dash-purple-line); background:light-dark(#FFFFFFA8,#19243BA8);
  color:var(--dash-purple-ink); font-size:.79rem; font-weight:800; letter-spacing:.03em;
}
.st-key-pastel_dashboard .dash-hero-label::before {
  content:""; width:7px; height:7px; border-radius:50%; background:var(--dash-purple-ink);
}
.st-key-pastel_dashboard .dash-hero h2 {
  color:var(--ink); font-size:2.15rem; line-height:1.25; margin:.55rem 0 .35rem; padding:0;
}
.st-key-pastel_dashboard .dash-hero p {
  margin:0; color:var(--dash-muted); font-size:.94rem; line-height:1.6;
}
.st-key-pastel_dashboard .dash-hero-art {flex:0 0 160px; width:160px; height:118px;}
.st-key-pastel_dashboard :is(.st-key-dashboard_filters,.st-key-dashboard_emotions,
  .st-key-dashboard_care,.st-key-dashboard_classes,.st-key-dashboard_students,.st-key-dashboard_trend) {
  border:1.5px solid var(--dash-line); border-radius:19px; padding:1rem 1.1rem;
  background:var(--dash-panel,var(--dash-surface)); gap:.7rem; min-width:0;
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
.st-key-dashboard_filters [data-testid="stToggle"] {
  padding:.65rem .75rem; border:1.5px solid var(--dash-mint-line); border-radius:12px;
  background:var(--dash-surface); min-height:44px;
}
.st-key-dashboard_filters [data-testid="stToggle"] label p {font-weight:750; color:var(--dash-mint-ink);}
body:has(.st-key-pastel_dashboard) [role="listbox"] [role="option"]:is([aria-selected="true"],[data-selected="true"]) {
  background:light-dark(#E3F2E9,#244437); color:light-dark(#28583F,#D1EEDB);
  box-shadow:inset 3px 0 0 light-dark(#397357,#A1D9B8); font-weight:750;
}
.st-key-dashboard_metrics {gap:0;}
.st-key-dashboard_metrics > [data-testid="stHorizontalBlock"],
.st-key-dashboard_metrics > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {gap:.8rem;}
.st-key-dashboard_metrics :is(.st-key-dashboard_metric_students,.st-key-dashboard_metric_logins,
  .st-key-dashboard_metric_online,.st-key-dashboard_metric_emotions) {
  padding:1rem 1.05rem; border:1.5px solid var(--metric-line); border-radius:18px;
  background:var(--metric-bg); min-width:0; position:relative; overflow:hidden;
  box-shadow:0 3px 0 color-mix(in srgb,var(--metric-line) 28%,transparent);
}
.st-key-dashboard_metrics :is(.st-key-dashboard_metric_students,.st-key-dashboard_metric_logins,
  .st-key-dashboard_metric_online,.st-key-dashboard_metric_emotions)::after {
  content:""; position:absolute; right:-14px; bottom:-20px; width:78px; height:78px;
  border:15px solid color-mix(in srgb,var(--metric-line) 25%,transparent); border-radius:50%;
  pointer-events:none;
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
.st-key-pastel_dashboard .st-key-dashboard_emotions {--dash-line:var(--dash-mint-line); --dash-accent:var(--dash-mint-ink); --dash-panel:light-dark(#EBF8F1,#20312D);}
.st-key-pastel_dashboard .st-key-dashboard_care {--dash-line:var(--dash-peach-line); --dash-accent:var(--dash-peach-ink); --dash-panel:light-dark(#FFF0E5,#342C29);}
.st-key-pastel_dashboard .st-key-dashboard_classes {--dash-line:var(--dash-purple-line); --dash-accent:var(--dash-purple-ink); --dash-panel:light-dark(#F0EAFB,#2C263B);}
.st-key-pastel_dashboard .st-key-dashboard_students {--dash-line:var(--dash-blue-line); --dash-accent:var(--dash-blue-ink); --dash-panel:light-dark(#EAF3FF,#233247);}
.st-key-pastel_dashboard .st-key-dashboard_trend {--dash-line:var(--dash-purple-line); --dash-accent:var(--dash-purple-ink); --dash-panel:light-dark(#F1ECFC,#2C263B);}
.st-key-pastel_dashboard .dash-panel-heading {
  display:flex; gap:.65rem; align-items:center; padding:0 0 .7rem;
  border-bottom:1px solid var(--dash-line);
}
.st-key-pastel_dashboard .dash-panel-icon {
  flex:0 0 38px; width:38px; height:38px; display:flex; align-items:center; justify-content:center;
  border:1px solid var(--dash-line); border-radius:12px; color:var(--dash-accent);
  background:light-dark(#FFFFFFA8,#19243B8F);
}
.st-key-pastel_dashboard .dash-panel-icon svg {width:22px; height:22px;}
.st-key-pastel_dashboard .dash-panel-heading h3 {
  color:var(--dash-accent); font-size:1.15rem; line-height:1.3; padding:0; margin:0 0 .1rem;
}
.st-key-pastel_dashboard .dash-panel-heading p {margin:0; color:var(--dash-muted); font-size:.79rem; line-height:1.45;}
.st-key-pastel_dashboard [data-testid="stVegaLiteChart"] {border-radius:12px; overflow:hidden;}
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
  .st-key-pastel_dashboard .dash-hero {padding:1.1rem 1.05rem; gap:.4rem; border-radius:19px;}
  .st-key-pastel_dashboard .dash-hero h2 {font-size:1.85rem;}
  .st-key-pastel_dashboard .dash-hero p {font-size:.86rem;}
  .st-key-pastel_dashboard .dash-hero-art {flex-basis:90px; width:90px; height:95px;}
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
@media (max-width:420px) {
  .st-key-pastel_dashboard .dash-hero-art {display:none;}
}
</style>"""


_HERO_ART = """<svg class="dash-hero-art" viewBox="0 0 160 118" fill="none" aria-hidden="true">
<circle cx="114" cy="37" r="30" fill="#D0E9DD"/>
<path d="M17 96V21M9 88H149" stroke="#9EAFC7" stroke-width="1.5" stroke-linecap="round"/>
<rect x="30" y="60" width="24" height="28" rx="6" fill="#B2D6C5" stroke="#6E9D88"/>
<rect x="66" y="40" width="24" height="48" rx="6" fill="#CBBCE9" stroke="#9C84C0"/>
<rect x="102" y="18" width="24" height="70" rx="6" fill="#AFCBEA" stroke="#7C9EBF"/>
<path d="M31 47L70 27L113 6" stroke="#A28ABD" stroke-width="2" stroke-linecap="round" stroke-dasharray="3 5"/>
<circle cx="31" cy="47" r="4" fill="#FFF4D8" stroke="#BBA56C"/>
<path d="M140 99L148 110H132L140 99Z" fill="#F3D3BC" stroke="#CCA58A"/>
<path d="M49 108H85" stroke="#B9ABD2" stroke-width="2" stroke-linecap="round"/>
</svg>"""


_PANEL_ICONS = {
    "emotions": '<path d="M12 20s-8-4.8-8-10a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.2-8 10-8 10Z"/>',
    "care": '<circle cx="9" cy="7" r="3"/><path d="M3 20v-3a6 6 0 0 1 10-4.5M18 11v6m-3-3h6"/>',
    "classes": '<path d="M4 20V7l8-4 8 4v13H4ZM9 20v-5h6v5M8 9h.01M16 9h.01M8 12h.01M16 12h.01"/>',
    "students": '<circle cx="9" cy="7" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3"/>',
    "trend": '<path d="M4 4v16h16M7 14l4-5 4 3 5-7"/>',
}


def _panel_heading(title: str, subtitle: str, icon: str):
    st.markdown(
        '<div class="dash-panel-heading"><span class="dash-panel-icon">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_PANEL_ICONS[icon]}</svg>'
        f'</span><div><h3>{ui.esc(title)}</h3><p>{ui.esc(subtitle)}</p></div></div>',
        unsafe_allow_html=True,
    )


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
            .configure_text(font="Pretendard").configure_view(strokeOpacity=0)
            .configure(background="transparent"))


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
            _panel_heading("감정별 통계", "학생들이 남긴 마음을 함께 살펴봐요.", "emotions")
            counts = {}
            for r in emos.values():
                counts[r["emotion"]] = counts.get(r["emotion"], 0) + 1
            st.altair_chart(_emotion_chart(counts), width="stretch")
        with right, st.container(border=True, key="dashboard_care"):
            _panel_heading("관심이 필요한 학생", "오늘의 마음에 따뜻한 안부를 건네요.", "care")
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
            _panel_heading("학급별 감정 분포", "학급마다 감정 응답을 비교해 보세요.", "classes")
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
        _panel_heading("학생별 상태", "접속과 감정 기록을 학생별로 확인해요.", "students")
        st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")


def _trend(cls: str):
    with st.container(border=True, key="dashboard_trend"):
        _trend_body(cls)


def _trend_body(cls: str):
    _panel_heading("최근 7일 감정 흐름", "일주일 동안 우리 반의 마음은 어땠을까요?", "trend")
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
        labelFont="Pretendard", titleFont="Pretendard").configure_view(strokeOpacity=0).configure(
        background="transparent")
    st.altair_chart(chart, width="stretch")


def page(user):
    if user["role"] != "teacher":
        st.error("선생님만 볼 수 있는 화면이에요.")
        return
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="pastel_dashboard"):
        st.markdown(
            '<section class="dash-hero"><div class="dash-hero-copy">'
            '<span class="dash-hero-label">선생님을 위한 우리 반 현황</span>'
            '<h2>대시보드</h2><p>우리 반의 접속과 마음을 한눈에 살펴보세요.<br>'
            f'감정 상태와 접속 상태는 선생님만 볼 수 있어요.</p></div>{_HERO_ART}</section>',
            unsafe_allow_html=True,
        )
        with st.container(border=True, key="dashboard_filters"):
            st.markdown('<p class="dash-filter-title">우리 반의 하루 살펴보기</p>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2, 2, 1.5], gap="small")
            today = db.now().date()
            day = c1.date_input("날짜", value=today, max_value=today, format="YYYY-MM-DD")
            cls = c2.selectbox("학급", ["전체"] + CLASSES)
            auto = c3.toggle("자동 새로고침", value=True, help="10초마다 접속 상태를 다시 불러와요.")
        st.fragment(_body, run_every=10 if auto else None)(day.strftime("%Y-%m-%d"), cls)
        _trend(cls)
