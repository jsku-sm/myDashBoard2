from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    data_dir: str = ".think_data"
    repo: str = "jsku-sm/class-dashboard-data"
    branch: str = "main"
    github_token: str = field(default="", repr=False)
    encryption_key: str = field(default="", repr=False)
    teacher_id: str = "teacher"
    teacher_password: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    model: str = "gpt-4.1-mini"
    transcription_model: str = "gpt-4o-mini-transcribe"
    ai_enabled: bool = False
    desmos_api_key: str = field(default="", repr=False)


def load_settings():
    import streamlit as st
    try:
        values = dict(st.secrets)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        values = {}
    def get(k, default=""):
        return os.environ.get(k, values.get(k, default))
    return Settings(
        mode=str(get("THINK_MODE", "demo")).lower(),
        data_dir=str(get("THINK_DATA_DIR", str(Path(__file__).resolve().parent.parent / ".think_data"))),
        repo=str(get("GITHUB_REPO", "jsku-sm/class-dashboard-data")), branch=str(get("GITHUB_BRANCH", "main")),
        github_token=str(get("GITHUB_TOKEN")), encryption_key=str(get("ENCRYPTION_KEY")),
        teacher_id=str(get("THINK_TEACHER_ID", "teacher")),
        teacher_password=str(get("THINK_TEACHER_PASSWORD")),
        api_key=str(get("OPENAI_API_KEY")), model=str(get("OPENAI_MODEL", "gpt-4.1-mini")),
        transcription_model=str(get("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")),
        ai_enabled=str(get("AI_ENABLED", "false")).lower() == "true",
        desmos_api_key=str(get("DESMOS_API_KEY")),
    )
