// web/src/projectors/message-sort.ts
import type { Message } from "./message-types";

export function sortMessages(messages: readonly Message[]): readonly Message[] {
  return [...messages].sort((a, b) => {
    const aRunning = a.status === "running" ? 1 : 0;
    const bRunning = b.status === "running" ? 1 : 0;
    if (aRunning !== bRunning) return aRunning - bRunning;

    if (a.completedAt != null && b.completedAt != null) {
      return a.completedAt - b.completedAt;
    }

    return a.startedAt - b.startedAt;
  });
}
