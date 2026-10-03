"""선생님 소개 (프로필)"""
from html import escape
from pathlib import Path

import streamlit as st

from profile_data import (ACTIVITIES, AWARD, FOCUS_AREAS, GLOBAL_TRAINING, LECTURE_SCHOOLS,
                          PROFILE, QUALIFICATIONS, SHARING_TOPICS, TRAINING_TEXT)

PROFILE_IMG = Path(__file__).resolve().parents[1] / "assets" / "profile.png"

# 이 화면에만 적용되는 디자인 (다른 메뉴에 영향 없도록 pf- 로 시작하는 이름만 사용)
CSS = """
<style>
.st-key-pf_image img { border-radius: 24px; }
.st-key-pf_tabs h3, .st-key-pf_intro h1, .st-key-pf_intro h3 { word-break:keep-all; }
.pf-eyebrow { color:light-dark(#755d8d, #B9A0D6); font-size:.8rem; font-weight:700; letter-spacing:.16em; }
.pf-hero-description { color:var(--muted); line-height:1.85; margin-top:.6rem; }
.pf-tag { display:inline-block; background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius:999px;
  padding:.32rem .8rem; margin:.15rem .3rem .3rem 0; font-size:.88rem; }
.pf-quote { margin:.9rem .15rem 0; padding:.85rem .9rem; border-top:1px solid var(--line); color:var(--muted);
  font-size:.94rem; font-style:italic; line-height:1.8; text-align:center; word-break:keep-all; }
.st-key-pf_tabs .stTabs [data-baseweb="tab-list"] { gap:.65rem; margin-top:1rem; }
.st-key-pf_tabs .stTabs [data-baseweb="tab"] { color:var(--muted); font-weight:600; }
.st-key-pf_tabs .stTabs [aria-selected="true"] { color:light-dark(#75578d, #C9B2EA) !important; }
.pf-card { box-sizing:border-box; background:var(--card); border:1px solid var(--line);
  border-top:4px solid #98b29b; border-radius:18px; padding:1.35rem 1.45rem; margin-bottom:1rem;
  box-shadow:0 5px 18px rgba(41,57,43,.035); }
.pf-card.purple { border-top-color:#b3a0c8; }
.pf-card.gold { border-top-color:#d3b16d; }
.pf-card h4 { margin:0 0 .85rem; padding:0; font-size:1.15rem; color:var(--ink); }
.pf-card p { color:var(--ink); margin:.4rem 0; line-height:1.85; word-break:keep-all; }
.pf-list { list-style:none !important; margin:0 !important; padding:0 !important; }
.pf-list li { margin:0 !important; list-style:none; color:var(--ink); padding:.65rem 0; line-height:1.8; border-bottom:1px solid var(--line); word-break:keep-all; }
.pf-list li:last-child { border-bottom:0; padding-bottom:.1rem; }
.pf-award { background:var(--note-y-bg); border:1px solid var(--note-y-bd); border-radius:20px;
  padding:1.4rem 1.5rem; margin:.6rem 0 1.3rem; }
.pf-award .year { color:light-dark(#805b22, #E8C779); font-weight:700; font-size:.85rem; }
.pf-award h3 { margin:.3rem 0; padding:0; font-size:1.35rem; color:var(--ink); }
.pf-award p { color:light-dark(#745d36, #D9C08A); margin:.35rem 0 0; }
.pf-section { display:block; box-sizing:border-box; width:100%; white-space:nowrap;
  font-size:clamp(.9rem,3.5vw,1.18rem); font-weight:700; line-height:1.6; color:light-dark(#304c39, #CFE3D2); background:light-dark(#eaf0e8, #1A2A25);
  border-left:4px solid #869d83; border-radius:0 12px 12px 0; padding:.75rem 1rem; margin:1.3rem 0 1rem; }
.pf-schools li { margin:0 !important; }
.pf-schools { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; list-style:none !important; margin:0 !important; padding:0 !important; }
.pf-schools li { background:light-dark(#f3f6ef, #1B2A26); border:1px solid var(--line); border-radius:10px; padding:.75rem .85rem;
  font-size:1rem; font-weight:600; color:light-dark(#324b39, #CFE3D2); word-break:keep-all; }
.pf-training { box-sizing:border-box; width:100%; margin-top:1.1rem; padding:1rem 1.1rem; border:1px solid var(--line);
  border-radius:12px; background:light-dark(#f7f3fa, #241E33); color:light-dark(#4d3f5b, #D9CCEA); font-size:1.03rem; font-weight:600; line-height:1.8;
  white-space:nowrap; overflow-x:auto; }
.pf-topics { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
.pf-topics .pf-card { margin-bottom:0; }
.pf-footer { text-align:center; color:var(--muted); font-size:.86rem; padding:.8rem 0; }
@media (max-width:720px) {
  .pf-quote { font-size:.9rem; padding:.75rem .5rem; }
  .pf-card { padding:1.1rem; }
  .pf-schools { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .pf-topics { grid-template-columns:1fr; }
}
@media (max-width:380px) { .pf-schools { grid-template-columns:1fr; } .pf-section { padding:.7rem .6rem; } }
</style>
"""


