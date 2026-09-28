"""Runtime settings (env / .env) and YAML config loading."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    config_dir: Path = ROOT_DIR / "config"
    data_dir: Path = ROOT_DIR / "data"
    database_url: str = ""

    # Security
    fernet_key: str = ""
    app_password: str = ""  # set on any deployed instance: enables the login screen
    session_secret: str = ""
    session_days: int = 30

    # LLM (Groq)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    llm_daily_cap: int = 300
    llm_min_interval_seconds: float = 2.5

    # Google OAuth (Gmail)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_client_secrets_file: str = ""
    oauth_redirect_uri: str = "http://localhost:8765/api/gmail/auth/callback"
    frontend_url: str = "http://localhost:5173"

    # Job API keys
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""
    careerjet_affid: str = ""

    # Runtime
    scheduler_enabled: bool = True
    timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_backend: str = "sentence-transformers"  # or "hashing" (no torch; used by the public demo)

    # Public showcase: fictional data, no Gmail, no live API calls, uploads disabled
    demo_mode: bool = False
    static_dir: str = ""  # serve the built frontend from the API process (single-service deploys)
    gmail_address: str = ""  # overrides gmail.address in profile.yaml (keeps it out of the repo)
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'remotehunt.db'}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def _load_yaml(name: str) -> dict[str, Any]:
    path = get_settings().config_dir / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_profile() -> dict[str, Any]:
    """User preferences. Re-read each call so edits apply without restart."""
    data = _load_yaml("profile.yaml")
    data.setdefault("candidate", {})
    data.setdefault("search", {})
    data.setdefault("matching", {})
    data.setdefault("gmail", {})
    if get_settings().gmail_address:
        data["gmail"]["address"] = get_settings().gmail_address
    return data


def load_sources_config() -> dict[str, Any]:
    data = _load_yaml("sources.yaml")
    data.setdefault("defaults", {})
    data.setdefault("sources", {})
    return data


def load_target_companies() -> dict[str, list[dict[str, str]]]:
    return _load_yaml("target_companies.yaml")


def env_flag(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}
