"""Teacher preparation and private participant entry, using a bundled JS game UI."""
import base64
from functools import lru_cache
import io
import json
from pathlib import Path
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit

import streamlit as st
import storage as db
from config import CLASSES
from . import engine, generator, service

_component = None


def component(data, key, error=""):
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        _component = components.declare_component("good_review_games", path=str(Path(__file__).parent / "frontend"))
    data = dict(data, full_screen=st.session_state.get("_review_focus", False))
    with st.container(key="review_canvas"):
        focus_css = """.st-key-review_canvas{position:fixed!important;inset:0!important;
            z-index:999990!important;width:100vw!important;height:100dvh!important;overflow:auto!important;
            background:#11172d!important;padding:0!important;margin:0!important;}
            .st-key-review_canvas iframe{width:100%!important;min-height:100dvh!important;}
            """ if data["full_screen"] else """.st-key-review_canvas{position:relative!important;
            inset:auto!important;z-index:auto!important;width:100%!important;height:auto!important;
            overflow:visible!important;} .st-key-review_canvas iframe{min-height:0!important;}"""
        # Keep the component's delta position stable across fragment reruns.
        st.markdown("<style>" + focus_css + "</style>", unsafe_allow_html=True)
        return _component(data=data, error=error, key=key, default=None)


def base_url():
    try:
        value = str(st.secrets.get("review_game", {}).get("public_url", ""))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        value = ""
    if not value:
        try:
            value = st.context.url or ""
        except AttributeError:
            value = ""
    return clean_url(value)


def clean_url(value):
    try:
        p = urlsplit(str(value).strip())
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return ""
        return urlunsplit((p.scheme, p.netloc, p.path or "/", "", ""))
    except ValueError:
        return ""


def join_url(base, code):
    url = clean_url(base)
    return url+"?"+urlencode({"review": code}) if url else ""


@lru_cache(maxsize=64)
def qr_image(url):
    if not url:
        return ""
    import qrcode
    out = io.BytesIO()
    qrcode.make(url).save(out, format="PNG")
    return "data:image/png;base64,"+base64.b64encode(out.getvalue()).decode()


def wide_toggle():
    if st.toggle("넓게 보기 · 메뉴 접기", key="_review_wide"):
        st.markdown('''<style>[data-testid="stSidebar"]{display:none}
        .block-container{max-width:100%!important;padding:1rem 1.5rem!important}
        .st-key-tool_selected_content{padding:12px!important}</style>''', unsafe_allow_html=True)
    st.caption("게임 화면 오른쪽 위 ‘전체화면’으로 더 크게 볼 수 있어요. 모바일에서는 ‘넓게 보기’를 사용할 수 있어요.")


def _new_draft(questions, source, files=()):
    st.session_state["_review_draft"] = questions
    st.session_state["_review_source"] = source
    st.session_state["_review_files"] = list(files)
    st.session_state["_review_draft_version"] = uuid.uuid4().hex


def _edit_paper():
    qs = st.session_state.get("_review_draft")
    if not qs:
        return None
    version = st.session_state["_review_draft_version"]
    st.markdown("##### ③ 문제와 정답 확인")
    st.caption("AI 초안은 실제 수업 범위와 정답을 검토한 뒤 시작하세요. 수식은 `$...$`로 입력할 수 있어요.")
    with st.form("review_edit_"+version):
        edits = []
        for i, q in enumerate(qs):
            with st.expander(f"{i+1}번 · {q['prompt'][:65]}", expanded=i==0):
                st.markdown(q["prompt"])
                prompt = st.text_area("문제", q["prompt"], key=f"rq_{version}_{i}")
                options = [st.text_input(f"보기 {j+1}", v, key=f"ro_{version}_{i}_{j}") for j, v in enumerate(q["options"])]
                answer = st.selectbox("정답 번호", list(range(len(options))), index=q["answer"],
                                      format_func=lambda x: f"{x+1}번", key=f"ra_{version}_{i}")
                why = st.text_area("해설", q["explanation"], key=f"re_{version}_{i}")
                st.caption("근거: "+q["source"])
                edits.append(dict(q, prompt=prompt, options=options, answer=answer, explanation=why))
        if st.form_submit_button("문제 검토 완료 · 수정 내용 반영", type="primary"):
            try:
                checked = engine.validate_questions(edits)
                st.session_state["_review_draft"] = checked
                st.session_state["_review_checked"] = version
                st.success("검토한 문제를 반영했어요. 아래에서 게임을 시작할 수 있습니다.")
            except engine.ReviewError as error:
                st.session_state.pop("_review_checked", None)
                st.error(str(error))
    return st.session_state["_review_draft"]


