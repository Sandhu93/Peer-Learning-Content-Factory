"""
Application configuration — loaded once at startup from environment variables.

Usage:
    from src.config import settings
    print(settings.repo_path)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ── Paths ─────────────────────────────────────────────────────────────────
    repo_path: Path = Path(".")
    output_path: Path = _PROJECT_ROOT / "output" / "teaching_guides"
    concepts_file: Path = _PROJECT_ROOT / "peer_learning_concepts.md"

    # ── Model names ───────────────────────────────────────────────────────────
    default_writer_model: str = "claude-sonnet-4-6"
    default_research_model: str = "claude-sonnet-4-6"
    default_openai_model: str = "gpt-4o"

    # ── Pipeline behaviour ────────────────────────────────────────────────────
    batch_size: int = 3
    max_revisions: int = 2

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("repo_path", mode="before")
    @classmethod
    def validate_repo_path(cls, v: str | Path) -> Path:
        p = Path(v)
        if not p.exists():
            raise ValueError(f"REPO_PATH does not exist: {p}")
        return p

    @field_validator("output_path", mode="before")
    @classmethod
    def ensure_output_path(cls, v: str | Path) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


def _load_settings() -> Settings:
    """Load and validate settings, raising clear errors on misconfiguration."""
    try:
        s = Settings()
    except Exception as exc:
        raise RuntimeError(f"Configuration error: {exc}") from exc

    if not s.anthropic_configured:
        raise RuntimeError("ANTHROPIC_API_KEY is required but not set.")

    return s


# Module-level singleton — imported everywhere as `from src.config import settings`
settings: Settings = _load_settings()
