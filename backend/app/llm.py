"""The only module that talks to the LLM provider (Google Gemini).

Every agent calls `generate_structured(...)` and gets back a validated Pydantic object.
To switch provider (OpenAI, Claude, ...), only this file needs to change.

Resilience built in:
- Retries on rate limits / overloads / bad JSON with exponential backoff.
- Optional fallback model (LLM_FALLBACK_MODEL) when the main model keeps failing.
- An `on_retry` callback so the UI can show retries live.
"""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

# HTTP codes worth retrying: rate limit, server errors, overloaded.
RETRYABLE_CODES = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """Raised with a friendly message when the LLM cannot give a usable answer."""


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("The server is missing its GEMINI_API_KEY.")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _models_to_try() -> list[str]:
    if not settings.llm_model:
        raise LLMError("The server is missing its LLM_MODEL setting.")
    models = [settings.llm_model]
    if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
        models.append(settings.llm_fallback_model)
    return models


async def generate_structured(
    prompt: str,
    schema: type[T],
    system: str,
    temperature: float = 0.3,
    attempts_per_model: int = 3,
    on_retry: Callable[[str], None] | None = None,
) -> T:
    """Ask the LLM for JSON matching `schema` and return it as a validated object."""
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
    )

    last_problem = "unknown error"
    for model in _models_to_try():
        for attempt in range(1, attempts_per_model + 1):
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
                last_problem = "the AI service is busy" if exc.code in (429, 503) else "a server error"
            except (ValidationError, ValueError):
                last_problem = "the AI returned an answer in the wrong format"

            if attempt < attempts_per_model:
                wait = 2 ** attempt  # 2s, 4s, ...
                if on_retry:
                    on_retry(f"Retrying because {last_problem} (attempt {attempt + 1}/{attempts_per_model})…")
                await asyncio.sleep(wait)

        if on_retry and model != _models_to_try()[-1]:
            on_retry("Switching to the backup AI model…")

    raise LLMError(f"The AI could not complete this step ({last_problem}). Please try again in a minute.")


def _friendly_api_error(exc: errors.APIError) -> str:
    if exc.code in (401, 403):
        return "The server's AI key is invalid or not allowed. (Check GEMINI_API_KEY.)"
    if exc.code == 404:
        return "The configured AI model was not found. (Check LLM_MODEL.)"
    return "The AI service rejected the request. Please try again."
