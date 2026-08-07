import type { StampedEvent } from "../contracts";

type Listener = (event: StampedEvent) => void;

/** append-only 事件日志 —— 前端唯一真相（镜像后端 journal）。 */
export class JournalLog {
  private readonly events: StampedEvent[] = [];
  private readonly listeners = new Set<Listener>();

  append(event: StampedEvent): void {
    this.events.push(event);
    for (const listener of this.listeners) {
      listener(event);
    }
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  snapshot(): readonly StampedEvent[] {
    return this.events;
  }

  clear(): void {
    this.events.length = 0;
  }
}
