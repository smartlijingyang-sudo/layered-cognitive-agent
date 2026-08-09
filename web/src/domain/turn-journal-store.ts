/**
 * Per-turn journal persistence (IndexedDB) for historical ProcessFold replay.
 * Live runs still stream via SSE; on completion we snapshot the event list.
 */

import { get, set, del } from "idb-keyval";
import type { StampedEvent } from "../contracts/stamped";

const KEY_PREFIX = "lca.turnJournal.v1.";

function keyFor(runId: string): string {
  return `${KEY_PREFIX}${runId}`;
}

export async function saveTurnJournal(
  runId: string,
  events: readonly StampedEvent[],
): Promise<void> {
  if (!runId) return;
  await set(keyFor(runId), [...events]);
}

export async function loadTurnJournal(runId: string): Promise<StampedEvent[] | null> {
  if (!runId) return null;
  const stored = await get<StampedEvent[]>(keyFor(runId));
  return stored ?? null;
}

export async function deleteTurnJournal(runId: string): Promise<void> {
  if (!runId) return;
  await del(keyFor(runId));
}

export async function deleteTurnJournals(runIds: readonly string[]): Promise<void> {
  await Promise.all(runIds.map((id) => deleteTurnJournal(id)));
}
