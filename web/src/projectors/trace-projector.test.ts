import { describe, expect, it } from "vitest";
import {
  buildTraceState,
  buildTraceTimeline,
  reduceTrace,
} from "./trace-projector";
import { EMPTY_TRACE_STATE } from "./types";
import { parseStampedRecord } from "../contracts/stamped";
import type { StampedRecord } from "../contracts";

const scope = {
  trace_id: "t",
  run_id: "run-1",
  parent_run_id: null,
  delegation_id: null,
  agent_role: "lead",
};

function stamp(
  seq: number,
  event: StampedRecord["event"],
  runId = scope.run_id,
): ReturnType<typeof parseStampedRecord> {
  const record: StampedRecord = {
    schema: "journal.v1",
    seq,
    ts: seq,
    scope: { ...scope, run_id: runId },
    event_type: event.type,
    event,
    domain: event.type === "StepTextDelta" ? "resource" : "event",
  };
  return parseStampedRecord(record);
}

describe("trace projector", () => {
  it("reduces team run lifecycle", () => {
    const started: StampedRecord = {
      schema: "journal.v1",
      seq: 1,
      ts: 1,
      scope: {
        trace_id: "t",
        run_id: "r",
        parent_run_id: null,
        delegation_id: null,
        agent_role: "",
      },
      event_type: "TeamRunStarted",
      event: {
        type: "TeamRunStarted",
        team_id: "team-x",
        mandate: "board",
        members: ["Alice", "Bob"],
        objective_preview: "hello",
        strategy_key: "",
        lead_role: "",
        objective: "",
        plan_steps: "",
      },
    };
    const state = buildTraceState([parseStampedRecord(started)]);
    expect(state.teamRun?.teamId).toBe("team-x");
    expect(state.teamRun?.members).toEqual(["Alice", "Bob"]);
    expect(state.phase).toBe("collaborating");
  });

  it("reduces casting lifecycle", () => {
    const castingScope = {
      trace_id: "t",
      run_id: "r",
      parent_run_id: null,
      delegation_id: null,
      agent_role: "",
    };
    const events = [
      parseStampedRecord({
        schema: "journal.v1",
        seq: 1,
        ts: 1,
        scope: castingScope,
        event_type: "CastingStarted",
        event: { type: "CastingStarted", objective_preview: "写文案" },
      }),
      parseStampedRecord({
        schema: "journal.v1",
        seq: 2,
        ts: 2,
        scope: castingScope,
        event_type: "CastingCompleted",
        event: {
          type: "CastingCompleted",
          governance_kind: "pipeline",
          lead_role: "",
          selected_roles: ["产品经理"],
          rationale: "ok",
        },
      }),
    ];
    const state = buildTraceState(events);
    expect(state.phase).toBe("collaborating");
    expect(state.casting?.selectedRoles).toEqual(["产品经理"]);
  });

  it("coalesces StepTextDelta by (run_id, step) into one stream", () => {
    let state = EMPTY_TRACE_STATE;
    state = reduceTrace(
      state,
      stamp(10, { type: "StepTextDelta", step: 0, text_delta: "```json\n", seq: 0 }),
    );
    state = reduceTrace(
      state,
      stamp(11, { type: "StepTextDelta", step: 0, text_delta: '{"action_type', seq: 1 }),
    );
    state = reduceTrace(
      state,
      stamp(12, { type: "StepTextDelta", step: 0, text_delta: '": "respond"}', seq: 2 }),
    );

    expect(state.stepStreams).toHaveLength(1);
    const stream = state.stepStreams[0]!;
    expect(stream.key).toBe("run-1:0");
    expect(stream.chunkCount).toBe(3);
    expect(stream.text).toBe('```json\n{"action_type": "respond"}');
    expect(stream.anchorJournalSeq).toBe(10);
    expect(stream.agentRole).toBe("lead");
  });

  it("reorders out-of-order delta.seq when joining text", () => {
    let state = EMPTY_TRACE_STATE;
    state = reduceTrace(
      state,
      stamp(1, { type: "StepTextDelta", step: 1, text_delta: "lo", seq: 1 }),
    );
    state = reduceTrace(
      state,
      stamp(2, { type: "StepTextDelta", step: 1, text_delta: "hel", seq: 0 }),
    );
    expect(state.stepStreams[0]!.text).toBe("hello");
    expect(state.stepStreams[0]!.lastDeltaSeq).toBe(1);
  });

  it("keeps separate streams for different steps and runs", () => {
    let state = EMPTY_TRACE_STATE;
    state = reduceTrace(
      state,
      stamp(1, { type: "StepTextDelta", step: 0, text_delta: "a", seq: 0 }),
    );
    state = reduceTrace(
      state,
      stamp(2, { type: "StepTextDelta", step: 1, text_delta: "b", seq: 0 }),
    );
    state = reduceTrace(
      state,
      stamp(3, { type: "StepTextDelta", step: 0, text_delta: "c", seq: 0 }, "run-2"),
    );
    expect(state.stepStreams.map((s) => s.key)).toEqual(["run-1:0", "run-1:1", "run-2:0"]);
    expect(state.stepStreams.map((s) => s.text)).toEqual(["a", "b", "c"]);
  });

  it("buildTraceTimeline collapses many deltas into one timeline item", () => {
    const events = [
      stamp(1, {
        type: "DecisionMade",
        step: 0,
        action_type: "think",
        rationale_preview: "",
        delegate_target: "",
        delegate_count: 0,
        tool_name: "",
        confidence: 1,
      }),
      stamp(2, { type: "StepTextDelta", step: 0, text_delta: "hel", seq: 0 }),
      stamp(3, { type: "StepTextDelta", step: 0, text_delta: "lo", seq: 1 }),
      stamp(4, {
        type: "LlmCallCompleted",
        model: "m",
        ok: true,
        latency_ms: 1,
        prompt_preview: "",
        response_preview: "",
        prompt_tokens: 0,
        completion_tokens: 0,
        stream: true,
      }),
    ];
    const state = buildTraceState(events, "verbose");
    const timeline = buildTraceTimeline(events, state.stepStreams, "verbose");
    expect(timeline).toHaveLength(3);
    expect(timeline[0]).toMatchObject({ kind: "event" });
    expect(timeline[1]).toMatchObject({
      kind: "step_stream",
      stream: { text: "hello", chunkCount: 2 },
    });
    expect(timeline[2]).toMatchObject({ kind: "event" });
  });

  it("hides StepTextDelta streams under standard verbosity", () => {
    const events = [
      stamp(1, { type: "StepTextDelta", step: 0, text_delta: "x", seq: 0 }),
    ];
    const state = buildTraceState(events, "standard");
    expect(state.stepStreams).toHaveLength(0);
    expect(buildTraceTimeline(events, state.stepStreams, "standard")).toHaveLength(0);
  });

  it("coalesces SandboxOutputDelta under standard verbosity and seals on ToolInvoked", () => {
    const events = [
      stamp(1, {
        type: "SandboxOutputDelta",
        invocation_id: "sbx_1",
        stream: "stdout",
        text_delta: "hello\n",
        seq: 0,
      }),
      stamp(2, {
        type: "SandboxOutputDelta",
        invocation_id: "sbx_1",
        stream: "stdout",
        text_delta: "world\n",
        seq: 1,
      }),
      stamp(3, {
        type: "SandboxOutputDelta",
        invocation_id: "sbx_1",
        stream: "stderr",
        text_delta: "warn\n",
        seq: 2,
      }),
      stamp(4, {
        type: "ToolInvoked",
        tool_name: "run_sandbox_code",
        arguments_preview: "{}",
        result_preview: "{}",
        ok: true,
        latency_ms: 10,
        attempt: 1,
        error: "",
        invocation_id: "sbx_1",
      }),
      stamp(5, {
        type: "SandboxOutputDelta",
        invocation_id: "sbx_1",
        stream: "stdout",
        text_delta: "late\n",
        seq: 3,
      }),
    ];
    const state = buildTraceState(events, "standard");
    expect(state.sandboxStreams).toHaveLength(2);
    const stdout = state.sandboxStreams.find((s) => s.stream === "stdout");
    const stderr = state.sandboxStreams.find((s) => s.stream === "stderr");
    expect(stdout?.text).toBe("hello\nworld\n");
    expect(stdout?.sealed).toBe(true);
    expect(stderr?.text).toBe("warn\n");
    expect(stderr?.sealed).toBe(true);
    const timeline = buildTraceTimeline(
      events,
      state.stepStreams,
      "standard",
      state.sandboxStreams,
    );
    expect(timeline.some((i) => i.kind === "sandbox_stream")).toBe(true);
    expect(timeline.some((i) => i.kind === "event")).toBe(true);
  });
});