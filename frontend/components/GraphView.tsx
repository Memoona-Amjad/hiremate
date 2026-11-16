"use client";

// A small picture of the agent graph. The running agent glows; the critic → writer
// arrow lights up amber whenever the critic sends a draft back.

import { motion } from "framer-motion";
import { NODES, type RunState } from "@/lib/runState";

const W = 440;
const STEP = W / NODES.length;
const Y = 74;
const R = 17;

const STATUS_FILL: Record<string, string> = {
  idle: "#f1f5f9",
  active: "#6366f1",
  waiting: "#f59e0b",
  retry: "#f59e0b",
  done: "#10b981",
  error: "#ef4444",
};

export default function GraphView({ state }: { state: RunState }) {
  const x = (i: number) => STEP * i + STEP / 2;
  const tailorX = x(4);
  const criticX = x(6);
  const looping = state.nodes.critic.status === "retry";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="mb-1 flex items-center justify-between px-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Agent graph</span>
        <span className="text-xs text-slate-500">
          Critic retries: <b className={state.criticRetries ? "text-amber-600" : ""}>{state.criticRetries}</b>/2
        </span>
      </div>
      <svg viewBox={`0 0 ${W} 118`} className="h-auto w-full" role="img" aria-label="Agent graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
          </marker>
          <marker id="arrow-amber" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#f59e0b" />
          </marker>
        </defs>

        {/* Straight edges between neighbours */}
        {NODES.slice(0, -1).map((n, i) => (
          <line key={n.id} x1={x(i) + R + 2} y1={Y} x2={x(i + 1) - R - 4} y2={Y}
            stroke="#cbd5e1" strokeWidth={2} markerEnd="url(#arrow)" />
        ))}

        {/* The critic's retry loop: critic → tailor_cv */}
        <motion.path
          d={`M ${criticX} ${Y - R - 2} C ${criticX} ${Y - 62}, ${tailorX} ${Y - 62}, ${tailorX} ${Y - R - 4}`}
          fill="none"
          strokeWidth={2}
          strokeDasharray="5 4"
          animate={{ stroke: looping ? "#f59e0b" : "#cbd5e1", strokeDashoffset: looping ? [0, -18] : 0 }}
          transition={looping ? { duration: 0.6, repeat: Infinity, ease: "linear" } : { duration: 0.3 }}
          markerEnd={looping ? "url(#arrow-amber)" : "url(#arrow)"}
        />
        <text x={(tailorX + criticX) / 2} y={20} textAnchor="middle" fontSize={11}
          fill={looping ? "#d97706" : "#94a3b8"} fontWeight={600}>
          {"retry if score < 80 (max 2)"}
        </text>

        {NODES.map((n, i) => {
          const s = state.nodes[n.id].status;
          const on = s === "active" || s === "waiting" || s === "retry";
          return (
            <g key={n.id}>
              {on && (
                <motion.circle cx={x(i)} cy={Y} r={R} fill={STATUS_FILL[s]}
                  initial={{ opacity: 0.5, scale: 1 }}
                  animate={{ opacity: 0, scale: 1.7 }}
                  transition={{ duration: 1.4, repeat: Infinity }}
                  style={{ transformOrigin: `${x(i)}px ${Y}px` }} />
              )}
              <circle cx={x(i)} cy={Y} r={R} fill={STATUS_FILL[s]}
                stroke={s === "idle" ? "#cbd5e1" : "white"} strokeWidth={2} />
              <text x={x(i)} y={Y + 5} textAnchor="middle" fontSize={12} fontWeight={700}
                fill={s === "idle" ? "#64748b" : "white"}>
                {s === "done" ? "✓" : i + 1}
              </text>
              <text x={x(i)} y={Y + R + 20} textAnchor="middle" fontSize={11}
                fill={on ? "#0f172a" : "#64748b"} fontWeight={on ? 700 : 500}>
                {n.short}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
