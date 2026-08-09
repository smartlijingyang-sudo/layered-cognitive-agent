import { describe, it, expect } from "vitest";
import type { Message, MessageKind } from "../message-types";

describe("Message types", () => {
  it("should define all message kinds", () => {
    const kinds: MessageKind[] = [
      "casting",
      "thinking",
      "tool_call",
      "sandbox",
      "delegation",
      "synthesis",
      "answer",
      "error",
      "insight",
    ];
    expect(kinds).toHaveLength(9);
  });

  it("should create a valid thinking message", () => {
    const msg: Message = {
      id: "thinking:run1:historian",
      kind: "thinking",
      agentRole: "historian",
      content: "分析历史背景...",
      streaming: true,
      status: "running",
      startedAt: Date.now(),
      metadata: { durationMs: undefined },
    };
    expect(msg.kind).toBe("thinking");
    expect(msg.streaming).toBe(true);
  });

  it("should create a valid tool_call message", () => {
    const msg: Message = {
      id: "tool:inv123",
      kind: "tool_call",
      content: "",
      streaming: false,
      status: "done",
      startedAt: Date.now() - 1000,
      completedAt: Date.now(),
      metadata: {
        toolName: "search_knowledge",
        argumentsPreview: '{"query": "test"}',
        resultPreview: '{"results": []}',
        latencyMs: 500,
        ok: true,
      },
    };
    expect(msg.metadata?.toolName).toBe("search_knowledge");
  });
});
