"""수업도구: 선택한 메뉴의 내용만 표시합니다."""
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


def open_app(name, url):
    st.session_state[ACTIVE_APP] = (name, url)


def close_app():
    st.session_state.pop(ACTIVE_APP, None)


def app_table(links):
    """번호와 학습 주제를 표시하고, 대시보드 세션 안에서 앱을 선택합니다."""
    st.markdown(
        "<style>"
        ".st-key-tool_apps_list{background:var(--card);border-color:var(--line);border-radius:12px;}"
        ".st-key-tool_apps_list button{justify-content:flex-start;text-align:left;color:var(--ink);font-weight:650;}"
        ".st-key-tool_apps_list button:hover{text-decoration:underline;text-decoration-color:var(--hl);text-decoration-thickness:3px;}"
        "</style>",
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="tool_apps_list"):
        number, topic = st.columns([1, 8], vertical_alignment="center")
        number.markdown("**번호**")
        topic.markdown("**학습 주제**")
        for i, (name, url) in enumerate(links, start=1):
            number, topic = st.columns([1, 8], vertical_alignment="center")
            number.caption(f"{i:02}")
            topic.button(
                name, key=f"tool_app_open_{i}", type="tertiary", width="stretch",
                on_click=open_app, args=(name, url),
            )


def apps_panel(links):
    selected = st.session_state.get(ACTIVE_APP)
    if selected not in links:
        close_app()
        app_table(links)
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
