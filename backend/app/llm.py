"""The only module that talks to the LLM provider (Google Gemini).

Every agent calls `generate_structured(...)` and gets back a validated Pydantic object.
To switch provider (OpenAI, Claude, ...), only this file needs to change.

Resilience built in:
- Retries on rate limits / overloads / bad JSON with exponential backoff.
- Optional fallback model (LLM_FALLBACK_MODEL) when the main model keeps failing.
- An `on_retry` callback so the UI can show retries live.
"""

import asyncio
import logging
import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("hiremate.llm")

# HTTP codes worth retrying: rate limit, server errors, overloaded.
RETRYABLE_CODES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT_SECONDS = 60


class LLMError(Exception):
    """Raised with a friendly message when the LLM cannot give a usable answer."""


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("The server is missing its GEMINI_API_KEY.")
        # Timeout (milliseconds) so a hung request fails fast and gets retried.
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
        )
    return _client


# When a model is overloaded we "rest" it for a few minutes and try the others first,
# so one busy model doesn't slow down every step of a run (a tiny circuit breaker).
COOLDOWN_SECONDS = 300
_resting_until: dict[str, float] = {}


def _models_to_try() -> list[str]:
    if not settings.llm_model:
        raise LLMError("The server is missing its LLM_MODEL setting.")
    models = [settings.llm_model]
    for name in settings.llm_fallback_model.split(","):
        if name.strip() and name.strip() not in models:
            models.append(name.strip())
    # Healthy models first, resting ones last (stable sort keeps the configured order).
    now = time.monotonic()
    return sorted(models, key=lambda m: _resting_until.get(m, 0) > now)


async def generate_structured(
    prompt: str,
    schema: type[T],
    system: str,
    temperature: float = 0.3,
    rounds: int = 3,
    on_retry: Callable[[str], None] | None = None,
) -> T:
    """Ask the LLM for JSON matching `schema` and return it as a validated object.

    Free-tier models are sometimes briefly overloaded, so we make up to `rounds` passes
    over the configured models (main model, then backups), waiting a bit longer each time.
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
    )

    active = _models_to_try()
    last_problem = "unknown error"
    for round_number in range(rounds):
        for model in list(active):
            wait = 1 + 2 * round_number + random.random()  # ~1s, 3s, 5s
            try:
                response = await client.aio.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                if not response.text:
                    raise ValueError("empty response")
                return schema.model_validate_json(response.text)
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_CODES:
                    # e.g. 400 bad request / 403 bad key: retrying will not help.
                    raise LLMError(_friendly_api_error(exc)) from exc
                details = str(exc)
                log.warning("LLM %s failed with %s: %s", model, exc.code, details[:200])
                if exc.code == 429 and "PerDay" in details:
                    # Daily free quota used up: don't try this model again today.
                    last_problem = "today's free AI quota is used up"
                    active.remove(model)
                    _resting_until[model] = time.monotonic() + 6 * 3600
                elif exc.code == 429:
                    # Per-minute limit: wait as long as Google asks (capped), then retry.
                    last_problem = "the AI is rate-limited for a moment"
                    wait = min(_retry_delay(details) or 10, 30)
                else:
                    last_problem = "the AI service is busy" if exc.code == 503 else "of a server error"
                    _resting_until[model] = time.monotonic() + COOLDOWN_SECONDS
            except (ValidationError, ValueError):
                last_problem = "the AI returned an answer in the wrong format"
            except Exception as exc:  # network drop, timeout, etc.
                log.warning("LLM %s connection problem: %r", model, exc)
                last_problem = "the connection to the AI service dropped"

            if not active:
                break
            if on_retry:
                on_retry(f"Retrying in {wait:.0f}s because {last_problem}…")
            await asyncio.sleep(wait)
        if not active:
            break

    raise LLMError(
        f"The AI could not complete this step because {last_problem}. "
        "The demo runs on free AI capacity, so please try again in a few minutes."
    )


def _retry_delay(details: str) -> float | None:
    """Google's 429 errors often include 'retryDelay': '23s'. Use it if present."""
    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", details)
    return float(match.group(1)) if match else None


def _friendly_api_error(exc: errors.APIError) -> str:
    if exc.code in (401, 403):
        return "The server's AI key is invalid or not allowed. (Check GEMINI_API_KEY.)"
    if exc.code == 404:
        return "The configured AI model was not found. (Check LLM_MODEL.)"
    return "The AI service rejected the request. Please try again."
