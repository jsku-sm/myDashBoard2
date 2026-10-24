# GOOD_RECORDS_1.1_FINAL5
"""Teacher-only operations. Actor/ownership is revalidated on EVERY action."""
from __future__ import annotations
import copy
import hashlib
import hmac
import json
import re
import uuid
from .archive import ArchiveError, canonical, fingerprint, utcnow
from .evidence import project, validate_reviews
from .ai import prepare_file, public_manifest, anonymize, draft_input


def scope_id(actor_id, sid, subject, start, end):
    return fingerprint([str(actor_id), str(sid), subject, str(start), str(end)])


def byte_count(text):
    # UTF-8 with CRLF newlines. A display aid, not a guarantee of NEIS rules.
    return len(str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8"))


def normalized_text(text):
    return re.sub(r"\s+", "", str(text))


def check_final(text, ai_draft, *, confirmed, review_note, byte_limit=1500):
    if not str(text).strip():
        raise ArchiveError("교사가 작성한 최종 문장을 입력하세요.")
    if not confirmed or len(str(review_note).strip()) < 5:
        raise ArchiveError("교사가 원본과 문장을 대조했는지 확인하고 수정·확인 사항을 남기세요.")
    if ai_draft and normalized_text(text) == normalized_text(ai_draft):
        raise ArchiveError("AI 초안 그대로는 최종 확인본으로 저장하지 않습니다. 사실을 대조하고 교사의 문장으로 직접 수정하세요.")
    if byte_count(text) > byte_limit:
        raise ArchiveError(f"설정한 분량 기준({byte_limit}B)을 넘었습니다. 학교의 입력 기준을 확인하고 분량을 조정하세요.")


class RecordService:
    def __init__(self, backend, actor_id, legacy_teacher_id="teacher"):
        self.backend = backend
        self.actor_id = actor_id
        self.legacy_teacher_id = legacy_teacher_id

    def actor(self):
        uid = self.actor_id() if callable(self.actor_id) else self.actor_id
        user = next((u for u in self.backend.read("users") if u.get("id") == uid), None)
        if not user or user.get("role") != "teacher" or user.get("must_change") == "1":
            raise PermissionError("현재 계정에 생기부생성기 접근 권한이 없습니다.")
        if getattr(self.backend, "is_local", True) or not getattr(self.backend, "archive_crypto", None):
            raise ArchiveError("생기부 자료함은 GitHub 비공개 저장소와 암호화키를 연결한 뒤 사용하세요. 로컬 임시 저장으로 대체하지 않습니다.")
        return user

    def student(self, sid):
        self.actor()
        user = next((u for u in self.backend.read("users") if u.get("id") == str(sid) and u.get("role") == "student"), None)
        if not user:
            raise ArchiveError("선택한 학생 계정을 찾을 수 없습니다.")
        return user

    def _sign(self, value):
        return hmac.new(self.backend.archive_crypto.key, canonical(value), hashlib.sha256).hexdigest()

    def _seal(self, data):
        return {"data":data, "signature":self._sign(data)}

    def validate(self, workspace):
        actor = self.actor()
        if not isinstance(workspace, dict) or not hmac.compare_digest(str(workspace.get("signature", "")), self._sign(workspace.get("data"))):
            raise ArchiveError("자료 선택 상태가 변경되었습니다. 학생 자료를 다시 불러오세요.")
        data = workspace["data"]
        if data.get("teacher_id") != actor["id"]:
            raise PermissionError("다른 교사의 작성 화면에 접근할 수 없습니다.")
        self.student(data["student_id"])
        return data

    def sync(self, sid, assessment_store):
        self.student(sid)
        from .assessment import bind, sync_state
        bind(assessment_store, self.backend)
        # Copies existing saved records, does not delete originals or mark AI consent.
        self.backend.archive_student_tables(sid)
        count = sync_state(assessment_store, self.backend, assessment_store.read(), student_id=sid)
        self.backend.flush()
        return count

    def load(self, sid, subject, start, end):
        teacher = self.actor(); self.student(sid)
        if subject not in ("공통수학1", "공통수학2") or str(start)[:10] > str(end)[:10]:
            raise ArchiveError("과목과 작성 기간을 확인하세요.")
        bundles = self.backend.archive_read_student(sid)
        evidence = project(bundles, sid=sid, teacher_id=teacher["id"], legacy_teacher_id=self.legacy_teacher_id,
                           subject=subject, start=start, end=end)
        scope = scope_id(teacher["id"], sid, subject, start, end)
        saved = [b["payload"] for b in bundles if b["category"] in ("drafts", "school_records", "analyses")
                 and b["payload"].get("scope_id") == scope and b["payload"].get("teacher_id") == teacher["id"]]
        if not any(p.get("kind") in ("working_draft", "final") for p in saved):
            for bundle in bundles:
                if bundle.get("payload", {}).get("table") == "records":
                    for row in bundle["payload"].get("rows", []):
                        if (row.get("student_id") == str(sid) and row.get("subject") == subject
                            and row.get("period") == f"{start}~{end}" and (row.get("author_id") or self.legacy_teacher_id) == teacher["id"]):
                            saved.append({"kind":"working_draft", "scope_id":scope, "teacher_id":teacher["id"], "text":row.get("text", ""),
                                          "saved_at":row.get("updated_at", ""), "reviews":[], "legacy_review_required":True})
        data = {"teacher_id":teacher["id"], "student_id":str(sid), "subject":subject, "start":str(start), "end":str(end),
                "scope_id":scope, "evidence":evidence, "saved":saved, "loaded_at":utcnow()}
        return self._seal(data)

    def _item(self, workspace, eid):
        data = self.validate(workspace)
        item = next((e for e in data["evidence"] if e["id"] == eid), None)
        if not item:
            raise ArchiveError("불러온 자료 목록에서 근거를 찾지 못했습니다.")
        return item

    def file(self, workspace, eid, index):
        data = self.validate(workspace)
        item = self._item(workspace, eid)
        if type(index) is not int or not 0 <= index < len(item["attachments"]):
            raise ArchiveError("선택한 첨부파일이 없습니다.")
        desc = item["attachments"][index]
        return self.backend.archive_load_attachment(data["student_id"], desc)

    def prepare(self, workspace, selections):
        data = self.validate(workspace)
        if not 1 <= len(selections) <= 5:
            raise ArchiveError("파일 1~5개를 선택하세요.")
        files, links = [], []
        for selection in selections:
            item = self._item(workspace, selection["evidence_id"])
            if not item["eligible"]:
                raise ArchiveError("이 자료는 AI 파일 분석 대상이 아닙니다.")
            index = selection["index"]
            original = self.file(workspace, item["id"], index)
            desc = item["attachments"][index]
            replacement = selection.get("replacement")
            raw = replacement["data"] if replacement is not None else original
            name = replacement["name"] if replacement is not None else desc["name"]
            file_id = "F" + fingerprint([item["id"], desc["sha256"]])[:16]
            f = prepare_file(raw, name, item["id"], file_id, selection.get("pages", ""), replacement is not None)
            links.append({"file_id":file_id, "evidence_id":item["id"], "source_sha256":desc["sha256"],
                          "evidence_hash":item["evidence_hash"]})
            files.append(f)
        # Bytes remain on this authenticated server session; signature covers hashes.
        signed = {"scope_id":data["scope_id"], "teacher_id":data["teacher_id"], "manifest":public_manifest(files), "links":links}
        return {"files":files, "data":signed, "signature":self._sign(signed)}

    def analyze(self, workspace, prepared, ai, *, consent):
        data = self.validate(workspace)
        signed = prepared.get("data", {})
        if not hmac.compare_digest(str(prepared.get("signature", "")), self._sign(signed)) or signed.get("scope_id") != data["scope_id"]:
            raise ArchiveError("전송용 파일 선택이 다른 학생 또는 작성 기간의 자료입니다.")
        for f in prepared.get("files", []):
            item = self._item(workspace, f["evidence_id"])
            link = next((l for l in signed["links"] if l["file_id"] == f["file_id"]), None)
            if not link or link["evidence_hash"] != item["evidence_hash"] or hashlib.sha256(f["data"]).hexdigest() != f["sha256"]:
                raise ArchiveError("전송용 파일이 변경되었습니다. 다시 준비하세요.")
        if public_manifest(prepared["files"]) != signed.get("manifest"):
            raise ArchiveError("전송 파일 목록이 변경되었습니다.")
        report = ai.analyze(prepared["files"], consent=consent)
        self.actor()  # Permission could have changed while the API was running.
        run_id = uuid.uuid4().hex
        payload = {k:data[k] for k in ("scope_id", "teacher_id", "student_id", "subject", "start", "end")}
        payload.update(kind="file_analysis", report=report, consent_at=utcnow(), saved_at=utcnow(), id=run_id)
        # Keep exact transmitted copies locally encrypted for an audit, never provider URLs.
        assets = [{"id":f["file_id"], "data":f["data"], "name":f["name"], "mime":f["mime"]} for f in prepared["files"]]
        self.backend.queue_archive(data["student_id"], "analyses", run_id, payload, assets)
        try:
            self.backend.flush()
        except Exception:
            # Caller can keep report in-memory; a failed archive isn't a second API call.
            error = ArchiveError("AI 분석은 끝났으나 GitHub 저장 확인에 실패했습니다. '저장 재시도'를 사용하세요. AI 분석 버튼을 다시 누를 필요가 없습니다.")
            error.completed_report = report
            raise error from None
        return report

    def identities(self):
        self.actor()
        return [v for user in self.backend.read("users") for v in (user.get("id", ""), user.get("name", "")) if v]

    def draft(self, workspace, reviews, ai, *, consent, target_chars=400):
        data = self.validate(workspace)
        facts = validate_reviews(data["evidence"], reviews, data["subject"])
        result = ai.draft(data["subject"], facts, self.identities(), target_chars, consent=consent)
        self.actor()
        result["evidence_hashes"] = {r["evidence_id"]:r["evidence_hash"] for r in reviews}
        return result

    def input_preview(self, workspace, reviews, target_chars=400):
        data = self.validate(workspace)
        facts = validate_reviews(data["evidence"], reviews, data["subject"])
        return draft_input(data["subject"], facts, self.identities(), target_chars)

    def save(self, workspace, reviews, text, ai_draft=None, analyses=None, *, final=False, confirmed=False, review_note="", byte_limit=1500):
        data = self.validate(workspace)
        if final:
            facts = validate_reviews(data["evidence"], reviews, data["subject"]) if reviews else []
        else:
            # Drafts retain unconfirmed notes; they are never passed to AI as facts.
            known = {e["id"]:e for e in data["evidence"]}
            for review in reviews:
                if review.get("evidence_id") not in known or review.get("evidence_hash") != known[review["evidence_id"]]["evidence_hash"]:
                    raise ArchiveError("작성 중 근거가 변경되었습니다. 원본을 다시 확인하세요.")
            approved = [r for r in reviews if r.get("context") == "정규 교과수업" and r.get("teacher_confirmed") and len(str(r.get("fact", "")).strip()) >= 5]
            facts = validate_reviews(data["evidence"], approved, data["subject"]) if approved else []
        if final:
            if not facts:
                raise ArchiveError("최종 문장에는 교사가 확인한 근거가 필요합니다.")
            check_final(text, (ai_draft or {}).get("text", ""), confirmed=confirmed, review_note=review_note, byte_limit=byte_limit)
            if ai_draft and ai_draft.get("evidence_hashes") != {r["evidence_id"]:r["evidence_hash"] for r in reviews}:
                raise ArchiveError("초안 작성 후 근거 선택이 바뀌었습니다. 새 근거로 초안을 다시 작성하거나 직접 작성 모드로 전환하세요.")
            # A new submission/grading between review and finalization requires review again.
            self.backend.flush()
            fresh = self.load(data["student_id"], data["subject"], data["start"], data["end"])
            validate_reviews(fresh["data"]["evidence"], reviews, data["subject"])
        payload = {k:data[k] for k in ("scope_id", "teacher_id", "student_id", "subject", "start", "end")}
        payload.update(kind="final" if final else "working_draft", text=str(text), reviews=copy.deepcopy(reviews),
                       ai_draft=copy.deepcopy(ai_draft), analyses=copy.deepcopy(analyses or []), sources=copy.deepcopy(facts),
                       source_manifest=[{"evidence_id":r["evidence_id"], "hash":r["evidence_hash"]} for r in reviews],
                       review_note=str(review_note), teacher_confirmed=bool(confirmed), saved_at=utcnow())
        self.backend.queue_archive(data["student_id"], "drafts", data["scope_id"], payload)
        if final:
            self.backend.queue_archive(data["student_id"], "school_records", data["scope_id"], payload)
            # Preserve the existing class export view, with explicit teacher ownership.
            rows = self.backend.read("records")
            period = f"{data['start']}~{data['end']}"
            old = next((r for r in rows if r.get("student_id") == data["student_id"] and r.get("subject") == data["subject"]
                        and r.get("period") == period and (r.get("author_id") or self.legacy_teacher_id) == data["teacher_id"]), None)
            student = self.student(data["student_id"])
            fields = {"updated_at":utcnow(), "text":str(text), "sources":json.dumps({"kind":"teacher_confirmed", "scope_id":data["scope_id"], "manifest":payload["source_manifest"]}, ensure_ascii=False),
                      "author_id":data["teacher_id"], "period":period, "subject":data["subject"], "student_id":data["student_id"],
                      "name":student.get("name", ""), "class":student.get("class", "")}
            if old:
                self.backend.update("records", old["id"], fields)
            else:
                self.backend.append("records", dict(fields, id=uuid.uuid4().hex))
        self.backend.flush()
        return payload
