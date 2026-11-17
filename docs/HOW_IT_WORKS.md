# How HireMate works (a walkthrough for the CEO call)

This guide explains HireMate in plain English: what each part does, why it was designed
that way, what happens when things go wrong, and the questions you are likely to be asked.

---

## 1. The idea in one minute

A job seeker pastes their CV and a job post. Instead of one big AI prompt, HireMate uses a
**team of small, focused agents**, each with one job, like a small recruitment agency:

| Agent | Job | Uses an LLM? | Tools it calls |
|---|---|---|---|
| **CV Parser** | Turns the CV into structured data (skills, roles, education, projects) | Yes | `pdf_to_text` (for PDF uploads) |
| **Job Analyst** | Finds required skills, nice-to-haves, seniority and key words | Yes | `fetch_job_text` (for job links) |
| **Fit Scorer** | Scores the fit 0–100, lists matched and missing skills, suggests quick wins | Yes | `keyword_coverage` |
| **Human review** | Pauses and asks the user which gaps are really true | No, it's you | |
| **CV Writer** | Rewrites the CV for this job, using only true facts | Yes | |
| **Letter Writer** | Writes a short, specific cover letter | Yes | |
| **Critic** | Checks the work and sends weak drafts back (max 2 times) | Yes | `truth_check`, `keyword_coverage` |

**The key promise: the agents never invent experience.** That is what makes this trustworthy
compared with "ask ChatGPT to rewrite my CV".

---

## 2. What makes it *agentic* (not just a chatbot)

A chatbot answers one message at a time. HireMate is an **agent system** because:

1. **It plans and runs several steps by itself.** Seven nodes run in order, each passing
   structured data to the next.
2. **It uses tools.** Plain Python functions read PDFs, download job pages, count key words
   and check facts. Each tool call is shown on screen with a 🔧 icon.
3. **It checks its own work and loops.** The Critic scores the draft. If the score is below 80,
   the draft goes back to the CV Writer with feedback. You can watch this loop happen: the
   dashed arrow in the graph turns amber and the Critic card shows "Draft 1: 72 ↻ sent back".
4. **It knows when to stop and ask a human.** Before writing anything, it pauses
   (a LangGraph **interrupt**) and asks the user to confirm their skills.
