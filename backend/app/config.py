"""App settings, read once from environment variables (and backend/.env when running locally)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _list(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_fallback_model: str = field(default_factory=lambda: os.getenv("LLM_FALLBACK_MODEL") or "")
    allowed_origins: list[str] = field(
        default_factory=lambda: _list(os.getenv("ALLOWED_ORIGINS") or "http://localhost:3000")
    )
    rate_limit_per_day: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_DAY") or 10)
    )
    # A job description can be short (even just a title and a few skills); below this it's empty.
    min_job_chars: int = 15
    # Below this many characters the Job Analyst also fills in typical requirements for the role.
    short_job_chars: int = 300
    # The critic must give at least this score, or the CV goes back for another draft.
    critic_threshold: int = 80
    # How many times the critic may send work back before we accept the best draft.
    max_retries: int = 2


settings = Settings()
SAMPLES_DIR = BACKEND_DIR / "samples"
