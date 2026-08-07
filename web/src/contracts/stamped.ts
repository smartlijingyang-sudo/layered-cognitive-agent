import type { JournalEvent, RunScope, StampedRecord } from "./journal.generated";

/** 前端盖章事件：SSE payload 解析 + 事件 type 字段归一。 */
export interface StampedEvent<E extends JournalEvent = JournalEvent> {
  readonly seq: number;
  readonly ts: number;
  readonly scope: RunScope;
  readonly event: E;
  readonly domain?: StampedRecord["domain"];
}

export function parseStampedRecord(raw: StampedRecord): StampedEvent {
  const eventType = raw.event_type;
  return {
    seq: raw.seq,
    ts: raw.ts,
    scope: raw.scope,
    domain: raw.domain,
    event: { ...raw.event, type: eventType } as JournalEvent,
  };
}
