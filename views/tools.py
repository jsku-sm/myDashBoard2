"""수업도구: 선택한 메뉴의 내용만 표시합니다."""
import html

import streamlit as st

import storage as db
import ui
from config import DEFAULT_SETTINGS
from snorkl_navigation import ACTIVE_TOOL, clear_link

TOOLS = [
    ("tool_desmos", "1. 데스모스", "그래프를 직접 그려 보며 생각해요."),
    ("tool_activity", "2. 데스모스 액티비티", "선생님이 알려 준 코드로 입장해요."),
    ("snorkl", "3. 수행평가", ""),
    ("tool_quiz", "4. 퀴즈", "배운 내용을 퀴즈로 확인해요."),
    ("tool_apps", "5. 앱 (by Good쌤)", "Good쌤이 직접 만든 수학 앱이에요."),
]
ACTIVE_APP = "_tool_apps_active_app"

APP_CARD_COLORS = (
    ("#EAF6EF", "#BBDDCB", "#36735B", "#192F29"),
    ("#F1EDFC", "#D7CCEE", "#7960A8", "#2B2540"),
    ("#EAF3FE", "#C6DAF2", "#4478AB", "#1D2C40"),
    ("#FFF1E7", "#F1D2B9", "#AE7043", "#3B2B23"),
    ("#FCECEF", "#EFC8D2", "#B2617B", "#3B2530"),
    ("#FBF6DD", "#E8DBA7", "#9A7C31", "#332E1C"),
)

APP_CARD_ART = {
    "pictogram": (
        "그림으로 읽는 데이터",
        '<circle cx="22" cy="15" r="5"/><path d="M15 36V28a7 7 0 0 1 14 0v8M22 28v17"/>'
        '<circle cx="46" cy="15" r="5"/><path d="M39 36V28a7 7 0 0 1 14 0v8M46 28v17"/>'
        '<circle cx="70" cy="15" r="5"/><path d="M63 36V28a7 7 0 0 1 14 0v8M70 28v17"/>',
    ),
    "math_setquiz": (
        "퀴즈로 익히는 집합 개념",
        '<rect x="15" y="6" width="57" height="43" rx="12"/>'
        '<path d="m27 27 7 7 12-15M53 23h8M53 32h8"/>'
        '<circle cx="76" cy="11" r="7" fill="currentColor" stroke="none" opacity=".25"/>',
    ),
    "js-math.streamlit.app": (
        "점과 좌표를 한눈에",
        '<path d="M16 45h63M24 51V7M74 40l5 5-5 5M19 12l5-5 5 5"/>'
        '<path d="M43 44V20h24" stroke-dasharray="3 4" opacity=".4"/>'
        '<circle cx="43" cy="20" r="5" fill="currentColor" stroke="none"/>',
    ),
    "math_quiz": (
        "겹쳐 보며 이해하는 집합",
        '<circle cx="34" cy="28" r="21" fill="currentColor" fill-opacity=".08"/>'
        '<circle cx="59" cy="28" r="21" fill="currentColor" fill-opacity=".15"/>'
        '<circle cx="46.5" cy="28" r="3" fill="currentColor" stroke="none"/>',
    ),
    "line_mathquiz": (
        "그래프와 함께 익히는 직선",
        '<path d="M16 46h65M25 52V5" opacity=".45"/>'
        '<path d="m18 42 55-30" stroke-width="3"/>'
        '<circle cx="37" cy="32" r="4" fill="currentColor" stroke="none"/>'
        '<circle cx="64" cy="17" r="4" fill="currentColor" stroke="none"/>',
    ),
    "moving": (
        "점과 도형의 변화를 탐색해요",
        '<rect x="10" y="28" width="23" height="23" rx="4" stroke-dasharray="4 4" opacity=".5"/>'
        '<rect x="57" y="5" width="25" height="25" rx="5" fill="currentColor" fill-opacity=".12"/>'
        '<path d="M32 20q5-12 18-8m-6-6 7 6-7 5"/>',
    ),
}

