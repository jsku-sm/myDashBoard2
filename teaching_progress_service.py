"""Teacher-owned lesson progress and performance-assessment planning.

Shares the existing local/GitHub backend; never modifies quizzes, scores or
legacy classroom data. Optimistic versions + one-server backend.lock prevent
lost edits on this app server, not edits by independent deployments.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime
from typing import Any

import streamlit as st
import storage as db
from config import CLASSES, SUBJECTS

TABLE = "teaching_progress"
LESSON_STATUSES = ("예정", "진행 중", "완료", "휴강")
ASSESSMENT_STATUSES = ("예정", "완료", "취소")
PERIODS = ("미정",) + tuple(f"{i}교시" for i in range(1, 9)) + ("방과후",)
FIELDS = ("date", "subject", "period", "content", "status", "assessment_title",
          "assessment_date", "assessment_period", "assessment_status", "memo")
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


class ConflictError(ValueError):
    pass


class SavePendingError(RuntimeError):
    def __init__(self, ids: list[str]):
        self.ids = list(ids)
        super().__init__("서버에는 변경이 반영되었지만 GitHub 영구 저장은 확인되지 않았어요. "
                         "입력을 반복 등록하지 말고 ‘저장 다시 확인’을 눌러 주세요. "
                         "자동 저장도 재시도하므로 화면을 닫아도 요청이 취소되는 것은 아닙니다.")


def require_teacher(user: dict, backend=None) -> dict:
    session = st.session_state.get("user")
    if (not isinstance(user, dict) or not isinstance(session, dict)
            or not user.get("id") or session.get("id") != user["id"]
            or user.get("role") != "teacher" or session.get("role") != "teacher"):
        raise PermissionError("진도관리는 로그인한 교사만 이용할 수 있어요.")
    backend = backend or db._ready_backend()
    current = next((u for u in backend.read("users") if u.get("id") == user["id"]), None)
    if not current or current.get("role") != "teacher" or current.get("must_change") == "1":
        raise PermissionError("현재 교사 권한을 확인하지 못했어요. 다시 로그인해 주세요.")
    return current


def _text(value: Any, label: str, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} 형식을 확인해 주세요.")
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(f"{label}은(는) {'1~' if required else ''}{limit:,}자 이내로 입력해 주세요.")
    if "\x00" in value:
        raise ValueError(f"{label}에 사용할 수 없는 문자가 있어요.")
    return value


def _date(value: Any, label: str, required: bool = True) -> str:
    if value in ("", None):
        if required:
            raise ValueError(f"{label}을(를) 선택해 주세요.")
        return ""
    if isinstance(value, datetime):
        raise ValueError(f"{label}은(는) 시각이 아닌 날짜로 입력해 주세요.")
    if isinstance(value, date):
        value = value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label}은(는) YYYY-MM-DD 형식이어야 해요.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}에 실제로 있는 날짜를 선택해 주세요.") from None
    if not 2000 <= parsed.year <= 2100:
        raise ValueError(f"{label}은(는) 2000~2100년 범위로 선택해 주세요.")
    return value


def normalize(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("기록할 내용을 확인해 주세요.")
    row = {k: payload.get(k, "") for k in FIELDS}
    row["date"] = _date(row["date"], "수업·기록일")
    row["subject"] = _text(row["subject"], "과목", 80, True)
    if row["subject"] not in SUBJECTS:
        raise ValueError("설정된 과목을 선택해 주세요.")
    row["period"] = _text(row["period"] or "미정", "수업 교시", 20)
    row["status"] = _text(row["status"] or "예정", "수업 상태", 20)
    if row["period"] not in PERIODS or row["status"] not in LESSON_STATUSES:
        raise ValueError("수업 교시와 진행 상태를 확인해 주세요.")
    row["content"] = _text(row["content"], "수업내용", 4000)
    row["memo"] = _text(row["memo"], "메모", 4000)
    row["assessment_title"] = _text(row["assessment_title"], "수행평가명", 300)
    row["assessment_date"] = _date(row["assessment_date"], "수행평가일", False)
    if not row["content"] and not row["assessment_title"]:
        raise ValueError("수업내용 또는 수행평가명을 하나 이상 입력해 주세요.")
    if not row["assessment_title"]:
        if row["assessment_date"]:
            raise ValueError("수행평가일을 입력했다면 수행평가명도 입력해 주세요.")
        row.update(assessment_period="", assessment_status="")
    else:
        row["assessment_period"] = _text(row["assessment_period"] or "미정", "평가 교시", 20)
        row["assessment_status"] = _text(row["assessment_status"] or "예정", "평가 상태", 20)
        if row["assessment_period"] not in PERIODS or row["assessment_status"] not in ASSESSMENT_STATUSES:
            raise ValueError("수행평가 교시와 상태를 확인해 주세요.")
        if row["assessment_status"] == "완료" and not row["assessment_date"]:
            raise ValueError("수행평가를 완료로 표시하려면 실제 평가일을 입력해 주세요.")
        if row["assessment_status"] == "완료" and row["assessment_date"] > db.today_str():
            raise ValueError("미래 수행평가를 완료로 기록할 수 없어요.")
    if not row["content"]:
        # An assessment-only entry does not count as completed lesson progress.
        row["status"] = "예정"
    elif row["status"] == "완료" and row["date"] > db.today_str():
        raise ValueError("미래 수업을 완료로 기록할 수 없어요. 실제 수업일을 확인해 주세요.")
    return row


def _owned(backend, uid: str, row_id: str, include_deleted: bool = False) -> dict:
    row = next((r for r in backend.read(TABLE) if r.get("id") == row_id and r.get("author_id") == uid), None)
    # Same error for missing and another teacher's ID; don't reveal existence.
    if row is None or (row.get("deleted_at") and not include_deleted):
        raise PermissionError("열 수 있는 기록이 없어요. 본인의 기록인지 확인해 주세요.")
    return dict(row)


def _version(row: dict, expected: str):
    if not isinstance(expected, str) or not expected or row.get("revision") != expected:
        raise ConflictError("다른 창에서 이 기록을 먼저 수정했어요. 입력한 내용을 복사해 둔 뒤 "
                            "‘최신 기록 다시 불러오기’로 확인해 주세요. 기존 기록은 덮어쓰지 않았습니다.")


def _persist(ids: list[str]) -> list[str]:
    db.invalidate(TABLE)
    # Never flush under backend.lock: the background writer acquires locks in
    # the opposite order. A failed flush is queued, NOT falsely called success.
    try:
        db.flush_now()
    except Exception:
        raise SavePendingError(ids) from None
    return ids


def list_records(user: dict, include_deleted: bool = False) -> list[dict]:
    backend = db._ready_backend()
    with backend.lock:
        actor = require_teacher(user, backend)
        rows = [dict(r) for r in backend.read(TABLE) if r.get("author_id") == actor["id"]
                and (include_deleted or not r.get("deleted_at"))]
    return sorted(rows, key=lambda r: (r["date"], r["class"], period_order(r.get("period", "")), r["id"]))


def get_record(user: dict, row_id: str, include_deleted: bool = False) -> dict:
    backend = db._ready_backend()
    with backend.lock:
        actor = require_teacher(user, backend)
        return _owned(backend, actor["id"], row_id, include_deleted)


def create_records(user: dict, classes: list[str], payload: dict, request_id: str) -> list[str]:
    backend = db._ready_backend()
    require_teacher(user, backend)
    if (not isinstance(classes, (list, tuple)) or not classes
            or any(not isinstance(c, str) or c not in CLASSES for c in classes)):
        raise ValueError("1-1반~1-7반에서 대상 학급을 하나 이상 선택해 주세요.")
    classes = list(dict.fromkeys(classes))
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", request_id):
        raise ValueError("저장 요청 번호를 확인하지 못했어요. 화면을 새로 열어 주세요.")
    content = normalize(payload)
    now = db.now_str()
    with backend.lock:
        actor = require_teacher(user, backend)
        existing = {r["id"]: r for r in backend.read(TABLE)}
        batch_rows = [r for r in existing.values() if r.get("author_id") == actor["id"]
                      and r.get("batch_id") == request_id]
        if batch_rows and {r["class"] for r in batch_rows} != set(classes):
            raise ConflictError("이미 처리한 등록 요청의 학급을 바꿀 수 없어요. 기존 기록을 확인해 주세요.")
        ids, additions = [], []
        for cls in classes:
            identity = json.dumps([actor["id"], request_id, cls], ensure_ascii=False)
            row_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
            ids.append(row_id)
            candidate = dict(content, id=row_id, author_id=actor["id"], batch_id=request_id,
                             created_at=now, updated_at=now, revision="1", **{"class": cls}, deleted_at="")
            if row_id in existing:
                old = existing[row_id]
                if old.get("deleted_at") or any(old.get(k) != candidate[k] for k in (*FIELDS, "class", "author_id")):
                    raise ConflictError("같은 저장 요청이 이미 처리됐고 내용이 달라요. 새 등록 대신 기존 기록을 확인해 주세요.")
            else:
                additions.append(candidate)
        if additions:
            backend.append_many(TABLE, additions)
    return _persist(ids)


def update_record(user: dict, row_id: str, payload: dict, cls: str, expected_revision: str) -> str:
    backend = db._ready_backend()
    require_teacher(user, backend)
    if cls not in CLASSES:
        raise ValueError("학급을 확인해 주세요.")
    content = normalize(payload)
    with backend.lock:
        actor = require_teacher(user, backend)
        old = _owned(backend, actor["id"], row_id)
        _version(old, expected_revision)
        changes = dict(content, **{"class": cls})
        if any(old.get(k) != v for k, v in changes.items()):
            changes.update(updated_at=db.now_str(), revision=str(int(old["revision"]) + 1))
            if not backend.update(TABLE, row_id, changes):
                raise ConflictError("기록을 저장하지 못했어요. 최신 상태를 다시 확인해 주세요.")
    _persist([row_id])
    return row_id


def set_completed(user: dict, row_id: str, expected_revision: str) -> str:
    old = get_record(user, row_id)
    if not old.get("content"):
        raise ValueError("수행평가 일정만 있는 기록은 수업 완료로 처리하지 않아요.")
    return update_record(user, row_id, dict(old, status="완료"), old["class"], expected_revision)


def _trash(user: dict, row_id: str, expected_revision: str, restore: bool):
    backend = db._ready_backend()
    with backend.lock:
        actor = require_teacher(user, backend)
        row = _owned(backend, actor["id"], row_id, include_deleted=True)
        _version(row, expected_revision)
        if bool(row.get("deleted_at")) == restore:
            backend.update(TABLE, row_id, {"deleted_at": "" if restore else db.now_str(),
                           "updated_at": db.now_str(), "revision": str(int(row["revision"]) + 1)})
    _persist([row_id])


def delete_record(user: dict, row_id: str, expected_revision: str):
    """Soft delete. Existing Git history and quizzes remain untouched."""
    _trash(user, row_id, expected_revision, False)


def restore_record(user: dict, row_id: str, expected_revision: str):
    _trash(user, row_id, expected_revision, True)


def retry_save(user: dict):
    require_teacher(user)
    _persist([])


def pending_save(user: dict) -> bool:
    backend = db._ready_backend()
    require_teacher(user, backend)
    if getattr(backend, "is_local", True):
        return False
    with backend.lock:
        return "data/teaching_progress.csv" in getattr(backend, "dirty", {})


def period_order(period: str) -> int:
    return PERIODS.index(period) if period in PERIODS else 0


def filter_records(rows: list[dict], start: str, end: str, cls: str = "전체",
                   subject: str = "전체", mode: str = "lesson", keyword: str = "",
                   include_undated: bool = True) -> list[dict]:
    start, end = _date(start, "시작일"), _date(end, "종료일")
    if start > end:
        raise ValueError("시작일은 종료일보다 늦을 수 없어요.")
    if mode not in ("lesson", "assessment"):
        raise ValueError("조회 기준을 확인해 주세요.")
    key = "date" if mode == "lesson" else "assessment_date"
    selected = []
    for r in rows:
        if r.get("deleted_at") or (cls != "전체" and r["class"] != cls) or (subject != "전체" and r["subject"] != subject):
            continue
        if mode == "assessment" and not r.get("assessment_title"):
            continue
        day = r.get(key, "")
        if not (start <= day <= end) and not (mode == "assessment" and not day and include_undated):
            continue
        text = " ".join(r.get(k, "") for k in ("content", "assessment_title", "memo"))
        if keyword.strip().casefold() not in text.casefold():
            continue
        selected.append(dict(r))
    return sorted(selected, key=lambda r: (r.get(key) or "9999-12-31", r["class"],
                   period_order(r.get("period" if mode == "lesson" else "assessment_period", "")), r["id"]))


def summaries(rows: list[dict], today: str, subject: str = "전체") -> list[dict]:
    today = _date(today, "기준일")
    result = []
    for cls in CLASSES:
        own = [r for r in rows if not r.get("deleted_at") and r["class"] == cls
               and (subject == "전체" or r["subject"] == subject)]
        lessons = [r for r in own if r.get("content")]
        done = sorted([r for r in lessons if r["status"] == "완료" and r["date"] <= today],
                      key=lambda r: (r["date"], period_order(r["period"]), r["id"]))
        upcoming = sorted([r for r in lessons if r["status"] in ("예정", "진행 중") and r["date"] >= today],
                          key=lambda r: (r["date"], period_order(r["period"]), r["id"]))
        assessments = sorted([r for r in own if r.get("assessment_title") and r.get("assessment_status") == "예정"
                              and r.get("assessment_date") and r["assessment_date"] >= today],
                             key=lambda r: (r["assessment_date"], period_order(r["assessment_period"]), r["id"]))
        result.append({"class": cls, "completed": len(done), "total": len(lessons),
                       "last": done[-1] if done else None, "next": upcoming[0] if upcoming else None,
                       "assessment": assessments[0] if assessments else None,
                       "undated": sum(bool(r.get("assessment_title")) and not r.get("assessment_date")
                                      and r.get("assessment_status") == "예정" for r in own),
                       "overdue": sum(r["status"] in ("예정", "진행 중") and r["date"] < today for r in lessons)})
    return result


def display_rows(rows: list[dict], mode: str = "lesson") -> list[dict]:
    result = []
    for r in rows:
        weekday = WEEKDAYS[date.fromisoformat(r["date"]).weekday()]
        if mode == "assessment":
            result.append({"수행평가일": r["assessment_date"] or "날짜 미정", "학급": r["class"], "과목": r["subject"],
                           "평가 교시": r["assessment_period"], "수행평가": r["assessment_title"],
                           "평가 상태": r["assessment_status"], "연결 수업일": r["date"], "수업내용": r["content"], "메모": r["memo"]})
        else:
            result.append({"날짜": r["date"], "요일": weekday, "학급": r["class"], "과목": r["subject"], "교시": r["period"],
                           "수업내용": r["content"] or "(수행평가 일정만 기록)", "진행 상태": r["status"] if r["content"] else "일정만",
                           "수행평가": r["assessment_title"], "수행평가일": r["assessment_date"] or ("날짜 미정" if r["assessment_title"] else ""),
                           "평가 교시": r["assessment_period"], "평가 상태": r["assessment_status"], "메모": r["memo"]})
    return result


def export_csv(user: dict, start: str, end: str, cls: str = "전체", subject: str = "전체",
               mode: str = "lesson", keyword: str = "", include_undated: bool = True) -> bytes:
    rows = filter_records(list_records(user), start, end, cls, subject, mode, keyword, include_undated)
    display = display_rows(rows, mode)
    # Headers remain even when the filtered view is empty.
    fields = (["수행평가일", "학급", "과목", "평가 교시", "수행평가", "평가 상태", "연결 수업일", "수업내용", "메모"]
              if mode == "assessment" else ["날짜", "요일", "학급", "과목", "교시", "수업내용", "진행 상태", "수행평가", "수행평가일", "평가 교시", "평가 상태", "메모"])
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    def safe(v):
        s = str(v)
        return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) or s.startswith(("\t", "\r", "\n")) else s
    writer.writerows({k: safe(v) for k, v in row.items()} for row in display)
    return buf.getvalue().encode("utf-8-sig")
