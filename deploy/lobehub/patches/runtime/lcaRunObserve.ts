/**
 * Run live observation loop (ADR-0100).
 *
 * Command vs observation: POST /runs starts one run; this module only
 * subscribes GET /live with a monotonic ?after= cursor — never a second run.
 */

import {
  parseSseBlock,
  projectJournalFrame,
  type JournalFrame,
  type Projected,
} from './lcaJournal';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

export const LIVE_TERMINAL = new Set(['canceled', 'completed', 'failed']);
export const LIVE_PAUSED = new Set(['waiting_input', 'awaiting_human', 'input-required']);

/** ADR-0100 resume cursor — server reads ``?after=``, not ``Last-Event-ID``. */
export function liveUrl(runId: string, afterSeq: number): string {
  const after = Number.isFinite(afterSeq) && afterSeq >= 0 ? Math.floor(afterSeq) : 0;
  return `/lca-api/runs/${runId}/live?after=${after}`;
}

export function reconnectDelayMs(attempt: number): number {
  return Math.min(400 * 2 ** attempt, 5000);
}

export async function* readSse(response: Response): AsyncGenerator<JournalFrame> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('live: empty body');
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    while (true) {
      const idx = buf.indexOf('\n\n');
      if (idx < 0) break;
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const frame = parseSseBlock(block);
      if (frame) yield frame;
    }
  }
}

export type LiveObserveCursor = {
  afterSeq: number;
  lastSeq: number;
  streamTerminal: boolean;
};

export type LiveObserveHandlers = {
  onProjected: (projected: Projected) => Promise<void>;
  onReconnectAttempt?: (attempt: number) => void;
  onSnapshot?: (snap: { error?: string; status?: string }) => Promise<void>;
};

/** Advance resume cursor when the server signals ring-buffer eviction."""
export function advanceLiveGapCursor(
  cursor: LiveObserveCursor,
  projected: Projected,
): boolean {
  if (projected.kind !== 'live-gap' || typeof projected.oldestSeq !== 'number') {
    return false;
  }
  if (projected.oldestSeq > 0) {
    cursor.afterSeq = Math.max(cursor.afterSeq, projected.oldestSeq - 1);
  }
  console.warn('lca: live gap — ring buffer evicted events', {
    afterSeq: cursor.afterSeq,
    oldestSeq: projected.oldestSeq,
    requestedSeq: projected.requestedSeq,
  });
  return true;
}

export type LiveObserveOptions = {
  authHeaders?: Record<string, string>;
  cursor: LiveObserveCursor;
  runId: string;
  signal: AbortSignal;
};

/**
 * Subscribe to one run's live SSE until terminal ``done``, abort, or snapshot
 * agreement. Reconnects with exponential backoff on the same run_id + cursor.
 */
export async function observeRunLive(
  options: LiveObserveOptions,
  handlers: LiveObserveHandlers,
): Promise<void> {
  const authHeaders = options.authHeaders ?? { Authorization: `Bearer ${LCA_TOKEN}` };
  const { cursor } = options;
  let reconnectAttempt = 0;

  while (!options.signal.aborted) {
    cursor.streamTerminal = false;
    const streamRes = await fetch(liveUrl(options.runId, cursor.afterSeq), {
      headers: authHeaders,
      signal: options.signal,
    });
    if (!streamRes.ok) {
      const text = await streamRes.text();
      throw new Error(`live HTTP ${streamRes.status}: ${text.slice(0, 200)}`);
    }
    for await (const frame of readSse(streamRes)) {
      if (typeof frame.seq === 'number') {
        cursor.lastSeq = frame.seq;
        cursor.afterSeq = frame.seq;
        reconnectAttempt = 0;
      }
      const projected = projectJournalFrame(frame);
      if (advanceLiveGapCursor(cursor, projected)) {
        continue;
      }
      await handlers.onProjected(projected);
      if (cursor.streamTerminal) break;
    }
    if (options.signal.aborted || cursor.streamTerminal) break;

    const snapRes = await fetch(`/lca-api/runs/${options.runId}`, {
      headers: authHeaders,
    });
    const snap = snapRes.ok
      ? ((await snapRes.json()) as { status?: string; error?: string })
      : {};
    const snapStatus = String(snap.status ?? '');
    if (handlers.onSnapshot) {
      await handlers.onSnapshot({ error: snap.error, status: snapStatus });
    }
    if (LIVE_TERMINAL.has(snapStatus)) break;

    reconnectAttempt += 1;
    handlers.onReconnectAttempt?.(reconnectAttempt);
    await new Promise((resolve) => setTimeout(resolve, reconnectDelayMs(reconnectAttempt)));
  }
}
