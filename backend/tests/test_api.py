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
    interrupt = events[-1][1]
    token = interrupt["state_token"]
    assert interrupt["kind"] == "confirm_gaps"
    assert {g["skill"] for g in interrupt["gaps"]} == {"Docker", "A/B testing"}

    response = client.post("/api/resume", json={"state_token": token, "confirmed": ["Docker"], "notes": {"Docker": "side project"}})
    events = parse_sse(response.text)
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert result["draft"] == 2  # critic sent the first draft back once
    assert result["critic"]["passed"]
    assert result["confirmed"] == ["Docker"]
    assert any(e["type"] == "retry" and e["node"] == "critic" for n, e in events if n == "agent")


def test_short_job_description_is_accepted(client):
    cv = (main.SAMPLES_DIR / "sample_cv.txt").read_text(encoding="utf-8")
    response = client.post("/api/runs", data={"cv_text": cv, "job_text": "Junior Data Scientist, Python and SQL"})
    events = parse_sse(response.text)
    assert events[-1][0] == "interrupt"
    assert any("Short job post" in e["message"] for n, e in events if n == "agent")
    # Empty-ish input is still rejected with a friendly message.
    r = client.post("/api/runs", data={"cv_text": cv, "job_text": "Analyst"})
    assert r.status_code == 400
    assert "job title" in r.json()["detail"]


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


def test_resume_rejects_bad_or_tampered_token(client):
    from app.statetoken import make_token

    assert client.post("/api/resume", json={"state_token": "nope", "confirmed": []}).status_code == 400
    token = make_token("confirm_gaps", {"cv_text": "x"})
    body, sig = token.rsplit(".", 1)
    tampered = body[:-2] + ("AA" if body[-2:] != "AA" else "BB") + "." + sig
    r = client.post("/api/resume", json={"state_token": tampered, "confirmed": []})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"]


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
    token = events[-1][1]["state_token"]

    # Too-short paste is rejected with a friendly message, then a real paste continues the run.
    assert client.post("/api/resume", json={"state_token": token, "job_text": "short"}).status_code == 400
    events = parse_sse(client.post("/api/resume", json={"state_token": token, "job_text": "A real job post. " * 20}).text)
    assert events[-1][0] == "interrupt"
    assert events[-1][1]["kind"] == "confirm_gaps"


def test_unexpected_error_is_friendly(monkeypatch):
    monkeypatch.setattr(main, "_sample", lambda name: (_ for _ in ()).throw(RuntimeError("secret internals")))
    r = TestClient(main.app, raise_server_exceptions=False).get("/api/sample")
    assert r.status_code == 500
    assert "secret" not in r.text
