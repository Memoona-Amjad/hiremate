"""HireMate API.

Flow for the frontend:
  1. POST /api/runs            (form: CV + job)  → SSE stream of agent events, ends with
                                                    an `interrupt` event (human review) or `result`.
  2. POST /api/runs/{id}/resume (JSON answer)   → SSE stream again, continuing the same graph.

Both streams send these SSE event names:
  run       {run_id}                  – first event, so the client knows which run this is
  agent     {node, type, message}     – live timeline step (started/thinking/tool/retry/done)
  interrupt {kind, ...}               – the graph paused and needs the user
  result    {...}                     – final CV, letter, scores and critic report
  error     {message}                 – friendly error text (never a stack trace)
"""

import asyncio
import json
import logging
import time
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
from app.tools import ToolError, pdf_to_text

log = logging.getLogger("hiremate")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HireMate API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https://hiremate[a-z0-9-]*\.vercel\.app",  # Vercel preview URLs
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

checkpointer = InMemorySaver()
graph = build_graph(checkpointer)

# run_id -> created time; used to clean up old runs and reject unknown ids.
RUN_TTL_SECONDS = 2 * 60 * 60
runs: dict[str, float] = {}
run_locks: dict[str, asyncio.Lock] = {}

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 30_000


def _sample(name: str) -> str:
    return (SAMPLES_DIR / name).read_text(encoding="utf-8")


def _cleanup_old_runs() -> None:
    now = time.time()
    for run_id, created in list(runs.items()):
        if now - created > RUN_TTL_SECONDS:
            runs.pop(run_id, None)
            run_locks.pop(run_id, None)
            checkpointer.delete_thread(run_id)


def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _result_payload(values: dict) -> dict:
    """The parts of the final state the UI needs."""
    keys = (
        "cv", "job", "fit", "confirmed", "tailored_cv", "cv_markdown",
        "cover_letter", "letter_text", "critic", "critic_history", "draft",
    )
    return {k: values.get(k) for k in keys}


async def _stream_graph(run_id: str, graph_input: Any) -> AsyncIterator[dict[str, str]]:
    """Run (or resume) the graph and translate everything into SSE events."""
    config = {"configurable": {"thread_id": run_id}}
    lock = run_locks.setdefault(run_id, asyncio.Lock())
    if lock.locked():
        yield _sse("error", {"message": "This run is already in progress in another tab."})
        return

    async with lock:
        yield _sse("run", {"run_id": run_id, "nodes": NODE_ORDER})
        try:
            async for event in graph.astream(graph_input, config, stream_mode="custom"):
                yield _sse("agent", event)
            state = await graph.aget_state(config)
            if state.interrupts:
                yield _sse("interrupt", state.interrupts[0].value)
            else:
                yield _sse("result", _result_payload(state.values))
        except (LLMError, ToolError) as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception:
            log.exception("Run %s failed", run_id)
            yield _sse("error", {"message": "Something went wrong on our side. Please try again."})


@app.get("/api/health")
async def health() -> dict:
    """Cheap endpoint the frontend calls first, to wake the server up on Render's free tier."""
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
    _cleanup_old_runs()

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
    if job_text and len(job_text) < 100:
        raise HTTPException(400, "The job description looks too short. Please paste the full post.")

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

    run_id = uuid.uuid4().hex
    runs[run_id] = time.time()
    inputs = {
        "cv_text": cv_text[:MAX_TEXT_CHARS],
        "cv_source": cv_source,
        "job_text": job_text[:MAX_TEXT_CHARS],
        "job_url": job_url,
    }
    return EventSourceResponse(_stream_graph(run_id, inputs), ping=10)


class ResumeBody(BaseModel):
    confirmed: list[str] | None = None   # answer to "confirm_gaps"
    notes: dict[str, str] | None = None
    job_text: str | None = None          # answer to "need_job_text"


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, body: ResumeBody):
    if run_id not in runs:
        raise HTTPException(404, "This session has expired. Please start again.")
    state = await graph.aget_state({"configurable": {"thread_id": run_id}})
    if not state.interrupts:
        raise HTTPException(409, "This run is not waiting for an answer.")

    kind = state.interrupts[0].value.get("kind")
    if kind == "need_job_text":
        if not body.job_text or len(body.job_text.strip()) < 100:
            raise HTTPException(400, "Please paste the full job description.")
        answer: dict = {"job_text": body.job_text.strip()[:MAX_TEXT_CHARS]}
    else:
        answer = {"confirmed": body.confirmed or [], "notes": body.notes or {}}
    return EventSourceResponse(_stream_graph(run_id, Command(resume=answer)), ping=10)
