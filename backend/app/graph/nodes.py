"""The agents. Each one is a small async function: read state -> do one job -> return updates.

Every agent reports progress with `emit(...)` so the UI can show its thinking live.
"""

import json

from langgraph.types import interrupt

from app.config import settings
from app.graph import prompts
from app.graph.events import emit, retry_reporter
from app.graph.state import HireMateState
from app.llm import generate_structured
from app.render import cv_to_markdown, letter_to_text, word_count
from app.schemas import CoverLetter, CriticReport, CVData, FitScore, JobData, TailoredCV
from app.tools import ToolError, fetch_job_text, find_unsupported_skills, keyword_coverage


def _confirmed_facts(state: HireMateState) -> str:
    """The extra facts the user confirmed in the review step, as text for prompts."""
    notes = state.get("confirmed_notes", {})
    confirmed = state.get("confirmed", [])
    if not confirmed:
        return "(none: the candidate did not confirm any extra skills)"
    return "\n".join(f"- {s}" + (f": {notes[s]}" if notes.get(s) else "") for s in confirmed)


# ---------------------------------------------------------------- 1. parse_cv
async def parse_cv(state: HireMateState) -> dict:
    node = "parse_cv"
    emit(node, "started", "Reading the CV")
    text = state["cv_text"]
    if state.get("cv_source") == "pdf":
        emit(node, "tool", f"pdf_to_text → extracted {len(text):,} characters from the PDF")
    emit(node, "thinking", "Pulling out skills, experience, education and projects…")

    cv = await generate_structured(
        f"CV:\n{text}", CVData, prompts.PARSE_CV, temperature=0.0, on_retry=retry_reporter(node)
    )
    emit(
        node,
        "done",
        f"Found {len(cv.skills)} skills, {len(cv.experience)} roles, {len(cv.projects)} projects",
        {"name": cv.name, "headline": cv.headline},
    )
    return {"cv": cv.model_dump()}


# ---------------------------------------------------------------- 2. analyze_job
async def analyze_job(state: HireMateState) -> dict:
    node = "analyze_job"
    emit(node, "started", "Reading the job post")
    job_text = state.get("job_text", "").strip()
    updates: dict = {}

    if not job_text and state.get("job_url"):
        url = state["job_url"]
        emit(node, "tool", f"fetch_job_text → downloading {url}")
        try:
            job_text = await fetch_job_text(url)
            emit(node, "thinking", f"Got {len(job_text):,} characters from the page")
        except ToolError as exc:
            emit(node, "retry", f"Couldn't read the link: {exc} Asking you to paste the text instead.")
            # Pause the graph and wait for the user to paste the job text.
            answer = interrupt({"kind": "need_job_text", "message": str(exc)})
            job_text = str(answer.get("job_text", "")).strip()
            if len(job_text) < 50:
                raise ToolError("The pasted job description is too short.")
        updates["job_text"] = job_text

    emit(node, "thinking", "Finding required skills, nice-to-haves, seniority and key words…")
    job = await generate_structured(
        f"JOB POST:\n{job_text}", JobData, prompts.ANALYZE_JOB, temperature=0.0,
        on_retry=retry_reporter(node),
    )
    emit(
        node,
        "done",
        f"{job.seniority} {job.title}: {len(job.required_skills)} required skills, "
        f"{len(job.nice_to_have)} nice-to-haves",
        {"title": job.title, "company": job.company},
    )
    return {**updates, "job": job.model_dump()}


# ---------------------------------------------------------------- 3. score_fit
async def score_fit(state: HireMateState) -> dict:
    node = "score_fit"
    emit(node, "started", "Comparing the CV with the job")
    job = JobData(**state["job"])

    coverage = keyword_coverage(state["cv_text"], job.keywords)
    emit(node, "tool", f"keyword_coverage → {coverage['percent']}% of the job's key words are already in the CV")

    emit(node, "thinking", "Matching skills (including close equivalents) and spotting gaps…")
    prompt = (
        f"JOB (structured):\n{job.model_dump_json(indent=1)}\n\n"
        f"CV (structured):\n{json.dumps(state['cv'], indent=1)}\n\n"
        f"Keyword check: {json.dumps(coverage)}"
    )
    fit = await generate_structured(prompt, FitScore, prompts.SCORE_FIT, on_retry=retry_reporter(node))
    fit.score = max(0, min(100, fit.score))
    emit(
        node,
        "done",
        f"Fit score {fit.score}/100: {len(fit.matched_skills)} matched, {len(fit.missing_skills)} gaps",
        {"score": fit.score},
    )
    return {"fit": {**fit.model_dump(), "keyword_coverage": coverage}}


