"""Teacher-only text edits for existing common-math-2 evaluation plans.

Uses the existing materials CSV and current GitHub/local backend; no migration,
new credentials, separate DB, PDF edits or attachment replacement.
"""
from __future__ import annotations

import hashlib
import json

import streamlit as st
import storage as db

SUBJECT = "공통수학2"
CATEGORY = "평가계획"
MAX_TITLE = 200
MAX_DESCRIPTION = 30_000


class PlanConflictError(ValueError):
    """Someone edited/deleted/replaced this material while the form was open."""


class PlanSavePendingError(RuntimeError):
    """The existing backend has queued the update but remote flush failed."""

    def __init__(self, revision: str):
        self.revision = revision
        super().__init__("변경 내용은 서버의 저장 대기에 반영됐지만 GitHub 저장은 아직 확인되지 않았어요. "
                         "앱을 종료하지 말고 연결을 확인한 뒤 ‘저장’을 다시 눌러 주세요. "
                         "기존 자동 저장도 재시도하므로 취소 버튼이 저장 대기를 되돌리지는 않습니다.")


def revision_of(row: dict) -> str:
    """Compare all existing material fields, including its attachment identity."""
    raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _teacher(user: dict, backend=None) -> dict:
    session_user = st.session_state.get("user")
    if (not isinstance(user, dict) or not isinstance(session_user, dict)
            or not user.get("id") or session_user.get("id") != user.get("id")
            or session_user.get("role") != "teacher" or user.get("role") != "teacher"):
        raise PermissionError("로그인한 교사만 평가계획을 수정할 수 있어요.")
    backend = backend or db._ready_backend()
    # Do not trust the supplied role or a stale cached copy of the account.
    current = next((u for u in backend.read("users") if u.get("id") == user["id"]), None)
    if not current or current.get("role") != "teacher" or current.get("must_change") == "1":
        raise PermissionError("교사 권한과 비밀번호 변경 여부를 확인한 뒤 다시 로그인해 주세요.")
    return current


def can_manage(user: dict) -> bool:
    try:
        _teacher(user)
        return True
    except PermissionError:
        return False


def _find(backend, material_id: str) -> dict:
    if not isinstance(material_id, str) or not material_id:
        raise ValueError("평가계획을 선택해 주세요.")
    row = next((m for m in backend.read("materials") if m.get("id") == material_id), None)
    if row is None:
        raise PlanConflictError("평가계획이 삭제되었거나 목록이 변경됐어요. 새로고침 후 확인해 주세요.")
    if row.get("subject") != SUBJECT or row.get("category") != CATEGORY:
        raise PermissionError("이 기능은 공통수학2의 평가계획 텍스트만 수정합니다.")
    return row


def get_plan(user: dict, material_id: str) -> dict:
    backend = db._ready_backend()
    with backend.lock:
        _teacher(user, backend)
        return dict(_find(backend, material_id))


def _check_revision(row: dict, expected_revision: str):
    if not isinstance(expected_revision, str) or expected_revision != revision_of(row):
        raise PlanConflictError("다른 화면에서 이 평가계획을 먼저 변경했어요. 입력 내용은 유지됩니다. "
                                "필요한 내용을 복사한 뒤 수정 취소 → 수정으로 최신 원문을 다시 열어 주세요.")


def update_plan_text(user: dict, material_id: str, title: str, description: str,
                     expected_revision: str) -> dict:
    """Only title and description change; all file and original-date fields stay.

    Serialises the compare/update using this backend's shared lock. The existing
    store is single-server buffered storage, not a cross-server transaction DB.
    Flush runs OUTSIDE backend.lock to avoid a lock-order deadlock with its
    background writer. A queued/failed flush is never reported as durable success.
    """
    backend = db._ready_backend()
    _teacher(user, backend)
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE:
        raise ValueError(f"제목을 1~{MAX_TITLE}자로 입력해 주세요.")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION:
        raise ValueError(f"평가계획 설명은 {MAX_DESCRIPTION:,}자 이내로 입력해 주세요.")
    # Preserve description verbatim, including line breaks and blank lines.
    changes = {"title": title.strip(), "description": description}
    with backend.lock:
        _teacher(user, backend)
        row = _find(backend, material_id)
        _check_revision(row, expected_revision)
        if row["title"] != changes["title"] or row["description"] != changes["description"]:
            if not backend.update("materials", material_id, changes):
                raise PlanConflictError("저장하기 전에 평가계획이 삭제됐어요. 목록을 다시 확인해 주세요.")
        result = dict(_find(backend, material_id))
    db.invalidate("materials")
    try:
        db.flush_now()
    except Exception:
        # Raw upstream errors might contain private repo names/tokens. Do not
        # put them on a student-facing page or into an unfiltered error log.
        raise PlanSavePendingError(revision_of(result)) from None
    return result


def delete_plan(user: dict, material_id: str, expected_revision: str):
    """Retain the original delete feature with fresh teacher/record validation."""
    backend = db._ready_backend()
    with backend.lock:
        _teacher(user, backend)
        row = _find(backend, material_id)
        _check_revision(row, expected_revision)
        file_id = row.get("file_id", "")
        still_used = any(m.get("id") != material_id and m.get("file_id") == file_id
                         for m in backend.read("materials"))
        # The old implementation also deleted the attached file. Do not delete
        # a file referenced by another material in the same table.
        if file_id and not still_used:
            backend.delete_file(file_id)
        backend.delete("materials", material_id)
    db.invalidate("materials")
    try:
        db.flush_now()
    except Exception:
        raise PlanSavePendingError("") from None


def pending_material_save() -> bool:
    """True for the existing GitHub backend's uncommitted materials CSV."""
    backend = db._ready_backend()
    if getattr(backend, "is_local", True):
        return False
    with backend.lock:
        return bool(getattr(backend, "dirty", {}).get("data/materials.csv"))
