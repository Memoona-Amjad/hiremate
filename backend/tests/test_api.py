"""API tests: SSE stream → interrupt → resume → result, plus validation and rate limiting."""

import json

import pytest
from fastapi.testclient import TestClient

from app import main, ratelimit
from app.graph import nodes
from tests.test_graph import make_fake_llm


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name and data:
            events.append((name, json.loads(data)))
    return events


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(nodes, "generate_structured", make_fake_llm([60, 90]))
    ratelimit._counts.clear()
    return TestClient(main.app)


def test_sample_run_with_review_and_retry(client):
    response = client.post("/api/runs", data={"use_sample": "true"})
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [n for n, _ in events]
    assert names[0] == "run" and names[-1] == "interrupt"
    run_id = events[0][1]["run_id"]
    interrupt = events[-1][1]
    assert interrupt["kind"] == "confirm_gaps"
    assert {g["skill"] for g in interrupt["gaps"]} == {"Docker", "A/B testing"}

    response = client.post(f"/api/runs/{run_id}/resume", json={"confirmed": ["Docker"], "notes": {"Docker": "side project"}})
    events = parse_sse(response.text)
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert result["draft"] == 2  # critic sent the first draft back once
    assert result["critic"]["passed"]
    assert result["confirmed"] == ["Docker"]
    assert any(e["type"] == "retry" and e["node"] == "critic" for n, e in events if n == "agent")


def test_validation_messages(client):
    r = client.post("/api/runs", data={"cv_text": "too short", "job_text": "x" * 200})
    assert r.status_code == 400
    assert "CV" in r.json()["detail"]
    r = client.post("/api/runs", data={"cv_text": "x" * 200})
    assert r.status_code == 400


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "check_and_count", lambda ip: (False, 0))
    monkeypatch.setattr(main, "check_and_count", lambda ip: (False, 0))
    r = client.post("/api/runs", data={"use_sample": "true"})
    assert r.status_code == 429
    assert "free runs" in r.json()["detail"]


def test_resume_unknown_run(client):
    r = client.post("/api/runs/nope/resume", json={"confirmed": []})
    assert r.status_code == 404


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_unreadable_pdf_gives_friendly_400(client):
    r = client.post(
        "/api/runs",
        data={"job_text": "x" * 200},
        files={"cv_file": ("cv.pdf", b"this is not really a pdf", "application/pdf")},
    )
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_blocked_job_link_asks_user_to_paste(client, monkeypatch):
    from app.tools import ToolError

    async def blocked(url):
        raise ToolError("The job site blocked us or didn't respond.")

    monkeypatch.setattr(nodes, "fetch_job_text", blocked)
    cv = (main.SAMPLES_DIR / "sample_cv.txt").read_text(encoding="utf-8")
    events = parse_sse(client.post("/api/runs", data={"cv_text": cv, "job_url": "https://jobs.example.com/1"}).text)
    assert events[-1][0] == "interrupt"
    assert events[-1][1]["kind"] == "need_job_text"
    run_id = events[0][1]["run_id"]

    # Too-short paste is rejected with a friendly message, then a real paste continues the run.
    assert client.post(f"/api/runs/{run_id}/resume", json={"job_text": "short"}).status_code == 400
    events = parse_sse(client.post(f"/api/runs/{run_id}/resume", json={"job_text": "A real job post. " * 20}).text)
    assert events[-1][0] == "interrupt"
    assert events[-1][1]["kind"] == "confirm_gaps"


def test_unexpected_error_is_friendly(monkeypatch):
    monkeypatch.setattr(main, "_sample", lambda name: (_ for _ in ()).throw(RuntimeError("secret internals")))
    r = TestClient(main.app, raise_server_exceptions=False).get("/api/sample")
    assert r.status_code == 500
    assert "secret" not in r.text