def _html(body: str):
    st.html(body, width="stretch")


def _tags(items):
    _html("<div>" + "".join(f'<span class="pf-tag">{escape(i)}</span>' for i in items) + "</div>")


def _card(title, lines, tone="green"):
    body = "".join(f"<li>{escape(line)}</li>" for line in lines)
    _html(f'<div class="pf-card {tone}"><h4>{escape(title)}</h4><ul class="pf-list">{body}</ul></div>')


def _section(number, title):
    _html(f'<div class="pf-section" role="heading" aria-level="3">{escape(f"{number} {title}")}</div>')


def intro_page(user):
    _html(CSS)

    image_col, intro_col = st.columns([1, 1.85], gap="large", vertical_alignment="center")
    with image_col:
        with st.container(key="pf_image"):
            if PROFILE_IMG.is_file():
                st.image(str(PROFILE_IMG), width="stretch")
            else:
                st.caption("assets/profile.png 파일을 넣어 주세요.")
        _html(f'<div class="pf-quote">“{escape(PROFILE["motto"])}”</div>')
    with intro_col, st.container(key="pf_intro"):
        _html('<div class="pf-eyebrow">MATH × AI · GOOD TEACHER</div>')
        st.title(PROFILE["name"])
        st.markdown("**수학교사 · AI 교육 전문가**")
        st.subheader(PROFILE["slogan"])
        _html('<p class="pf-hero-description">수학을 통해 학생과 소통하고,<br>'
              'AI·디지털 기술을 더 깊은 배움으로 연결합니다.</p>')
        _tags(["수학교육", "AI·디지털 교육", "교사 성장"])

    with st.container(key="pf_tabs"):
        edu, career, lecture, contact = st.tabs(
            ["🌱 교육과 관심 분야", "🏅 경력과 주요 활동", "🎤 강의와 나눔", "📧 연락처"])

        with edu:
            st.subheader("더 나은 배움의 경험을 만듭니다")
            st.write("기술의 새로움보다 학생에게 일어나는 배움의 변화에 주목합니다. "
                     "학생이 참여하고, 자신의 생각을 표현하며, 작은 성장을 경험하는 수업을 지향합니다.")
            for start in range(0, len(FOCUS_AREAS), 2):
                cols = st.columns(2, gap="medium")
                for col, (title, lines) in zip(cols, FOCUS_AREAS[start:start + 2]):
                    with col:
                        _card(title, lines)
            st.markdown("#### 배움을 멈추지 않는 교사")
            st.write("교실에서 만난 질문을 연구로 이어 가고, 연구에서 얻은 통찰을 다시 수업으로 가져옵니다. "
                     "동료 교사들과 경험을 나누며 교육의 본질을 함께 고민합니다.")

        with career:
            st.subheader("배우고, 실천하고, 나누어 온 발자취")
            _html(f'<div class="pf-award"><div class="year">{escape(AWARD["year"])}</div>'
                  f'<h3>{escape(AWARD["title"])}</h3><p>{escape(AWARD["desc"])}</p></div>')
            left, right = st.columns(2, gap="medium")
            with left:
                _card("주요 활동", ACTIVITIES)
            with right:
                _card("연수 · 전문성", QUALIFICATIONS, "purple")
            _card("글로벌 연수", GLOBAL_TRAINING, "gold")

        with lecture:
            st.subheader("교실의 경험을 나누고, 함께 성장합니다")
            _section("01", "강의·연수 경력")
            schools = "".join(f"<li>{escape(s)}</li>" for s in LECTURE_SCHOOLS)
            _html('<div class="pf-card"><h4>학교 강의 경력</h4>'
                  f'<ul class="pf-schools">{schools}</ul>'
                  f'<div class="pf-training">{escape(TRAINING_TEXT)}</div></div>')
            _section("02", "함께 나누고 싶은 교육 주제")
            topics = "".join(f'<div class="pf-card"><h4>{escape(t)}</h4><p>{escape(d)}</p></div>'
                             for t, d in SHARING_TOPICS)
            _html(f'<div class="pf-topics">{topics}</div>')

        with contact:
            st.markdown("#### 교육청 이메일")
            st.markdown(f"📧 [{PROFILE['email']}](mailto:{PROFILE['email']})")

    st.divider()
    _html(f'<div class="pf-footer">© 2026 {escape(PROFILE["name"])} · 배우고, 나누고, 함께 성장합니다.</div>')
    if user["role"] == "teacher":
        st.caption("✏️ 이 화면의 내용은 코드 저장소의 `profile_data.py`에서, 사진은 `assets/profile.png`에서 바꿀 수 있어요.")