5. **It recovers from failures.** If the AI service is busy, it waits and retries, switching to
   a backup model if needed. This is also shown live ("↻ Retrying in 2s because the AI
   service is busy…").

---

## 3. How a run flows, step by step

1. **The browser sends the CV and job** to the backend (`POST /api/runs`).
2. The backend **checks the input first** (is the CV long enough? is the PDF readable?) and
   **checks the rate limit** (10 runs per visitor per day). Bad input never spends AI quota.
3. The **LangGraph graph starts**. Each agent sends small progress messages (`started`,
   `thinking`, `tool`, `retry`, `done`). The backend streams these to the browser as
   **Server-Sent Events (SSE)**: one long HTTP response that delivers events as they happen.
4. After the Fit Scorer, the **human_review** node calls `interrupt(...)`. The graph stops.
   The server packs the run's full state into a **signed state token** (HMAC-SHA256) and sends
   it to the browser with the checklist. Nothing is kept in server memory.
5. The user ticks what is true (and can add a short note, e.g. "used Docker in a side project").
   The browser calls `POST /api/resume` with the token and the answer. The server checks the
   signature, loads the state back into the graph, and continues **from exactly where it paused**.
6. The CV Writer and Letter Writer run. Then the Critic reviews:
   - **Approved (80+)** → finish.
   - **Below 80, and retries left** → back to the CV Writer with the critic's feedback.
   - **Out of retries** → show the **best** draft so far, with the critic's notes.
7. The final **result** event arrives, and the browser shows four tabs: Fit score, Tailored CV,
   Cover letter and Critic report, with Copy and Download as PDF buttons.

---

## 4. How "never invent experience" is enforced

There are **four layers**, because one is not enough:

1. **Prompts.** Every writing agent gets a "golden rule": only use facts from the original CV
   and the confirmed facts.
2. **The human review.** The user decides which gaps are true. Only gaps that were actually
   offered can be confirmed (the backend ignores anything else).
3. **The declined list.** Skills the user did *not* tick are passed to the writers as
   "THE CANDIDATE DOES NOT HAVE: …", and to the critic as "their absence is correct".
4. **An automatic truth check in plain code** (not an LLM). If the new CV mentions a skill the
   user declined, the draft **fails automatically**, whatever the critic LLM thought. Other new
   wording (e.g. "machine learning" for a scikit-learn project) is passed to the critic to verify.

**Why have a non-LLM check?** LLMs can be persuaded or make mistakes. A simple rule written in
code can't. Using both gives flexibility *and* a hard safety line.

---

## 5. Why it is designed this way

| Decision | Why |
|---|---|
| **Several small agents, not one big prompt** | Each prompt is short and focused, so it's more reliable. Each step can be tested, shown on screen and improved alone. |
| **LangGraph** | The flow is a clear graph, with built-in pause/resume (interrupt + checkpointer) and loops (the critic retry). Easy to explain in a diagram. |
| **Structured output (Pydantic schemas)** | Agents pass clean, validated data to each other, never messy text that has to be guessed at. |
| **Gemini free tier** | Zero cost for a public demo. |
| **One small LLM wrapper (`llm.py`)** | All AI calls go through one file. Switching to OpenAI or Claude means changing only that file. Retries and backup models live there too. |
| **Model name in an environment variable** | Upgrade the model without touching code. |
| **SSE streaming** | Users see progress live instead of a spinner for 2 minutes. This is what shows the "thinking". |
| **Human-in-the-loop before writing** | Honesty and trust. Recruiters and candidates both care about accuracy. |
| **Critic with max 2 retries** | Better quality, but with a cap so cost and waiting time stay predictable. |
| **Rate limit (10 runs/IP/day)** | Protects the free AI quota on a public link. |
| **Stateless API with signed state tokens** | On serverless hosting (Vercel) each request may run on a different machine, so a paused run can't wait in memory. The browser holds the paused state, and the signature stops anyone editing it (e.g. adding skills that were never offered). Bonus: any number of servers can handle resumes. |
| **Browser "Save as PDF"** | The simplest *reliable* way to make a PDF: no extra server libraries, and fonts and special characters always work. |

---

## 6. What happens when something fails

| Failure | What the user sees | What the system does |
|---|---|---|
| AI service busy (503) or rate-limited (429) | "↻ Retrying in 2s because the AI service is busy…" in the timeline | Waits and retries, alternating between the main and backup model. A model that keeps failing is "rested" for 5 minutes. |
| Daily free AI quota used up | Friendly message: try again later | Stops trying that model for the day and uses the backup. |
| AI returns badly formatted JSON | A retry line in the timeline | Validation fails, so it retries automatically. |
| Job link blocked (e.g. LinkedIn) | "We couldn't read that job link. Please paste the text" | A second LangGraph interrupt pauses the run, the user pastes the text, and the run continues. |
| Scanned / unreadable PDF | "That PDF has almost no readable text… please paste the CV text" | Rejected **before** any AI is used. |
| Visitor used 10 runs today | "You've used all 10 free runs for today… come back tomorrow!" | HTTP 429 with a friendly message. |
| Backend cold start (free serverless hosting) | "Waking up the server…" if it takes more than a few seconds | The page pings `/api/health` as soon as it opens, to warm the server up early. |
| Paused for more than 2 hours, or a tampered state token | "This session has expired. Please start again." | The signature or age check fails, and nothing runs. |
| Connection drops mid-run | "We lost the connection to the server…" with a **Try again** button | |
| Any unexpected server error | "Something went wrong on our side. Please try again." | The real error is logged on the server. Users never see stack traces. |
| Critic never reaches 80 | Results with "Best of 3 drafts" and the critic's notes | Keeps the highest-scoring draft rather than the last one. |

---

## 7. Likely interview questions (with short answers)

**1. Why is this "agentic" and not just a prompt?**
It runs a multi-step plan by itself, calls tools, checks its own work and loops back when the
work isn't good enough. It also knows when to stop and ask a human. You can watch all of it live.

**2. How do you stop the AI from making things up?**
Four layers: strict prompts, the human confirmation step, telling the writers exactly which
skills the user does NOT have, and a plain-code truth check that automatically fails any
draft claiming a declined skill. The LLM can't override that last one.

**3. Why LangGraph instead of writing the loop yourself?**
It gives pause/resume (interrupt + checkpointer), conditional loops and streaming out of the
box. The flow is also a real graph I can draw and test. Writing that by hand means
reinventing state saving and resuming.

**4. How does the human-in-the-loop step work technically?**
The `human_review` node calls `interrupt()` and the graph stops. The server signs the graph's
state (HMAC) and sends it to the browser as a token. When the user answers, the browser sends
the token back. The server verifies it, loads the state into a fresh graph (`update_state`),
and resumes with `Command(resume=...)`. The backend keeps no memory between requests.

**5. What does the critic actually check, and why cap retries at 2?**
Truthfulness, key-word match, tone and length, each scored 0–100, plus two code tools
(`truth_check` and `keyword_coverage`). The cap keeps cost and waiting time predictable.
After that, we show the best draft with honest notes rather than loop forever.

**6. How would you scale this to many users?**
The API is already stateless (paused runs travel as signed tokens), so it runs on serverless
hosting and scales out automatically. Next: move rate-limit counts to Redis so all instances
share them, add a job queue for long runs, and use a paid model tier for capacity.

**7. How much does a run cost?**
About 6–9 LLM calls per run. On the free tier it costs nothing. On a paid "flash" model
it would be a fraction of a cent per run.

**8. What happens when the AI service is down or busy?**
The LLM wrapper retries with growing waits, switches to a backup model, and rests a failing
model for a few minutes. Every retry is shown to the user, so it never looks frozen.

**9. How did you test it?**
17 automated tests (pytest). They use a **fake LLM**, so they run in seconds with no API key.
They cover the full graph, the pause/resume, the critic loop and its 2-retry cap, the truth
check, rate limiting, blocked job links and bad PDFs. I also ran full end-to-end tests in a
real browser (desktop and mobile) against the real Gemini API.

**10. What would you build next?**
A side-by-side "what changed" view of the CV, saved applications, designed PDF templates,
claim-by-claim evidence links ("this bullet comes from line 4 of your CV"), and an evaluation
set of sample CVs to measure quality when prompts or models change.

---

## 8. Where things live in the code

| File | What it does |
|---|---|
| `backend/app/graph/builder.py` | Wires the 7 nodes into the LangGraph graph (start here) |
| `backend/app/graph/nodes.py` | The agents themselves, one function each |
| `backend/app/graph/prompts.py` | All system prompts in one place |
| `backend/app/tools.py` | The non-LLM tools (PDF, web fetch, key words, truth check) |
| `backend/app/llm.py` | The only file that talks to Gemini (retries, backup model) |
| `backend/app/main.py` | The API: start run, resume run, SSE streaming |
| `backend/app/ratelimit.py` | 10 runs per IP per day |
| `backend/app/statetoken.py` | Signs and checks the paused-run token (stateless resume) |
| `backend/cli.py` | Run the whole team from the terminal |
| `frontend/components/HireMateApp.tsx` | The page: landing → run → review → results |
| `frontend/lib/runState.ts` | Turns streamed events into what each card shows |
| `frontend/components/Timeline.tsx`, `GraphView.tsx` | The live timeline and the graph picture |
