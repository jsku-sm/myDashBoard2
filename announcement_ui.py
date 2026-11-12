"""Presentation for the native, accessible student announcement dialog.

Only this dialog is restyled. A decorative, isolated JavaScript header never
reads the parent page, notice text, student identifiers, or acknowledgement state.
"""
from pathlib import Path

CSS = r'''<style>
/* :has scopes every modal override to this particular announcement dialog. */
[data-testid="stDialog"]:has(.good-notice-marker) {
  background:rgba(59,43,65,.32)!important;backdrop-filter:blur(5px);
}
/* Newer Streamlit versions wrap the ARIA dialog in a separate modal panel. */
[data-testid="stDialog"]:has(.good-notice-marker) > div:has([role="dialog"]) {
  background:transparent!important;box-shadow:none!important;border:0!important;overflow:visible!important;
}
[data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] {
  position:fixed!important;top:50%!important;left:50%!important;
  right:auto!important;bottom:auto!important;transform:translate(-50%,-50%)!important;
  margin:0!important;width:min(640px,calc(100vw - 32px))!important;
  max-width:calc(100vw - 32px)!important;
  max-height:calc(100vh - 36px)!important;max-height:calc(100dvh - 36px)!important;
  overflow-y:auto!important;overscroll-behavior:contain;
  background:#fffaf8!important;color:#513d4c!important;
  border:1px solid #efcad4!important;border-radius:28px!important;
  box-shadow:0 24px 80px #50304338,0 0 0 6px #fff6fa66!important;
  scrollbar-width:thin;scrollbar-color:#e0abbc #fffaf8;
}
[data-testid="stDialog"]:has(.good-notice-marker) [data-baseweb="modal"] {
  background:rgba(59,43,65,.32)!important;backdrop-filter:blur(5px);
}
[data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] [data-testid="stDialogHeader"] {
  background:transparent!important;border-bottom:0!important;
}
[data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] :is(h1,h2,h3,h4,p,li,label) {
  color:#513d4c!important;
}
[data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] h2 {
  font-size:1.15rem!important;letter-spacing:-.025em;font-weight:750;
}
[data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] h3 {
  font-size:1.22rem!important;line-height:1.6;letter-spacing:-.025em;
}
.good-notice-marker{display:none}
.good-notice-intro{text-align:center;color:#886a7a!important;font-size:.9rem;line-height:1.8;margin:-.2rem 0 .75rem;}
.good-notice-count{display:inline-block;border-radius:30px;background:#f9e5ed;color:#9b5670;font-size:.72rem;font-weight:700;padding:5px 12px;letter-spacing:.03em;margin-bottom:8px;}
[data-testid="stDialog"]:has(.good-notice-marker) [class*="st-key-good_notice_card_"] {
  background:#fff!important;border:1px solid #f0dae1;border-radius:18px;
  padding:18px 20px!important;margin-bottom:8px;box-shadow:0 4px 14px #79516406;
}
[data-testid="stDialog"]:has(.good-notice-marker) [class*="st-key-good_notice_card_"] [data-testid="stCaptionContainer"] p {
  font-size:.76rem!important;color:#927587!important;line-height:1.65;
}
[data-testid="stDialog"]:has(.good-notice-marker) [class*="st-key-good_notice_card_"] [data-testid="stMarkdownContainer"] {
  line-height:1.85;overflow-wrap:anywhere;word-break:normal;
}
[data-testid="stDialog"]:has(.good-notice-marker) .st-key-acknowledge_announcements button {
  background:linear-gradient(115deg,#bd6589,#a868a3)!important;color:#fff!important;
  border:1px solid #ad6287!important;border-radius:16px!important;
  min-height:50px;box-shadow:0 6px 16px #ac5f872b;transition:box-shadow .18s ease,filter .18s ease;
}
[data-testid="stDialog"]:has(.good-notice-marker) .st-key-acknowledge_announcements button p {
  color:#fff!important;font-weight:750;font-size:1rem;
}
[data-testid="stDialog"]:has(.good-notice-marker) .st-key-acknowledge_announcements button:hover {
  filter:brightness(1.05);box-shadow:0 8px 22px #ac5f873d;
}
[data-testid="stDialog"]:has(.good-notice-marker) .st-key-acknowledge_announcements button:focus-visible {
  outline:3px solid #744563!important;outline-offset:4px!important;
}
.good-notice-footer{text-align:center;color:#967786!important;font-size:.75rem;line-height:1.8;padding-top:2px}
@media(max-width:600px){
 [data-testid="stDialog"]:has(.good-notice-marker) [role="dialog"] {width:calc(100vw - 24px)!important;border-radius:22px!important;}
 [data-testid="stDialog"]:has(.good-notice-marker) [class*="st-key-good_notice_card_"] {padding:14px 15px!important;}
}
@media(prefers-reduced-motion:reduce){
 [data-testid="stDialog"]:has(.good-notice-marker) * {animation:none!important;transition:none!important;}
}
</style>'''


def header_html():
    return Path(__file__).with_name('assets').joinpath('announcement_letter.html').read_text(encoding='utf-8')
