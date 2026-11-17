// Talks to the FastAPI backend. Streams Server-Sent Events over fetch (EventSource
// only supports GET, but starting a run is a POST with a file upload).

import type { StreamEvent } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** A friendly error we can show the user as-is. */
export class FriendlyError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

/**
 * Ping the backend until it answers. Render's free tier sleeps when idle, so the first
 * request can take 30-60 seconds. `onSlow` fires if it takes longer than a few seconds.
 */
export async function wakeUp(onSlow: () => void, timeoutMs = 90_000): Promise<void> {
  const slowTimer = setTimeout(onSlow, 3_000);
  const started = Date.now();
  try {
    while (Date.now() - started < timeoutMs) {
      try {
        const res = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
        if (res.ok) return;
      } catch {
        // Server still waking up (or a network blip): try again shortly.
      }
      await new Promise((r) => setTimeout(r, 2_500));
    }
    throw new FriendlyError("The server didn't wake up. Please refresh the page and try again.");
  } finally {
    clearTimeout(slowTimer);
  }
}

async function readStream(res: Response, onEvent: (e: StreamEvent) => void): Promise<void> {
  if (!res.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON: keep the generic message */
    }
    throw new FriendlyError(message, res.status);
  }
  if (!res.body) throw new FriendlyError("Your browser doesn't support live updates.");

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    let chunk: ReadableStreamReadResult<string>;
    try {
      chunk = await reader.read();
    } catch {
      throw networkError(); // connection dropped mid-run
    }
    const { value, done } = chunk;
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    // SSE messages are separated by a blank line.
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length || event === "message") continue; // pings/comments
      try {
        onEvent({ event, data: JSON.parse(dataLines.join("\n")) } as StreamEvent);
      } catch {
        /* ignore a malformed message rather than crash the UI */
      }
    }
  }
}

function networkError(): FriendlyError {
  return new FriendlyError("We lost the connection to the server. Please check your internet and try again.");
}

export async function startRun(form: FormData, onEvent: (e: StreamEvent) => void): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/runs`, { method: "POST", body: form });
  } catch {
    throw networkError();
  }
  await readStream(res, onEvent);
}

export async function resumeRun(
  body: { state_token: string; confirmed?: string[]; notes?: Record<string, string>; job_text?: string },
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw networkError();
  }
  await readStream(res, onEvent);
}