def teacher_page(user):
    try:
        service.teacher(user)
    except PermissionError as error:
        st.error(str(error))
        return
    wide_toggle()
    active = st.session_state.get("_review_active", "")
    if active:
        if st.button("← 게임 목록 · 새 게임 준비", key="review_back"):
            st.session_state.pop("_review_active", None)
            st.rerun()
        live(user, active)
        return
    history = service.history(user)
    if history:
        with st.expander("지난 게임 결과 · 진행 중인 게임 다시 열기"):
            labels = {r["code"]: f'{r["created_at"]} · {r["title"]} · {dict(lobby="대기", running="진행 중", ended="종료")[r["status"]]}' for r in history}
            selected = st.selectbox("저장된 게임", list(labels), format_func=labels.get)
            a, b = st.columns(2)
            if a.button("게임·결과 열기", width="stretch"):
                st.session_state["_review_active"] = selected
                st.rerun()
            if b.button("문제만 복사해서 새 게임 준비", width="stretch"):
                paper = service.paper(user, selected)
                _new_draft(paper["questions"], paper["source"])
                st.session_state["review_title"] = paper["title"]
                st.rerun()
    mode = st.session_state.setdefault("_review_mode", "treasure")
    event = component(dict(screen="select", modes=engine.MODES, selected=mode), "review_mode_select")
    if event and event.get("id") != st.session_state.get("_review_mode_event"):
        st.session_state["_review_mode_event"] = event.get("id")
        if event.get("action") == "fullscreen":
            st.session_state["_review_focus"] = not st.session_state.get("_review_focus", False)
            st.rerun()
        if event.get("action") == "mode" and event.get("mode") in engine.MODES:
            st.session_state["_review_mode"] = event["mode"]
            st.rerun()
    st.markdown("##### ② 지난 시간의 배움 불러오기")
    title = st.text_input("복습 제목", key="review_title", placeholder="예: 점과 도형의 평행이동")
    count = st.number_input("문항 수", min_value=1, max_value=20, value=8, step=1)
    source_type = st.radio("문제 준비 방법", ["자료·제목으로 AI 생성", "기본 문제은행", "직접 입력·JSON 가져오기"], horizontal=True)
    if source_type == "자료·제목으로 AI 생성":
        uploaded = st.file_uploader("수업 자료 (선택)", type=generator.FILE_TYPES, accept_multiple_files=True, key="review_uploads")
        st.caption("PDF·DOCX·PPTX·TXT·이미지 / 최대 3개, 파일당 10MB, 총 20MB. PDF는 30쪽 이하. 제목만으로도 만들 수 있어요.")
        consent = st.checkbox("입력한 제목·수업 자료를 AI에 보내 복습 문제 초안을 만듭니다.", key="review_ai_consent")
        cfg = generator.settings()
        if not cfg.api_key or not cfg.enabled:
            st.info("현재 복습 AI가 연결되지 않았습니다. 기본 문제은행은 바로 사용할 수 있습니다.")
        with st.expander("AI 연결 안내"):
            st.write("기존 OPENAI_API_KEY 또는 [openai] api_key를 사용합니다. 별도 설정은 Streamlit Secrets에 아래 구역을 추가하세요. 키는 채팅이나 GitHub 코드에 적지 않습니다.")
            st.code('[review_ai]\nenabled = true\napi_key = "본인의 API 키"\nmodel = "gpt-4.1-mini"', language="toml")
            st.caption("DOCX·PPTX는 텍스트를 추출합니다. 그림·수식 개체가 중요하면 PDF로 저장해 올리세요.")
        if st.button("✨ 복습 문제 만들기", type="primary", disabled=not cfg.api_key or not cfg.enabled):
            try:
                service.teacher(user)
                if len(uploaded) > 3 or sum(f.size for f in uploaded) > 20_000_000:
                    raise engine.ReviewError("자료는 최대 3개·총 20MB까지 올릴 수 있어요.")
                files = [generator.prepare_file(f.name, f.getvalue()) for f in uploaded]
                with st.spinner("수업 자료를 읽고 복습 문제를 만드는 중…"):
                    questions, source = generator.generate(title, files, int(count), consent=consent, config=cfg)
                _new_draft(questions, source, files)
                st.rerun()
            except engine.ReviewError as error:
                st.error(str(error))
    elif source_type == "기본 문제은행":
        from game_core.curriculum import TOPICS
        topic_ids = list(TOPICS)
        target = next((i for i, key in enumerate(topic_ids) if title.strip() and title.strip() in TOPICS[key]["label"]),
                      topic_ids.index("move.translation"))
        topic_id = st.selectbox("이번에 복습할 세부 주제", topic_ids, index=target, format_func=lambda key: TOPICS[key]["label"])
        st.caption("기존 개념 문제은행에서 생성합니다. 업로드 자료를 분석한 문제는 아닙니다.")
        if st.button("기본 개념 문제 준비", type="primary"):
            try:
                questions = generator.bank_questions(topic_id, int(count))
                _new_draft(questions, dict(kind="built_in", topic_id=topic_id))
                if not title.strip():
                    st.session_state["_review_suggested_title"] = TOPICS[topic_id]["label"]
                st.rerun()
            except engine.ReviewError as error:
                st.error(str(error))
    else:
        example = [{"prompt": "점 (2, 3)을 x축에 대하여 대칭이동한 점은?", "options": ["(2, -3)", "(-2, 3)", "(-2, -3)", "(3, 2)"],
                    "answer": 0, "explanation": "x축 대칭에서는 x좌표는 같고 y좌표의 부호가 바뀝니다.", "concept": "대칭이동", "source": "교사 작성"}]
        raw = st.text_area("문제 JSON (answer: 0은 1번 보기)", json.dumps(example, ensure_ascii=False, indent=2), height=180)
        imported = st.file_uploader("문제 JSON 파일", type=["json"], key="review_json")
        if st.button("입력한 문제 불러오기"):
            try:
                if imported and imported.size > 1_000_000:
                    raise engine.ReviewError("문제 JSON은 1MB 이하로 올려 주세요.")
                values = json.loads(imported.getvalue().decode("utf-8-sig") if imported else raw)
                _new_draft(engine.validate_questions(values), dict(kind="teacher"))
                st.rerun()
            except (ValueError, UnicodeError) as error:
                st.error("문제 형식을 확인해 주세요. "+str(error)[:250])
    questions = _edit_paper()
    if not questions:
        return
    st.download_button("문제·정답 JSON 내려받기 (교사용)", json.dumps(questions, ensure_ascii=False, indent=2),
                       file_name="review_questions.json", mime="application/json")
    st.markdown("##### ④ 참여할 반과 시간 설정")
    a, b = st.columns(2)
    classes = a.multiselect("참여할 반", CLASSES, default=[CLASSES[0]], key="review_classes")
    minutes = b.slider("게임 시간 (분)", 1, 30, 7)
    actual_title = title.strip() or st.session_state.get("_review_suggested_title", "지난 시간 복습")
    st.caption(f'선택한 게임: {engine.MODES[mode]["name"]} · {len(questions)}문제 · {actual_title}')
    checked = st.session_state.get("_review_checked") == st.session_state.get("_review_draft_version")
    if not checked:
        st.info("위의 ‘문제 검토 완료 · 수정 내용 반영’을 누르면 게임을 열 수 있습니다.")
    if st.button("🎮 게임 시작 · 참여코드 만들기", type="primary", disabled=not checked, width="stretch"):
        try:
            code = service.create(user, title=actual_title, questions=questions, mode=mode, classes=classes,
                                  duration=int(minutes)*60, source=st.session_state.get("_review_source", {}))
            st.session_state["_review_active"] = code
            st.rerun()
        except (engine.ReviewError, PermissionError) as error:
            st.error(str(error))


