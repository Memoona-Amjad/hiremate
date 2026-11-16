"use client";

// The live agent timeline: one card per agent. A card lights up while its agent runs,
// shows a one-line status, and can be opened to see every step, tool call and retry.

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { NODES, type NodeState, type RunState } from "@/lib/runState";
import type { AgentEvent } from "@/lib/types";

const CARD_STYLE: Record<string, string> = {
  idle: "border-slate-200 bg-white opacity-60",
  active: "border-indigo-400 bg-indigo-50/60 shadow-md shadow-indigo-100",
  waiting: "border-amber-400 bg-amber-50 shadow-md shadow-amber-100",
  retry: "border-amber-400 bg-amber-50 shadow-md shadow-amber-100",
  done: "border-emerald-200 bg-white",
  error: "border-red-300 bg-red-50",
};

const EVENT_ICON: Record<AgentEvent["type"], string> = {
  started: "▶",
  thinking: "💭",
  tool: "🔧",
  retry: "↻",
  done: "✓",
};

function StatusDot({ status }: { status: NodeState["status"] }) {
  if (status === "active") {
    return (
      <span className="relative flex h-3 w-3">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-indigo-500" />
      </span>
    );
  }
  const colour = {
    idle: "bg-slate-300",
    waiting: "bg-amber-500 animate-pulse",
    retry: "bg-amber-500 animate-pulse",
    done: "bg-emerald-500",
    error: "bg-red-500",
  }[status];
  return <span className={`inline-flex h-3 w-3 rounded-full ${colour}`} />;
}

function AgentCard({ index, title, node, extra }: {
  index: number; title: string; node: NodeState; extra?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const steps = node.log.length;
  return (
    <motion.li layout
      className={`rounded-xl border px-3 py-2.5 transition-colors duration-300 ${CARD_STYLE[node.status]}`}>
      <button type="button" onClick={() => steps && setOpen(!open)}
        className="flex w-full items-start gap-3 text-left" aria-expanded={open}>
        <span className="mt-1.5"><StatusDot status={node.status} /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-slate-900">
              <span className="mr-1.5 text-slate-400">{index}.</span>{title}
            </span>
            {steps > 0 && (
              <span className="shrink-0 text-xs text-slate-400">{open ? "hide" : `${steps} steps`}</span>
            )}
          </span>
          <AnimatePresence mode="wait">
            <motion.span key={node.message} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
              className="mt-0.5 block text-sm text-slate-600">
              {node.message}
            </motion.span>
          </AnimatePresence>
          {extra}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} className="ml-6 mt-2 space-y-1 overflow-hidden border-l border-slate-200 pl-3">
            {node.log.map((e, i) => (
              <li key={i} className={`text-xs leading-relaxed ${
                e.type === "retry" ? "text-amber-700" : e.type === "tool" ? "font-mono text-indigo-700" : "text-slate-600"}`}>
                <span className="mr-1">{EVENT_ICON[e.type]}</span>{e.message}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

export default function Timeline({ state }: { state: RunState }) {
  return (
    <ol className="space-y-2">
      {NODES.map((n, i) => (
        <AgentCard key={n.id} index={i + 1} title={n.title} node={state.nodes[n.id]}
          extra={n.id === "critic" && state.criticScores.length > 0 ? (
            // The critic loop, made visible: one chip per draft it reviewed.
            <span className="mt-2 flex flex-wrap items-center gap-1.5">
              {state.criticScores.map((c) => (
                <span key={c.draft} className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  c.passed ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
                  Draft {c.draft}: {c.score}/100{" "}
                  {c.passed ? "✓ approved" : c.draft > 2 ? "· retries used up" : "↻ sent back"}
                </span>
              ))}
            </span>
          ) : undefined}
        />
      ))}
    </ol>
  );
}