APP_CARDS_CSS = """
<style>
.st-key-tool_apps_list {
    display:grid !important;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:12px !important;
}
.st-key-tool_apps_list [class*="st-key-tool_app_card_"] {
    position:relative;
    min-width:0;
    height:100%;
    padding:17px 18px 16px;
    border:1px solid var(--app-border);
    border-radius:18px;
    background:light-dark(var(--app-bg),var(--app-dark));
    box-shadow:0 2px 3px rgba(30,42,74,.025);
    transition:transform .16s ease,box-shadow .16s ease;
    gap:0 !important;
}
.st-key-tool_apps_list [class*="st-key-tool_app_card_"]:hover {
    transform:translateY(-2px);
    box-shadow:0 6px 16px rgba(30,42,74,.08);
}
.st-key-tool_apps_list [data-testid="stMarkdownContainer"] {margin-bottom:0;}
.app-card {
    pointer-events:none;color:light-dark(#25324A,#F1F3FA);
    font-family:'Pretendard',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
.app-card-top {display:flex;align-items:flex-start;justify-content:space-between;gap:12px;min-height:57px;}
.app-card-number {
    display:inline-flex;align-items:center;justify-content:center;
    width:30px;height:26px;border-radius:8px;
    background:light-dark(#FFFFFFA6,#FFFFFF14);
    color:light-dark(var(--app-accent),var(--app-border));
    font-size:.76rem;font-weight:750;font-variant-numeric:tabular-nums;
}
.app-card svg {width:86px;height:53px;color:light-dark(var(--app-accent),var(--app-border));}
.app-card-title {display:flex;align-items:baseline;justify-content:space-between;gap:9px;margin-top:9px;}
.app-card-title strong {
    font-size:1rem;font-weight:750;line-height:1.4;
    word-break:keep-all;overflow-wrap:anywhere;
}
.app-card-arrow {font-size:1.05rem;color:light-dark(var(--app-accent),var(--app-border));}
.app-card p {margin:5px 0 0;font-size:.78rem;line-height:1.45;color:light-dark(#667085,#BEC7D8);}
.st-key-tool_apps_list [class*="st-key-tool_app_open_"] {
    position:absolute !important;inset:0;z-index:1;
    width:100% !important;height:100% !important;margin:0;
}
.st-key-tool_apps_list [class*="st-key-tool_app_open_"] [data-testid="stButton"] {height:100%;}
.st-key-tool_apps_list [class*="st-key-tool_app_open_"] button {
    width:100%;height:100%;padding:0;border:0 !important;border-radius:18px;
    background:transparent !important;box-shadow:none !important;
}
.st-key-tool_apps_list [class*="st-key-tool_app_open_"] button [data-testid="stMarkdownContainer"] {opacity:0;}
.st-key-tool_apps_list [class*="st-key-tool_app_open_"] button:focus-visible {
    outline:3px solid var(--app-accent);outline-offset:3px;
}
@media(max-width:900px) {.st-key-tool_apps_list {grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:520px) {
    .st-key-tool_apps_list {grid-template-columns:minmax(0,1fr);gap:10px !important;}
    .st-key-tool_apps_list [class*="st-key-tool_app_card_"] {padding:14px 16px;}
}
@media(prefers-reduced-motion:reduce) {
    .st-key-tool_apps_list [class*="st-key-tool_app_card_"],
    .st-key-tool_apps_list [class*="st-key-tool_app_card_"]:hover {transition:none;transform:none;}
}
</style>
"""


def open_app(name, url):
    st.session_state[ACTIVE_APP] = (name, url)


def close_app():
    st.session_state.pop(ACTIVE_APP, None)


