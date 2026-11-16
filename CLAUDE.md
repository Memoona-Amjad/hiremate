# HireMate — a team of AI agents that tailors a job application

**This is the flagship project. Give it the most polish.**

---

## How to work (read this first)
- **Work through ALL milestones below, in order, until the project is deployed.**
  Do not stop to ask for approval between steps or milestones.
- After each milestone: test it yourself (run it, run tests, run the build),
  fix any problems, then **commit and push**, give a 2-line progress update, and
  go straight on to the next milestone.
- **Only stop and ask the user when you truly need something from them**, for example:
  an API key in `.env`, a login, a button they must click on a hosting site,
  a decision this file does not cover, or something still failing after a few tries.
  When you ask, give exact numbered steps (what to open, what to click, what to paste
  back to you), then continue once they reply.
- **At the very start**, send one message listing everything you will need from the user
  for the whole project (keys, accounts), so they can get it all ready at once.
- **When the last milestone is done**, give the user: the **live demo link**, the
  GitHub link, and a short list of anything left as TODO.

## Who this is for
- Owner: **Memoona Amjad**. GitHub username: **Memoona-Amjad**
- This is one of 3 **agentic AI** portfolio projects being sent to a **CEO** in a few days.
- The audience is a busy CEO first and engineers second. The project must:
  1. Work end to end with a **live demo link**.
  2. Have a **"Try with sample data"** option, so nobody needs to upload their own files.
  3. Show the **agent's thinking on screen** (steps, tool calls, retries).
     This is what proves it is agentic, not just a chatbot.
- We only have a few days: **working end to end first, polish second.**
  Do not add features that are not in this file without asking.

## Git and GitHub
- Git identity is already set to Memoona Amjad. Do not change git config.
- This folder is its own repo. Remote: `https://github.com/Memoona-Amjad/hiremate.git`
- If it is not a git repo yet: `git init`, `git branch -M main`, add the remote.
- Create `.gitignore` **before the first commit** (`.env`, `node_modules`, `.venv`,
  `__pycache__`, `.next`, build outputs, OS files).
- Small commits with clear messages (e.g. `feat: add fit scoring agent`).
- **Do not add any `Co-Authored-By` line or "Generated with Claude Code" line**
  to commits, PRs or READMEs. Plain commit messages only.
- Never force push. The first push may open a GitHub login window: tell the user to
  log in as Memoona-Amjad.

## Secrets
- Never put API keys in code or commits. Read them from `.env`.
- Keep an up-to-date `.env.example` with empty values.
- The user fills in `.env` by hand. Do not read or print `.env`.

## LLM
- Use **Google Gemini** (free tier) through its official SDK.
- Model name comes from an env variable (`LLM_MODEL`), never hard-coded.
  Check the current Gemini docs for the right free-tier "flash" model and SDK.
- Keep LLM calls behind one small wrapper module, so the provider can be swapped.
- Protect the free tier on the public demo: per-IP rate limit
  (about 10 runs per IP per day) with a friendly message when it is hit.

## Code quality (so Memoona can explain it)
- Simple, readable code with short plain-English comments on the important parts.
- Type hints in Python, TypeScript in JS projects.
- Friendly error messages in the UI (never show raw stack traces).
- Check the latest docs for any library whose API may have changed.

## The repo must include
1. `README.md`, in this order: one-line pitch + **Live demo** link + demo GIF/screenshot
   placeholder; the problem (2–3 lines, business language); what the agent does
   (short numbered steps); architecture diagram in **Mermaid**; tech stack;
   run locally (Windows commands); honest "Limitations and next steps".
2. `docs/HOW_IT_WORKS.md`: a simple-English walkthrough for Memoona to prepare for a call
   with the CEO: what each agent/tool does, why it is designed this way, what happens when
   something fails, and 8–10 likely interview questions with short answers.

## Environment
- Windows 11, VS Code, Python 3.12, Node, Git. Give Windows-friendly commands.
- Python: use a `.venv` virtual environment and `requirements.txt`.

---
# Project spec

## Pitch
Paste a CV and a job post. A team of AI agents reads both, scores the fit,
asks you to confirm before changing anything, then writes a tailored CV and
cover letter — and a critic agent checks the work before you see it.

## Stack
- Backend: Python 3.12, **FastAPI**, **LangGraph**, Pydantic, Gemini SDK, `pypdf`,
  `httpx` (+ a readability/HTML-to-text library) for job links.
- Frontend: **Next.js (App Router) + TypeScript + Tailwind**, framer-motion for animations.
- Streaming: Server-Sent Events (SSE) from backend to frontend, so agent steps show live.
- Hosting: backend on **Render** (free), frontend on **Vercel** (free).
- Folders: `backend/` and `frontend/` in the same repo.

## The agent graph (LangGraph)
1. `parse_cv` — turn the CV (PDF upload or pasted text) into structured data
   (skills, experience, education, projects).
2. `analyze_job` — job text (pasted, or fetched from a link) → required skills,
   nice-to-haves, seniority, key words.
   If fetching the link fails (many job sites block bots), ask the user to paste the text.
3. `score_fit` — fit score 0–100, matched skills, missing skills, quick wins.
4. `human_review` — **LangGraph interrupt**. Show the gaps and ask the user:
   "Which of these do you actually have experience with?" The user ticks boxes.
   **Rule: agents must never invent experience the user did not confirm.**
5. `tailor_cv` — rewrite the CV for this job using only true, confirmed facts.
6. `write_cover_letter` — short, specific cover letter.
7. `critic` — reviews the CV + letter (truthfulness, keyword match, tone, length) and gives
   a score. If the score is below a threshold, send it back to `tailor_cv` with feedback.
   **Max 2 retries.** This loop must be visible in the UI.

Every node emits events (`started`, `thinking`, `done`, `retry`) with a short
human-readable message, streamed to the UI.

## UI
- Landing section: pitch + big **"Try with a sample"** button (a sample CV + sample
  job post are bundled), plus "Use my own" (PDF upload or paste; job link or paste).
- **Live agent timeline**: each agent is a card that lights up when it runs, shows a
  one-line status, and shows the critic's retry loop clearly.
  Also show a small graph view of the nodes with the active one highlighted.
- Review step: the human-review checklist.
- Results tabs: Fit score (gauge + matched/missing skills), Tailored CV,
  Cover letter, Critic report. Copy buttons + **Download as PDF**
  (choose the simplest reliable way).
- Render free tier sleeps: if the first request is slow, show "Waking up the server
  (about 30–60 seconds)…" instead of looking broken.
- Clean, modern, professional look. Must look good on mobile too.

## Milestones (test, commit and push after each, then continue)
1. Backend graph runs from the command line on the bundled sample CV + job and prints results.
2. FastAPI endpoints + SSE streaming + the human-review interrupt/resume.
3. Next.js UI: sample flow, live timeline, review step, results tabs, PDF download.
4. Rate limiting, error handling, loading/cold-start states, mobile check.
5. README + `docs/HOW_IT_WORKS.md`.
6. **Deploy the backend to Render** (add a `render.yaml` so it can be deployed as a
   Blueprint; Python version pinned; CORS set for the Vercel domain).
   Ask the user for the clicks they must do on render.com and for the backend URL.
7. **Deploy the frontend to Vercel** (Vercel CLI via `npx vercel` or the dashboard,
   whichever is simpler; set `NEXT_PUBLIC_API_URL` and the other env vars).
   Ask the user for any login or clicks needed.
8. **Test the live site** end to end (sample flow), fix anything broken, put the live
   link in the README, push, and give the user the **live demo link**.
