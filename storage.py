"""데이터 저장소.

- GoogleBackend : 구글 시트(표 데이터) + 구글 드라이브(파일)  ← 실제 배포용
- LocalBackend  : data/ 폴더의 CSV + 파일  ← 내 컴퓨터에서 시험해 볼 때

secrets 에 [app] storage = "google" 이 있으면 구글을, 없으면 로컬을 씁니다.
모든 값은 문자열로 저장합니다(학번 앞의 0 이 사라지지 않도록).
"""
from __future__ import annotations

import csv
import io
import os
import threading
import time
import uuid
from datetime import datetime

import streamlit as st

from config import TZ

SCHEMAS: dict[str, list[str]] = {
    "users": ["id", "name", "class", "role", "pw_hash", "must_change", "created_at"],
    "settings": ["id", "value"],
    "logins": ["id", "created_at", "date", "student_id", "name", "class"],
    "emotions": ["id", "created_at", "date", "student_id", "name", "class", "emotion"],
    "materials": ["id", "uploaded_at", "subject", "category", "unit", "title", "description",
                  "file_id", "file_name", "file_url", "mime"],
    "submissions": ["id", "created_at", "subject", "class", "student_id", "name", "unit", "title",
                    "content", "file_id", "file_name", "file_url", "mime", "feedback", "teacher_comment"],
    "questions": ["id", "created_at", "subject", "class", "student_id", "name", "anonymous", "unit",
                  "title", "content", "answer", "answered_at"],
    "observations": ["id", "created_at", "class", "student_id", "name", "category", "content"],
    "points": ["id", "created_at", "class", "student_id", "name", "kind", "score", "reason"],
}

CACHE_TTL = {"users": 60, "settings": 60}
DEFAULT_TTL = 20


def now() -> datetime:
    return datetime.now(TZ)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def new_id() -> str:
    return now().strftime("%y%m%d%H%M%S") + uuid.uuid4().hex[:6]


def _norm(row: dict, table: str) -> dict:
    return {c: "" if row.get(c) is None else str(row.get(c)) for c in SCHEMAS[table]}


# ---------------------------------------------------------------- 로컬 ---
class LocalBackend:
    is_local = True
    label = "로컬 파일 (시험용)"

    def __init__(self, root: str = "data"):
        self.root = root
        self.files_dir = os.path.join(root, "files")
        os.makedirs(self.files_dir, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, table):
        return os.path.join(self.root, f"{table}.csv")

    def read(self, table):
        with self.lock:
            p = self._path(table)
            if not os.path.exists(p):
                return []
            with open(p, newline="", encoding="utf-8") as f:
                return [_norm(r, table) for r in csv.DictReader(f)]

    def _write_all(self, table, rows):
        p = self._path(table)
        tmp = p + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SCHEMAS[table])
            w.writeheader()
            for r in rows:
                w.writerow(_norm(r, table))
        os.replace(tmp, p)

    def append(self, table, row):
        with self.lock:
            rows = self.read(table)
            rows.append(row)
            self._write_all(table, rows)

    def append_many(self, table, new_rows):
        with self.lock:
            rows = self.read(table)
            rows.extend(new_rows)
            self._write_all(table, rows)

    def update(self, table, row_id, changes):
        with self.lock:
            rows = self.read(table)
            hit = False
            for r in rows:
                if r["id"] == row_id:
                    r.update({k: str(v) for k, v in changes.items()})
                    hit = True
            if hit:
                self._write_all(table, rows)
            return hit

    def delete(self, table, row_id):
        with self.lock:
            rows = self.read(table)
            self._write_all(table, [r for r in rows if r["id"] != row_id])

    # 파일
    def save_file(self, data: bytes, filename: str, mime: str, public: bool):
        fid = new_id()
        safe = "".join(ch for ch in filename if ch not in '\\/:*?"<>|')
        with open(os.path.join(self.files_dir, f"{fid}__{safe}"), "wb") as f:
            f.write(data)
        return fid, ""

    def _find(self, file_id):
        for name in os.listdir(self.files_dir):
            if name.startswith(file_id + "__"):
                return os.path.join(self.files_dir, name)
        return None

    def load_file(self, file_id) -> bytes | None:
        p = self._find(file_id)
        if not p:
            return None
        with open(p, "rb") as f:
            return f.read()

    def delete_file(self, file_id):
        p = self._find(file_id)
        if p:
            os.remove(p)


