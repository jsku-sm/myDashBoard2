"""5. 수업도구 (화면 잠금은 교사전용 메뉴로 옮김)."""
import html

import streamlit as st

import storage as db
import ui
from config import DEFAULT_SETTINGS

TOOLS = [
    ("tool_snorkl", "가. 스노클", "AI가 내 풀이 설명을 듣고 피드백해 줘요."),
    ("tool_desmos", "나. 데스모스", "그래프를 직접 그려 보며 생각해요."),
    ("tool_activity", "다. 데스모스 액티비티", "선생님이 알려 준 코드로 입장해요."),
    ("tool_quiz", "라. 퀴즈", "배운 내용을 퀴즈로 확인해요."),
    ("tool_apps", "마. 앱 (by 구쌤)", "구쌤이 직접 만든 수학 앱이에요."),
]


def app_table(links):
    """마. 앱 (by 구쌤): 번호와 학습 주제만 표로 보여 주고, 주제를 누르면 새 탭에서 열림."""
    rows = "".join(
        f'<tr><td class="num">{i:02}</td><td class="topic">'
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{html.escape(name)}</a></td></tr>'
        for i, (name, url) in enumerate(links, start=1)
    )
    st.markdown(
        "<style>"
        ".app-table-wrap{overflow-x:auto;border:1.5px solid #D5DFEE;border-radius:12px;background:#fff;}"
        ".app-table{width:100%;border-collapse:collapse;color:var(--ink);font-size:1rem;margin:0;}"
        ".app-table th,.app-table td{padding:.85rem 1.2rem;border-bottom:1px solid #E9EEF6;text-align:left;}"
        ".app-table th{background:#EEF2FA;color:#526070;font-size:.84rem;font-weight:700;}"
        ".app-table tr:last-child td{border-bottom:0;}"
        ".app-table .num{width:5rem;color:#8391A8;font-variant-numeric:tabular-nums;}"
        ".app-table .topic a{color:var(--ink);font-weight:650;text-decoration:none;}"
        ".app-table .topic a:hover{text-decoration:underline;text-decoration-color:var(--hl);text-decoration-thickness:3px;}"
        "</style>"
        f'<div class="app-table-wrap"><table class="app-table"><thead><tr><th>번호</th><th>학습 주제</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def page(user):
    is_t = user["role"] == "teacher"
    ui.page_title("수업도구", "수업에서 함께 쓰는 도구 모음")

    for key, title, desc in TOOLS:
        raw = db.get_setting(key)
        if key == "tool_apps" and not raw.strip():
            raw = DEFAULT_SETTINGS["tool_apps"]
        links = ui.parse_links(raw)
        st.markdown(f"#### {title}")
        st.caption(desc)
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
        st.write("")
