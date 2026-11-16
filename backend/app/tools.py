"""Plain Python "tools" the agents use. No LLM here: fast, free and predictable.

- pdf_to_text:          read text out of an uploaded CV PDF
- fetch_job_text:       download a job post from a link and strip it to readable text
- keyword_coverage:     how many of the job's keywords already appear in a text
- find_unsupported_skills: skills in the new CV that are not backed by the original
                           CV or by something the user confirmed (truthfulness guard)
"""

import io
import re

import httpx
import trafilatura
from pypdf import PdfReader


class ToolError(Exception):
    """A tool failed in a way we can explain to the user."""


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # pypdf raises many different error types
        raise ToolError("We couldn't read that PDF. Try pasting the CV text instead.") from exc
    text = text.strip()
    if len(text) < 100:
        raise ToolError(
            "That PDF has almost no readable text (it may be a scanned image). "
            "Please paste the CV text instead."
        )
    return text


async def fetch_job_text(url: str) -> str:
    """Fetch a job page and return its main text. Raises ToolError if blocked or empty."""
    if not re.match(r"^https?://", url):
        raise ToolError("That doesn't look like a web link (it should start with http).")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HireMate/1.0",
        "Accept-Language": "en",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolError("The job site blocked us or didn't respond.") from exc

    text = trafilatura.extract(response.text) or ""
    if len(text) < 200:
        raise ToolError("The page didn't contain a readable job description (it may need a login).")
    return text[:15000]


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", text.lower()).strip()


def _mentions(haystack: str, term: str) -> bool:
    """True if `term` (or every word of it) appears in the normalised haystack."""
    term_n = _normalise(term)
    if not term_n:
        return True
    if f" {term_n} " in f" {haystack} ":
        return True
    words = [w for w in term_n.split() if len(w) > 2]
    return bool(words) and all(f" {w} " in f" {haystack} " for w in words)


def keyword_coverage(text: str, keywords: list[str]) -> dict:
    """Return which job keywords appear in `text` and the coverage percentage."""
    haystack = _normalise(text)
    found = [k for k in keywords if _mentions(haystack, k)]
    missing = [k for k in keywords if k not in found]
    percent = round(100 * len(found) / len(keywords)) if keywords else 100
    return {"percent": percent, "found": found, "missing": missing}


def find_unsupported_skills(new_skills: list[str], original_cv_text: str, confirmed: list[str]) -> list[str]:
    """Skills listed in the tailored CV that neither the original CV nor the user backs up."""
    evidence = _normalise(original_cv_text + " " + " ".join(confirmed))
    return [s for s in new_skills if not _mentions(evidence, s)]
