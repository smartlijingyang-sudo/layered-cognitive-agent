// The server snapshot is the chat projection. This loop pulls it when the
// WebSocket completion event never arrives, and again after a refresh.
// It does not write messages. The backend already did.

import type { ConversationContext } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

export type ReconcileAction = 'watch' | 'park' | 'finish';

const TERMINAL = new Set(['completed', 'error', 'interrupted', 'failed', 'canceled', 'cancelled']);

export function reconcileAction(status: string | undefined): ReconcileAction {
  if (status === 'waiting_input') return 'park';
  if (status && TERMINAL.has(status)) return 'finish';
  return 'watch';
}

type Snapshot = {
  session_status?: string;
  status?: string;
};

const watchers = new Map<string, { operationId: string; stop: () => void }>();

function bearer(): string {
  return process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
}

function snapshotStatus(body: Snapshot): string {
  return body.session_status || body.status || '';
}

function runningOperationIds(get: () => ChatStore, runId: string, topicId?: string): string[] {
  const ops = get().operations ?? {};
  return Object.entries(ops)
    .filter(([, op]) => {
      if (!op) return false;
      if (op.status === 'completed' || op.status === 'cancelled') return false;
      const serverId = (op.metadata as { serverOperationId?: string } | undefined)
        ?.serverOperationId;
      if (serverId === runId) return true;
      // The status tray follows whichever op is still running on this topic.
      // A paused run must stop all of them, not only the one that stored the id.
      return Boolean(topicId) && op.context?.topicId === topicId;
    })
    .map(([id]) => id);
}

async function pull(runId: string): Promise<Snapshot | null> {
  const resp = await fetch(`/lca-api/runs/${encodeURIComponent(runId)}`, {
    headers: { Authorization: `Bearer ${bearer()}` },
  });
  if (!resp.ok) return null;
  return (await resp.json()) as Snapshot;
}

/**
 * Poll one run until it leaves `running`. `park` unlocks the composer and
 * reloads the ask card. `finish` reloads the final reply and stops.
 */
export function startLcaRunReconcile(
  get: () => ChatStore,
  params: {
    runId: string;
    operationId?: string;
    topicId?: string;
    context?: Partial<ConversationContext>;
  },
): void {
  const { runId } = params;
  if (!runId) return;
  const operationId = params.operationId || runId;
  const existing = watchers.get(runId);
  if (existing?.operationId === operationId) return;
  existing?.stop();

  let stopped = false;
  let parked = false;
  let seenWaiting = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const stop = () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    if (watchers.get(runId)?.operationId === operationId) watchers.delete(runId);
  };
  watchers.set(runId, { operationId, stop });

  const tick = async () => {
    if (stopped) return;
    try {
      const body = await pull(runId);
      const action = reconcileAction(body ? snapshotStatus(body) : undefined);
      if (action === 'park') {
        seenWaiting += 1;
        // The status flips before the ask row commit returns. Wait one more
        // tick so the reload cannot wipe the in-memory card with an empty read.
        if (seenWaiting >= 2 && !parked) {
          parked = true;
          await get().refreshMessages?.({ ...params.context, topicId: params.topicId });
          for (const id of runningOperationIds(get, runId, params.topicId)) get().completeOperation(id);
        }
      }
      if (action === 'finish') {
        await get().refreshMessages?.({ ...params.context, topicId: params.topicId });
        for (const id of runningOperationIds(get, runId, params.topicId)) get().completeOperation(id);
        stop();
        return;
      }
    } catch (error) {
      console.error('[LCA] run reconcile failed', error);
    }
    if (!stopped) timer = setTimeout(tick, 2000);
  };

  timer = setTimeout(tick, 500);
}
