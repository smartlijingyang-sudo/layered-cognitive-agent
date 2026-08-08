import { describe, expect, it } from "vitest";
import type { StampedRecord } from "../contracts";
import { parseStampedRecord } from "../contracts/stamped";
import { shouldPersistTurnOnEvent } from "./persist-turn";

const scope = {
  trace_id: "t1",
  run_id: "r1",
  parent_run_id: null,
  delegation_id: null,
  agent_role: "lead",
};

function stamped(type: string, extra: Record<string, unknown> = {}) {
  const record: StampedRecord = {
    schema: "journal.v1",
    seq: 1,
    ts: 1,
    scope,
    event_type: type as StampedRecord["event_type"],
    event: { type, ...extra } as StampedRecord["event"],
  };
  return parseStampedRecord(record);
}

describe("shouldPersistTurnOnEvent", () => {
  it("persists on user-facing DecisionMade actions", () => {
    expect(shouldPersistTurnOnEvent(stamped("DecisionMade", { action_type: "respond", step: 1 }))).toBe(
      true,
    );
    expect(shouldPersistTurnOnEvent(stamped("DecisionMade", { action_type: "delegate", step: 1 }))).toBe(
      false,
    );
  });

  it("persists on terminal run events", () => {
    expect(shouldPersistTurnOnEvent(stamped("TeamRunFinished", { status: "completed" }))).toBe(true);
    expect(shouldPersistTurnOnEvent(stamped("AgentRunFinished", { status: "completed" }))).toBe(true);
    expect(shouldPersistTurnOnEvent(stamped("CastingFailed", { error: "x" }))).toBe(true);
  });

  it("does not persist on StepTextDelta", () => {
    expect(
      shouldPersistTurnOnEvent(stamped("StepTextDelta", { step: 1, seq: 0, text_delta: "hi" })),
    ).toBe(false);
  });
});
