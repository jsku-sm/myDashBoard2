import base64
import hashlib
import html
from pathlib import Path
import uuid
import pandas as pd
import streamlit as st
from streamlit.components.v1 import declare_component
from .ai import AI, board_image, normalized_image
from .config import load_settings
from .service import Service, CLASSES, report_rows, misconception_counts, effective, safe_csv
from .storage import MemoryStore, LocalStore, GitHubStore, AppError

ROOT = Path(__file__).parent
board = declare_component("think_whiteboard", path=str(ROOT / "board"))
CORRECT = {"correct": "정확해요", "partial": "일부 수정이 필요해요", "incorrect": "다시 살펴봐요", "uncertain": "판단 보류", "pending": "평가 대기"}
LEVELS = {"met": "도달", "developing": "발전 중", "not_yet": "더 살펴보기", "uncertain": "확인 필요"}
STATUS = {"pending": "피드백 대기", "processing": "AI 분석 중", "ready": "AI 피드백 도착", "error": "AI 재시도 필요"}


@st.cache_resource(show_spinner=False)
def persistent_service(settings):
    if settings.mode == "github":
        store = GitHubStore(settings.repo, settings.branch, settings.github_token, settings.encryption_key)
    elif settings.mode == "local":
        store = LocalStore(settings.data_dir, settings.encryption_key)
    else:
        raise AppError("THINK_MODE는 demo, local, github 중 하나로 설정하세요.")
    service = Service(store, settings)
    service.bootstrap()
    return service


def make_service(settings):
    if settings.mode == "demo":
        if "think_demo_store" not in st.session_state:
            st.session_state.think_demo_store = MemoryStore()
        service = Service(st.session_state.think_demo_store, settings)
        service.bootstrap()
        return service
    return persistent_service(settings)


