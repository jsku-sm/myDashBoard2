"""Dashboard integration settings and access checks (no Streamlit UI side effects)."""
from collections.abc import Mapping
from pathlib import Path
import os
import re
from urllib.parse import urlencode, urlsplit, urlunsplit

from .config import Settings
from .storage import AppError


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def resolve_settings(values=None, environ=None):
    """Support [snorkl], standalone keys and the dashboard connection groups.

    Dedicated [snorkl] values take precedence. The embedded assessment uses
    persistent storage, including older explicit demo configurations. Dashboard
    CSV records are not migrated, read as Snorkl records, or changed here.
    """
    values = _mapping(values)
    group = _mapping(values.get("snorkl"))
    github = _mapping(values.get("github"))
    shared_openai = _mapping(values.get("openai"))
    # The record generator can use a custom API provider. Its credentials must
    # not be reused by the assessment client's official OpenAI endpoint.
    if str(shared_openai.get("base_url", "https://api.openai.com/v1")).strip().rstrip("/") != "https://api.openai.com/v1":
        shared_openai = {}
    shared_model = str(shared_openai.get("model", "")).strip() or "gpt-4.1-mini"
    environ = os.environ if environ is None else environ

    def pick(field, legacy, default=""):
        if field in group:
            return group[field]
        if legacy in group:
            return group[legacy]
        if legacy in environ:
            return environ[legacy]
        return values.get(legacy, default)

    def flag(field, legacy, default=False):
        value = pick(field, legacy, default)
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "1", "yes", "on"):
            return True
        if str(value).strip().lower() in ("false", "0", "no", "off", ""):
            return False
        raise AppError(f"[snorkl] {field} 값은 true 또는 false로 설정하세요.")

    repo = str(pick("github_repo", "GITHUB_REPO", github.get("repo", ""))).strip()
    token = str(pick("github_token", "GITHUB_TOKEN", github.get("token", ""))).strip()
    encryption_key = str(pick("encryption_key", "ENCRYPTION_KEY", "")).strip()
    persistent_mode = "github" if repo and token else "local"
    missing_mode = object()
    configured_mode = pick("mode", "THINK_MODE", missing_mode)
    if configured_mode is missing_mode:
        mode = persistent_mode
    else:
        mode = str(configured_mode).strip().lower()
        if mode not in ("demo", "local", "github"):
            raise AppError('[snorkl] mode는 "demo", "local", "github" 중 하나로 설정하세요.')
        if mode == "demo":
            mode = persistent_mode
    return Settings(
        mode=mode,
        data_dir=str(pick("data_dir", "THINK_DATA_DIR", str(Path(__file__).resolve().parent.parent / ".think_data"))),
        repo=repo,
        branch=str(pick("github_branch", "GITHUB_BRANCH", github.get("branch", "main"))).strip(),
        github_token=token,
        encryption_key=encryption_key,
        api_key=str(pick("openai_api_key", "OPENAI_API_KEY", shared_openai.get("api_key", ""))).strip(),
        model=str(pick("openai_model", "OPENAI_MODEL", shared_model)).strip(),
        transcription_model=str(pick("transcription_model", "TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")).strip(),
        ai_enabled=flag("ai_enabled", "AI_ENABLED"),
        desmos_api_key=str(pick("desmos_api_key", "DESMOS_API_KEY", "")).strip(),
    )


def load_embedded_settings():
    import streamlit as st
    try:
        values = st.secrets.to_dict()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        values = {}
    return resolve_settings(values)


def matching_class(user, course):
    """Map grade 1 dashboard classes to legacy Snorkl names; never match grade 2."""
    if user.get("role") != "student":
        return None
    own_class = str(user.get("class", "")).strip()
    allowed = course.get("classes", [])
    if not own_class:
        return None
    if own_class in allowed:
        return own_class
    match = re.fullmatch(r"1-([1-7])", own_class)
    legacy = f"{match.group(1)}반" if match else None
    return legacy if legacy and legacy in allowed else None


def student_identity(user, course):
    """Identity comes only from the authenticated dashboard account, not widgets."""
    classroom = matching_class(user, course)
    student_id = str(user.get("id", "")).strip()
    name = str(user.get("name", "")).strip()
    if not classroom or not student_id or not name:
        raise AppError("이 수업에 참여할 권한이 없습니다. 등록된 학번·이름·반을 선생님께 확인하세요.")
    return student_id, name, classroom


def visible_courses(user, courses):
    return [course for course in courses if matching_class(user, course) is not None]


def course_url(current_url, course_id):
    parts = urlsplit(current_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise AppError("현재 앱 주소를 확인할 수 없습니다. 배포된 앱에서 공유 주소를 확인하세요.")
    if not re.fullmatch(r"[a-f0-9]{32}", str(course_id)):
        raise AppError("수업 식별자를 확인하세요.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode({"tool": "snorkl", "course_id": course_id}), ""))
