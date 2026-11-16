"use client";

import { motion } from "framer-motion";
import { useState } from "react";

function Toggle<T extends string>({ value, options, onChange }: {
  value: T; options: { id: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg bg-slate-100 p-1">
      {options.map((o) => (
        <button key={o.id} type="button" onClick={() => onChange(o.id)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition ${
            value === o.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const field =
  "w-full rounded-xl border border-slate-300 bg-white p-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100";

export default function InputForm({ onSubmit, onBack, error }: {
  onSubmit: (form: FormData) => void;
  onBack: () => void;
  error: string | null;
}) {
  const [cvMode, setCvMode] = useState<"paste" | "pdf">("paste");
  const [jobMode, setJobMode] = useState<"paste" | "link">("paste");
  const [cvText, setCvText] = useState("");
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [jobText, setJobText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (cvMode === "paste" && cvText.trim().length < 100) return setLocalError("Please paste your full CV (at least a few lines).");
    if (cvMode === "pdf" && !cvFile) return setLocalError("Please choose a PDF file for your CV.");
    if (cvFile && cvFile.size > 5 * 1024 * 1024) return setLocalError("That PDF is larger than 5 MB.");
    if (jobMode === "paste" && jobText.trim().length < 100) return setLocalError("Please paste the full job description.");
    if (jobMode === "link" && !/^https?:\/\//.test(jobUrl.trim())) return setLocalError("Please enter a job link starting with http.");

    const form = new FormData();
    if (cvMode === "pdf" && cvFile) form.append("cv_file", cvFile);
    else form.append("cv_text", cvText);
    if (jobMode === "link") form.append("job_url", jobUrl.trim());
    else form.append("job_text", jobText);
    onSubmit(form);
  };

  const shownError = localError ?? error;
  return (
    <motion.form onSubmit={submit} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-4xl space-y-5">
      <button type="button" onClick={onBack} className="text-sm text-slate-500 hover:text-slate-800">← Back</button>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-bold text-slate-900">Your CV</h2>
            <Toggle value={cvMode} onChange={setCvMode} options={[{ id: "paste", label: "Paste" }, { id: "pdf", label: "Upload PDF" }]} />
          </div>
          {cvMode === "paste" ? (
            <textarea rows={12} value={cvText} onChange={(e) => setCvText(e.target.value)} className={field}
              placeholder="Paste your CV text here…" />
          ) : (
            <label className="flex h-[17.5rem] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 p-4 text-center hover:border-indigo-400">
              <span className="text-3xl">📄</span>
              <span className="mt-2 text-sm font-medium text-slate-700">{cvFile ? cvFile.name : "Choose a PDF (max 5 MB)"}</span>
              <span className="mt-1 text-xs text-slate-500">Text-based PDFs work best (not scanned images)</span>
              <input type="file" accept="application/pdf,.pdf" className="sr-only"
                onChange={(e) => setCvFile(e.target.files?.[0] ?? null)} />
            </label>
          )}
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-bold text-slate-900">The job</h2>
            <Toggle value={jobMode} onChange={setJobMode} options={[{ id: "paste", label: "Paste" }, { id: "link", label: "Link" }]} />
          </div>
          {jobMode === "paste" ? (
            <textarea rows={12} value={jobText} onChange={(e) => setJobText(e.target.value)} className={field}
              placeholder="Paste the job description here…" />
          ) : (
            <div className="space-y-2">
              <input type="url" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} className={field}
                placeholder="https://…" />
              <p className="text-xs text-slate-500">
                Some job sites (like LinkedIn) block automated readers. If that happens, the agent will ask you to paste the text.
              </p>
            </div>
          )}
        </div>
      </div>
      {shownError && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700" role="alert">{shownError}</p>}
      <div className="flex justify-end">
        <button type="submit" className="w-full rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white shadow-sm hover:bg-indigo-700 sm:w-auto">
          Run the agents →
        </button>
      </div>
    </motion.form>
  );
}
