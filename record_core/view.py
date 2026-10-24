# GOOD_RECORDS_1.1_FINAL5
"""Streamlit teacher workspace: choose -> inspect -> review -> draft -> edit.

No data are sent to AI on render, student selection, file preparation or download.
"""
from __future__ import annotations
import calendar
import hashlib
import json
from datetime import date
import pandas as pd
import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS
from . import VERSION
from .archive import ArchiveError, EXPECTED_REPO, fingerprint
from .ai import AIConfig, RecordAI, public_manifest
from .service import RecordService, scope_id, byte_count
from .evidence import LABELS


def values():
    try:
        return st.secrets.to_dict() if hasattr(st.secrets, "to_dict") else dict(st.secrets)
    except Exception:
        return {}


def dates():
    t = db.now().date()
    y = t.year if t.month >= 3 else t.year-1
    return date(y,3,1), date(y+1,2,calendar.monthrange(y+1,2)[1])


def _error(error):
    if isinstance(error, (ArchiveError, PermissionError, db.SetupError)):
        st.error(str(error))
    else:
        st.error("처리 결과를 확인하지 못했습니다. 작성 내용은 그대로 두고 저장소 연결을 확인하세요. 자동 AI 재시도는 하지 않습니다.")


def _ai_ready(config):
    return config.enabled and bool(config.api_key) and bool(config.model)


