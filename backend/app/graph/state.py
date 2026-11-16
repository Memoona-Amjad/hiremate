"""The shared state every agent reads from and writes to.

Values are plain dicts/lists (not Pydantic objects) so the LangGraph checkpointer can
save them between the human-review pause and the resume.
"""

from typing import TypedDict


class HireMateState(TypedDict, total=False):
    # Inputs
    cv_text: str
    cv_source: str          # "paste", "pdf" or "sample"
    job_text: str
    job_url: str

    # Agent outputs
    cv: dict                # CVData
    job: dict               # JobData
    fit: dict               # FitScore + keyword coverage
    confirmed: list[str]    # gaps the user said they really have
    confirmed_notes: dict[str, str]  # optional "how I used it" note per confirmed skill
    declined: list[str]     # gaps the user did not tick: must never be claimed
    tailored_cv: dict       # TailoredCV
    cv_markdown: str
    cover_letter: dict      # CoverLetter
    letter_text: str
    critic: dict            # latest CriticReport + extra checks
    critic_history: list[dict]
    draft: int              # how many drafts have been written (1 = first try)
    best_draft: dict        # best-scoring draft so far, used if all retries fail
