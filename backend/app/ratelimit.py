"""Very small per-IP daily rate limiter, to protect the free Gemini quota on the public demo.

In-memory is enough here: the demo runs as a single server, and a restart simply resets counts.
"""

from datetime import date
from threading import Lock

from fastapi import Request

from app.config import settings

_counts: dict[str, tuple[date, int]] = {}
_lock = Lock()


def client_ip(request: Request) -> str:
    # Render/Vercel put the real visitor IP first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_and_count(ip: str) -> tuple[bool, int]:
    """Count one run for this IP. Returns (allowed, runs_left_today)."""
    today = date.today()
    with _lock:
        day, used = _counts.get(ip, (today, 0))
        if day != today:
            used = 0
        if used >= settings.rate_limit_per_day:
            return False, 0
        _counts[ip] = (today, used + 1)
        return True, settings.rate_limit_per_day - used - 1
