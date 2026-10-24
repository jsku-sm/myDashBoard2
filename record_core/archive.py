# GOOD_RECORDS_1.1_FINAL5
"""Encrypted, pseudonymous student archives; no Streamlit or AI side effects.

The existing private source stores are retained for compatibility. The vault is
an additional versioned copy, not a claim that legacy CSV/Git history is erased.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken

EXPECTED_REPO = "jsku-sm/class-dashboard-data"
SENTINEL = "student-vault-v1/key-check.enc"
TABLE_CATEGORIES = {
    "sudanotes": "sudanotes", "submissions": "submissions", "questions": "questions",
    "observations": "observations", "points": "points", "quiz_attempts": "quizzes",
    "game_profiles": "games", "records": "school_records",
}
CATEGORIES = set(TABLE_CATEGORIES.values()) | {"assessments", "uploads", "analyses", "reviews", "drafts"}

class ArchiveError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def encryption_key(values):
    """Never create a key silently and never store a key in the repository."""
    for section, field in (("student_archive", "encryption_key"), (None, "ENCRYPTION_KEY"), ("snorkl", "encryption_key")):
        group = values if section is None else values.get(section, {})
        if isinstance(group, dict) and str(group.get(field, "")).strip():
            return str(group[field]).strip()
    raise ArchiveError("학생별 자료함 암호화키가 없습니다. Secrets의 [student_archive] encryption_key에 Fernet 키를 넣으세요. 기존 수행평가 키는 변경하지 마세요.")

class ArchiveCrypto:
    def __init__(self, key):
        try:
            self.key = key.encode("ascii")
            self.cipher = Fernet(self.key)
        except (ValueError, TypeError, AttributeError, UnicodeError):
            raise ArchiveError("학생별 자료함 암호화키 형식이 올바르지 않습니다. 임의 비밀번호가 아닌 Fernet 키를 사용하세요.") from None

    def student_dir(self, sid):
        sid = str(sid).strip()
        if not sid or len(sid) > 200:
            raise ArchiveError("학생 식별자를 확인하세요.")
        opaque = hmac.new(self.key, ("student-vault-v1:" + sid).encode(), hashlib.sha256).hexdigest()
        return "students/" + opaque

    def encrypt(self, payload):
        return self.cipher.encrypt(canonical(payload)).decode("ascii")

    def decrypt(self, data):
        try:
            result = json.loads(self.cipher.decrypt(data.encode() if isinstance(data, str) else data))
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            raise ArchiveError("학생 자료를 복호화하지 못했습니다. 최초 자료함 암호화키를 유지하세요. 기존 파일을 덮어쓰지 않습니다.") from None
        if not isinstance(result, dict):
            raise ArchiveError("학생 자료함의 파일 형식이 올바르지 않습니다.")
        return result

    def sentinel(self):
        return self.encrypt({"format": "student-vault-v1", "key_check": "student-evidence"})

    def verify_sentinel(self, raw):
        if self.decrypt(raw) != {"format": "student-vault-v1", "key_check": "student-evidence"}:
            raise ArchiveError("학생 자료함 확인 파일이 올바르지 않습니다.")

    def bundle(self, sid, category, logical_id, payload, attachments=()):
        if category not in CATEGORIES:
            raise ArchiveError("허용되지 않은 학생 자료 종류입니다.")
        directory = self.student_dir(sid)
        item = hashlib.sha256(str(logical_id).encode()).hexdigest()
        entries, descriptions = {}, []
        for attachment in attachments:
            raw = attachment["data"]
            if not isinstance(raw, bytes) or not raw:
                raise ArchiveError("보관할 첨부파일이 비어 있습니다.")
            digest = hashlib.sha256(raw).hexdigest()
            path = directory + "/attachments/" + digest + ".bin.enc"
            entries[path] = self.cipher.encrypt(raw).decode("ascii")
            descriptions.append({"id": str(attachment.get("id", digest)), "path": path,
                "sha256": digest, "bytes": len(raw), "name": str(attachment.get("name", "첨부파일")),
                "mime": str(attachment.get("mime", "application/octet-stream"))})
        stable = {"format": "student-evidence-v1", "student_id": str(sid), "category": category,
                  "logical_id": str(logical_id), "payload": copy.deepcopy(payload), "attachments": descriptions}
        version = fingerprint(stable)
        envelope = dict(stable, version=version, archived_at=utcnow())
        encrypted = self.encrypt(envelope)
        current = f"{directory}/{category}/{item}/current.json.enc"
        entries[current] = encrypted
        entries[f"{directory}/{category}/{item}/history/{version}.json.enc"] = encrypted
        return entries, envelope

    def open_bundle(self, raw, sid, path=None):
        result = self.decrypt(raw)
        if result.get("format") != "student-evidence-v1" or result.get("student_id") != str(sid):
            raise ArchiveError("다른 학생의 자료 또는 지원하지 않는 형식입니다.")
        root = self.student_dir(sid) + "/"
        if path is not None and (not path.startswith(root) or ".." in path.split("/")):
            raise ArchiveError("학생 자료 경로가 올바르지 않습니다.")
        for file in result.get("attachments", []):
            if not re.fullmatch(re.escape(root) + r"attachments/[a-f0-9]{64}\.bin\.enc", str(file.get("path", ""))):
                raise ArchiveError("첨부파일이 선택한 학생의 자료함에 속하지 않습니다.")
        return result

    def open_attachment(self, raw, description, sid):
        prefix = self.student_dir(sid) + "/attachments/"
        if not re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}\.bin\.enc", description.get("path", "")):
            raise ArchiveError("다른 학생의 첨부파일은 열 수 없습니다.")
        try:
            content = self.cipher.decrypt(raw)
        except InvalidToken:
            raise ArchiveError("첨부파일 암호화키를 확인하세요.") from None
        if hashlib.sha256(content).hexdigest() != description.get("sha256") or len(content) != description.get("bytes"):
            raise ArchiveError("첨부파일 무결성 검사를 통과하지 못했습니다.")
        return content


def table_bundle(crypto, table, sid, rows, all_tables, load_file):
    """Snapshot the complete saved table for one student, including empty deletes."""
    if table not in TABLE_CATEGORIES:
        raise ArchiveError("지원하지 않는 학생 표입니다.")
    mine = [copy.deepcopy(r) for r in rows if str(r.get("student_id")) == str(sid)]
    user = next((r for r in all_tables.get("users", []) if str(r.get("id")) == str(sid)), {})
    payload = {"table": table, "identity": {k: user.get(k, "") for k in ("id", "name", "class")}, "rows": mine}
    if table == "quiz_attempts":
        ids = {r.get("quiz_id") for r in mine}
        payload["quiz_sets"] = [copy.deepcopy(r) for r in all_tables.get("quiz_sets", []) if r.get("id") in ids]
    attachments = []
    seen = set()
    for row in mine:
        fid = row.get("file_id")
        if fid and fid not in seen:
            data = load_file(fid)
            if data is None:
                raise ArchiveError("학생 제출 첨부파일을 읽지 못해 자료함 저장을 보류했습니다. 원본을 유지하고 재시도하세요.")
            seen.add(fid)
            attachments.append({"id": fid, "data": data, "name": row.get("file_name", "첨부파일"), "mime": row.get("mime", "")})
    return crypto.bundle(sid, TABLE_CATEGORIES[table], "table:" + table, payload, attachments)
