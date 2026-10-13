"""Shared classroom visual language based on the supplied design reference."""
import html

import streamlit as st


def style_page():
    st.markdown("""
    <style>
    :root { --lab-ink:#222222; --lab-paper:#fffdf6; --lab-lime:#cbf56e;
            --lab-blue:#4384ff; --lab-yellow:#ffdc62; --lab-muted:#747b88; }
    .stApp, [data-testid="stAppViewContainer"] { background:var(--lab-paper); color:var(--lab-ink); }
    [data-testid="stSidebar"] { background:#f4f2e9; border-right:1px solid #e6e3da; }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.8rem; }
    .block-container { max-width:1500px; padding-top:2.5rem; padding-bottom:4rem; }
    h1,h2,h3 { color:var(--lab-ink); letter-spacing:-.045em; font-weight:800 !important; }
    h1 { font-size:clamp(2rem,3.5vw,3.1rem) !important; line-height:1.25 !important; }
    [data-testid="stCaptionContainer"] { color:var(--lab-muted); }
    div.stButton > button, div.stDownloadButton > button, [data-testid="stFormSubmitButton"] button {
      min-height:44px; border:2px solid var(--lab-ink); border-radius:12px; color:var(--lab-ink);
      background:#fffdf6; font-weight:650; transition:box-shadow .15s,transform .15s;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
      border-color:var(--lab-ink); color:var(--lab-ink); box-shadow:3px 3px 0 var(--lab-ink); transform:translate(-1px,-1px);
    }
    div.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
      background:var(--lab-lime); border-color:var(--lab-ink); color:var(--lab-ink); box-shadow:3px 3px 0 var(--lab-ink);
    }
    button:disabled { opacity:.5; }
    [data-testid="stSidebar"] div.stButton > button {
      border:0; background:transparent; box-shadow:none; text-align:left; justify-content:flex-start; border-radius:22px;
    }
    [data-testid="stSidebar"] div.stButton > button:hover { background:#eae5d4; transform:none; }
    [data-testid="stSidebar"] button p { text-align:left; width:100%; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:20px; }
    [data-testid="stForm"] { background:white; border:1px solid #e3e1dc; border-radius:20px; }
    [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
      background:#fff; border-radius:10px; }
    [data-testid="stMetric"] { border:1px solid #e5e1d6; border-radius:16px; background:#fff; padding:16px; }
    [data-testid="stTabs"] [role="tab"] { color:var(--lab-muted); font-weight:700; }
    [data-testid="stTabs"] [aria-selected="true"] { color:var(--lab-ink); }
    [data-baseweb="tab-highlight"] { background:var(--lab-ink); }
    .lab-brand { font-size:27px; font-weight:900; line-height:1.02; letter-spacing:-1.2px; margin-bottom:12px; }
    .lab-brand mark { color:var(--lab-ink); background:var(--lab-lime); border-radius:4px; padding:0 5px; }
    .lab-tagline { font-size:12px; font-weight:600; color:var(--lab-muted); margin-bottom:28px; }
    .lab-eyebrow { color:var(--lab-muted); font-size:12px; font-weight:750; letter-spacing:1.5px; margin:20px 0 12px; }
    .lab-status { display:inline-block; border:2px solid var(--lab-ink); background:white; border-radius:99px;
      padding:6px 14px; font-size:12px; font-weight:800; }
    .lab-intro { color:var(--lab-muted); font-size:1.05rem; margin:0 0 28px; line-height:1.7; }
    .lab-card { min-height:240px; padding:24px; border:2px solid var(--lab-ink); border-radius:22px;
      box-shadow:6px 6px 0 var(--lab-ink); margin-bottom:22px; }
    .lab-card h3 { font-size:1.3rem; margin:12px 0 8px; }
    .lab-card p { font-size:.95rem; line-height:1.65; margin:0; }
    .lab-card small { font-size:11px; font-weight:800; letter-spacing:1.3px; }
    .lab-section { display:flex; align-items:center; gap:14px; margin:18px 0 24px; }
    .lab-section strong { font-size:1.7rem; letter-spacing:-.04em; }
    .lab-number { display:inline-flex; align-items:center; justify-content:center; width:44px; height:44px;
      background:var(--lab-blue); border:2px solid var(--lab-ink); border-radius:13px;
      box-shadow:3px 3px 0 var(--lab-ink); font-size:20px; font-weight:850; }
    .lab-course { margin:0 0 16px; padding:14px 0; border-top:1px solid #e6e2d8; }
    .course-title { font-size:1.05rem; font-weight:750; }
    .course-meta { color:var(--lab-muted); font-size:.9rem; }
    @media(max-width:640px) { .block-container { padding-top:1.4rem; } .lab-card { min-height:0; padding:20px; }
      .lab-section strong { font-size:1.35rem; } }
    </style>
    """, unsafe_allow_html=True)


def section(number, title, color="#4384ff"):
    st.markdown(f'<div class="lab-section"><span class="lab-number" style="background:{color}">'
                f'{html.escape(number)}</span><strong>{html.escape(title)}</strong></div>', unsafe_allow_html=True)