# ---------------------------------------------------------------- 4. human_review
async def human_review(state: HireMateState) -> dict:
    node = "human_review"
    gaps = state["fit"]["missing_skills"]
    emit(node, "started", "Waiting for you: which of these gaps do you actually have experience with?")

    # LangGraph interrupt: the graph pauses here and is saved by the checkpointer.
    # It continues when the API resumes it with the user's answer.
    answer = interrupt(
        {
            "kind": "confirm_gaps",
            "question": "Which of these do you actually have experience with?",
            "gaps": gaps,
        }
    )

    # Only accept skills that were actually offered (agents must never invent experience).
    offered = {g["skill"] for g in gaps}
    confirmed = [s for s in answer.get("confirmed", []) if s in offered]
    raw_notes = answer.get("notes", {}) or {}
    notes = {s: str(raw_notes[s])[:300] for s in confirmed if raw_notes.get(s)}

    if confirmed:
        emit(node, "done", f"You confirmed {len(confirmed)}: {', '.join(confirmed)}")
    else:
        emit(node, "done", "No extra skills confirmed: the CV will use only what it already says")
    return {"confirmed": confirmed, "confirmed_notes": notes, "draft": 0, "critic_history": []}


# ---------------------------------------------------------------- 5. tailor_cv
async def tailor_cv(state: HireMateState) -> dict:
    node = "tailor_cv"
    draft = state.get("draft", 0) + 1
    emit(node, "started", "Writing the tailored CV" + (f" (draft {draft})" if draft > 1 else ""))

    feedback = ""
    if state.get("critic"):
        feedback = f"\n\nTHE CRITIC REJECTED THE LAST DRAFT. Fix these points:\n{state['critic']['feedback']}"
        emit(node, "thinking", "Applying the critic's feedback…")
    else:
        emit(node, "thinking", "Reordering for relevance and weaving in the job's key words (only where true)…")

    prompt = (
        f"JOB:\n{json.dumps(state['job'], indent=1)}\n\n"
        f"ORIGINAL CV:\n{json.dumps(state['cv'], indent=1)}\n\n"
        f"CONFIRMED FACTS (the candidate ticked these):\n{_confirmed_facts(state)}\n\n"
        f"QUICK WINS suggested earlier:\n{json.dumps(state['fit']['quick_wins'])}"
        f"{feedback}"
    )
    tailored = await generate_structured(
        prompt, TailoredCV, prompts.TAILOR_CV, temperature=0.4, on_retry=retry_reporter(node)
    )
    emit(node, "done", f"Draft {draft} ready: {len(tailored.changes_made)} changes made")
    return {
        "tailored_cv": tailored.model_dump(),
        "cv_markdown": cv_to_markdown(tailored),
        "draft": draft,
    }


# ---------------------------------------------------------------- 6. write_cover_letter
async def write_cover_letter(state: HireMateState) -> dict:
    node = "write_cover_letter"
    emit(node, "started", "Writing the cover letter")
    emit(node, "thinking", "Linking 2-3 real achievements to what this employer needs…")

    feedback = ""
    if state.get("critic"):
        feedback = f"\n\nTHE CRITIC'S FEEDBACK ON THE LAST VERSION:\n{state['critic']['feedback']}"
    prompt = (
        f"JOB:\n{json.dumps(state['job'], indent=1)}\n\n"
        f"TAILORED CV:\n{state['cv_markdown']}\n\n"
        f"CONFIRMED FACTS:\n{_confirmed_facts(state)}"
        f"{feedback}"
    )
    letter = await generate_structured(
        prompt, CoverLetter, prompts.COVER_LETTER, temperature=0.5, on_retry=retry_reporter(node)
    )
    text = letter_to_text(letter)
    emit(node, "done", f"Letter ready ({word_count(text)} words)")
    return {"cover_letter": letter.model_dump(), "letter_text": text}