def css():
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
    html,body,[class*="css"],.stApp{font-family:'Noto Sans KR',sans-serif}
    .stApp{background:#f8faf7;color:#183d39}.block-container{max-width:1260px;padding-top:2rem;padding-bottom:3rem}
    [data-testid="stSidebar"]{background:#edf4ee;border-right:1px solid #dce7de}
    [data-testid="stSidebar"] .block-container{padding-top:1.5rem}
    h1,h2,h3{color:#143e38;letter-spacing:-.035em}h1{font-size:2.2rem!important}
    div[data-testid="stMetric"]{background:white;border:1px solid #dce7df;padding:17px;border-radius:15px}
    div[data-testid="stMetricLabel"]{color:#526f65}div[data-testid="stMetricValue"]{color:#145f50}
    .stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:#176b59;border:0;border-radius:10px}
    .stButton>button,.stFormSubmitButton>button{border-radius:10px;min-height:42px}
    .think-hero{background:#eaf1de;border:1px solid #d6e3c9;border-radius:22px;padding:26px 30px;margin:0 0 24px;position:relative;overflow:hidden}
    .think-hero p{color:#4d6655;max-width:760px;margin:8px 0 0;line-height:1.8}
    .think-kicker{font-size:11px;letter-spacing:2px;font-weight:800;color:#538568;margin-bottom:8px}
    .think-hero h1{margin:0;padding:0;font-weight:800}.think-brand{font-size:20px;font-weight:800;margin:12px 0 4px}
    .think-sub{font-size:12px;color:#5c7e6c;margin-bottom:24px}.think-steps{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 25px}
    .think-step{padding:9px 15px;border-radius:100px;background:white;border:1px solid #dbe5dc;font-size:13px;color:#587267}
    .think-step.active{background:#176b59;color:#fff;border-color:#176b59}
    .think-note{padding:16px 20px;background:#fff4dc;border-left:4px solid #dfb563;border-radius:10px;color:#5d5135;margin:12px 0}
    .think-card{padding:18px 22px;border-radius:15px;background:#fff;border:1px solid #dce6df;margin:12px 0}
    .think-card b{font-size:15px;color:#16664f}.think-card p{margin:8px 0 0;line-height:1.85}
    [data-testid="stExpander"]{background:white;border-radius:13px}
    @media(max-width:700px){.think-hero{padding:22px}h1{font-size:1.8rem!important}.block-container{padding:1rem}}
    </style>""", unsafe_allow_html=True)


def hero(title, subtitle, kicker="GUSSAEM · THINK OUT LOUD"):
    st.markdown(f'<div class="think-hero"><div class="think-kicker">{html.escape(kicker)}</div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)


def card(title, text):
    st.markdown(f'<div class="think-card"><b>{html.escape(title)}</b><p>{html.escape(text).replace(chr(10),"<br>")}</p></div>', unsafe_allow_html=True)


def flash(message):
    st.session_state.think_flash = message
    st.rerun()


def logout():
    for key in list(st.session_state):
        if str(key).startswith("think_") and key not in ("think_demo_store", "think_flash"):
            del st.session_state[key]
    st.rerun()


def login_view(svc, settings):
    hero("생각을 말해요.", "쓰고, 말하고, 다시 생각하는 수학. 풀이를 설명하는 순간, 배움이 시작됩니다.")
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        card("01 · 나의 생각을 꺼내요", "풀이판에 그리고, 글이나 목소리로 왜 그렇게 생각했는지 설명해요.")
        card("02 · 한 걸음 더 생각해요", "피드백 속 작은 힌트로 풀이를 돌아보고 다시 도전해요.")
        card("03 · 성장 과정을 함께 봐요", "선생님과 첫 풀이부터 달라진 생각까지 확인해요.")
    with right:
        if settings.mode == "demo":
            st.subheader("먼저 체험해 보세요")
            st.info("체험 기록은 현재 브라우저 세션에만 남습니다. 새로고침·접속 종료 시 사라질 수 있어요. 실제 학생 정보는 입력하지 마세요.")
            if st.button("교사로 체험하기", type="primary", use_container_width=True):
                st.session_state.think_token = svc.demo_login("teacher")
                st.rerun()
            if st.button("학생으로 체험하기", use_container_width=True):
                st.session_state.think_token = svc.demo_login("student")
                st.rerun()
            st.caption("학생으로 제출한 뒤 교사로 전환하면 같은 세션의 제출물을 볼 수 있습니다.")
        tabs = st.tabs(["로그인", "학생 가입"])
        with tabs[0]:
            with st.form("think_login"):
                uid = st.text_input("학번 또는 교사 아이디", key="think_login_id", max_chars=40)
                pw = st.text_input("비밀번호", type="password", key="think_login_pw")
                if st.form_submit_button("로그인", type="primary", use_container_width=True):
                    try:
                        st.session_state.think_token = svc.login(uid, pw)
                        st.rerun()
                    except AppError as e:
                        st.error(str(e))
        with tabs[1]:
            with st.form("think_signup"):
                sid = st.text_input("학번", max_chars=10)
                name = st.text_input("이름", max_chars=40)
                cls = st.selectbox("학급", CLASSES)
                code = st.text_input("선생님이 알려준 가입코드", max_chars=16)
                pw = st.text_input("새 비밀번호 · 10자 이상", type="password")
                pw2 = st.text_input("비밀번호 확인", type="password")
                if st.form_submit_button("가입하기", use_container_width=True):
                    try:
                        if pw != pw2:
                            raise AppError("비밀번호가 서로 다릅니다.")
                        svc.register(sid, name, cls, code, pw)
                        st.success("가입했습니다. 로그인 탭에서 접속하세요.")
                    except AppError as e:
                        st.error(str(e))


def teacher_home(svc, token, snap):
    hero("학생의 생각을 만나는 교실", "문제를 만들고, 풀이를 듣고, 학생이 다시 시도하는 과정을 함께 봅니다.", "TEACHER STUDIO")
    students = [u for u in snap["users"] if u["role"] == "student"]
    cols = st.columns(4)
    for col, label, value in zip(cols, ["함께하는 학생", "열린 과제", "누적 풀이", "교사 확인 필요"],
                               [len(students), sum(t["open"] for t in snap["activities"]), len(snap["attempts"]),
                                sum(not a["review"] and (not a["feedback"] or a["feedback"].get("needs_teacher_review")) for a in snap["attempts"])]):
        col.metric(label, value)
    st.subheader("우리 반 과제")
    if not snap["activities"]:
        st.info("‘학급·학생’에서 학급을 연 뒤 ‘새 과제 만들기’에서 첫 과제를 배정하세요.")
    for task in reversed(snap["activities"]):
        with st.container(border=True):
            a, b = st.columns([4, 1])
            a.markdown("**" + task["title"] + "**")
            a.caption(f'{task["subject"]} · {", ".join(task["classes"])} · 최대 {task["max_attempts"]}회 · {"제출 가능" if task["open"] else "제출 마감"}')
            with a.expander("문제와 평가 기준"):
                st.write(task["prompt"])
                st.write("교사용 모범 풀이")
                st.info(task["expected"])
                for criterion in task["criteria"]:
                    st.write("• " + criterion)
            if b.button("제출 마감" if task["open"] else "다시 열기", key="think_toggle_"+task["id"]):
                svc.toggle_activity(token, task["id"])
                flash("과제 상태를 변경했습니다.")


def create_activity_view(svc, token, snap):
    hero("어떤 생각을 듣고 싶으세요?", "학생에게 보여줄 문제와 교사용 평가 기준을 정하세요. 모범 풀이는 학생 화면에 표시되지 않습니다.", "01 · CREATE AN ACTIVITY")
    if not snap["classes"]:
        st.info("‘학급·학생’에서 가입코드를 발급하면 학급을 선택할 수 있습니다.")
        return
    with st.form("think_create_activity"):
        a, b = st.columns([2, 1])
        title = a.text_input("과제 제목", placeholder="예: 서로 평행한 두 직선을 설명해 볼까요?", max_chars=120)
        subject = b.selectbox("과목", ["공통수학2", "공통수학1", "수학Ⅰ", "수학Ⅱ", "확률과 통계", "기타"])
        prompt = st.text_area("학생에게 제시할 문제", height=130, max_chars=10000)
        expected = st.text_area("교사용 모범 풀이·핵심 개념", height=110, max_chars=10000)
        criteria = st.text_area("평가 기준 · 한 줄에 한 가지", value="사용한 개념을 자신의 말로 설명한다.\n풀이 과정에 수학적 근거를 제시한다.\n답과 그림 또는 식의 관계를 설명한다.", height=120)
        a, b = st.columns(2)
        classes = a.multiselect("배정할 학급", snap["classes"], default=snap["classes"][:1])
        attempts = b.number_input("최대 제출 횟수", min_value=1, max_value=10, value=5)
        st.caption("제출물이 생긴 과제의 기준이 달라지지 않도록, 이 버전에서는 과제 수정 대신 새 과제로 등록합니다.")
        if st.form_submit_button("과제 만들고 배정하기", type="primary", use_container_width=True):
            try:
                svc.create_activity(token, title, prompt, expected,
                    [c.strip() for c in criteria.splitlines() if c.strip()], classes, attempts, subject)
                flash("새 과제를 배정했습니다. 학생 화면에서 바로 확인할 수 있습니다.")
            except AppError as e:
                st.error(str(e))


def class_view(svc, token, snap):
    hero("함께 배울 학급을 열어요", "가입코드를 전달하면 학생이 학번과 비밀번호로 가입할 수 있습니다.", "CLASSROOM")
    a, b = st.columns([1, 1.5], gap="large")
    with a:
        cls = st.selectbox("학급", CLASSES, key="think_new_class")
        if st.button("가입코드 발급 / 재발급", type="primary"):
            code = svc.class_code(token, cls)
            st.session_state.think_issued = (cls, code)
            st.rerun()
        if st.session_state.get("think_issued"):
            cls, code = st.session_state.think_issued
            st.success(f"{cls} 가입코드")
            st.code(code)
            st.caption("재발급하면 이전 가입코드는 사용할 수 없습니다. 이미 가입한 학생은 그대로 로그인할 수 있습니다.")
    with b:
        rows = [{"학급": u["class_id"], "학번": u["id"], "이름": u["name"]} for u in snap["users"] if u["role"] == "student"]
        st.subheader(f"등록 학생 · {len(rows)}명")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("아직 가입한 학생이 없습니다.")


def show_feedback(a):
    if a.get("review"):
        r = a["review"]
        st.success("선생님이 확인했어요 · " + CORRECT[r["correctness"]])
        st.write(r["comment"])
        st.caption("교사 설명점수: " + (str(r["score"]) + " / 4" if r["score"] is not None else "판단 보류"))
    f = a.get("feedback")
    if not f:
        st.info("제출은 완료되었습니다. " + (a.get("error") or "아직 AI 피드백이 없습니다. 선생님은 제출물을 확인하고 피드백할 수 있습니다."))
        return
    st.caption("AI 학습 피드백 · 교사가 수정할 수 있는 잠정 결과")
    c1, c2 = st.columns(2)
    c1.metric("답·결론", {"correct": "정확", "partial": "부분 수정", "incorrect": "재검토", "uncertain": "판단 보류"}[f["correctness"]])
    c2.metric("설명의 충실도", f'{f["explanation_score"]} / 4' if f["explanation_score"] is not None else "판단 보류")
    card("잘한 점", f["praise"])
    card("이 부분을 살펴봐요", f["observation"])
    card("작은 힌트", f["hint"])
    card("다음 생각을 여는 질문", f["next_question"])
    if f["needs_teacher_review"]:
        st.warning("선생님 확인이 필요해요. " + f["uncertainty_reason"])
    with st.expander("평가 기준별 근거"):
        for c in f["criteria"]:
            st.markdown(f'**{c["criterion"]} · {LEVELS[c["level"]]}**')
            st.write(c["evidence"])


def attempt_detail(svc, token, a, ai, teacher=False):
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**학생이 남긴 설명**")
        st.write(a["text"] or "글 설명 없음")
        if a["transcript"]:
            st.markdown("**목소리로 설명한 내용 · 학생 확인 전사**")
            st.write(a["transcript"])
        if a["reflection"]:
            st.markdown("**고치며 달라진 생각**")
            st.write(a["reflection"])
        if a["images"] and st.checkbox("풀이 이미지 보기", key="think_images_"+a["id"]):
            for idx in range(len(a["images"])):
                st.image(svc.image(token, a["id"], idx), use_container_width=True)
        st.caption(f'{a["created"][:16].replace("T", " ")} · {a["number"]}번째 도전 · {STATUS[a["status"]]}')
        if not a["feedback"] and ai.available:
            consent = a["consent"]
            if not teacher and not consent:
                consent = st.checkbox("이 제출 내용을 OpenAI에 보내 AI 피드백을 받겠습니다", key="think_late_consent_"+a["id"])
            if consent and st.button("AI 피드백 받기 / 다시 시도", key="think_retry_"+a["id"]):
                try:
                    if not a["consent"]:
                        svc.allow_ai(token, a["id"])
                    with st.spinner("설명과 풀이를 살펴보고 있어요…"):
                        svc.evaluate(token, a["id"], ai)
                    flash("AI 피드백을 받았습니다.")
                except AppError as e:
                    st.error(str(e))
    with right:
        show_feedback(a)
    if teacher:
        with st.form("think_review_"+a["id"]):
            st.markdown("**교사 확인·피드백**")
            score, correct = effective(a)
            choices = list(CORRECT)[:-1]
            c1, c2 = st.columns(2)
            verdict = c1.selectbox("교사 판단", choices, index=choices.index(correct) if correct in choices else 3, format_func=lambda x: CORRECT[x])
            scores = [None, 0, 1, 2, 3, 4]
            grade = c2.selectbox("설명점수", scores, index=scores.index(score), format_func=lambda x: "판단 보류" if x is None else str(x))
            comment = st.text_area("학생에게 전할 말", value=(a["review"] or {}).get("comment", ""), max_chars=3000)
            if st.form_submit_button("교사 피드백 저장", type="primary"):
                svc.review(token, a["id"], verdict, grade, comment)
                flash("교사 피드백을 저장했습니다. 학생 화면에도 표시됩니다.")


def report_view(svc, token, snap, ai):
    hero("답 너머의 생각을 살펴봐요", "학생별 시도와 설명의 변화, AI가 제안한 오개념을 확인하고 교사 피드백을 남깁니다.", "05 · CLASS INSIGHTS")
    if not snap["activities"]:
        st.info("과제를 먼저 만들어 주세요.")
        return
    mapping = {a["id"]: a for a in snap["activities"]}
    aid = st.selectbox("분석할 과제", list(mapping), format_func=lambda x: mapping[x]["title"], key="think_report_task")
    cls = st.selectbox("학급 필터", ["전체"] + mapping[aid]["classes"], key="think_report_class_"+aid)
    rows = [r for r in report_rows(snap, aid) if cls == "전체" or r["학급"] == cls]
    attempts = [a for a in snap["attempts"] if a["activity_id"] == aid and (cls == "전체" or a["class_id"] == cls)]
    scores = [r["최근설명점수"] for r in rows if r["최근설명점수"] is not None]
    c1, c2, c3 = st.columns(3)
    c1.metric("제출 학생 / 등록 학생", f'{sum(r["제출횟수"]>0 for r in rows)} / {len(rows)}')
    c2.metric("두 번 이상 도전", sum(r["제출횟수"] > 1 for r in rows))
    c3.metric("최근 설명점수 평균", f"{sum(scores)/len(scores):.1f} / 4" if scores else "평가 대기")
    st.caption("평균은 점수가 있는 학생만 포함합니다. 교사 점수가 있으면 우선 반영하고, 없으면 AI 잠정 점수를 사용합니다.")
    if rows:
        visible = [{**r, "판정": CORRECT[r["판정"]]} for r in rows]
        st.dataframe(visible, use_container_width=True, hide_index=True)
        st.download_button("학생별 결과 CSV 내려받기", safe_csv(visible), file_name="설명학습_학생별결과.csv", mime="text/csv")
    counts = misconception_counts(attempts)
    with st.expander("AI가 제안한 공통 오개념", expanded=bool(counts)):
        st.caption("학생별 최근 제출 중 교사가 아직 확인하지 않은 AI 결과를 모았습니다. 수업에서 직접 확인해 주세요.")
        if counts:
            st.bar_chart(pd.DataFrame({"오개념": list(counts), "학생 수": list(counts.values())}).set_index("오개념"), color="#34896e")
        else:
            st.write("표시할 오개념이 없습니다. AI 분석 전이거나 교사가 이미 확인한 결과입니다.")
    if not attempts:
        st.info("아직 제출된 풀이가 없습니다.")
        return
    names = {u["id"]: u["name"] for u in snap["users"]}
    student_ids = sorted({a["student_id"] for a in attempts})
    sid = st.selectbox("학생의 풀이 살펴보기", student_ids, format_func=lambda x: x+" · "+names.get(x,x), key="think_review_student_"+aid+cls)
    for a in reversed([a for a in attempts if a["student_id"] == sid]):
        with st.expander(f'{a["number"]}번째 도전 · {STATUS[a["status"]]}', expanded=a == [x for x in attempts if x["student_id"] == sid][-1]):
            attempt_detail(svc, token, a, ai, teacher=True)
    export = [{"학번": a["student_id"], "과제": mapping[aid]["title"], "시도": a["number"], "설명": a["text"],
               "음성전사": a["transcript"], "성찰": a["reflection"], "AI관찰": (a["feedback"] or {}).get("observation", ""),
               "교사피드백": (a["review"] or {}).get("comment", ""), "제출일시": a["created"]} for a in attempts]
    st.download_button("풀이·성찰 전체 CSV 내려받기", safe_csv(export), file_name="설명학습_풀이성찰.csv", mime="text/csv")


def student_work(svc, token, snap, ai):
    hero("너의 생각이 궁금해!", "완벽한 답이 아니어도 괜찮아요. 어떻게 생각했는지 들려주세요.", "MY THINKING STUDIO")
    if not snap["activities"]:
        st.info("선생님이 우리 반에 과제를 배정하면 여기에 나타납니다.")
        return
    mapping = {a["id"]: a for a in snap["activities"]}
    aid = st.selectbox("오늘의 과제", list(mapping), format_func=lambda x: mapping[x]["title"], key="think_student_task")
    task = mapping[aid]
    previous = [a for a in snap["attempts"] if a["activity_id"] == aid]
    card(task["title"], task["prompt"])
    with st.expander("어떤 점을 살펴보나요?"):
        for c in task["criteria"]:
            st.write("• " + c)
    st.markdown('<div class="think-steps"><span class="think-step active">1 쓰고 말하기</span><span class="think-step">2 피드백 살펴보기</span><span class="think-step">3 다시 도전하기</span></div>', unsafe_allow_html=True)
    if previous:
        with st.expander("최근 피드백과 이전 풀이", expanded=True):
            show_feedback(previous[-1])
        st.caption(f'지금까지 {len(previous)}회 제출했어요. 최대 {task["max_attempts"]}회 도전할 수 있어요.')
    if not task["open"] or len(previous) >= task["max_attempts"]:
        st.info("이 과제는 추가 제출이 마감되었습니다. ‘나의 기록’에서 풀이와 피드백을 확인하세요.")
        return
    revision_key = "think_rev_"+aid
    rev = st.session_state.get(revision_key, 0)
    key = f'think_draft_{snap["user"]["id"]}_{aid}_{rev}'
    if previous and st.button("이전 설명을 가져와 고쳐 쓰기", key=key+"_copy"):
        st.session_state[key+"_text"] = previous[-1]["text"]
        st.session_state[key+"_transcript"] = previous[-1]["transcript"]
        if previous[-1]["images"]:
            st.session_state[key+"_initial"] = "data:image/jpeg;base64,"+base64.b64encode(svc.image(token, previous[-1]["id"], 0)).decode()
        st.session_state[key+"_board_rev"] = st.session_state.get(key+"_board_rev", 0)+1
        st.rerun()
    l, r = st.columns([1.5, 1], gap="large")
    with l:
        st.subheader("그리며 생각하기")
        value = board(initial_image=st.session_state.get(key+"_initial"),
                      key=key+"_board_"+str(st.session_state.get(key+"_board_rev",0)), default=None)
        upload = st.file_uploader("종이에 푼 풀이도 올릴 수 있어요", type=["png","jpg","jpeg"], key=key+"_image")
        st.caption("풀이판과 사진을 함께 제출할 수 있어요. 사진에는 풀이만 담아 주세요.")
    with r:
        st.subheader("나의 설명")
        explanation = st.text_area("왜 그렇게 생각했나요?", placeholder="나는 먼저 …을 확인했어요. 그 이유는 …이에요.", height=190, max_chars=8000, key=key+"_text")
        consent = st.checkbox("AI 피드백 받기 · 설명과 풀이를 OpenAI에 전송", value=False, disabled=not ai.available, key=key+"_consent")
        audio = st.audio_input("목소리로 설명하기 · 2분 이내", sample_rate=16000, key=key+"_audio")
        audio_hash = hashlib.sha256(audio.getvalue()).hexdigest() if audio else ""
        if audio_hash != st.session_state.get(key+"_seen_audio", ""):
            st.session_state[key+"_seen_audio"] = audio_hash
            st.session_state[key+"_converted_audio"] = ""
            # Keep a manually written transcript but clearly require the new recording to be converted.
        if st.button("녹음한 말을 글로 바꾸기", disabled=not(audio and ai.available and consent), key=key+"_convert"):
            try:
                if st.session_state.get(key+"_audio_calls",0) >= 5:
                    raise AppError("이 초안의 음성 변환은 5회까지 가능합니다. 설명을 직접 수정해 주세요.")
                st.session_state[key+"_audio_calls"] = st.session_state.get(key+"_audio_calls",0)+1
                with st.spinner("목소리를 글로 옮기고 있어요…"):
                    st.session_state[key+"_transcript"] = ai.transcribe(audio.getvalue())
                st.session_state[key+"_converted_audio"] = audio_hash
                st.rerun()
            except AppError as e:
                st.error(str(e))
        transcript = st.text_area("말한 내용 확인·수정", height=110, max_chars=4000, key=key+"_transcript")
        st.caption("음성 원본은 저장하지 않습니다. 글로 바꾼 내용을 확인하고 제출해 주세요.")
        if not ai.available:
            st.info("AI 미연결: 설명과 그림을 제출하면 선생님이 확인할 수 있어요. 음성 자동 변환은 연결 후 사용할 수 있습니다.")
    reflection = st.text_area("다시 도전하며 달라진 생각 · 선택", placeholder="처음에는 …라고 생각했는데, 이제는 …", key=key+"_reflection", max_chars=2000)
    if st.button("설명 제출하고 피드백 받기" if ai.available and consent else "설명 제출하기", type="primary", use_container_width=True, key=key+"_submit"):
        try:
            if audio and audio_hash != st.session_state.get(key+"_converted_audio"):
                raise AppError("녹음한 말을 먼저 글로 바꿔 확인하세요. AI를 사용하지 않으면 녹음을 지우고 설명을 직접 입력해 주세요.")
            images = []
            drawn = board_image(value)
            if drawn:
                images.append(drawn)
            if upload:
                images.append(normalized_image(upload.getvalue()))
            rid = st.session_state.setdefault(key+"_request", uuid.uuid4().hex)
            with st.spinner("나의 풀이를 저장하고 있어요…"):
                submitted = svc.submit(token, aid, explanation, transcript, images, reflection, consent, rid)
            message = "풀이를 제출했습니다."
            # Submission is durably saved before any paid AI call.
            if consent and ai.available:
                try:
                    with st.spinner("AI가 풀이와 설명을 살펴보고 있어요…"):
                        svc.evaluate(token, submitted, ai)
                    message += " AI 피드백을 확인해 보세요."
                except AppError as e:
                    message += " " + str(e)
            st.session_state[revision_key] = rev+1
            flash(message)
        except AppError as e:
            st.error(str(e))


def student_history(svc, token, snap, ai):
    hero("다시 생각한 만큼, 자라고 있어요", "처음 남긴 설명과 수정한 설명을 나란히 돌아보세요.", "04 · MY LEARNING JOURNEY")
    names = {a["id"]: a["title"] for a in snap["activities"]}
    if not snap["attempts"]:
        st.info("첫 풀이를 제출하면 나의 기록이 시작됩니다.")
    for a in reversed(snap["attempts"]):
        with st.expander(f'{names.get(a["activity_id"],"과제")} · {a["number"]}번째 도전', expanded=False):
            attempt_detail(svc, token, a, ai)


def account_view(svc, token, settings):
    hero("내 계정", "비밀번호를 변경하면 다시 로그인합니다.")
    if settings.mode == "demo":
        st.info("체험 계정은 비밀번호 변경을 사용하지 않습니다.")
        return
    with st.form("think_password_change"):
        old = st.text_input("현재 비밀번호", type="password")
        new = st.text_input("새 비밀번호 · 10자 이상", type="password")
        confirm = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("비밀번호 변경", type="primary"):
            if new != confirm:
                raise AppError("새 비밀번호가 서로 다릅니다.")
            svc.change_password(token, old, new)
            st.session_state.think_flash = "비밀번호를 변경했습니다. 다시 로그인하세요."
            logout()


def run():
    st.set_page_config(page_title="구쌤 · 생각을 말해요", page_icon="🌱", layout="wide")
    css()
    settings = load_settings()
    try:
        svc = make_service(settings)
    except AppError as e:
        hero("교실을 열 준비를 해요", "설정을 확인하면 학생과 함께 시작할 수 있습니다.")
        st.error(str(e))
        st.info("README_시작하기.md와 secrets.toml.example을 확인하세요. 운영 저장소 오류가 나도 임시 체험 저장으로 전환하지 않습니다.")
        return
    ai = AI(settings)
    if st.session_state.get("think_flash"):
        st.success(st.session_state.pop("think_flash"))
    token = st.session_state.get("think_token")
    if not token:
        login_view(svc, settings)
        return
    try:
        snap = svc.snapshot(token)
    except AppError as e:
        st.error(str(e))
        if st.button("로그인 화면으로"):
            logout()
        return
    user = snap["user"]
    teacher = user["role"] == "teacher"
    with st.sidebar:
        st.markdown('<div class="think-brand">🌱 생각을 말해요</div><div class="think-sub">GUSSAEM · MATH LEARNING STUDIO</div>', unsafe_allow_html=True)
        st.write(user["name"] + (" 선생님" if teacher else " · " + user["class_id"]))
        if settings.mode == "demo":
            st.info("체험 모드 · 세션 임시 기록")
            if st.button("학생으로 전환" if teacher else "교사로 전환", use_container_width=True):
                st.session_state.think_token = svc.demo_login("student" if teacher else "teacher")
                st.session_state.pop("think_nav", None)
                st.rerun()
        elif settings.mode == "local":
            st.caption("로컬 시험 운영 · 이 컴퓨터에 저장")
        if ai.available:
            st.caption("● AI 연결 설정됨 · 제출 시 호출")
        else:
            st.caption("○ AI 미연결 · 교사 피드백 가능")
        menus = ["교실 홈", "새 과제 만들기", "제출·분석", "학급·학생", "내 계정"] if teacher else ["오늘의 과제", "나의 기록", "내 계정"]
        nav = st.radio("메뉴", menus, label_visibility="collapsed", key="think_nav")
        st.divider()
        if st.button("새로고침", use_container_width=True):
            if hasattr(svc.store, "invalidate"):
                svc.store.invalidate()
            st.rerun()
        if st.button("로그아웃", use_container_width=True):
            logout()
        st.caption("작은 설명이 모여 큰 자신감으로.")
    try:
        if nav == "교실 홈": teacher_home(svc, token, snap)
        elif nav == "새 과제 만들기": create_activity_view(svc, token, snap)
        elif nav == "학급·학생": class_view(svc, token, snap)
        elif nav == "제출·분석": report_view(svc, token, snap, ai)
        elif nav == "오늘의 과제": student_work(svc, token, snap, ai)
        elif nav == "나의 기록": student_history(svc, token, snap, ai)
        else: account_view(svc, token, settings)
    except AppError as e:
        st.error(str(e))
