import { describe, expect, it } from "vitest";
import { parseStampedRecord } from "../contracts/stamped";
import type { StampedRecord } from "../contracts";
import { reduceChat, USER_FACING_TERMINAL_ACTIONS } from "./chat-projector";

const scope = {
  trace_id: "t1",
  run_id: "run-1",
  parent_run_id: null,
  delegation_id: null,
  agent_role: "lead",
};

function stamp<E extends StampedRecord["event"]>(
  seq: number,
  event: E,
): ReturnType<typeof parseStampedRecord> {
  const record: StampedRecord = {
    schema: "journal.v1",
    seq,
    ts: seq,
    scope,
    event_type: event.type,
    event,
  };
  return parseStampedRecord(record);
}

describe("chat projector", () => {
  it("buffers StepTextDelta until user-facing DecisionMade commits answer-delta", () => {
    let state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", pendingSteps: new Map() },
      stamp(1, { type: "StepTextDelta", step: 0, text_delta: "hel", seq: 0 }),
    );
    expect(state.answer).toBe("");
    expect(state.pendingSteps.size).toBe(1);

    state = reduceChat(
      state,
      stamp(2, { type: "StepTextDelta", step: 0, text_delta: "lo", seq: 1 }),
    );
    expect(state.answer).toBe("");

    state = reduceChat(
      state,
      stamp(3, { type: "DecisionMade", step: 0, action_type: "respond", rationale_preview: "", delegate_target: "", delegate_count: 0, tool_name: "", confidence: 1 }),
    );
    expect(state.answer).toBe("hello");
    expect(state.answerDeltas).toEqual(["hel", "lo"]);
    expect(state.pendingSteps.size).toBe(0);
  });

  it("discards buffered deltas for non-user-facing decisions", () => {
    let state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", pendingSteps: new Map() },
      stamp(1, { type: "StepTextDelta", step: 1, text_delta: "delegate json", seq: 0 }),
    );
    state = reduceChat(
      state,
      stamp(2, { type: "DecisionMade", step: 1, action_type: "delegate", rationale_preview: "", delegate_target: "x", delegate_count: 1, tool_name: "", confidence: 0.9 }),
    );
    expect(state.answer).toBe("");
    expect(state.answerDeltas).toEqual([]);
    expect(state.pendingSteps.size).toBe(0);
  });

  it("exports user-facing terminal action set", () => {
    expect(USER_FACING_TERMINAL_ACTIONS.has("respond")).toBe(true);
    expect(USER_FACING_TERMINAL_ACTIONS.has("delegate")).toBe(false);
  });
});
