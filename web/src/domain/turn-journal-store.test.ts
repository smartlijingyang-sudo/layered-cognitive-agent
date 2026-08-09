import { describe, expect, it, vi } from "vitest";

const memory = new Map<string, unknown>();

vi.mock("idb-keyval", () => ({
  get: async (key: string) => memory.get(key),
  set: async (key: string, value: unknown) => {
    memory.set(key, value);
  },
  del: async (key: string) => {
    memory.delete(key);
  },
}));

import type { StampedEvent } from "../contracts/stamped";
import {
  deleteTurnJournal,
  loadTurnJournal,
  saveTurnJournal,
} from "./turn-journal-store";

function sample(seq: number): StampedEvent {
  return {
    seq,
    ts: 1000 + seq,
    scope: {
      trace_id: "t",
      run_id: "r1",
      parent_run_id: null,
      delegation_id: null,
      agent_role: "lead",
    },
    event: {
      type: "ToolStarted",
      tool_name: "calculator",
      arguments_preview: "{}",
      invocation_id: "inv-1",
    },
    domain: "resource",
  };
}

describe("turn-journal-store", () => {
  it("round-trips journal events by runId", async () => {
    memory.clear();
    await saveTurnJournal("r1", [sample(1), sample(2)]);
    const loaded = await loadTurnJournal("r1");
    expect(loaded).toHaveLength(2);
    expect(loaded?.[0]?.event.type).toBe("ToolStarted");
  });

  it("deletes journal", async () => {
    memory.clear();
    await saveTurnJournal("r1", [sample(1)]);
    await deleteTurnJournal("r1");
    expect(await loadTurnJournal("r1")).toBeNull();
  });
});
