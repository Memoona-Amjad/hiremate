"""Live progress events.

Each agent calls `emit(...)` to report what it is doing. LangGraph forwards these through
its "custom" stream, the API turns them into Server-Sent Events, and the UI draws the timeline.

Event types:
  started   – agent began
  thinking  – a short status line ("Reading the job post…")
  tool      – a non-LLM tool was used (PDF reader, web fetch, keyword checker…)
  retry     – something is being tried again (LLM retry, or critic sending work back)
  done      – agent finished (with a one-line result)
"""

from typing import Any

from langgraph.config import get_stream_writer


def emit(node: str, type_: str, message: str, data: dict[str, Any] | None = None) -> None:
    event = {"node": node, "type": type_, "message": message}
    if data:
        event["data"] = data
    try:
        get_stream_writer()(event)
    except RuntimeError:
        # Called outside a graph run (e.g. a unit test): just ignore.
        pass


def retry_reporter(node: str):
    """A callback the LLM wrapper uses to show its own retries in the timeline."""
    return lambda message: emit(node, "retry", message)
