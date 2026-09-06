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
import { fetchRunSnapshot, lcaAuthHeaders } from './lcaRunCommand';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

export const LIVE_TERMINAL = new Set(['canceled', 'completed', 'failed']);
export const LIVE_PAUSED = new Set(['waiting_input', 'awaiting_human', 'input-required']);
/**
 * Hard cap on consecutive SSE reconnects without terminal evidence.
 * Prevents an infinite poll loop when the backend GC's a run before the
 * cursor / snapshot agree on terminal (run gone → snapshot 404 → reconnect
 * → repeat). Caller treats this as terminal: stop streaming, fall back to
 * the last-known cursor / snapshot.
 */
export const LIVE_MAX_RECONNECTS = 8;

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
function applyLiveGapCursorAdvance(
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

export function advanceLiveGapCursor(
  cursor: LiveObserveCursor,
  projected: Projected,
): boolean {
  return applyLiveGapCursorAdvance(cursor, projected);
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
 *
 * Termination contract (any one of these exits the loop):
 *   1. ``options.signal.aborted`` — caller cancelled.
 *   2. ``cursor.streamTerminal`` — driver observed a terminal ``run-finished``.
 *   3. SSE delivered ``run-finished`` with status in {@link LIVE_TERMINAL}.
 *   4. {@link fetchRunSnapshot} returns a terminal status
 *      ({@link LIVE_TERMINAL} ∪ {@link LIVE_PAUSED} ∪ ``missing=true``).
 *   5. Reconnect budget exhausted ({@link LIVE_MAX_RECONNECTS}).
 *
 * ``LIVE_PAUSED`` is treated as terminal-for-SSE because the live stream is
 * irrelevant once the run is blocked on a human; the driver renders the
 * askUserQuestion card from the snapshot and the SSE poll must stop.
 * ``missing=true`` covers the GC-after-completion case where the backend
 * has dropped the run record — without it the observation face would loop
 * forever asking for ``/live`` on a run that no longer exists.
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
    let streamOk = true;
    try {
      const streamRes = await fetch(liveUrl(options.runId, cursor.afterSeq), {
        headers: authHeaders,
        signal: options.signal,
      });
      if (!streamRes.ok) {
        const text = await streamRes.text();
        // 404/410 on the live endpoint means the run is gone — stop polling.
        if (streamRes.status === 404 || streamRes.status === 410) {
          streamOk = false;
          cursor.streamTerminal = true;
        } else {
          throw new Error(`live HTTP ${streamRes.status}: ${text.slice(0, 200)}`);
        }
      } else {
        for await (const frame of readSse(streamRes)) {
          if (typeof frame.seq === 'number') {
            cursor.lastSeq = frame.seq;
            cursor.afterSeq = frame.seq;
            reconnectAttempt = 0;
          }
          const projected = projectJournalFrame(frame);
          if (projected.kind === 'live-gap' && typeof projected.oldestSeq === 'number') {
            if (projected.oldestSeq > 0) {
              cursor.afterSeq = Math.max(cursor.afterSeq, projected.oldestSeq - 1);
            }
            console.warn('lca: live gap — ring buffer evicted events', {
              afterSeq: cursor.afterSeq,
              oldestSeq: projected.oldestSeq,
              requestedSeq: projected.requestedSeq,
            });
            continue;
          }
          await handlers.onProjected(projected);
          if (cursor.streamTerminal) break;
        }
      }
    } catch (error) {
      if (options.signal.aborted) return;
      // Transport error: hand to caller (driver decides retry/abort policy).
      throw error;
    }

    if (options.signal.aborted || cursor.streamTerminal) break;
    if (!streamOk) break;

    const snap = await fetchRunSnapshot(options.runId, options.signal);
    const snapStatus = String(snap.status ?? '');
    if (handlers.onSnapshot) {
      await handlers.onSnapshot({ error: snap.error, status: snapStatus });
    }
    // Terminal-or-paused: stop the SSE loop. Driver handles paused runs
    // through the askUserQuestion card; missing means the run was GC'd.
    if (
      LIVE_TERMINAL.has(snapStatus) ||
      LIVE_PAUSED.has(snapStatus) ||
      snap.missing === true
    ) {
      break;
    }

    reconnectAttempt += 1;
    if (reconnectAttempt > LIVE_MAX_RECONNECTS) {
      console.warn('lca: live reconnect budget exhausted, stopping', {
        runId: options.runId,
        afterSeq: cursor.afterSeq,
        attempts: reconnectAttempt,
      });
      break;
    }
    handlers.onReconnectAttempt?.(reconnectAttempt);
    await new Promise((resolve) => setTimeout(resolve, reconnectDelayMs(reconnectAttempt)));
  }
}
