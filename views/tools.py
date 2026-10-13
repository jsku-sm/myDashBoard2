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
    ("snorkl", "3. 수행평가", "풀이를 쓰고 말하며 생각을 설명해요. 기존 소노클 수업과 활동을 여기에서 실행합니다."),
    ("tool_quiz", "4. 퀴즈", "배운 내용을 퀴즈로 확인해요."),
    ("tool_apps", "5. 앱 (by Good쌤)", "Good쌤이 직접 만든 수학 앱이에요."),
]


def app_table(links):
    """앱 목록: 번호와 학습 주제를 표시하고, 주제를 누르면 새 탭에서 엽니다."""
    rows = "".join(
        f'<tr><td class="num">{i:02}</td><td class="topic">'
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{html.escape(name)}</a></td></tr>'
        for i, (name, url) in enumerate(links, start=1)
    )
    st.markdown(
        "<style>"
        ".app-table-wrap{overflow-x:auto;border:1.5px solid var(--line);border-radius:12px;background:var(--card);}"
        ".app-table{width:100%;border-collapse:collapse;color:var(--ink);font-size:1rem;margin:0;}"
        ".app-table th,.app-table td{padding:.85rem 1.2rem;border-bottom:1px solid var(--line);text-align:left;}"
        ".app-table th{background:var(--soft);color:var(--muted);font-size:.84rem;font-weight:700;}"
        ".app-table tr:last-child td{border-bottom:0;}"
        ".app-table .num{width:5rem;color:var(--muted);font-variant-numeric:tabular-nums;}"
        ".app-table .topic a{color:var(--ink);font-weight:650;text-decoration:none;}"
        ".app-table .topic a:hover{text-decoration:underline;text-decoration-color:var(--hl);text-decoration-thickness:3px;}"
        "</style>"
        f'<div class="app-table-wrap"><table class="app-table"><thead><tr><th>번호</th><th>학습 주제</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        unsafe_allow_html=True,
    )


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
        app_table(links)
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