def render():
    st.caption(VERSION + " · 학생별 자료 불러오기 · PDF/손글씨 분석 · 교사 최종 확인")
    backend = db._ready_backend()
    config = AIConfig.from_values(values())
    legacy = str(values().get("app", {}).get("teacher_id", values().get("TEACHER_ID", "teacher")))
    service = RecordService(backend, lambda:(st.session_state.get("user") or {}).get("id"), legacy)
    try:
        actor = service.actor()
    except (ArchiveError, PermissionError) as error:
        st.warning(str(error)); return
    st.markdown("### 학생의 배움에서, 교사의 기록으로")
    st.caption("학생별 자료함 → 선택한 PDF·손글씨 분석 → 교사가 확인한 근거 → 참고 초안 → 교사 수정·최종 확인")
    st.info("상점·벌점도 보관하지만 AI 초안에는 보내지 않습니다. 파일 분석은 관찰 사실을 찾는 보조 기능이며, 성적이나 세특을 자동 확정하지 않습니다.")
    a,b,c = st.columns([1,1,2])
    cls = a.selectbox("학급", CLASSES, key="rv_class")
    subject = b.selectbox("과목", SUBJECTS, key="rv_subject")
    period = c.date_input("작성 기간", value=dates(), key="rv_dates", format="YYYY-MM-DD")
    if not isinstance(period, (tuple,list)) or len(period) != 2:
        st.info("시작일과 종료일을 모두 선택하세요."); return
    start,end=period
    roster = sorted([u for u in backend.read("users") if u.get("role")=="student" and u.get("class")==cls], key=lambda u:u["id"])
    if not roster:
        st.info("이 학급에 등록된 학생이 없습니다."); return
    tab_one,tab_class,tab_help=st.tabs(["학생별 작성하기", "학급 저장 현황", "저장·AI 설정 안내"])
    with tab_one:
        lookup={u["id"]:u for u in roster}
        sid=st.selectbox("학생 선택", list(lookup), format_func=lambda x:f"{x} · {lookup[x]['name']}", key="rv_student_"+cls)
        prefix="rv_"+scope_id(actor["id"],sid,subject,start,end)[:24]
        st.caption(f"저장 대상: {EXPECTED_REPO} / {backend.archive_crypto.student_dir(sid)}")
        left,right=st.columns([2,1])
        if left.button("📂 학생 자료파일 불러오기 · 기존 자료 동기화", key=prefix+"load", type="primary", width="stretch"):
            try:
                with st.spinner("선택한 학생의 기존 자료와 첨부파일을 확인하고 자료함에 보관합니다."):
                    from think_app.embedded import get_store
                    from think_app.integration import load_embedded_settings
                    assessment_store=get_store(load_embedded_settings())
                    service.sync(sid,assessment_store)
                    workspace=service.load(sid,subject,start,end)
                    st.session_state[prefix+"workspace"]=workspace
                    _restore(prefix,workspace)
                st.success("학생별 자료함에 저장된 파일을 불러왔습니다. AI에는 아직 전송하지 않았습니다.")
            except Exception as error:
                _error(error)
        if right.button("저장 재시도 (AI 호출 없음)",key=prefix+"retry",width="stretch"):
            try:
                service.actor(); backend.flush(); st.success("대기 중인 GitHub 저장을 확인했습니다.")
            except Exception as error: _error(error)
        workspace=st.session_state.get(prefix+"workspace")
        if workspace:
            try:
                _workspace(service,workspace,prefix,config)
            except Exception as error: _error(error)
        else:
            st.caption("학생을 선택한 뒤 위 버튼을 누르세요. 학생·과목·기간별로 자료와 초안이 분리됩니다.")
    with tab_class:
        rows=[r for r in backend.read("records") if r.get("class")==cls and r.get("subject")==subject
              and r.get("period")==f"{start}~{end}" and (r.get("author_id") or legacy)==actor["id"]
              and '"teacher_confirmed"' in r.get("sources", "")]
        st.caption("이 화면에는 교사가 최종 확인해 기존 생기부 표에도 저장한 문장만 표시됩니다.")
        if rows:
            frame=pd.DataFrame([{"학번":r["student_id"],"이름":r["name"],"과목":r["subject"],"교사 확인본":r["text"],"저장일":r["updated_at"]} for r in rows])
            st.dataframe(frame,hide_index=True,width="stretch")
            # Formula-injection safe CSV for spreadsheet applications.
            safe=frame.map(lambda v:"'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v)
            st.download_button("교사 확인본 CSV",safe.to_csv(index=False).encode("utf-8-sig"),file_name=f"교사확인본_{cls}_{subject}.csv",mime="text/csv",key="rv_class_export")
        else: st.info("이 기간에 저장한 교사 최종 확인본이 없습니다.")
    with tab_help:
        st.markdown("**학생 자료 저장:** 기존 비공개 데이터는 삭제하지 않습니다. 학생별 `students/고유번호/`에는 암호화한 현재 자료와 변경 이력을 추가로 남깁니다. 학생은 GitHub 권한을 받지 않습니다.")
        st.warning("GitHub는 변경 이력을 보관합니다. 화면에서 삭제해도 과거 커밋·자료함 이력이 자동 영구 삭제되지는 않습니다. 학교 기준에 맞게 보관 기간과 접근 권한을 관리하세요.")
        st.markdown("**파일 분석:** 선택한 PDF·PNG·JPG·WEBP만 전송합니다. PDF는 필요한 페이지를 선택하고, 이름·학번은 직접 가린 사본을 준비할 수 있습니다. 문서 이미지의 개인정보를 자동으로 완전히 지워 주지는 않습니다.")
        st.caption("앱 내부 제한: 파일당 8MB, 1회 5개·합계 20MB, PDF 선택 20쪽 이하. 음성·HWP·DOCX는 보관·다운로드만 하며 이 기능의 분석은 PDF·이미지 사본을 사용합니다.")
        st.warning("외부 AI 전송에는 학교의 개인정보 처리·외부 서비스 이용 기준 확인이 필요합니다. store=false로 요청하지만 서비스 제공자의 보안·남용 방지 보관까지 0일로 보장하는 설정은 아닙니다. API 비용이 발생할 수 있습니다.")
        st.code('''# 기존 [github], [snorkl] 및 키 값은 유지하세요.
[student_archive]
encryption_key = "기존_자료함_Fernet_키_또는_처음_생성한_키"

[school_record_ai]
enabled = true
api_key = "OpenAI_API_키"
model = "gpt-5.4-mini"''',language="toml")
        st.caption("OPENAI_API_KEY / OPENAI_MODEL 또는 공식 OpenAI용 [openai] 설정도 재사용할 수 있습니다. enabled는 이 기능의 외부 전송 허용 설정입니다.")
        st.markdown("**최종 입력 전:** 교사의 직접 관찰·평가 사실과 대조하고, 학생 자기기록·AI 추정과 구별하세요. 기재 가능 범위와 분량은 학교의 최신 지침을 확인하세요. AI 초안을 그대로 최종 확인본으로 저장하지 않도록 했습니다.")
        st.link_button("학교생활기록부 공식 기재요령", "https://star.moe.go.kr/web/contents/m21100.do")
    st.caption(VERSION+" · 기존 학습게임/수행평가/퀴즈 유지 · 선택 전송 · 교사 최종 확인")


def _restore(prefix,workspace):
    saved=[s for s in workspace["data"]["saved"] if s.get("kind") in ("working_draft","final")]
    standalone = [s.get("report") for s in workspace["data"]["saved"] if s.get("kind")=="file_analysis" and s.get("report")]
    if standalone:
        st.session_state[prefix+"analyses"] = standalone
    allowed_ids={e["id"] for e in workspace["data"]["evidence"] if e["eligible"]}
    if prefix+"selected" in st.session_state:
        st.session_state[prefix+"selected"]=[eid for eid in st.session_state[prefix+"selected"] if eid in allowed_ids]
    st.session_state.pop(prefix+"file_choices",None)
    st.session_state.pop(prefix+"prepared",None)
    st.session_state.pop(prefix+"prepared_stamp",None)
    if not saved: return
    latest=sorted(saved,key=lambda x:x.get("saved_at",""))[-1]
    st.session_state[prefix+"text"]=latest.get("text","")
    st.session_state[prefix+"draft"]=latest.get("ai_draft")
    st.session_state[prefix+"analyses"]=list({fingerprint(r):r for r in (standalone+latest.get("analyses",[]))}.values())
    allowed={e["id"]:e for e in workspace["data"]["evidence"]}
    reviews=latest.get("reviews",[])
    st.session_state[prefix+"selected"]=[r["evidence_id"] for r in reviews if r["evidence_id"] in allowed]
    for r in reviews:
        if r["evidence_id"] not in allowed: continue
        k=prefix+r["evidence_id"]
        st.session_state[k+"fact"]=r.get("fact","")
        st.session_state[k+"context"]=r.get("context","확인 필요")
        st.session_state[k+"confirm"]=bool(r.get("teacher_confirmed")) and r.get("evidence_hash")==allowed[r["evidence_id"]]["evidence_hash"]


def _workspace(service,workspace,prefix,config):
    data=service.validate(workspace); evidence=data["evidence"]
    st.caption("자료를 불러온 시각: "+data["loaded_at"]+" · 최신 제출을 반영하려면 다시 불러오기")
    if not evidence:
        st.info("선택 기간·과목에 표시할 자료가 없습니다. 기간과 실제 제출 여부를 확인하세요."); return
    st.markdown("#### 1. 활용할 자료 선택")
    frame=pd.DataFrame([{"종류":e["label"],"날짜":e["date"] or "날짜 미확인","제목":e["title"],"과목":e["subject"] or "교사 확인 필요","첨부":len(e["attachments"]),"출처":e["origin"]} for e in evidence])
    st.dataframe(frame,hide_index=True,width="stretch",height=240)
    points=[e for e in evidence if e["category"]=="points"]
    if points:
        with st.expander(f"상점·벌점 {len(points)}건 (보관·조회 전용, AI 제외)"):
            for e in points: st.write(f"{e['date']} · {e['title']} · {e['text']}")
    eligible={e["id"]:e for e in evidence if e["eligible"]}
    selected=st.multiselect("세특 근거로 검토할 자료 (최대 30개)",list(eligible),
        format_func=lambda k:f"{eligible[k]['date']} · {eligible[k]['label']} · {eligible[k]['title']}",key=prefix+"selected",max_selections=30)
    chosen=[eligible[eid] for eid in selected]
    for e in chosen:
        with st.expander(f"{e['label']} · {e['date']} · {e['title']}"):
            st.caption(e["origin"]+" · 근거번호 "+e["id"])
            st.text(e["text"])
            if not e["subject"]: st.warning("원본에 과목 정보가 없습니다. 아래 교사 확인 단계에서 선택 과목의 수업 자료인지 확인하세요.")
            for i,f in enumerate(e["attachments"]):
                cache_key=prefix+e["id"]+"file"+str(i)+f["sha256"]
                if st.button("첨부파일 열기: "+f["name"],key=cache_key+"open"):
                    st.session_state[cache_key]=service.file(workspace,e["id"],i)
                raw=st.session_state.get(cache_key)
                if raw:
                    if f["mime"].startswith("image/"): st.image(raw,caption=f["name"],width="stretch")
                    st.download_button("원본 내려받기",raw,file_name=f["name"],mime=f["mime"],key=cache_key+"download")
    if not chosen:
        st.caption("먼저 자료를 선택하세요. 선택만으로 AI에 전송되지는 않습니다."); return
    _files(service,workspace,prefix,chosen,config)
    st.markdown("#### 3. 교사가 확인한 사실 기록")
    st.caption("자기평가·자동 채점·AI 분석을 그대로 관찰 사실로 바꾸지 마세요. 직접 관찰·평가한 수학적 행동과 확인 근거를 구체적으로 기록합니다.")
    reviews=[]
    for e in chosen:
        k=prefix+e["id"]
        with st.container(border=True):
            st.markdown(f"**{e['label']} · {e['title']}**")
            context=st.selectbox("활동 맥락",["확인 필요","정규 교과수업","방과후·자유 학습","기타"],key=k+"context")
            text=st.text_area("교사가 확인한 구체적 사실",key=k+"fact",height=100,placeholder="예: 수업에서 두 직선의 기울기를 비교한 풀이를 직접 확인함. 부호를 수정한 뒤 수직 조건을 설명함.")
            confirmed=st.checkbox(f"{data['subject']} 정규 수업에서 직접 관찰·평가한 사실을 확인함",key=k+"confirm")
            if context!="정규 교과수업": st.caption("이 기록은 보관할 수 있지만, 정규 교과수업 근거 확인 전에는 세특 AI 생성에 사용할 수 없습니다.")
            reviews.append({"evidence_id":e["id"],"evidence_hash":e["evidence_hash"],"fact":text,"context":context,"subject":data["subject"],"teacher_confirmed":confirmed})
    st.markdown("#### 4. 참고 초안 작성 · 교사 수정")
    target=st.number_input("참고 초안 목표 글자 수 (사실이 부족하면 억지로 늘리지 않음)",min_value=100,max_value=700,value=400,step=50,key=prefix+"length")
    try: preview=service.input_preview(workspace,reviews,target); ready=True
    except (ArchiveError,PermissionError) as error: preview=str(error); ready=False
    with st.expander("텍스트 전송 미리보기 · 실제 전송할 내용"):
        st.text(preview)
        st.caption("이름·학번·연락처의 일부 패턴을 제거했지만 완전한 익명화를 보장하지 않습니다. 내용과 수식이 잘못 치환되지 않았는지 확인하세요.")
    consent=st.checkbox("미리보기와 학교의 외부 AI 이용 기준을 확인했고, 이번 확인 근거 텍스트를 OpenAI로 전송합니다.",key=prefix+"text_consent")
    if not _ai_ready(config): st.caption("AI는 아직 비활성입니다. 자료 조회·직접 작성은 가능하며, 설정 안내에서 AI 사용을 활성화하세요.")
    if st.button("확인한 근거로 AI 참고 초안 작성",disabled=not (ready and consent and _ai_ready(config)),key=prefix+"generate",type="primary"):
        try:
            with st.spinner("확인한 근거로 참고 초안을 작성합니다."):
                draft=service.draft(workspace,reviews,RecordAI(config),consent=consent,target_chars=target)
                st.session_state[prefix+"draft"]=draft
                st.session_state[prefix+"text"]=draft["text"]
                service.save(workspace,reviews,draft["text"],draft,st.session_state.get(prefix+"analyses",[]))
            st.success("참고 초안을 저장했습니다. 근거와 대조하고 교사의 문장으로 직접 수정하세요.")
        except Exception as error: _error(error)
    draft=st.session_state.get(prefix+"draft")
    if draft:
        with st.expander("AI 원문 · 문장별 근거 · 확인할 점",expanded=False):
            st.text(draft.get("text",""))
            for sentence in draft.get("sentences",[]): st.write({"문장":sentence["text"],"근거":sentence["evidence_ids"]})
            for caution in draft.get("cautions",[]): st.warning(caution)
        if st.button("AI 초안과 연결 해제 · 교사 직접 작성으로 전환",key=prefix+"manual"):
            st.session_state[prefix+"draft"]=None; st.rerun()
    text=st.text_area("교사 작성·수정란",key=prefix+"text",height=230)
    count=byte_count(text)
    st.caption(f"{len(text)}자 · UTF-8/CRLF 참고값 {count}B · 학교의 실제 입력 기준과 대조하세요.")
    if st.button("작성 중 내용 저장",key=prefix+"save_draft"):
        try:
            # Unconfirmed observations remain drafts and cannot generate/finalize.
            service.save(workspace,reviews,text,draft,st.session_state.get(prefix+"analyses",[]))
            st.success("GitHub 학생별 자료함에 작성 중 내용을 저장했습니다.")
        except Exception as error: _error(error)
    note=st.text_input("교사 확인·수정 사항",key=prefix+"review_note",placeholder="원본의 수식·활동 맥락과 대조하고 수정한 내용을 기록")
    verified=st.checkbox("근거·사실·기재 가능 범위·분량을 확인하고 교사가 직접 작성 또는 수정했습니다.",key=prefix+"final_confirm")
    if st.button("교사 최종 확인본 저장",key=prefix+"final",disabled=not (text.strip() and verified and ready)):
        try:
            service.save(workspace,reviews,text,draft,st.session_state.get(prefix+"analyses",[]),final=True,confirmed=verified,review_note=note)
            db.invalidate("records")
            st.success("교사 최종 확인본을 저장했습니다. 나이스에는 자동 입력하지 않습니다.")
            st.download_button("확인본 텍스트 내려받기",text.encode("utf-8-sig"),file_name="교과세특_교사확인본.txt",mime="text/plain",key=prefix+"final_download")
        except Exception as error: _error(error)


def _files(service,workspace,prefix,chosen,config):
    st.markdown("#### 2. 선택한 PDF·손글씨 분석 (선택 사항)")
    options={}
    for e in chosen:
        for i,f in enumerate(e["attachments"]):
            key=e["id"]+":"+str(i)
            options[key]=(e,i,f)
    if not options:
        st.caption("선택한 자료에는 첨부파일이 없습니다. 텍스트 근거 확인 단계로 진행하세요.")
        _show_analyses(prefix,chosen); return
    if prefix+"file_choices" in st.session_state:
        current=st.session_state[prefix+"file_choices"]
        valid=[key for key in current if key in options]
        if current!=valid: st.session_state[prefix+"file_choices"]=valid
    selected=st.multiselect("분석할 첨부파일만 선택",list(options),format_func=lambda k:options[k][0]["title"]+" · "+options[k][2]["name"],key=prefix+"file_choices",max_selections=5)
    selections=[]; shape=[]
    for key in selected:
        e,index,f=options[key]
        k=prefix+hashlib.sha256(key.encode()).hexdigest()[:12]
        st.write("**"+f["name"]+"**")
        pages=st.text_input("PDF 원본 페이지 (예: 1,3-5 · 빈칸은 전체, 최대 20쪽)",key=k+"pages")
        replacement=st.file_uploader("개인정보를 직접 가린 사본으로 대체 (선택)",type=["pdf","png","jpg","jpeg","webp"],key=k+"replacement")
        rep={"name":replacement.name,"data":replacement.getvalue()} if replacement else None
        selections.append({"evidence_id":e["id"],"index":index,"pages":pages,"replacement":rep})
        shape.append([key,pages,hashlib.sha256(rep["data"]).hexdigest() if rep else None,f["sha256"]])
    stamp=fingerprint(shape)
    if st.button("전송용 사본 준비 · 아직 AI 전송 안 함",disabled=not selected,key=prefix+"prepare"):
        try:
            st.session_state[prefix+"prepared"]=service.prepare(workspace,selections)
            st.session_state[prefix+"prepared_stamp"]=stamp
        except Exception as error: _error(error)
    prepared=st.session_state.get(prefix+"prepared") if st.session_state.get(prefix+"prepared_stamp")==stamp else None
    if prepared and selected:
        st.warning("문서에 보이는 이름·학번·얼굴·연락처는 자동 제거되지 않습니다. 아래 전송용 사본을 직접 확인하세요. 필요한 경우 가림 사본을 올린 뒤 다시 준비하세요.")
        for f in prepared["files"]:
            st.caption(f"{f['name']} · {f['bytes']/1024:.1f}KB · 원본 페이지 {f['pages'] or '이미지'} · {'가림 사본' if f['replacement'] else '원본 기반 사본'}")
            if f["mime"].startswith("image/"): st.image(f["data"],width="stretch")
            st.download_button("전송용 사본 확인",f["data"],file_name=f["name"],mime=f["mime"],key=prefix+f["file_id"]+"preview_"+f["sha256"])
        consent=st.checkbox("전송용 사본의 개인정보와 학교 기준을 확인했고, 선택한 파일을 OpenAI로 전송합니다. API 비용·제공자 보관 정책을 확인했습니다.",key=prefix+"file_consent_"+stamp)
        if st.button("선택한 파일만 AI 분석",key=prefix+"analyze",disabled=not (consent and _ai_ready(config))):
            try:
                with st.spinner("선택한 파일의 수학적 풀이와 불명확한 부분을 분석합니다."):
                    report=service.analyze(workspace,prepared,RecordAI(config),consent=consent)
                    st.session_state.setdefault(prefix+"analyses",[]).append(report)
                st.success("분석 결과를 보관했습니다. 아래 확인 사항을 대조하고 교사 사실 기록에 반영하세요.")
            except Exception as error:
                if hasattr(error,"completed_report"):
                    st.session_state.setdefault(prefix+"analyses",[]).append(error.completed_report)
                _error(error)
    _show_analyses(prefix,chosen)


def _show_analyses(prefix,chosen):
    allowed={e["id"] for e in chosen}
    reports=st.session_state.get(prefix+"analyses",[])
    for n,report in enumerate(reports,1):
        with st.expander(f"파일 분석 {n} · 교사 확인 전",expanded=True):
            for observation in report.get("result",{}).get("observations",[]):
                if observation["evidence_id"] not in allowed: continue
                st.markdown("**"+observation["evidence_id"]+" · "+observation["page_or_region"]+"**")
                st.write("보이는 내용: "+observation["observed_text"])
                st.write("풀이 과정: "+observation["process_seen"])
                st.write("수학 개념: "+", ".join(observation["math_concepts"]))
                if observation["uncertain_parts"]: st.warning("불명확: "+" / ".join(observation["uncertain_parts"]))
                st.info("교사 확인: "+observation["teacher_check"])
            for warning in report.get("result",{}).get("warnings",[]): st.warning(warning)
