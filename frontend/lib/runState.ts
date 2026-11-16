// Turns the stream of backend events into UI state (which card is lit, what it says, etc.).

import type { AgentEvent, InterruptPayload, NodeId, RunResult, StreamEvent } from "./types";

export const NODES: { id: NodeId; title: string; short: string; blurb: string }[] = [
  { id: "parse_cv", title: "CV Parser", short: "Parse CV", blurb: "Reads your CV into structured data" },
  { id: "analyze_job", title: "Job Analyst", short: "Job", blurb: "Finds what the employer really needs" },
  { id: "score_fit", title: "Fit Scorer", short: "Fit", blurb: "Scores the match and spots gaps" },
  { id: "human_review", title: "Your Review", short: "You", blurb: "You confirm what's true" },
  { id: "tailor_cv", title: "CV Writer", short: "Tailor", blurb: "Rewrites the CV for this job" },
  { id: "write_cover_letter", title: "Letter Writer", short: "Letter", blurb: "Writes a short, specific letter" },
  { id: "critic", title: "Critic", short: "Critic", blurb: "Checks truth, key words, tone, length" },
];

export type NodeStatus = "idle" | "active" | "waiting" | "retry" | "done" | "error";

export interface NodeState {
  status: NodeStatus;
  message: string;
  log: AgentEvent[];
}

export type Stage = "landing" | "input" | "running" | "review" | "results" | "error";

export interface RunState {
  stage: Stage;
  runId: string | null;
  nodes: Record<NodeId, NodeState>;
  activeNode: NodeId | null;
  criticRetries: number;
  criticScores: { draft: number; score: number; passed: boolean }[];
  interrupt: InterruptPayload | null;
  result: RunResult | null;
  error: string | null;
  waking: boolean;
}

function freshNodes(): Record<NodeId, NodeState> {
  return Object.fromEntries(
    NODES.map((n) => [n.id, { status: "idle", message: n.blurb, log: [] }]),
  ) as unknown as Record<NodeId, NodeState>;
}

export const initialState: RunState = {
  stage: "landing",
  runId: null,
  nodes: freshNodes(),
  activeNode: null,
  criticRetries: 0,
  criticScores: [],
  interrupt: null,
  result: null,
  error: null,
  waking: false,
};

export type Action =
  | { type: "goto"; stage: Stage }
  | { type: "begin" }
  | { type: "waking"; value: boolean }
  | { type: "stream"; event: StreamEvent }
  | { type: "fail"; message: string }
  | { type: "reset" };

function applyAgentEvent(state: RunState, e: AgentEvent): RunState {
  const node = state.nodes[e.node];
  if (!node) return state;
  // When the graph resumes after the review pause, LangGraph re-runs that node from the top,
  // so its "started" message arrives twice. Skip exact repeats.
  const last = node.log[node.log.length - 1];
  if (last && last.type === e.type && last.message === e.message) return state;
  let status: NodeStatus = node.status;
  let { criticRetries, criticScores } = state;

  if (e.type === "started") status = e.node === "human_review" ? "waiting" : "active";
  else if (e.type === "done") status = "done";
  else if (e.type === "retry" && e.node === "critic") status = "retry";

  // Track the critic's verdict on each draft, so the loop is visible.
  if (e.node === "critic" && (e.type === "done" || e.type === "retry")) {
    const score = Number(e.data?.score ?? 0);
    const passed = e.type === "done" && e.data?.passed !== false;
    criticScores = [...criticScores, { draft: criticScores.length + 1, score, passed }];
    if (e.type === "retry") criticRetries += 1;
  }

  const nodes = { ...state.nodes, [e.node]: { status, message: e.message, log: [...node.log, e] } };

  // A new draft after a critic retry: dim the writer/letter cards until they run again.
  if (e.node === "tailor_cv" && e.type === "started" && state.criticRetries > 0) {
    nodes.write_cover_letter = { ...nodes.write_cover_letter, status: "idle" };
  }

  const isActive = status === "active" || status === "waiting";
  return {
    ...state,
    nodes,
    criticRetries,
    criticScores,
    activeNode: isActive ? e.node : state.activeNode === e.node ? null : state.activeNode,
  };
}

export function reducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "goto":
      return { ...state, stage: action.stage };
    case "reset":
      return initialState;
    case "begin":
      return { ...initialState, stage: "running" };
    case "waking":
      return { ...state, waking: action.value };
    case "fail": {
      const nodes = { ...state.nodes };
      if (state.activeNode) nodes[state.activeNode] = { ...nodes[state.activeNode], status: "error" };
      return { ...state, stage: "error", error: action.message, nodes, waking: false };
    }
    case "stream": {
      const ev = action.event;
      switch (ev.event) {
        case "run":
          return { ...state, runId: ev.data.run_id, waking: false };
        case "agent":
          return applyAgentEvent(state, ev.data);
        case "interrupt":
          return { ...state, stage: "review", interrupt: ev.data };
        case "result":
          return { ...state, stage: "results", result: ev.data, activeNode: null, interrupt: null };
        case "error":
          return reducer(state, { type: "fail", message: ev.data.message });
      }
    }
  }
  return state;
}
