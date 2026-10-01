"""로그인/비밀번호 관련 기능. 비밀번호는 원문이 아니라 해시로만 저장합니다."""
import hashlib
import hmac
import os

import streamlit as st

import storage as db

DEFAULT_TEACHER_ID = "teacher"
DEFAULT_TEACHER_PW = "teacher1234"


def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120_000)
    return f"{salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$")
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def initial_password(student_id: str) -> str:
    """학생 초기 비밀번호 규칙: 학번 그대로. 첫 로그인 때 반드시 바꾸게 합니다."""
    return str(student_id)


def _teacher_secret():
    try:
        app = st.secrets["app"]
        return app.get("teacher_id", DEFAULT_TEACHER_ID), app.get("teacher_password", DEFAULT_TEACHER_PW)
    except Exception:
        return DEFAULT_TEACHER_ID, DEFAULT_TEACHER_PW


def ensure_teacher():
    """교사 계정이 하나도 없으면 secrets 의 아이디/비밀번호로 만듭니다."""
    if st.session_state.get("_teacher_ok"):
        return
    users = db.read("users")
    if not any(u["role"] == "teacher" for u in users):
        tid, tpw = _teacher_secret()
        db.append("users", {
            "id": tid, "name": "선생님", "class": "", "role": "teacher",
            "pw_hash": hash_pw(tpw), "must_change": "1" if tpw == DEFAULT_TEACHER_PW else "0",
            "created_at": db.now_str(),
        })
    st.session_state["_teacher_ok"] = True


def get_user(uid: str):
    for u in db.read("users"):
        if u["id"] == uid:
            return u
    return None


def students(cls: str | None = None):
    rows = [u for u in db.read("users") if u["role"] == "student"]
    if cls and cls != "전체":
        rows = [u for u in rows if u["class"] == cls]
    return sorted(rows, key=lambda u: (u["class"], u["id"]))


def login(uid: str, pw: str):
    db.invalidate("users")  # 방금 바뀐 비밀번호도 바로 반영
    u = get_user(uid.strip())
    if u and check_pw(pw, u["pw_hash"]):
        return u
    return None


def change_password(uid: str, new_pw: str):
    db.update("users", uid, {"pw_hash": hash_pw(new_pw), "must_change": "0"})


def reset_password(uid: str):
    db.update("users", uid, {"pw_hash": hash_pw(initial_password(uid)), "must_change": "1"})


def add_students(rows: list[dict], overwrite: bool):
    """rows: [{'id','name','class', 'pw'(선택)}] → (추가 수, 갱신 수, 건너뜀 수)"""
    existing = {u["id"]: u for u in db.read("users")}
    new_rows, updated, skipped = [], 0, 0
    for r in rows:
        sid = str(r["id"]).strip()
        if not sid:
            continue
        if sid in existing:
            if existing[sid]["role"] == "teacher":
                skipped += 1
                continue
            if overwrite:
                db.update("users", sid, {"name": r["name"], "class": r["class"]})
                updated += 1
            else:
                skipped += 1
            continue
        pw = str(r.get("pw") or "").strip() or initial_password(sid)
        new_rows.append({
            "id": sid, "name": r["name"].strip(), "class": r["class"].strip(), "role": "student",
            "pw_hash": hash_pw(pw), "must_change": "1", "created_at": db.now_str(),
        })
        existing[sid] = new_rows[-1]
    db.append_many("users", new_rows)
    return len(new_rows), updated, skipped
