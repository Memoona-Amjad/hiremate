"""End-to-end graph test with a fake LLM: checks the interrupt, resume and critic retry loop."""

import asyncio
import uuid

from langgraph.types import Command

from app.config import SAMPLES_DIR
from app.graph import nodes
from app.graph.builder import build_graph
from app.schemas import CoverLetter, CriticReport, CVData, FitScore, JobData, SkillGap, TailoredCV


def make_fake_llm(critic_scores: list[int], extra_skill: str | None = None):
    scores = iter(critic_scores)

    async def fake(prompt, schema, system, **kwargs):
        if schema is CVData:
            return CVData(name="Alex Morgan", headline="Data Analyst", skills=["Python", "SQL"])
        if schema is JobData:
            return JobData(title="Junior Data Scientist", seniority="Junior", summary="ML role",
                           required_skills=["Python", "SQL"], nice_to_have=["Docker"],
                           keywords=["Python", "SQL", "Docker", "A/B testing"])
        if schema is FitScore:
            return FitScore(score=70, summary="Good", matched_skills=["Python", "SQL"],
                            missing_skills=[SkillGap(skill="Docker", importance="nice-to-have", why_it_matters="deploy"),
                                            SkillGap(skill="A/B testing", importance="nice-to-have", why_it_matters="exp")],
                            quick_wins=["Mention churn model"])
        if schema is TailoredCV:
            skills = ["Python", "SQL"] + ([extra_skill] if extra_skill else [])
            return TailoredCV(name="Alex Morgan", headline="Data Analyst", skills=skills)
        if schema is CoverLetter:
            return CoverLetter(greeting="Dear team,", paragraphs=["Hello there."], sign_off="Alex")
        if schema is CriticReport:
            s = next(scores)
            return CriticReport(score=s, truthfulness=s, keyword_match=s, tone=s, length=s,
                                issues=[] if s >= 80 else ["too generic"], feedback="be specific")
        raise AssertionError(schema)

    return fake


async def run_graph(monkeypatch, critic_scores, confirmed, extra_skill=None):
    monkeypatch.setattr(nodes, "generate_structured", make_fake_llm(critic_scores, extra_skill))
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    cv_text = (SAMPLES_DIR / "sample_cv.txt").read_text(encoding="utf-8")
    events = []

    inputs = {"cv_text": cv_text, "cv_source": "sample", "job_text": "a job post", "job_url": ""}
    async for chunk in graph.astream(inputs, config, stream_mode="custom"):
        events.append(chunk)
    state = await graph.aget_state(config)
    assert state.interrupts[0].value["kind"] == "confirm_gaps"

    async for chunk in graph.astream(Command(resume={"confirmed": confirmed, "notes": {}}), config, stream_mode="custom"):
        events.append(chunk)
    state = await graph.aget_state(config)
    return state.values, events


def test_happy_path_no_retry(monkeypatch):
    values, events = asyncio.run(run_graph(monkeypatch, [90], ["Docker"]))
    assert values["draft"] == 1
    assert values["critic"]["passed"]
    assert values["confirmed"] == ["Docker"]
    assert not any(e["type"] == "retry" for e in events)


def test_critic_retry_loop(monkeypatch):
    values, events = asyncio.run(run_graph(monkeypatch, [60, 85], []))
    assert values["draft"] == 2
    assert [e for e in events if e["type"] == "retry" and e["node"] == "critic"]


def test_max_two_retries_then_best_draft(monkeypatch):
    values, _ = asyncio.run(run_graph(monkeypatch, [50, 70, 60], []))
    assert values["draft"] == 3  # first draft + 2 retries, then stop
    assert values["critic"]["final_after_retries"]
    assert values["critic"]["score"] == 70  # best draft kept


def test_unconfirmed_skills_are_ignored_and_flagged(monkeypatch):
    # User "confirms" a skill that was never offered (ignored), declines Docker,
    # and the CV writer claims Docker anyway.
    values, _ = asyncio.run(run_graph(monkeypatch, [95, 95, 95], ["Rust"], extra_skill="Docker"))
    assert values["confirmed"] == []
    assert values["critic"]["unsupported_skills"] == ["Docker"]
    assert values["critic"]["score"] <= 65  # truth check overrides the LLM's 95
