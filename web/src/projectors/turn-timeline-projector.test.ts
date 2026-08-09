import { describe, expect, it } from "vitest";
import type { StampedEvent } from "../contracts/stamped";
import {
  buildTurnTimeline,
  shouldFoldProcess,
} from "./turn-timeline-projector";

function stamped(
  type: string,
  event: Record<string, unknown>,
  seq = 1,
  ts = 1_000,
): StampedEvent {
  return {
    seq,
    ts,
    scope: {
      trace_id: "t1",
      run_id: "r1",
      parent_run_id: null,
      delegation_id: null,
      agent_role: "lead",
    },
    event: { type, ...event } as StampedEvent["event"],
    domain: "event",
  };
}

describe("buildTurnTimeline", () => {
  it("builds thinking + casting process and folds after final answer", () => {
    const events = [
      stamped("CastingStarted", { objective_preview: "写报告" }, 1, 1000),
      stamped(
        "CastingCompleted",
        {
          governance_kind: "board",
          lead_role: "pm",
          selected_roles: ["pm", "dev"],
          rationale: "需要产品与研发",
        },
        2,
        2000,
      ),
      stamped(
        "DecisionMade",
        {
          step: 1,
          action_type: "respond",
          rationale_preview: "可以直接回答",
          delegate_target: "",
          delegate_count: 0,
          tool_name: "",
          confidence: 0.9,
          response_text: "这是最终答案",
          output_truncated: false,
        },
        3,
        5000,
      ),
      stamped(
        "TeamRunFinished",
        {
          status: "completed",
          output_text: "这是最终答案",
          output_truncated: false,
          steps: 1,
          error: "",
        },
        4,
        6000,
      ),
    ];

    const timeline = buildTurnTimeline(events);
    expect(timeline.status).toBe("completed");
    expect(timeline.finalAnswer).toContain("最终答案");
    expect(timeline.process.some((b) => b.kind === "casting")).toBe(true);
    expect(timeline.process.some((b) => b.kind === "thinking")).toBe(true);
    expect(timeline.foldProcess).toBe(true);
    expect(shouldFoldProcess(timeline)).toBe(true);
  });

  it("nests live sandbox under running tool before ToolInvoked", () => {
    const events = [
      stamped("AgentRunStarted", {
        agent_role: "coder",
        strategy_key: "react",
        objective: "run",
        objective_preview: "run",
        from_role: "",
      }, 1, 1000),
      stamped(
        "SandboxOutputDelta",
        {
          invocation_id: "sbx-1",
          stream: "stdout",
          text_delta: "hello\n",
          seq: 0,
        },
        2,
        1100,
      ),
      stamped(
        "ToolInvoked",
        {
          tool_name: "run_code",
          arguments_preview: '{"code":"print(1)"}',
          result_preview: "ok",
          ok: true,
          latency_ms: 120,
          attempt: 1,
          error: "",
          invocation_id: "sbx-1",
          files: [],
        },
        3,
        2000,
      ),
    ];

    const mid = buildTurnTimeline(events.slice(0, 2));
    expect(mid.process.some((b) => b.kind === "tool" && b.status === "running")).toBe(true);
    expect(mid.process.some((b) => b.kind === "sandbox" && !b.sealed)).toBe(true);

    const done = buildTurnTimeline(events);
    const tool = done.process.find((b) => b.kind === "tool");
    const sandbox = done.process.find((b) => b.kind === "sandbox");
    expect(tool?.status).toBe("done");
    expect(sandbox && sandbox.kind === "sandbox" && sandbox.sealed).toBe(true);
  });

  it("does not fold while still running", () => {
    const events = [
      stamped("AgentRunStarted", {
        agent_role: "a",
        strategy_key: "react",
        objective: "x",
        objective_preview: "x",
        from_role: "",
      }),
      stamped("StepTextDelta", { step: 1, text_delta: '{"response_text":"hi', seq: 0 }),
    ];
    const timeline = buildTurnTimeline(events);
    expect(timeline.status).toBe("running");
    expect(timeline.foldProcess).toBe(false);
  });

  it("opens tool card on ToolStarted and prefers model reasoning deltas", () => {
    const events = [
      stamped(
        "ToolStarted",
        {
          tool_name: "calculator",
          arguments_preview: '{"expression":"1+1"}',
          invocation_id: "inv-9",
        },
        1,
        1000,
      ),
      stamped("ReasoningDelta", { step: 1, text_delta: "先算加法", seq: 0 }, 2, 1100),
      stamped(
        "ReasoningCompleted",
        { step: 1, duration_ms: 800, content_preview: "先算加法" },
        3,
        1900,
      ),
      stamped(
        "ToolInvoked",
        {
          tool_name: "calculator",
          arguments_preview: '{"expression":"1+1"}',
          result_preview: "2",
          ok: true,
          latency_ms: 5,
          attempt: 1,
          error: "",
          invocation_id: "inv-9",
          files: [],
        },
        4,
        2000,
      ),
      stamped(
        "DecisionMade",
        {
          step: 1,
          action_type: "respond",
          rationale_preview: "should be ignored when model reasoning exists",
          delegate_target: "",
          delegate_count: 0,
          tool_name: "",
          confidence: 1,
          response_text: "答案是 2",
          output_truncated: false,
        },
        5,
        2100,
      ),
      stamped(
        "AgentRunFinished",
        {
          status: "completed",
          output_text: "答案是 2",
          output_truncated: false,
          steps: 1,
          error: "",
        },
        6,
        2200,
      ),
    ];

    const mid = buildTurnTimeline(events.slice(0, 1));
    expect(mid.process.some((b) => b.kind === "tool" && b.status === "running")).toBe(true);

    const done = buildTurnTimeline(events);
    const thinking = done.process.find((b) => b.kind === "thinking");
    expect(thinking && thinking.kind === "thinking" && thinking.content).toContain("先算加法");
    expect(thinking && thinking.kind === "thinking" && thinking.content).not.toContain(
      "should be ignored",
    );
    const tool = done.process.find((b) => b.kind === "tool");
    expect(tool && tool.kind === "tool" && tool.status).toBe("done");
    expect(done.foldProcess).toBe(true);
  });
});