@st.fragment(run_every=1.5)
def live(user, code):
    try:
        view = service.snapshot(user, code)
        if view["role"] == "teacher":
            url = join_url(st.session_state.get("_review_public_url", base_url()), code)
            view.update(join_url=url, qr=qr_image(url))
        event = component(view, "review_live_"+code, st.session_state.get("_review_error", ""))
        if event and event.get("id") != st.session_state.get("_review_live_event"):
            st.session_state["_review_live_event"] = event.get("id")
            st.session_state.pop("_review_error", None)
            try:
                if event.get("action") == "fullscreen":
                    st.session_state["_review_focus"] = not st.session_state.get("_review_focus", False)
                elif event.get("action") in ("answer", "reward"):
                    service.submit(user, code, event.get("index"), event.get("choice"), event["action"])
                elif event.get("action") in ("start", "end", "review"):
                    service.control(user, code, event["action"], event.get("qid", ""), event.get("reveal") is True)
            except (engine.ReviewError, PermissionError) as error:
                st.session_state["_review_error"] = str(error)
            st.rerun(scope="fragment")
        if view["role"] == "teacher" and view["status"] == "lobby":
            with st.expander("QR 참여 주소 확인·수정"):
                st.caption("실제 배포한 앱 주소여야 다른 기기에서 접속할 수 있습니다. 자동 주소가 다르면 수정해 주세요.")
                with st.form("review_public_url_"+code):
                    value = st.text_input("앱 배포 주소", st.session_state.get("_review_public_url", base_url()), placeholder="https://앱이름.streamlit.app/")
                    if st.form_submit_button("QR 주소 적용"):
                        valid = clean_url(value)
                        if valid:
                            st.session_state["_review_public_url"] = valid
                            st.rerun(scope="fragment")
                        else:
                            st.error("http:// 또는 https://로 시작하는 앱 주소를 입력해 주세요.")
        status = service.save_status(user, code)
        if status["local"]:
            st.caption("🧪 로컬 시험 저장 · 실제 배포에서는 기존 GitHub 저장 설정을 사용합니다.")
        elif status["durable"]:
            st.caption("☁️ 기존 저장소에 저장 완료 · 학생별 자료함에도 반영됨")
        else:
            st.caption("⏳ 서버에 반영됨 · GitHub 영구 저장 대기 중 (기존 자동 저장 주기 약 30초)")
        if status["error"]:
            st.warning("저장소 연결에 오류가 있습니다. ‘저장 확인·재시도’를 눌러 확인해 주세요.")
        if view["role"] == "teacher" and view["status"] == "ended":
            c1, c2 = st.columns(2)
            c1.download_button("학급 결과 CSV 내려받기", service.csv_export(user, code),
                               file_name=f"review_{code}_results.csv", mime="text/csv", key="review_csv_"+code)
            if c2.button("저장 확인·재시도", key="review_flush_"+code):
                status = service.flush(user, code)
                if status["durable"]:
                    st.success("저장 상태를 확인했습니다.")
                else:
                    st.warning("아직 저장 대기 중입니다. 기존 GitHub 설정을 확인하고 다시 시도하세요.")
    except (engine.ReviewError, PermissionError) as error:
        st.error(str(error))


def student_entry(user, code):
    wide_toggle()
    if st.button("← 수업 대시보드로 돌아가기", key="review_student_back"):
        st.query_params.pop("review", None)
        st.rerun()
    if user.get("role") != "student":
        st.info("학생 참여용 링크입니다. 교사는 ‘수학 플레이 → 퀴즈 → 전시학습 확인’에서 게임을 관리하세요.")
        return
    if code == "join":
        with st.form("review_join_form"):
            entered = st.text_input("6자리 참여코드", max_chars=6, placeholder="선생님 화면의 숫자 6자리")
            if st.form_submit_button("게임 참여", type="primary"):
                try:
                    service.join(user, entered.strip())
                    st.query_params["review"] = entered.strip()
                    st.rerun()
                except (engine.ReviewError, PermissionError) as error:
                    st.error(str(error))
        return
    try:
        service.join(user, code)
        live(user, code)
    except (engine.ReviewError, PermissionError) as error:
        st.error(str(error))
