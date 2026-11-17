"""Signed "state tokens": how a paused run survives without server memory.

When the graph pauses for the human, we pack its state into a token, sign it with a secret
(HMAC-SHA256) and send it to the browser. On resume, the browser sends it back; we check the
signature, so the user can't tamper with it (e.g. add skills that were never offered), and
continue the graph from that state.

Why: on serverless hosting (Vercel) the resume request may reach a different machine,
so nothing can be kept in memory between requests. This also lets the API scale out freely.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import zlib

from app.config import settings

MAX_AGE_SECONDS = 2 * 60 * 60  # a paused run can be resumed for 2 hours


class InvalidToken(Exception):
    pass


def _secret() -> bytes:
    explicit = os.getenv("STATE_SECRET", "")
    if explicit:
        return explicit.encode()
    # No separate secret configured: derive one from the (already secret) API key.
    return hashlib.sha256(f"hiremate-state:{settings.gemini_api_key}".encode()).digest()


def _sign(body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_secret(), body, hashlib.sha256).digest()).decode().rstrip("=")


def make_token(kind: str, values: dict) -> str:
    payload = json.dumps({"kind": kind, "values": values, "iat": int(time.time())}, ensure_ascii=False)
    body = base64.urlsafe_b64encode(zlib.compress(payload.encode())).decode().rstrip("=")
    return f"{body}.{_sign(body.encode())}"


def read_token(token: str) -> dict:
    try:
        body, signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise InvalidToken from exc
    if not hmac.compare_digest(signature, _sign(body.encode())):
        raise InvalidToken
    padded = body + "=" * (-len(body) % 4)
    data = json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)))
    if time.time() - data["iat"] > MAX_AGE_SECONDS:
        raise InvalidToken
    return data
