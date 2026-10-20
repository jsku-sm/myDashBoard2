"""Compact student-home styles, isolated from other pages and the sidebar."""

HOME_CSS = """
<style>
.stApp:has(.st-key-student_home) {
  background-image:none;
}
[data-testid="stMain"]:has(.st-key-student_home) .block-container {
  max-width:1120px;
  padding:1.1rem clamp(1rem, 2.2vw, 2rem) 1rem;
}
.st-key-student_home {
  min-width:0;
  max-width:100%;
  color:var(--ink);
  gap:.65rem;
}
.st-key-student_home [data-testid="stVerticalBlock"] {
  min-width:0;
  gap:.4rem;
}
.st-key-student_home [data-testid="stMarkdownContainer"] p {
  margin:0;
}
.st-key-student_home [data-testid="stMarkdownContainer"] {
  margin-bottom:0;
}
.st-key-student_home [data-testid="stCaptionContainer"] p {
  margin:0;
}
.st-key-student_home .home-welcome {
  display:flex;
  align-items:center;
  justify-content:space-between;
  flex-wrap:wrap;
  gap:.35rem 1rem;
  padding:.1rem 0 .15rem;
}
.st-key-student_home .home-name {
  margin:0;
  padding:0;
  color:var(--ink);
  font-family:'Pretendard', sans-serif !important;
  font-size:clamp(1.3rem, 2vw, 1.65rem);
  font-weight:750 !important;
  line-height:1.3;
  letter-spacing:-.035em;
  overflow-wrap:anywhere;
}
.st-key-student_home .home-date {
  margin:0;
  color:var(--muted);
  font-size:.875rem;
  line-height:1.4;
}
.st-key-student_home :is(.st-key-home_summary, .st-key-home_documents,
  .st-key-home_feedback, .st-key-home_assessments, .st-key-home_announcements) {
  min-width:0;
  padding:.7rem .85rem;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--card);
  box-shadow:0 2px 10px color-mix(in srgb, var(--ink) 4%, transparent);
}
.st-key-student_home .st-key-home_summary {
  padding:.65rem .9rem;
  background:color-mix(in srgb, var(--card) 85%, var(--soft));
}
.st-key-student_home .st-key-home_summary [data-testid="stHorizontalBlock"] {
  align-items:center;
}
.st-key-student_home .home-label {
  margin:0 0 .15rem;
  color:var(--muted);
  font-size:.875rem;
  line-height:1.35;
}
.st-key-student_home .home-emotion {
  display:flex;
  align-items:center;
  gap:.45rem;
  color:var(--ink);
  font-size:1rem;
  font-weight:650;
  line-height:1.35;
}
.st-key-student_home .home-emotion-icon {
  font-size:1.7rem;
  font-weight:400;
  line-height:1.1;
}
.st-key-student_home .home-points {
  display:flex;
  align-items:baseline;
  justify-content:flex-start;
  flex-wrap:wrap;
  gap:.4rem 1rem;
}
.st-key-student_home .home-points > span {
  display:inline-flex;
  align-items:baseline;
  gap:.35rem;
}
.st-key-student_home .home-point-label {
  color:var(--muted);
  font-size:.875rem;
  line-height:1.4;
}
.st-key-student_home .home-points strong {
  color:var(--ink);
  font-size:1.15rem;
  font-weight:750;
  font-variant-numeric:tabular-nums;
  line-height:1.4;
}
.st-key-student_home .st-key-home_updates {
  gap:.65rem;
}
.st-key-student_home .home-section-label {
  display:flex;
  align-items:baseline;
  flex-wrap:wrap;
  gap:.2rem .65rem;
  color:var(--ink);
  font-size:.9375rem;
  font-weight:650;
  line-height:1.4;
}
.st-key-student_home .home-section-label span {
  color:var(--muted);
  font-size:.875rem;
  font-weight:400;
}
.st-key-student_home .home-count {
  display:block;
  width:max-content;
  margin-left:auto;
  padding:.08rem .45rem;
  border-radius:99px;
  background:var(--soft);
  color:var(--muted);
  font-size:.875rem;
  line-height:1.45;
  white-space:nowrap;
}
.st-key-student_home .st-key-home_updates :is(h4, h5) {
  margin:0;
  padding:0;
  color:var(--ink);
  font-family:'Pretendard', sans-serif !important;
  font-size:1rem;
  font-weight:750 !important;
  line-height:1.4;
  letter-spacing:-.02em;
  overflow-wrap:anywhere;
}
.st-key-student_home .st-key-home_updates :is(.home-meta, [data-testid="stCaptionContainer"]) {
  margin:0;
  color:var(--muted);
  font-size:.875rem;
  line-height:1.35;
  overflow-wrap:anywhere;
}
.st-key-student_home .st-key-home_updates small {
  color:var(--muted);
  font-size:.875rem;
  line-height:1.35;
}
.st-key-student_home .st-key-home_updates [data-testid="stCaptionContainer"] p {
  font-size:inherit;
  line-height:inherit;
}
.st-key-student_home .home-preview {
  display:-webkit-box;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:2;
  line-clamp:2;
  overflow:hidden;
  overflow-wrap:anywhere;
  color:var(--ink);
  font-size:.9375rem;
  line-height:1.4;
  white-space:pre-line;
}
.st-key-student_home .st-key-home_updates [data-testid="stSelectbox"] {
  min-width:0;
  max-width:100%;
  font-size:.9375rem;
}
.st-key-student_home .st-key-home_updates [data-testid="stSelectbox"]
  :is([data-baseweb="select"] > div, .react-aria-ComboBox > div[role="group"]:has(input[role="combobox"])) {
  min-height:2.25rem;
  border-color:var(--line);
  border-radius:9px;
  background:var(--paper);
  color:var(--ink);
  font-size:.9375rem;
}
.st-key-student_home .st-key-home_updates [data-testid="stSelectbox"] input {
  font-size:.9375rem;
}
.st-key-student_home :is(.st-key-home_updates, .st-key-home_summary, .st-key-home_recent_feedback)
  :is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stPopover"]) button {
  min-height:2.15rem;
  max-width:100%;
  padding:.35rem .65rem;
  border-radius:9px;
  font-size:.875rem;
  line-height:1.35;
  white-space:normal;
  overflow-wrap:anywhere;
}
.st-key-student_home :is(.st-key-home_updates, .st-key-home_summary, .st-key-home_recent_feedback)
  :is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stPopover"]) button p {
  font-size:.875rem;
  line-height:1.35;
}
.st-key-student_home :is(button, input):focus-visible {
  outline:2px solid var(--sky);
  outline-offset:2px;
}
@media (max-width:640px) {
  [data-testid="stMain"]:has(.st-key-student_home) .block-container {
    padding:1rem 1rem 1.5rem;
  }
  .st-key-student_home .home-welcome {
    align-items:flex-start;
    flex-direction:column;
  }
  .st-key-student_home .home-points {
    justify-content:flex-start;
  }
  .st-key-student_home :is(.st-key-home_summary, .st-key-home_documents,
    .st-key-home_feedback, .st-key-home_assessments, .st-key-home_announcements) {
    padding:.8rem;
  }
  .st-key-student_home :is(.st-key-home_updates, .st-key-home_summary, .st-key-home_recent_feedback)
    :is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stPopover"]) button {
    min-height:2.75rem;
  }
}
</style>
"""
