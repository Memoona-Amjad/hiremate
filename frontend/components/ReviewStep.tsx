"use client";

// Human-in-the-loop step. The graph is paused (LangGraph interrupt) until the user answers.
// Rule: the writers may only use gaps the user ticks here. Nothing is invented.

import { motion } from "framer-motion";
import { useState } from "react";
import type { SkillGap } from "@/lib/types";

export function ReviewStep({ question, gaps, onSubmit, busy }: {
  question: string;
  gaps: SkillGap[];
  onSubmit: (confirmed: string[], notes: Record<string, string>) => void;
  busy: boolean;
}) {
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const confirmed = gaps.filter((g) => picked[g.skill]).map((g) => g.skill);

  return (
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border-2 border-amber-300 bg-white p-5 shadow-lg shadow-amber-100 sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">The agents paused for you</p>
      <h2 className="mt-1 text-xl font-bold text-slate-900">{question}</h2>
      <p className="mt-1 text-sm text-slate-600">
        The job asks for these, but your CV doesn&apos;t clearly show them. Tick only what is <b>true</b>.
        The writers will never add anything you leave unticked.
      </p>

      {gaps.length === 0 ? (
        <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          No gaps found. Your CV already covers everything the job lists.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {gaps.map((g) => (
            <li key={g.skill} className={`rounded-xl border p-3 transition-colors ${
              picked[g.skill] ? "border-indigo-300 bg-indigo-50/60" : "border-slate-200"}`}>
              <label className="flex cursor-pointer items-start gap-3">
                <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-indigo-600"
                  checked={!!picked[g.skill]}
                  onChange={(e) => setPicked({ ...picked, [g.skill]: e.target.checked })} />
                <span>
                  <span className="font-semibold text-slate-900">{g.skill}</span>
                  <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${
                    g.importance.toLowerCase().startsWith("req")
                      ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>
                    {g.importance}
                  </span>
                  <span className="mt-0.5 block text-sm text-slate-600">{g.why_it_matters}</span>
                </span>
              </label>
              {picked[g.skill] && (
                <input type="text" maxLength={300} placeholder={`Optional: how have you used ${g.skill}? (helps the writer be specific)`}
                  value={notes[g.skill] ?? ""} onChange={(e) => setNotes({ ...notes, [g.skill]: e.target.value })}
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
              )}
            </li>
          ))}
        </ul>
      )}

      <button type="button" disabled={busy}
        onClick={() => onSubmit(confirmed, Object.fromEntries(confirmed.filter((s) => notes[s]?.trim()).map((s) => [s, notes[s].trim()])))}
        className="mt-5 w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-60 sm:w-auto">
        {confirmed.length ? `Continue with ${confirmed.length} confirmed` : "Continue: I have none of these"}
      </button>
    </motion.section>
  );
}

export function NeedJobText({ message, onSubmit, busy }: {
  message: string; onSubmit: (jobText: string) => void; busy: boolean;
}) {
  const [text, setText] = useState("");
  return (
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border-2 border-amber-300 bg-white p-5 shadow-lg sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">The Job Analyst needs your help</p>
      <h2 className="mt-1 text-xl font-bold text-slate-900">We couldn&apos;t read that job link</h2>
      <p className="mt-1 text-sm text-slate-600">
        {message} Many job sites block automated readers. Please copy the job description from the page and paste it here.
      </p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10}
        placeholder="Paste the full job description…"
        className="mt-4 w-full rounded-xl border border-slate-300 p-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
      <button type="button" disabled={busy || text.trim().length < 100} onClick={() => onSubmit(text)}
        className="mt-3 rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
        Continue
      </button>
      {text.trim().length > 0 && text.trim().length < 100 && (
        <p className="mt-2 text-xs text-slate-500">Please paste the full post (at least a few lines).</p>
      )}
    </motion.section>
  );
}
