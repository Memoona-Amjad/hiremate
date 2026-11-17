"""Very small per-IP daily rate limiter, to protect the free Gemini quota on the public demo.

Counts live in memory, so on serverless hosting each instance counts separately and the limit
is approximate. Good enough to protect a demo; a shared store (e.g. Redis) would make it exact.
"""

from datetime import date
from threading import Lock

from fastapi import Request

from app.config import settings

_counts: dict[str, tuple[date, int]] = {}
_lock = Lock()


def client_ip(request: Request) -> str:
    # Vercel (and most hosts) put the real visitor IP first in X-Forwarded-For.
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
