"""Run the whole agent team from the command line on the bundled sample (or your own files).

    python cli.py                      # sample CV + sample job, asks you to confirm gaps
    python cli.py --yes                # sample, auto-confirm nothing (non-interactive)
    python cli.py --cv my_cv.pdf --job job.txt
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from langgraph.types import Command

from app.config import SAMPLES_DIR
from app.graph.builder import build_graph
from app.llm import LLMError
from app.tools import ToolError, pdf_to_text

ICONS = {"started": "▶", "thinking": "…", "tool": "🔧", "retry": "↻", "done": "✔"}


def load_cv(path: Path) -> tuple[str, str]:
    if path.suffix.lower() == ".pdf":
        return pdf_to_text(path.read_bytes()), "pdf"
    return path.read_text(encoding="utf-8"), "paste"


def ask_user(payload: dict, auto: bool) -> dict:
    """Answer an interrupt from the terminal."""
    if payload["kind"] == "need_job_text":
        print(f"\n{payload['message']}\nPaste the job text, then press Enter twice:")
        lines = iter(input, "")
        return {"job_text": "\n".join(lines)}

    gaps = payload["gaps"]
    print(f"\n=== HUMAN REVIEW ===\n{payload['question']}")
    for i, gap in enumerate(gaps, 1):
        print(f"  {i}. {gap['skill']} ({gap['importance']}): {gap['why_it_matters']}")
    if auto or not gaps:
        print("  (auto mode: confirming none)")
        return {"confirmed": [], "notes": {}}
    raw = input("Numbers you have real experience with (e.g. 1,3), or Enter for none: ")
    picks = [gaps[int(n) - 1]["skill"] for n in raw.replace(" ", "").split(",") if n.isdigit() and 0 < int(n) <= len(gaps)]
    notes = {s: input(f"  Briefly, how have you used {s}? ") for s in picks}
    return {"confirmed": picks, "notes": notes}


async def run(cv_path: Path, job_path: Path | None, job_url: str, auto: bool) -> None:
    cv_text, source = load_cv(cv_path)
    inputs = {"cv_text": cv_text, "cv_source": source, "job_text": "", "job_url": job_url}
    if job_path:
        inputs["job_text"] = job_path.read_text(encoding="utf-8")

    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    next_input: dict | Command = inputs

    while True:
        async for mode, chunk in graph.astream(next_input, config, stream_mode=["custom", "updates"]):
            if mode == "custom":
                print(f"{ICONS.get(chunk['type'], '-')} [{chunk['node']}] {chunk['message']}")
        state = await graph.aget_state(config)
        if not state.interrupts:
            break
        next_input = Command(resume=ask_user(state.interrupts[0].value, auto))

    final = state.values
    critic = final["critic"]
    print("\n" + "=" * 70)
    print(f"FIT SCORE: {final['fit']['score']}/100  |  CRITIC: {critic['score']}/100  |  drafts: {final['draft']}")
    print("=" * 70 + "\nTAILORED CV\n" + "-" * 70)
    print(final["cv_markdown"])
    print("-" * 70 + "\nCOVER LETTER\n" + "-" * 70)
    print(final["letter_text"])
    print("-" * 70 + "\nCRITIC REPORT\n" + "-" * 70)
    for key in ("truthfulness", "keyword_match", "tone", "length"):
        print(f"  {key}: {critic[key]}")
    for issue in critic["issues"]:
        print(f"  - {issue}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # emoji/arrows on Windows terminals
    parser = argparse.ArgumentParser(description="HireMate agent team (command line)")
    parser.add_argument("--cv", type=Path, default=SAMPLES_DIR / "sample_cv.txt")
    parser.add_argument("--job", type=Path, default=None)
    parser.add_argument("--job-url", default="")
    parser.add_argument("--yes", action="store_true", help="non-interactive: confirm no gaps")
    args = parser.parse_args()
    if not args.job and not args.job_url:
        args.job = SAMPLES_DIR / "sample_job.txt"
    try:
        asyncio.run(run(args.cv, args.job, args.job_url, args.yes))
    except (LLMError, ToolError) as exc:
        print(f"\n✖ {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
