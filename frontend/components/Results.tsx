"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { RunResult } from "@/lib/types";

type Tab = "fit" | "cv" | "letter" | "critic";
const TABS: { id: Tab; label: string; short: string }[] = [
  { id: "fit", label: "Fit score", short: "Fit" },
  { id: "cv", label: "Tailored CV", short: "CV" },
  { id: "letter", label: "Cover letter", short: "Letter" },
  { id: "critic", label: "Critic report", short: "Critic" },
];

function scoreColour(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

/** Half-circle gauge, 0-100. */
function Gauge({ score, label }: { score: number; label: string }) {
  const r = 70;
  const circumference = Math.PI * r;
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 180 105" className="w-48">
        <path d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke="#e2e8f0" strokeWidth={16} strokeLinecap="round" />
        <motion.path d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke={scoreColour(score)} strokeWidth={16}
          strokeLinecap="round" strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - score / 100) }}
          transition={{ duration: 1.2, ease: "easeOut" }} />
        <text x={90} y={88} textAnchor="middle" fontSize={34} fontWeight={800} fill="#0f172a">{score}</text>
      </svg>
      <span className="-mt-1 text-sm font-medium text-slate-500">{label}</span>
    </div>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-slate-700">{label}</span><b>{value}</b></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
        <motion.div className="h-full rounded-full" style={{ background: scoreColour(value) }}
          initial={{ width: 0 }} animate={{ width: `${value}%` }} transition={{ duration: 0.8 }} />
      </div>
    </div>
  );
}

function Chips({ items, tone }: { items: string[]; tone: "good" | "bad" | "info" }) {
  const cls = { good: "bg-emerald-50 text-emerald-800 border-emerald-200",
    bad: "bg-rose-50 text-rose-800 border-rose-200", info: "bg-indigo-50 text-indigo-800 border-indigo-200" }[tone];
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((s) => <span key={s} className={`rounded-full border px-2.5 py-0.5 text-sm ${cls}`}>{s}</span>)}
    </div>
  );
}

function ActionButtons({ text, onPdf }: { text: string; onPdf: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      alert("Your browser blocked copying. Please select the text and copy it manually.");
    }
  };
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" onClick={copy}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
        {copied ? "✓ Copied" : "Copy text"}
      </button>
      <button type="button" onClick={onPdf}
        className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700">
        Download as PDF
      </button>
    </div>
  );
}

export default function Results({ result, onPdf }: {
  result: RunResult;
  onPdf: (doc: "cv" | "letter") => void;
}) {
  const [tab, setTab] = useState<Tab>("fit");
  const { fit, critic } = result;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex overflow-x-auto border-b border-slate-200 px-2" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            aria-label={t.label}
            className={`relative flex-1 shrink-0 px-3 py-3 sm:flex-none text-sm font-semibold transition sm:px-4 ${
              tab === t.id ? "text-indigo-700" : "text-slate-500 hover:text-slate-800"}`}>
            <span className="sm:hidden">{t.short}</span>
            <span className="hidden sm:inline">{t.label}</span>
            {tab === t.id && <motion.span layoutId="tab-underline" className="absolute inset-x-2 bottom-0 h-0.5 rounded bg-indigo-600" />}
          </button>
        ))}
      </div>

      <div className="p-4 sm:p-6">
        {tab === "fit" && (
          <div className="space-y-5">
            <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
              <Gauge score={fit.score} label="Fit score" />
              <div>
                <h3 className="text-lg font-bold text-slate-900">
                  {result.job.title}{result.job.company ? ` at ${result.job.company}` : ""}
                </h3>
                <p className="mt-1 text-sm text-slate-600">{fit.summary}</p>
                <p className="mt-2 text-sm text-slate-600">
                  Job key words in your CV: <b>{critic.keyword_coverage_before}%</b> before →{" "}
                  <b className="text-emerald-700">{critic.keyword_coverage.percent}%</b> after tailoring
                </p>
              </div>
            </div>
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700">Matched skills</h4>
              <Chips items={fit.matched_skills} tone="good" />
            </div>
            {result.confirmed.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-700">Gaps you confirmed you have</h4>
                <Chips items={result.confirmed.map((s) => `✓ ${s}`)} tone="info" />
              </div>
            )}
            {fit.missing_skills.some((g) => !result.confirmed.includes(g.skill)) && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-700">Still missing (left out, not invented)</h4>
                <Chips items={fit.missing_skills.filter((g) => !result.confirmed.includes(g.skill)).map((g) => g.skill)} tone="bad" />
              </div>
            )}
            {fit.quick_wins.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-700">Quick wins</h4>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {fit.quick_wins.map((w) => <li key={w}>{w}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        {tab === "cv" && (
          <div>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-500">Written using only your CV and what you confirmed.</p>
              <ActionButtons text={result.cv_markdown} onPdf={() => onPdf("cv")} />
            </div>
            <article className="doc rounded-xl border border-slate-200 p-4 sm:p-8">
              <ReactMarkdown>{result.cv_markdown}</ReactMarkdown>
            </article>
          </div>
        )}

        {tab === "letter" && (
          <div>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-500">{critic.letter_words} words</p>
              <ActionButtons text={result.letter_text} onPdf={() => onPdf("letter")} />
            </div>
            <article className="doc whitespace-pre-line rounded-xl border border-slate-200 p-4 leading-relaxed text-slate-800 sm:p-8">
              {result.letter_text}
            </article>
          </div>
        )}

        {tab === "critic" && (
          <div className="space-y-5">
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <Gauge score={critic.score} label="Critic score" />
              <div className="text-sm text-slate-600">
                {critic.passed ? (
                  <p className="font-semibold text-emerald-700">✓ Approved on draft {critic.draft} (needs {critic.threshold}+)</p>
                ) : (
                  <p className="font-semibold text-amber-700">
                    Best of {result.critic_history.length} drafts. The critic still had notes, see below.
                  </p>
                )}
                <p className="mt-1">
                  The critic reviewed {result.critic_history.length} draft{result.critic_history.length > 1 ? "s" : ""}:{" "}
                  {result.critic_history.map((h) => `${h.score}`).join(" → ")}
                </p>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Bar label="Truthfulness" value={critic.truthfulness} />
              <Bar label="Key-word match" value={critic.keyword_match} />
              <Bar label="Tone" value={critic.tone} />
              <Bar label="Length" value={critic.length} />
            </div>
            <div className="rounded-xl bg-slate-50 p-4 text-sm">
              <h4 className="font-semibold text-slate-800">Automatic truth check</h4>
              {critic.unsupported_skills.length ? (
                <p className="mt-1 text-rose-700">Claims skills you said you don&apos;t have: {critic.unsupported_skills.join(", ")}</p>
              ) : (
                <p className="mt-1 text-emerald-700">✓ No skills you declined were added.</p>
              )}
              {critic.unverified_skills?.length > 0 && (
                <p className="mt-1 text-slate-600">
                  Reworded skills the critic double-checked against your CV: {critic.unverified_skills.join(", ")}
                </p>
              )}
            </div>
            {critic.issues.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-700">Notes from the critic</h4>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {critic.issues.map((i) => <li key={i}>{i}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