# ---------------------------------------------------------------- 구글 ---
class GoogleBackend:
    is_local = False
    label = "구글 시트 + 구글 드라이브"

    def __init__(self, secrets):
        import gspread
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials as UserCredentials
        from googleapiclient.discovery import build

        app = secrets["app"]
        sa_info = dict(secrets["gcp_service_account"])
        sa_creds = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"],
        )
        self.lock = threading.RLock()
        self.gc = gspread.authorize(sa_creds)
        self.sh = self.gc.open_by_key(app["spreadsheet_id"])
        self._ws = {}

        # 드라이브: 개인 지메일은 OAuth(교사 본인 계정), 학교 공유드라이브는 서비스 계정
        if "gdrive_oauth" in secrets:
            o = secrets["gdrive_oauth"]
            drive_creds = UserCredentials(
                None,
                refresh_token=o["refresh_token"],
                client_id=o["client_id"],
                client_secret=o["client_secret"],
                token_uri="https://oauth2.googleapis.com/token",
                scopes=["https://www.googleapis.com/auth/drive.file"],
            )
        else:
            drive_creds = sa_creds
        self.drive = build("drive", "v3", credentials=drive_creds, cache_discovery=False)
        self.folder_id = app.get("drive_folder_id", "") or ""

    def _sheet(self, table):
        if table in self._ws:
            return self._ws[table]
        import gspread
        try:
            ws = self.sh.worksheet(table)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=table, rows=200, cols=len(SCHEMAS[table]))
            ws.update(range_name="A1", values=[SCHEMAS[table]], value_input_option="RAW")
        header = ws.row_values(1)
        if header != SCHEMAS[table]:
            ws.update(range_name="A1", values=[SCHEMAS[table]], value_input_option="RAW")
        self._ws[table] = ws
        return ws

    def read(self, table):
        with self.lock:
            values = self._sheet(table).get_all_values()
        if not values:
            return []
        header = values[0]
        out = []
        for v in values[1:]:
            if not any(v):
                continue
            out.append(_norm(dict(zip(header, v)), table))
        return out

    def append(self, table, row):
        self.append_many(table, [row])

    def append_many(self, table, rows):
        data = [[_norm(r, table)[c] for c in SCHEMAS[table]] for r in rows]
        with self.lock:
            self._sheet(table).append_rows(data, value_input_option="RAW",
                                           insert_data_option="INSERT_ROWS")

    def _row_index(self, ws, row_id):
        ids = ws.col_values(1)
        try:
            return ids.index(row_id) + 1
        except ValueError:
            return None

    def update(self, table, row_id, changes):
        with self.lock:
            ws = self._sheet(table)
            idx = self._row_index(ws, row_id)
            if not idx:
                return False
            cur = ws.row_values(idx)
            cur += [""] * (len(SCHEMAS[table]) - len(cur))
            row = dict(zip(SCHEMAS[table], cur))
            row.update({k: str(v) for k, v in changes.items()})
            ws.update(range_name=f"A{idx}", values=[[row[c] for c in SCHEMAS[table]]],
                      value_input_option="RAW")
            return True

    def delete(self, table, row_id):
        with self.lock:
            ws = self._sheet(table)
            idx = self._row_index(ws, row_id)
            if idx and idx > 1:
                ws.delete_rows(idx)

    # 파일
    def _folder(self):
        if self.folder_id:
            return self.folder_id
        # 폴더 id 가 없으면 앱이 직접 폴더를 만들고 settings 에 기억
        for r in self.read("settings"):
            if r["id"] == "drive_folder_id" and r["value"]:
                self.folder_id = r["value"]
                return self.folder_id
        meta = {"name": "수업대시보드_파일", "mimeType": "application/vnd.google-apps.folder"}
        f = self.drive.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
        self.folder_id = f["id"]
        self.append("settings", {"id": "drive_folder_id", "value": self.folder_id})
        return self.folder_id

    def save_file(self, data: bytes, filename: str, mime: str, public: bool):
        from googleapiclient.http import MediaIoBaseUpload
        with self.lock:
            media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime or "application/octet-stream",
                                      resumable=len(data) > 5 * 1024 * 1024)
            f = self.drive.files().create(
                body={"name": filename, "parents": [self._folder()]},
                media_body=media, fields="id", supportsAllDrives=True,
            ).execute()
            fid = f["id"]
            url = ""
            if public:
                try:
                    self.drive.permissions().create(
                        fileId=fid, body={"type": "anyone", "role": "reader"},
                        supportsAllDrives=True).execute()
                    url = f"https://drive.google.com/uc?export=download&id={fid}"
                except Exception:
                    url = ""  # 학교 도메인 정책으로 공개 공유가 막힌 경우 → 앱을 통해 내려받기
            return fid, url

    def load_file(self, file_id) -> bytes | None:
        from googleapiclient.http import MediaIoBaseDownload
        with self.lock:
            req = self.drive.files().get_media(fileId=file_id, supportsAllDrives=True)
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()

    def delete_file(self, file_id):
        with self.lock:
            try:
                self.drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            except Exception:
                pass


