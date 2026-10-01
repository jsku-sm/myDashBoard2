"""데이터 저장소.

- GitHubBackend : 별도의 비공개 깃허브 저장소  ← 실제 배포용
- LocalBackend  : data/ 폴더의 CSV + 파일      ← 내 컴퓨터에서 시험해 볼 때

secrets 에 [app] storage = "github" 이 있으면 깃허브를, 없으면 로컬을 씁니다.
모든 값은 문자열로 저장합니다(학번 앞의 0 이 사라지지 않도록).
"""
from __future__ import annotations

import base64
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


# -------------------------------------------------------------- 깃허브 ---
class SetupError(Exception):
    """설정이 잘못되었을 때 화면에 보여 줄 오류."""


PARTITIONED = {"logins", "emotions"}  # 매일 쌓이는 표는 월별 파일로 나눠 저장
FLUSH_SEC = 8


class GitHubBackend:
    """별도의 '비공개' 깃허브 저장소에 데이터를 저장합니다.

    - 표 데이터: data/<표>.csv  (logins, emotions 는 data/<표>/<YYYY-MM>.csv)
    - 업로드 파일: files/<YYYY-MM>/<이름>
    읽기는 서버 메모리에서 바로 하고, 변경 사항은 8초마다 모아서 커밋 1개로 저장합니다.
    (학생 30명이 동시에 저장해도 커밋은 하나라서 빠르고 충돌이 없습니다)
    """
    is_local = False
    API = "https://api.github.com"

    def __init__(self, cfg):
        import atexit
        import requests

        self.repo = cfg.get("repo", "").strip()
        self.branch = cfg.get("branch", "main") or "main"
        self.API = cfg.get("api_url", self.API)  # 보통은 적지 않음 (GitHub Enterprise 등)
        token = cfg.get("token", "").strip()
        if not self.repo or "/" not in self.repo or not token:
            raise SetupError("secrets 의 [github] 에 token 과 repo(\"아이디/저장소이름\")를 모두 적어 주세요.")
        self.label = f"깃허브 비공개 저장소 ({self.repo})"
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.lock = threading.RLock()
        self.flush_lock = threading.Lock()
        self.rows = {t: [] for t in SCHEMAS}
        self.dirty: dict[str, int] = {}
        self.pending_files: list[tuple[str, str | None]] = []
        self.ver = 0
        self.last_saved = ""
        self.last_error = ""

        self._check_repo()
        self._load_all()
        threading.Thread(target=self._loop, daemon=True).start()
        atexit.register(self.flush)

    # 기본 요청
    def _req(self, method, path, **kw):
        r = self.s.request(method, self.API + path, timeout=40, **kw)
        return r

    def _check_repo(self):
        try:
            r = self._req("GET", f"/repos/{self.repo}")
        except Exception as e:
            raise SetupError(f"깃허브에 연결하지 못했어요: {e}")
        if r.status_code == 401:
            raise SetupError("깃허브 토큰이 올바르지 않거나 만료되었어요. 새 토큰을 만들어 secrets 에 넣어 주세요.")
        if r.status_code == 404:
            raise SetupError(f"'{self.repo}' 저장소를 찾을 수 없어요. 저장소 이름과, 토큰에 이 저장소 권한을 줬는지 확인해 주세요.")
        if r.status_code != 200:
            raise SetupError(f"깃허브 응답 오류 ({r.status_code}): {r.text[:200]}")
        if not r.json().get("private", False):
            raise SetupError(
                f"'{self.repo}' 저장소가 공개(Public) 상태예요. 학생 정보가 노출되지 않도록 "
                "저장소 Settings 에서 비공개(Private)로 바꾼 뒤 앱을 다시 시작해 주세요."
            )

    def _head(self):
        r = self._req("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
        if r.status_code == 200:
            return r.json()["object"]["sha"]
        # 빈 저장소면 첫 파일을 만들어 초기화
        body = {"message": "init", "branch": self.branch,
                "content": base64.b64encode("# 수업 대시보드 데이터 (앱이 자동으로 저장)\n".encode()).decode()}
        r2 = self._req("PUT", f"/repos/{self.repo}/contents/README.md", json=body)
        if r2.status_code not in (200, 201):
            if r2.status_code in (403, 404):
                raise SetupError("토큰에 저장소 '쓰기' 권한이 없어요. 토큰의 Contents 권한을 'Read and write'로 설정해 주세요.")
            raise SetupError(f"저장소를 초기화하지 못했어요 ({r2.status_code}): {r2.text[:200]}")
        r = self._req("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
        r.raise_for_status()
        return r.json()["object"]["sha"]

    def _blob(self, sha) -> bytes:
        r = self._req("GET", f"/repos/{self.repo}/git/blobs/{sha}")
        r.raise_for_status()
        return base64.b64decode(r.json()["content"])

    def _load_all(self):
        head = self._head()
        r = self._req("GET", f"/repos/{self.repo}/git/trees/{head}", params={"recursive": "1"})
        r.raise_for_status()
        for e in sorted(r.json().get("tree", []), key=lambda e: e["path"]):
            p = e["path"]
            if e["type"] != "blob" or not p.startswith("data/") or not p.endswith(".csv"):
                continue
            parts = p[5:-4].split("/")
            table = parts[0]
            if table not in SCHEMAS:
                continue
            text = self._blob(e["sha"]).decode("utf-8-sig")
            self.rows[table].extend(_norm(row, table) for row in csv.DictReader(io.StringIO(text)))

    @staticmethod
    def _path(table, row):
        if table in PARTITIONED:
            month = (row.get("date") or row.get("created_at") or "")[:7] or "unknown"
            return f"data/{table}/{month}.csv"
        return f"data/{table}.csv"

    def _mark(self, table, rows):
        self.ver += 1
        for r in rows:
            self.dirty[self._path(table, r)] = self.ver

    # 표 데이터
    def read(self, table):
        with self.lock:
            return [dict(r) for r in self.rows[table]]

    def append(self, table, row):
        self.append_many(table, [row])

    def append_many(self, table, rows):
        rows = [_norm(r, table) for r in rows]
        with self.lock:
            self.rows[table].extend(rows)
            self._mark(table, rows)

    def update(self, table, row_id, changes):
        with self.lock:
            hit = [r for r in self.rows[table] if r["id"] == row_id]
            for r in hit:
                r.update({k: str(v) for k, v in changes.items()})
            if hit:
                self._mark(table, hit)
            return bool(hit)

    def delete(self, table, row_id):
        with self.lock:
            gone = [r for r in self.rows[table] if r["id"] == row_id]
            self.rows[table] = [r for r in self.rows[table] if r["id"] != row_id]
            self._mark(table, gone)

    # 파일
    def save_file(self, data: bytes, filename: str, mime: str, public: bool):
        r = self._req("POST", f"/repos/{self.repo}/git/blobs",
                      json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"파일을 깃허브에 저장하지 못했어요 ({r.status_code})")
        sha = r.json()["sha"]
        safe = "".join(ch for ch in filename if ch not in '\\/:*?"<>|#').strip() or "file"
        path = f"files/{today_str()[:7]}/{sha[:10]}_{safe}"
        with self.lock:
            self.pending_files.append((path, sha))
            self.ver += 1
        return f"{sha}:{path}", ""

    def load_file(self, file_id) -> bytes | None:
        try:
            return self._blob(file_id.split(":", 1)[0])
        except Exception:
            return None

    def delete_file(self, file_id):
        if ":" not in file_id:
            return
        sha, path = file_id.split(":", 1)
        with self.lock:
            if (path, sha) in self.pending_files:
                self.pending_files.remove((path, sha))  # 아직 커밋 전이면 목록에서만 빼기
            else:
                self.pending_files.append((path, None))
                self.ver += 1

    # 저장(커밋)
    def _csv(self, path):
        table = path[5:-4].split("/")[0]
        rows = [r for r in self.rows[table] if self._path(table, r) == path]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=SCHEMAS[table])
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def pending_count(self):
        with self.lock:
            return len(self.dirty) + len(self.pending_files)

    def flush(self):
        with self.flush_lock:
            with self.lock:
                if not self.dirty and not self.pending_files:
                    return
                versions = dict(self.dirty)
                entries = [{"path": p, "mode": "100644", "type": "blob", "content": self._csv(p)}
                           for p in versions]
                files = list(self.pending_files)
            entries += [{"path": p, "mode": "100644", "type": "blob", "sha": sha} for p, sha in files]
            for attempt in range(4):
                head = self._head()
                c = self._req("GET", f"/repos/{self.repo}/git/commits/{head}")
                c.raise_for_status()
                t = self._req("POST", f"/repos/{self.repo}/git/trees",
                              json={"base_tree": c.json()["tree"]["sha"], "tree": entries})
                t.raise_for_status()
                nc = self._req("POST", f"/repos/{self.repo}/git/commits",
                               json={"message": f"자동 저장 {now_str()}", "tree": t.json()["sha"],
                                     "parents": [head]})
                nc.raise_for_status()
                u = self._req("PATCH", f"/repos/{self.repo}/git/refs/heads/{self.branch}",
                              json={"sha": nc.json()["sha"], "force": False})
                if u.status_code == 200:
                    break
                time.sleep(1 + attempt)
            else:
                raise RuntimeError(f"깃허브 저장 충돌이 계속돼요 ({u.status_code})")
            with self.lock:
                for p, v in versions.items():
                    if self.dirty.get(p) == v:
                        del self.dirty[p]
                self.pending_files = [f for f in self.pending_files if f not in files]
            self.last_saved = now_str()
            self.last_error = ""

    def _loop(self):
        while True:
            time.sleep(FLUSH_SEC)
            try:
                self.flush()
            except Exception as e:  # 다음 주기에 다시 시도
                self.last_error = f"{now_str()} {e}"


# ------------------------------------------------------- 공용 접근 함수 ---
@st.cache_resource(show_spinner="저장소에 연결하는 중...")
def get_backend():
    try:
        secrets = st.secrets
        mode = secrets["app"].get("storage", "local") if "app" in secrets else "local"
    except Exception:
        secrets, mode = None, "local"
    if mode == "github":
        if "github" not in secrets:
            raise SetupError("secrets 에 [github] 부분(token, repo)이 없어요.")
        return GitHubBackend(dict(secrets["github"]))
    return LocalBackend()


def backend_status() -> str:
    b = get_backend()
    if b.is_local:
        return "로컬 시험 모드 (서버가 재시작되면 데이터가 사라져요)"
    msg = f"{b.label}"
    n = b.pending_count()
    msg += f" · 저장 대기 {n}건" if n else " · 모두 저장됨"
    if b.last_error:
        msg += f"\n⚠️ 마지막 저장 오류: {b.last_error[:150]}"
    return msg


def flush_now():
    b = get_backend()
    if hasattr(b, "flush"):
        b.flush()


@st.cache_resource(show_spinner=False)
def _cache():
    # 모든 접속자가 함께 쓰는 읽기 캐시 → 저장소 접근 횟수를 줄임
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
MAX_UPLOAD_MB = 10


def save_upload(uploaded, public: bool):
    data = uploaded.getvalue()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"파일이 너무 커요. {MAX_UPLOAD_MB}MB 이하만 올릴 수 있어요.")
    return get_backend().save_file(data, uploaded.name, uploaded.type or "", public)


@st.cache_data(ttl=600, max_entries=12, show_spinner="파일을 불러오는 중...")
def load_file_cached(file_id: str):
    return get_backend().load_file(file_id)


def delete_file(file_id: str):
    if file_id:
        get_backend().delete_file(file_id)
