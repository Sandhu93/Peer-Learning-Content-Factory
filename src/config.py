"""
Application configuration — loaded once at startup from environment variables.

Usage:
    from src.config import settings
    print(settings.repo_path)          # may be None if REPO_PATH not set
    print(settings.effective_repo_path(override))  # resolves with fallback

Design note — REPO_PATH is intentionally optional at startup:
    The repo to analyse is a per-run input, not a global constant. It can come from:
      1. REPO_PATH in .env       — default for CLI usage
      2. --repo CLI flag         — overrides .env for a single run
      3. API request body        — when a frontend is added

    This means config.py never crashes on a missing REPO_PATH.
    Validation happens at the point of use (run_single_concept), where the
    resolved path is checked for existence before the graph starts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

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
    # Optional — validated at runtime, not startup, so the app boots without it.
    repo_path: Optional[Path] = None
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
    def coerce_repo_path(cls, v: str | Path | None) -> Path | None:
        """Convert string to Path but do NOT check existence here."""
        if v is None or v == "":
            return None
        return Path(v)

    @field_validator("output_path", mode="before")
    @classmethod
    def ensure_output_path(cls, v: str | Path) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def effective_repo_path(self, override: Path | str | None = None) -> Path:
        """
        Resolve the repo path for a specific run.

        Priority: override arg > REPO_PATH in .env

        Raises ValueError if neither is set or the resolved path doesn't exist.
        This is called once per run, not at startup.
        """
        raw = Path(override) if override else self.repo_path
        if raw is None:
            raise ValueError(
                "No repository path provided.\n"
                "  Option 1: Set REPO_PATH=/path/to/repo in your .env file\n"
                "  Option 2: Pass --repo /path/to/repo on the command line\n"
                "  Option 3: (future) send repo_path in the API request body"
            )
        if not raw.exists():
            raise ValueError(f"Repository path does not exist: {raw}")
        if not raw.is_dir():
            raise ValueError(f"Repository path is not a directory: {raw}")
        return raw

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


def _load_settings() -> Settings:
    """Load and validate settings. Only ANTHROPIC_API_KEY is required at startup."""
    try:
        s = Settings()
    except Exception as exc:
        raise RuntimeError(f"Configuration error: {exc}") from exc

    if not s.anthropic_configured:
        raise RuntimeError("ANTHROPIC_API_KEY is required but not set.")

    return s


# Module-level singleton — imported everywhere as `from src.config import settings`
settings: Settings = _load_settings()