# ------------------------------------------------------- 공용 접근 함수 ---
@st.cache_resource(show_spinner=False)
def get_backend():
    try:
        secrets = st.secrets
        use_google = "app" in secrets and secrets["app"].get("storage", "local") == "google"
    except Exception:
        secrets, use_google = None, False
    if use_google:
        return GoogleBackend(secrets)
    return LocalBackend()


@st.cache_resource(show_spinner=False)
def _cache():
    # 모든 접속자가 함께 쓰는 읽기 캐시 → 구글 API 호출 횟수를 크게 줄임
    return {"data": {}, "lock": threading.Lock()}


def read(table: str) -> list[dict]:
    c = _cache()
    ttl = CACHE_TTL.get(table, DEFAULT_TTL)
    with c["lock"]:
        hit = c["data"].get(table)
        if hit and time.time() - hit[0] < ttl:
            return [dict(r) for r in hit[1]]
    rows = get_backend().read(table)
    with c["lock"]:
        c["data"][table] = (time.time(), rows)
    return [dict(r) for r in rows]


def invalidate(table: str):
    c = _cache()
    with c["lock"]:
        c["data"].pop(table, None)


def append(table: str, row: dict):
    row = dict(row)
    row.setdefault("id", new_id())
    get_backend().append(table, row)
    invalidate(table)
    return row["id"]


def append_many(table: str, rows: list[dict]):
    if rows:
        get_backend().append_many(table, rows)
        invalidate(table)


def update(table: str, row_id: str, changes: dict):
    ok = get_backend().update(table, row_id, changes)
    invalidate(table)
    return ok


def delete(table: str, row_id: str):
    get_backend().delete(table, row_id)
    invalidate(table)


# 설정값
def get_setting(key: str) -> str:
    from config import DEFAULT_SETTINGS
    for r in read("settings"):
        if r["id"] == key:
            return r["value"]
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str):
    if not update("settings", key, {"value": value}):
        append("settings", {"id": key, "value": value})


# 파일
def save_upload(uploaded, public: bool):
    data = uploaded.getvalue()
    return get_backend().save_file(data, uploaded.name, uploaded.type or "", public)


@st.cache_data(ttl=600, max_entries=30, show_spinner="파일을 불러오는 중...")
def load_file_cached(file_id: str):
    return get_backend().load_file(file_id)


def delete_file(file_id: str):
    if file_id:
        get_backend().delete_file(file_id)
