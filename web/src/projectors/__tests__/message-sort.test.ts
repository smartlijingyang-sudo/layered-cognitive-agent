// web/src/projectors/__tests__/message-sort.test.ts
import { describe, it, expect } from "vitest";
import { sortMessages } from "../message-sort";
import type { Message } from "../message-types";

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: "msg",
    kind: "answer",
    content: "",
    streaming: false,
    status: "done",
    startedAt: 0,
    ...overrides,
  };
}

describe("sortMessages", () => {
  it("should sort completed messages by completedAt ascending", () => {
    const msgs = [
      makeMessage({ id: "a", completedAt: 300 }),
      makeMessage({ id: "b", completedAt: 100 }),
      makeMessage({ id: "c", completedAt: 200 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["b", "c", "a"]);
  });

  it("should place running messages after completed ones", () => {
    const msgs = [
      makeMessage({ id: "running", status: "running", startedAt: 50 }),
      makeMessage({ id: "done", completedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["done", "running"]);
  });

  it("should sort running messages by startedAt ascending", () => {
    const msgs = [
      makeMessage({ id: "r2", status: "running", startedAt: 200 }),
      makeMessage({ id: "r1", status: "running", startedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["r1", "r2"]);
  });

  it("should handle mixed completed and running", () => {
    const msgs = [
      makeMessage({ id: "r1", status: "running", startedAt: 300 }),
      makeMessage({ id: "d1", completedAt: 200 }),
      makeMessage({ id: "r2", status: "running", startedAt: 250 }),
      makeMessage({ id: "d2", completedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["d2", "d1", "r2", "r1"]);
  });
});