# ---------------------------------------------------------------- 7. critic
async def critic(state: HireMateState) -> dict:
    node = "critic"
    draft = state["draft"]
    emit(node, "started", f"Reviewing draft {draft}")

    # Tool 1: hard truthfulness check (no LLM): every listed skill must have evidence.
    evidence = state.get("confirmed", []) + list(state.get("confirmed_notes", {}).values())
    unsupported = find_unsupported_skills(state["tailored_cv"]["skills"], state["cv_text"], evidence)
    if unsupported:
        emit(node, "tool", f"truth_check → ⚠ not backed by your CV: {', '.join(unsupported)}")
    else:
        emit(node, "tool", "truth_check → every listed skill is backed by your CV or your confirmations")

    # Tool 2: keyword coverage of the new CV vs the original.
    keywords = state["job"]["keywords"]
    coverage = keyword_coverage(state["cv_markdown"], keywords)
    before = state["fit"]["keyword_coverage"]["percent"]
    emit(node, "tool", f"keyword_coverage → {before}% before, {coverage['percent']}% now")

    letter_words = word_count(state["letter_text"])
    emit(node, "thinking", "Checking truthfulness, key words, tone and length…")
    prompt = (
        f"ORIGINAL CV:\n{state['cv_text']}\n\n"
        f"CONFIRMED FACTS:\n{_confirmed_facts(state)}\n\n"
        f"JOB:\n{json.dumps(state['job'], indent=1)}\n\n"
        f"TAILORED CV:\n{state['cv_markdown']}\n\n"
        f"COVER LETTER ({letter_words} words):\n{state['letter_text']}\n\n"
        f"AUTOMATIC CHECKS: unsupported skills = {unsupported or 'none'}; "
        f"keyword coverage = {coverage['percent']}% (missing: {coverage['missing']})"
    )
    report = await generate_structured(
        prompt, CriticReport, prompts.CRITIC, temperature=0.0, on_retry=retry_reporter(node)
    )

    # The automatic truth check overrides the LLM: unsupported skills always fail the draft.
    if unsupported:
        report.truthfulness = min(report.truthfulness, 50)
        report.score = min(report.score, 65)
        report.issues.insert(0, f"Skills not backed by the CV or your confirmations: {', '.join(unsupported)}")
        report.feedback = f"Remove these unsupported skills: {', '.join(unsupported)}. " + report.feedback

    passed = report.score >= settings.critic_threshold
    result = {
        **report.model_dump(),
        "draft": draft,
        "passed": passed,
        "threshold": settings.critic_threshold,
        "unsupported_skills": unsupported,
        "keyword_coverage": coverage,
        "keyword_coverage_before": before,
        "letter_words": letter_words,
    }
    history = [*state.get("critic_history", []), result]
    updates: dict = {"critic": result, "critic_history": history}

    # Remember the best draft in case every retry fails.
    best = state.get("best_draft")
    if not best or report.score > best["score"]:
        best = {
            "score": report.score,
            "critic": result,
            "tailored_cv": state["tailored_cv"],
            "cv_markdown": state["cv_markdown"],
            "cover_letter": state["cover_letter"],
            "letter_text": state["letter_text"],
        }
        updates["best_draft"] = best

    retries_used = draft - 1
    if passed:
        emit(node, "done", f"Approved: {report.score}/100 (needs {settings.critic_threshold})", {"score": report.score})
    elif retries_used < settings.max_retries:
        emit(
            node,
            "retry",
            f"Score {report.score}/100 is below {settings.critic_threshold}. Sending back to the CV writer "
            f"(retry {retries_used + 1} of {settings.max_retries})",
            {"score": report.score, "issues": report.issues[:3]},
        )
    else:
        # Out of retries: hand over the best draft we produced.
        for key in ("tailored_cv", "cv_markdown", "cover_letter", "letter_text"):
            updates[key] = best[key]
        updates["critic"] = {**best["critic"], "final_after_retries": True}
        emit(
            node,
            "done",
            f"Used all {settings.max_retries} retries. Showing the best draft ({best['score']}/100) with the critic's notes",
            {"score": best["score"]},
        )
    return updates


def route_after_critic(state: HireMateState) -> str:
    """Conditional edge: retry the writer, or finish."""
    critic_result = state["critic"]
    if critic_result["passed"] or critic_result.get("final_after_retries"):
        return "end"
    return "retry"
