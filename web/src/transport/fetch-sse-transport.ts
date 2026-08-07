import type { StampedRecord } from "../contracts";
import { parseStampedRecord, type StampedEvent } from "../contracts/stamped";
import { parseSseChunk } from "./sse-parser";

export interface EventTransport {
  connect(runId: string, onEvent: (event: StampedEvent) => void): Promise<void>;
  disconnect(): void;
}

export interface FetchSseTransportOptions {
  readonly baseUrl?: string;
  readonly onError?: (error: unknown) => void;
}

const DEFAULT_BASE = "";

/** fetch SSE 传输：手写帧解析 + Last-Event-ID 重连。 */
export class FetchSseTransport implements EventTransport {
  private readonly baseUrl: string;
  private readonly onError?: (error: unknown) => void;
  private abort: AbortController | null = null;
  private lastEventId = 0;

  constructor(options: FetchSseTransportOptions = {}) {
    this.baseUrl = options.baseUrl ?? DEFAULT_BASE;
    this.onError = options.onError;
  }

  async connect(runId: string, onEvent: (event: StampedEvent) => void): Promise<void> {
    this.disconnect();
    this.abort = new AbortController();
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (this.lastEventId > 0) {
      headers["Last-Event-ID"] = String(this.lastEventId);
    }
    try {
      const response = await fetch(`${this.baseUrl}/runs/${runId}/events`, {
        headers,
        signal: this.abort.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`SSE failed: ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { messages, rest } = parseSseChunk(buffer);
        buffer = rest;
        for (const msg of messages) {
          if (msg.event === "error") continue;
          const record = JSON.parse(msg.data) as StampedRecord;
          const stamped = parseStampedRecord(record);
          this.lastEventId = stamped.seq;
          onEvent(stamped);
        }
      }
    } catch (error) {
      this.onError?.(error);
      throw error;
    }
  }

  disconnect(): void {
    this.abort?.abort();
    this.abort = null;
  }

  resetCursor(): void {
    this.lastEventId = 0;
  }
}
