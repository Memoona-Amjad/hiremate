"""HireMate API.

Flow for the frontend:
  1. POST /api/runs            (form: CV + job)  → SSE stream of agent events, ends with
                                                    an `interrupt` event (human review) or `result`.
  2. POST /api/resume  (JSON: state_token + answer) → SSE stream again, continuing the graph.

The API is stateless: when the graph pauses, the `interrupt` event carries a signed
`state_token` (see statetoken.py). The browser sends it back to resume, so any server
instance can continue the run. This is what makes serverless hosting (Vercel) work.

Both streams send these SSE event names:
  run       {run_id}                  – first event (an id for logs)
  agent     {node, type, message}     – live timeline step (started/thinking/tool/retry/done)
  interrupt {kind, state_token, ...}  – the graph paused and needs the user
  result    {...}                     – final CV, letter, scores and critic report
  error     {message}                 – friendly error text (never a stack trace)
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import SAMPLES_DIR, settings
from app.graph.builder import NODE_ORDER, build_graph
from app.llm import LLMError
from app.ratelimit import check_and_count, client_ip
from app.statetoken import InvalidToken, make_token, read_token
from app.tools import ToolError, pdf_to_text

log = logging.getLogger("hiremate")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HireMate API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https://hiremate[a-z0-9-]*\.vercel\.app",  # our Vercel frontend URLs
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def friendly_errors(request: Request, exc: Exception) -> JSONResponse:
    """Last safety net: log the real error, show the user a friendly message (no stack trace)."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


# Each request runs on its own short-lived thread in this in-memory checkpointer;
# nothing needs to survive between requests (the state token carries it).
checkpointer = InMemorySaver()
graph = build_graph(checkpointer)

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 30_000


def _sample(name: str) -> str:
    return (SAMPLES_DIR / name).read_text(encoding="utf-8")


def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _result_payload(values: dict) -> dict:
    """The parts of the final state the UI needs."""
    keys = (
        "cv", "job", "fit", "confirmed", "tailored_cv", "cv_markdown",
        "cover_letter", "letter_text", "critic", "critic_history", "draft",
    )
    return {k: values.get(k) for k in keys}


async def _stream_graph(steps: list[Any], prepare: dict | None = None) -> AsyncIterator[dict[str, str]]:
    """Run the graph and translate everything into SSE events.

    `prepare` (optional) = {"values": ..., "as_node": ...}: load a saved state first (resume).
    `steps` = inputs to run one after another (e.g. [None, Command(resume=...)]).
    Only events from the last step are streamed to the user.
    """
    run_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": run_id}}
    yield _sse("run", {"run_id": run_id, "nodes": NODE_ORDER})
    try:
        if prepare:
            await graph.aupdate_state(config, prepare["values"], as_node=prepare["as_node"])
        for i, step in enumerate(steps):
            async for event in graph.astream(step, config, stream_mode="custom"):
                if i == len(steps) - 1:
                    yield _sse("agent", event)
        state = await graph.aget_state(config)
        if state.interrupts:
            payload = state.interrupts[0].value
            token = make_token(payload["kind"], state.values)
            yield _sse("interrupt", {**payload, "state_token": token})
        else:
            yield _sse("result", _result_payload(state.values))
    except (LLMError, ToolError) as exc:
        yield _sse("error", {"message": str(exc)})
    except Exception:
        log.exception("Run %s failed", run_id)
        yield _sse("error", {"message": "Something went wrong on our side. Please try again."})
    finally:
        checkpointer.delete_thread(run_id)  # free memory: the token holds what we need


@app.get("/api/health")
async def health() -> dict:
    """Cheap endpoint the frontend calls first, to wake the server up (free hosting sleeps)."""
    return {"ok": True, "model_configured": bool(settings.llm_model and settings.gemini_api_key)}


@app.get("/api/sample")
async def sample() -> dict:
    return {"cv_text": _sample("sample_cv.txt"), "job_text": _sample("sample_job.txt")}


@app.post("/api/runs")
async def start_run(
    request: Request,
    use_sample: bool = Form(False),
    cv_text: str = Form(""),
    job_text: str = Form(""),
    job_url: str = Form(""),
    cv_file: UploadFile | None = File(None),
):
    # ---- Validate input before spending any AI quota ----
    cv_source = "paste"
    if use_sample:
        cv_text, job_text, job_url, cv_source = _sample("sample_cv.txt"), _sample("sample_job.txt"), "", "sample"
    elif cv_file is not None and cv_file.filename:
        data = await cv_file.read()
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(400, "That PDF is larger than 5 MB. Please use a smaller file or paste the text.")
        try:
            cv_text, cv_source = pdf_to_text(data), "pdf"
        except ToolError as exc:
            raise HTTPException(400, str(exc)) from exc

    cv_text, job_text, job_url = cv_text.strip(), job_text.strip(), job_url.strip()
    if len(cv_text) < 100:
        raise HTTPException(400, "Please add your CV (paste at least a few lines, or upload a PDF).")
    if not job_text and not job_url:
        raise HTTPException(400, "Please paste the job description or give a link to it.")
    if job_text and len(job_text) < settings.min_job_chars:
        raise HTTPException(400, "Please add a little more about the job: at least the job title and a skill or two.")

    # ---- Rate limit (only new runs count, not resumes) ----
    allowed, _left = check_and_count(client_ip(request))
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"You've used all {settings.rate_limit_per_day} free runs for today. "
                "This keeps the demo free for everyone. Please come back tomorrow!"
            },
        )

    inputs = {
        "cv_text": cv_text[:MAX_TEXT_CHARS],
        "cv_source": cv_source,
        "job_text": job_text[:MAX_TEXT_CHARS],
        "job_url": job_url,
    }
    return EventSourceResponse(_stream_graph([inputs]), ping=10)


class ResumeBody(BaseModel):
    state_token: str                     # from the `interrupt` event
    confirmed: list[str] | None = None   # answer to "confirm_gaps"
    notes: dict[str, str] | None = None
    job_text: str | None = None          # answer to "need_job_text"


@app.post("/api/resume")
async def resume_run(body: ResumeBody):
    try:
        saved = read_token(body.state_token)
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(400, "This session has expired. Please start again.")
    values = saved["values"]

    if saved["kind"] == "need_job_text":
        if not body.job_text or len(body.job_text.strip()) < settings.min_job_chars:
            raise HTTPException(400, "Please add a little more about the job: at least the job title and a skill or two.")
        # Restart right after the CV parser, now with the pasted job text.
        values = {**values, "job_text": body.job_text.strip()[:MAX_TEXT_CHARS], "job_url": ""}
        return EventSourceResponse(
            _stream_graph([None], prepare={"values": values, "as_node": "parse_cv"}), ping=10
        )

    # confirm_gaps: restore the state just before human_review, let it pause again
    # (instant, no AI call), then resume it with the user's answer.
    answer = {"confirmed": body.confirmed or [], "notes": body.notes or {}}
    return EventSourceResponse(
        _stream_graph([None, Command(resume=answer)], prepare={"values": values, "as_node": "score_fit"}),
        ping=10,
    )
