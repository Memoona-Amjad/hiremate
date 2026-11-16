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