def app_cards(links):
    """파스텔 카드에서 앱을 고르고, 대시보드 세션 안에서 실행합니다."""
    color_rules = []
    for i in range(1, len(links) + 1):
        bg, border, accent, dark = APP_CARD_COLORS[(i - 1) % len(APP_CARD_COLORS)]
        color_rules.append(
            f'.st-key-tool_app_card_{i}'
            f'{{--app-bg:{bg};--app-border:{border};--app-accent:{accent};--app-dark:{dark};}}'
        )
    st.markdown(APP_CARDS_CSS + '<style>' + ''.join(color_rules) + '</style>', unsafe_allow_html=True)
    with st.container(key="tool_apps_list", gap="small"):
        for i, (name, url) in enumerate(links, start=1):
            description, drawing = next(
                (art for token, art in APP_CARD_ART.items() if token in url.lower()),
                ("눌러서 탐구를 시작해 보세요", '<circle cx="29" cy="25" r="17"/><rect x="50" y="13" width="29" height="29" rx="5"/>'),
            )
            with st.container(key=f"tool_app_card_{i}", gap=None):
                st.markdown(
                    '<div class="app-card" aria-hidden="true">'
                    '<div class="app-card-top">'
                    f'<span class="app-card-number">{i:02}</span>'
                    '<svg viewBox="0 0 94 58" fill="none" stroke="currentColor" '
                    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                    f'{drawing}</svg></div>'
                    f'<div class="app-card-title"><strong>{html.escape(name)}</strong>'
                    '<span class="app-card-arrow">→</span></div>'
                    f'<p>{description}</p></div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    name, key=f"tool_app_open_{i}", type="tertiary", width="stretch",
                    on_click=open_app, args=(name, url),
                )


def apps_panel(links):
    selected = st.session_state.get(ACTIVE_APP)
    if selected not in links:
        close_app()
        app_cards(links)
        return

    name, url = selected
    st.button("← 앱 목록으로 돌아가기", key="tool_apps_back", on_click=close_app)
    st.subheader(name)
    ui.embed(url, height=760)


def page(user):
    is_t = user["role"] == "teacher"
    ui.page_title("수업도구", "메뉴를 선택하면 해당 도구의 내용이 보여요.")

    tools = {key: (title, desc) for key, title, desc in TOOLS}
    if st.session_state.get(ACTIVE_TOOL) not in tools:
        st.session_state[ACTIVE_TOOL] = TOOLS[0][0]
    # 공유 수업 링크도 같은 선택값을 사용하므로 수행평가가 바로 열립니다.
    key = st.radio(
        "수업도구 메뉴", list(tools), format_func=lambda tool: tools[tool][0],
        key=ACTIVE_TOOL, horizontal=True, label_visibility="collapsed",
        on_change=clear_link, args=(st.session_state, st.query_params),
    )
    title, desc = tools[key]
    st.markdown(f"#### {title}")
    if desc:
        st.caption(desc)

    if key == "snorkl":
        from views import snorkl
        snorkl.page(user)
        return

    raw = db.get_setting(key)
    if key == "tool_apps" and not raw.strip():
        raw = DEFAULT_SETTINGS["tool_apps"]
    links = ui.parse_links(raw)
    if not links:
        st.caption("선생님이 링크를 준비 중이에요.")
    elif key == "tool_apps":
        apps_panel(links)
    else:
        cols = st.columns(min(len(links), 3))
        for i, (name, url) in enumerate(links):
            cols[i % len(cols)].link_button(name, url, width="stretch")
    if key == "tool_desmos" and links:
        with st.expander("이 화면에서 바로 계산기 열기"):
            ui.embed(links[0][1], height=560)
    if is_t:
        with st.expander(f"⚙️ {title} 링크 고치기"):
            st.caption("한 줄에 하나씩 `이름|주소` 형식으로 적어 주세요.")
            new = st.text_area("링크", value=db.get_setting(key), key=f"edit_{key}", height=100)
            if st.button("저장", key=f"save_{key}"):
                db.set_setting(key, new)
                st.rerun()
