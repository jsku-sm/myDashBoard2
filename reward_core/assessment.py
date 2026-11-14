# GOOD_RECORDS_1.1_FINAL5
"""Mirror persisted assessment writes into the SAME private student vault.

Original assessment keys/storage are preserved. A failure after source commit is
reported explicitly; the teacher can retry '기존 자료 동기화'. No silent fallback.
"""
from __future__ import annotations
import copy
import hashlib
import mimetypes
from .archive import ArchiveError


def bind(store, backend):
    if getattr(backend, "is_local", True):
        raise ArchiveError("수행평가와 학생 자료함은 같은 GitHub 비공개 저장소에 연결해야 합니다.")
    if store.repo.casefold() != backend.repo.casefold() or store.branch != backend.branch:
        raise ArchiveError("수행평가와 대시보드 저장소가 다릅니다. 둘 다 jsku-sm/class-dashboard-data와 같은 브랜치를 지정하세요. 기존 자료는 자동 이동하지 않습니다.")
    store._student_archive_backend = backend


def _assets(store, item, kind):
    files = {}
    def add(ref, name, mime):
        if ref and ref not in files:
            raw = store.get_blob(ref)
            # Older normalized images can be JPEG even when the UI called them PNG.
            if raw.startswith(b"\xff\xd8\xff"):
                mime="image/jpeg"
                if name.startswith("손글씨풀이_"):
                    name=name.rsplit(".",1)[0]+".jpg"
            elif raw.startswith(b"\x89PNG\r\n\x1a\n"):
                mime="image/png"
            elif raw.startswith(b"%PDF-"):
                mime="application/pdf"
            files[ref] = {"id": ref, "data": raw, "name": name, "mime": mime}
    if kind == "upload":
        add(item.get("original_ref"), item.get("filename", "원본첨부"), item.get("original_mime", item.get("mime", "application/octet-stream")))
        add(item.get("blob_ref"), item.get("filename", "정규화첨부"), item.get("mime", "image/png"))
    else:
        for n, ref in enumerate(item.get("images", []), 1):
            add(ref, f"손글씨풀이_{n}.png", "image/png")
        add(item.get("audio"), "학생설명.wav", "audio/wav")
        for n, document in enumerate(item.get("documents", []), 1):
            add(document.get("original_ref"), document.get("filename", f"첨부_{n}.pdf"), document.get("original_mime", "application/pdf"))
            add(document.get("blob_ref"), document.get("filename", f"첨부_{n}.pdf"), document.get("mime", "application/pdf"))
    return list(files.values())


def sync_state(store, backend, state, previous=None, student_id=None):
    count = 0
    for table in ("course_attempts", "attempts", "course_uploads"):
        values = state.get(table, {})
        old = (previous or {}).get(table, {})
        for rid, item in values.items():
            sid = str(item.get("student_id", "")).strip()
            if not sid or item.get("preview") or (student_id is not None and sid != str(student_id)):
                continue
            if previous is not None and item == old.get(rid):
                continue
            kind = "upload" if table == "course_uploads" else "attempt"
            task = copy.deepcopy(item.get("activity_snapshot") or state.get("course_activities", {}).get(item.get("activity_id"), {}) or state.get("activities", {}).get(item.get("activity_id"), {}))
            cid = item.get("course_id") or task.get("course_id")
            course = copy.deepcopy(state.get("courses", {}).get(cid, {}))
            payload = {"source_table": table, "item": copy.deepcopy(item), "activity": task, "course": course,
                       "source_saved": True, "deleted": False}
            backend.queue_archive(sid, "uploads" if kind == "upload" else "assessments", table + ":" + str(rid),
                                  payload, _assets(store, item, kind))
            count += 1
        if previous is not None:
            for rid, item in old.items():
                sid = str(item.get("student_id", ""))
                if rid not in values and sid and not item.get("preview"):
                    backend.queue_archive(sid, "uploads" if table == "course_uploads" else "assessments", table + ":" + str(rid),
                                          {"source_table": table, "item": copy.deepcopy(item), "deleted": True})
                    count += 1
    return count


def after_commit(store, previous, state):
    backend = getattr(store, "_student_archive_backend", None)
    if backend is None:
        return  # standalone tests/app: embedding explicitly binds the shared vault
    try:
        sync_state(store, backend, state, None if getattr(store, "_archive_retry", False) else previous)
        backend.flush()
        store._archive_retry = False
    except Exception:
        store._archive_retry = True
        from think_app.storage import AppError
        raise AppError("수행평가 원본은 저장되었으나 학생별 자료함 저장 확인에 실패했습니다. 자료를 지우지 말고 생기부생성기의 '기존 자료 동기화'로 재시도하세요.") from None
