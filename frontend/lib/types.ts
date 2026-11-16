// Shapes of the data the backend streams to us. Mirrors backend/app/schemas.py.

export type NodeId =
  | "parse_cv"
  | "analyze_job"
  | "score_fit"
  | "human_review"
  | "tailor_cv"
  | "write_cover_letter"
  | "critic";

export type AgentEventType = "started" | "thinking" | "tool" | "retry" | "done";

export interface AgentEvent {
  node: NodeId;
  type: AgentEventType;
  message: string;
  data?: Record<string, unknown>;
}

export interface SkillGap {
  skill: string;
  importance: string;
  why_it_matters: string;
}

export interface KeywordCoverage {
  percent: number;
  found: string[];
  missing: string[];
}

export interface FitResult {
  score: number;
  summary: string;
  matched_skills: string[];
  missing_skills: SkillGap[];
  quick_wins: string[];
  keyword_coverage: KeywordCoverage;
}

export interface CriticResult {
  score: number;
  truthfulness: number;
  keyword_match: number;
  tone: number;
  length: number;
  issues: string[];
  feedback: string;
  draft: number;
  passed: boolean;
  threshold: number;
  unsupported_skills: string[];
  unverified_skills: string[];
  keyword_coverage: KeywordCoverage;
  keyword_coverage_before: number;
  letter_words: number;
  final_after_retries?: boolean;
}

export interface RunResult {
  cv: { name: string; headline: string };
  job: { title: string; company: string; seniority: string };
  fit: FitResult;
  confirmed: string[];
  cv_markdown: string;
  letter_text: string;
  critic: CriticResult;
  critic_history: CriticResult[];
  draft: number;
}

export type InterruptPayload =
  | { kind: "confirm_gaps"; question: string; gaps: SkillGap[] }
  | { kind: "need_job_text"; message: string };

// Events from the SSE stream, already parsed.
export type StreamEvent =
  | { event: "run"; data: { run_id: string; nodes: NodeId[] } }
  | { event: "agent"; data: AgentEvent }
  | { event: "interrupt"; data: InterruptPayload }
  | { event: "result"; data: RunResult }
  | { event: "error"; data: { message: string } };