def sidebar(settings, course=None, student=False):
    with st.sidebar:
        st.markdown('<div class="lab-brand">STUDENT<br><mark>INSIGHT</mark> LAB</div>'
                    '<div class="lab-tagline">EXPLORE IDEAS. EXPLAIN YOUR THINKING.</div>'
                    '<div class="lab-eyebrow">NAVIGATE</div>', unsafe_allow_html=True)
        if student:
            st.markdown("**학생 활동 공간**")
        else:
            if st.button("⌂  HOME · 수업 목록", key="lab_home", use_container_width=True):
                for key in ("selected_course", "selected_activity", "show_guide"):
                    st.session_state.pop(key, None)
                st.rerun()
            if st.button("01 · 수업 활동", key="lab_activities", disabled=course is None, use_container_width=True):
                st.session_state.pop("selected_activity", None)
                st.session_state["workspace_" + course["id"]] = "활동 관리"
                st.rerun()
            if st.button("02 · 학생 제출함", key="lab_submissions", disabled=course is None, use_container_width=True):
                st.session_state.pop("selected_activity", None)
                st.session_state["workspace_" + course["id"]] = "학생 제출함"
                st.rerun()
            if st.button("03 · 사용 안내", key="lab_guide", use_container_width=True):
                st.session_state.show_guide = True
                st.session_state.pop("selected_course", None)
                st.session_state.pop("selected_activity", None)
                st.rerun()
        if course:
            st.markdown('<div class="lab-eyebrow">CURRENT CLASS</div>', unsafe_allow_html=True)
            st.write(course["title"])
            st.caption(" · ".join(course["classes"]))
        st.markdown('<div class="lab-eyebrow">WORK STATUS</div>', unsafe_allow_html=True)
        label = {"github": "GITHUB CONNECTED", "local": "LOCAL STORAGE", "demo": "DEMO MODE"}.get(settings.mode, "SETUP NEEDED")
        st.markdown(f'<span class="lab-status">{label}</span>', unsafe_allow_html=True)
        st.caption({"github": "제출한 활동은 학생별 파일로 저장됩니다.",
                    "local": "제출한 활동은 이 서버에 저장됩니다.",
                    "demo": "체험 기록은 서버를 재시작하면 사라집니다."}.get(settings.mode, "저장 설정을 확인하세요."))
        st.markdown('<div class="lab-eyebrow">THINK · DRAW · EXPLAIN</div>', unsafe_allow_html=True)
        st.caption("수식, 손글씨, 목소리로 나의 생각을 표현해보세요.")


def introduction():
    st.markdown('<div class="lab-eyebrow">A LITTLE CURIOSITY. A BIG DISCOVERY.</div>', unsafe_allow_html=True)
    st.title("생각을 펼치고, 배움을 발견하세요.")
    st.markdown('<p class="lab-intro">그래프로 탐구하고, 손으로 풀고, 목소리로 설명하는 우리 반의 학습 공간입니다.</p>',
                unsafe_allow_html=True)
    cards = [("#cbf56e", "01 / GRAPH EXPLORER", "데스모스로 탐구하기", "수식을 입력하고 그래프의 변화를 관찰하세요. 작업을 저장하고 선생님에게 제출할 수 있어요."),
             ("#ffdc62", "02 / QUIZ & CHALLENGE", "퀴즈로 확인하기", "객관식과 단답형 문제에 도전하세요. 답을 고른 이유도 함께 설명해보세요."),
             ("#f0edff", "03 / WRITE & EXPLAIN", "손글씨·음성으로 풀기", "풀이판에 생각을 쓰거나 풀이 사진을 올리세요. 음성 녹음으로 설명을 더할 수 있어요.")]
    for column, (color, label, title, text) in zip(st.columns(3, gap="large"), cards):
        with column:
            st.markdown(f'<div class="lab-card" style="background:{color}"><small>{label}</small>'
                        f'<h3>{title}</h3><p>{text}</p></div>', unsafe_allow_html=True)


def guide():
    section("01", "수업에서 시작해보세요")
    st.markdown("1. **수업 만들기**에서 이름과 참여 학급을 선택하세요.\n"
                "2. **데스모스**가 포함된 수업 이름을 선택하면 그래프 작업 화면이 바로 열립니다.\n"
                "3. **활동 관리 → 활동 추가하기**에서 그래프, 퀴즈, 손글씨 활동을 만들 수 있습니다.\n"
                "4. 수업의 **공유** 버튼으로 링크와 QR 코드를 학생에게 전달하세요.")
    section("02", "표현하고, 저장하고, 제출하세요", "#ffdc62")
    st.markdown("- **그래프**: 수식을 입력한 뒤 반영 완료를 확인하세요. 작업 JSON을 저장하고 다시 불러올 수 있습니다.\n"
                "- **퀴즈**: 답을 선택하거나 직접 입력하세요.\n"
                "- **손글씨**: 펜·지우개·되돌리기·좌표 격자로 풀이를 작성하세요.\n"
                "- **음성**: 마이크를 허용하고 2분 이내로 녹음하세요. 녹음은 답안과 함께 저장됩니다.\n"
                "- **제출**: 학번과 이름을 확인하고 답안 제출을 누르세요. 선생님은 학생 제출함에서 확인합니다.")
    section("03", "저장 연결", "#cbf56e")
    st.write("실제 GitHub 저장에는 THINK_MODE=github, 비공개 데이터 저장소와 토큰, 암호화키가 필요합니다. "
             "데스모스 연결에는 DESMOS_API_KEY가 필요합니다. 설정 방법은 README_시작하기.md를 참고하세요.")
