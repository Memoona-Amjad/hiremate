"use client";

// The whole app on one page: landing → (inputs) → live agent run → human review → results.

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useReducer, useState } from "react";
import ReactMarkdown from "react-markdown";
import GraphView from "@/components/GraphView";
import InputForm from "@/components/InputForm";
import Results from "@/components/Results";
import { NeedJobText, ReviewStep } from "@/components/ReviewStep";
import Timeline from "@/components/Timeline";
import { FriendlyError, resumeRun, startRun, wakeUp } from "@/lib/api";
import { initialState, reducer } from "@/lib/runState";
import type { StreamEvent } from "@/lib/types";

const GITHUB_URL = "https://github.com/Memoona-Amjad/hiremate";

function friendly(err: unknown): string {
  return err instanceof FriendlyError ? err.message : "Something went wrong. Please try again.";
}

export default function HireMateApp() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [busy, setBusy] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [printDoc, setPrintDoc] = useState<"cv" | "letter" | null>(null);
  const [lastForm, setLastForm] = useState<FormData | null>(null);

  // Wake the (possibly sleeping) free-tier server as soon as someone opens the page.
  useEffect(() => {
    wakeUp(() => {}).catch(() => {});
  }, []);

  /** Run one SSE stream; detect if it ends without a proper final event. */
  const consume = useCallback(async (run: (onEvent: (e: StreamEvent) => void) => Promise<void>) => {
    let finished = false;
    setBusy(true);
    try {
      await run((e) => {
        if (e.event === "interrupt" || e.event === "result" || e.event === "error") finished = true;
        dispatch({ type: "stream", event: e });
      });
      if (!finished) throw new FriendlyError("The connection dropped before the agents finished. Please try again.");
    } finally {
      setBusy(false);
    }
  }, []);

  const start = useCallback(async (form: FormData, fromInputs: boolean) => {
    setLastForm(form);
    setInputError(null);
    dispatch({ type: "begin" });
    try {
      await wakeUp(() => dispatch({ type: "waking", value: true }));
      dispatch({ type: "waking", value: false });
      await consume((onEvent) => startRun(form, onEvent));
    } catch (err) {
      if (fromInputs && err instanceof FriendlyError && err.status === 400) {
        // Input problems (e.g. unreadable PDF): send the user back to fix them.
        setInputError(err.message);
        dispatch({ type: "goto", stage: "input" });
      } else {
        dispatch({ type: "fail", message: friendly(err) });
      }
    }
  }, [consume]);

  const runSample = () => {
    const form = new FormData();
    form.append("use_sample", "true");
    start(form, false);
  };

  const resume = async (answer: { confirmed?: string[]; notes?: Record<string, string>; job_text?: string }) => {
    if (!state.interrupt) return;
    const body = { ...answer, state_token: state.interrupt.state_token };
    dispatch({ type: "goto", stage: "running" });
    try {
      await consume((onEvent) => resumeRun(body, onEvent));
    } catch (err) {
      dispatch({ type: "fail", message: friendly(err) });
    }
  };

  // "Download as PDF": render a clean print-only copy, open the browser's print dialog
  // (users pick "Save as PDF"). This is the simplest reliable way and keeps fonts/Unicode intact.
  const downloadPdf = (doc: "cv" | "letter") => {
    const name = state.result?.cv.name || "HireMate";
    const oldTitle = document.title;
    document.title = `${name} - ${doc === "cv" ? "CV" : "Cover letter"}`;
    setPrintDoc(doc);
    window.addEventListener("afterprint", () => { document.title = oldTitle; }, { once: true });
    setTimeout(() => window.print(), 100);
  };

  const inRun = !["landing", "input"].includes(state.stage);

  return (
    <>
      <div className="no-print flex min-h-screen flex-col">
        <header className="border-b border-slate-200/70 bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <button type="button" onClick={() => dispatch({ type: "reset" })} className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-black text-white">H</span>
              <span className="text-lg font-bold tracking-tight text-slate-900">HireMate</span>
            </button>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="text-sm font-medium text-slate-600 hover:text-slate-900">
              GitHub ↗
            </a>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:py-12">
          <AnimatePresence mode="wait">
            {state.stage === "landing" && (
              <motion.section key="landing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="mx-auto max-w-3xl text-center">
                <p className="inline-block rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
                  A team of 6 AI agents + you
                </p>
                <h1 className="mt-4 text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl">
                  Tailor your job application <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">in minutes</span>, without inventing a thing.
                </h1>
                <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
                  Paste a CV and a job post. AI agents read both, score the fit, ask you to confirm before changing
                  anything, then write a tailored CV and cover letter. A critic agent checks the work before you see it.
                </p>
                <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                  <button type="button" onClick={runSample}
                    className="w-full rounded-xl bg-indigo-600 px-7 py-4 text-lg font-semibold text-white shadow-lg shadow-indigo-200 transition hover:-translate-y-0.5 hover:bg-indigo-700 sm:w-auto">
                    ▶ Try with a sample
                  </button>
                  <button type="button" onClick={() => dispatch({ type: "goto", stage: "input" })}
                    className="w-full rounded-xl border border-slate-300 bg-white px-7 py-4 text-lg font-semibold text-slate-800 transition hover:bg-slate-50 sm:w-auto">
                    Use my own
                  </button>
                </div>
                <p className="mt-3 text-sm text-slate-500">
                  Sample: Alex Morgan, Data Analyst → Junior Data Scientist at Northwind Analytics (fictional)
                </p>
                <div className="mt-12 grid gap-4 text-left sm:grid-cols-3">
                  {[
                    ["🧠", "Watch the agents think", "Every step, tool call and retry is shown live as it happens."],
                    ["✋", "You stay in control", "The agents pause and ask before using any skill your CV doesn't show."],
                    ["🔍", "Checked before you see it", "A critic scores truthfulness, key words, tone and length, and sends weak drafts back."],
                  ].map(([icon, title, text]) => (
                    <div key={title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="text-2xl">{icon}</div>
                      <h3 className="mt-2 font-bold text-slate-900">{title}</h3>
                      <p className="mt-1 text-sm text-slate-600">{text}</p>
                    </div>
                  ))}
                </div>
              </motion.section>
            )}

            {state.stage === "input" && (
              <InputForm key="input" error={inputError} onBack={() => dispatch({ type: "goto", stage: "landing" })}
                onSubmit={(form) => start(form, true)} />
            )}

            {inRun && (
              <motion.div key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
                {/* Left: graph + live timeline */}
                <aside className="space-y-3 lg:sticky lg:top-6 lg:self-start">
                  <GraphView state={state} />
                  <Timeline state={state} />
                  <p className="px-1 text-xs text-slate-400">Tip: tap a card to see every step, tool call and retry.</p>
                </aside>

                {/* Right: what needs attention now */}
                <div className={`space-y-4 ${state.stage === "review" || state.stage === "results" ? "order-first lg:order-none" : ""}`}>
                  {state.waking && (
                    <div className="flex items-center gap-3 rounded-2xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900">
                      <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-700" />
                      Waking up the server (about 30–60 seconds)… The free hosting sleeps when nobody is using it.
                    </div>
                  )}

                  {state.stage === "running" && !state.waking && (
                    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                      <div className="flex items-center gap-3">
                        <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
                        <h2 className="text-lg font-bold text-slate-900">The agents are working…</h2>
                      </div>
                      <p className="mt-2 text-sm text-slate-600">
                        {state.activeNode ? state.nodes[state.activeNode].message : "Starting up…"}
                      </p>
                      <p className="mt-4 text-xs text-slate-500">
                        This usually takes 1–2 minutes. It runs on free AI capacity, so you may see a few retries when it&apos;s busy.
                      </p>
                    </div>
                  )}

                  {state.stage === "review" && state.interrupt?.kind === "confirm_gaps" && (
                    <ReviewStep question={state.interrupt.question} gaps={state.interrupt.gaps} busy={busy}
                      onSubmit={(confirmed, notes) => resume({ confirmed, notes })} />
                  )}
                  {state.stage === "review" && state.interrupt?.kind === "need_job_text" && (
                    <NeedJobText message={state.interrupt.message} busy={busy}
                      onSubmit={(job_text) => resume({ job_text })} />
                  )}

                  {state.stage === "results" && state.result && (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="text-2xl font-bold text-slate-900">Your tailored application</h2>
                        <button type="button" onClick={() => dispatch({ type: "reset" })}
                          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50">
                          Start over
                        </button>
                      </div>
                      <Results result={state.result} onPdf={downloadPdf} />
                    </>
                  )}

                  {state.stage === "error" && (
                    <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6" role="alert">
                      <h2 className="text-lg font-bold text-rose-900">That didn&apos;t work</h2>
                      <p className="mt-1 text-sm text-rose-800">{state.error}</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {lastForm && (
                          <button type="button" onClick={() => start(lastForm, false)}
                            className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700">
                            Try again
                          </button>
                        )}
                        <button type="button" onClick={() => dispatch({ type: "reset" })}
                          className="rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-800">
                          Start over
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </main>

        <footer className="border-t border-slate-200/70 py-6 text-center text-xs text-slate-500">
          Built by Memoona Amjad · FastAPI + LangGraph + Gemini · Next.js ·{" "}
          <a href={GITHUB_URL} className="underline hover:text-slate-800" target="_blank" rel="noreferrer">Source</a>
        </footer>
      </div>

      {/* Only visible when printing ("Download as PDF") */}
      {state.result && printDoc && (
        <div className="print-only doc">
          {printDoc === "cv"
            ? <ReactMarkdown>{state.result.cv_markdown}</ReactMarkdown>
            : <div className="whitespace-pre-line leading-relaxed">{state.result.letter_text}</div>}
        </div>
      )}
    </>
  );
}
