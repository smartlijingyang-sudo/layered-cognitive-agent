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
      { question: "q", answer: "", answerDeltas: [], status: "running", phase: "collaborating", files: [], pendingSteps: new Map(), committedAnswer: "" },
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
      stamp(3, {
        type: "DecisionMade",
        step: 0,
        action_type: "respond",
        rationale_preview: "",
        delegate_target: "",
        delegate_count: 0,
        tool_name: "",
        confidence: 1,
        response_text: "",
        output_truncated: false,
      }),
    );
    expect(state.answer).toBe("hello");
    expect(state.answerDeltas).toEqual(["hello"]);
    expect(state.pendingSteps.size).toBe(0);
  });

  it("prefers DecisionMade.response_text over raw delta JSON (ADR-0045)", () => {
    const malformed = JSON.stringify({
      action_type: "use_tool",
      tool_name: "respond",
      arguments: { response_text: "缓冲里的旧提取" },
    });
    let state = reduceChat(
      {
        question: "q",
        answer: "",
        answerDeltas: [],
        status: "running",
        phase: "collaborating",
        files: [],
        pendingSteps: new Map(),
        committedAnswer: "",
      },
      stamp(1, { type: "StepTextDelta", step: 0, text_delta: malformed, seq: 0 }),
    );
    state = reduceChat(
      state,
      stamp(2, {
        type: "DecisionMade",
        step: 0,
        action_type: "respond",
        rationale_preview: "",
        delegate_target: "",
        delegate_count: 0,
        tool_name: "",
        confidence: 0.95,
        response_text: "规范正文：来自防腐层",
        output_truncated: false,
      }),
    );
    expect(state.answer).toBe("规范正文：来自防腐层");
    expect(state.answer).not.toContain("use_tool");
    expect(state.pendingSteps.size).toBe(0);
  });

  it("discards buffered deltas for non-user-facing decisions", () => {
    let state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", phase: "collaborating", files: [], pendingSteps: new Map(), committedAnswer: "" },
      stamp(1, { type: "StepTextDelta", step: 1, text_delta: "delegate json", seq: 0 }),
    );
    state = reduceChat(
      state,
      stamp(2, {
        type: "DecisionMade",
        step: 1,
        action_type: "delegate",
        rationale_preview: "",
        delegate_target: "x",
        delegate_count: 1,
        tool_name: "",
        confidence: 0.9,
        response_text: "",
        output_truncated: false,
      }),
    );
    expect(state.answer).toBe("");
    expect(state.answerDeltas).toEqual([]);
    expect(state.pendingSteps.size).toBe(0);
  });

  it("tracks casting phase through CastingCompleted", () => {
    let state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", phase: "casting", files: [], pendingSteps: new Map(), committedAnswer: "" },
      stamp(1, { type: "CastingStarted", objective_preview: "写文案" }),
    );
    expect(state.phase).toBe("casting");

    state = reduceChat(
      state,
      stamp(2, {
        type: "CastingCompleted",
        governance_kind: "pipeline",
        lead_role: "",
        selected_roles: ["产品经理", "内容专家"],
        rationale: "先需求后文案",
      }),
    );
    expect(state.phase).toBe("collaborating");
  });

  it("marks failed on CastingFailed", () => {
    const state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", phase: "casting", files: [], pendingSteps: new Map(), committedAnswer: "" },
      stamp(1, { type: "CastingFailed", error: "自动组队失败" }),
    );
    expect(state.status).toBe("failed");
    expect(state.phase).toBe("failed");
    expect(state.errorMessage).toBe("自动组队失败");
  });

  it("extracts response_text from decision JSON on commit", () => {
    const json =
      '{"action_type":"respond","response_text":"你好，这是正式回答。"}';
    let state = reduceChat(
      { question: "q", answer: "", answerDeltas: [], status: "running", phase: "collaborating", files: [], pendingSteps: new Map(), committedAnswer: "" },
      stamp(1, { type: "StepTextDelta", step: 0, text_delta: json, seq: 0 }),
    );
    state = reduceChat(
      state,
      stamp(2, {
        type: "DecisionMade",
        step: 0,
        action_type: "respond",
        rationale_preview: "",
        delegate_target: "",
        delegate_count: 0,
        tool_name: "",
        confidence: 1,
        response_text: "",
        output_truncated: false,
      }),
    );
    expect(state.answer).toBe("你好，这是正式回答。");
    expect(state.answer).not.toContain("action_type");
  });

  it("exports user-facing terminal action set", () => {
    expect(USER_FACING_TERMINAL_ACTIONS.has("respond")).toBe(true);
    expect(USER_FACING_TERMINAL_ACTIONS.has("delegate")).toBe(false);
  });

  it("projects write_file ToolInvoked result into chat.files", () => {
    const preview = JSON.stringify({
      name: "out.html",
      mimeType: "text/html",
      url: "/files/f1",
      sizeBytes: 9,
      previewable: true,
    });
    const state = reduceChat(
      {
        question: "q",
        answer: "",
        answerDeltas: [],
        status: "running",
        phase: "collaborating",
        files: [],
        pendingSteps: new Map(),
        committedAnswer: "",
      },
      stamp(1, {
        type: "ToolInvoked",
        tool_name: "write_file",
        arguments_preview: "{}",
        result_preview: preview,
        ok: true,
        latency_ms: 1,
        attempt: 1,
        error: "",
        invocation_id: "",
        files: [],
      }),
    );
    expect(state.files).toHaveLength(1);
    expect(state.files[0]?.name).toBe("out.html");
    expect(state.files[0]?.url).toBe("/files/f1");
  });

  it("prefers structured ToolInvoked.files when result_preview JSON is truncated", () => {
    const state = reduceChat(
      {
        question: "q",
        answer: "",
        answerDeltas: [],
        status: "running",
        phase: "collaborating",
        files: [],
        pendingSteps: new Map(),
        committedAnswer: "",
      },
      stamp(1, {
        type: "ToolInvoked",
        tool_name: "run_sandbox_code",
        arguments_preview: "{}",
        result_preview: '{"stdout": "' + "x".repeat(2100),
        ok: true,
        latency_ms: 10,
        attempt: 1,
        error: "",
        invocation_id: "inv_1",
        files: [
          {
            name: "chart_person.png",
            mimeType: "image/png",
            sizeBytes: 100,
            url: "/files/file_chart",
            previewable: true,
            attachmentId: "file_chart",
          },
          {
            name: "report.md",
            mimeType: "text/markdown",
            sizeBytes: 50,
            url: "/files/file_md",
            previewable: true,
            attachmentId: "file_md",
          },
        ],
      }),
    );
    expect(state.files).toHaveLength(2);
    expect(state.files.map((f) => f.name)).toEqual(["chart_person.png", "report.md"]);
    expect(state.files[0]?.previewable).toBe(true);
  });

  it("ignores decision-channel StepTextDelta for answer preview", () => {
    let state = reduceChat(
      {
        question: "q",
        answer: "",
        answerDeltas: [],
        status: "running",
        phase: "collaborating",
        files: [],
        pendingSteps: new Map(),
        committedAnswer: "",
      },
      stamp(1, {
        type: "StepTextDelta",
        step: 0,
        text_delta: '{"action_type":"use_tool"}',
        seq: 0,
        channel: "decision",
      }),
    );
    expect(state.answer).toBe("");
    state = reduceChat(
      state,
      stamp(2, {
        type: "StepTextDelta",
        step: 0,
        text_delta: "可见回答",
        seq: 1,
        channel: "answer",
      }),
    );
    expect(state.answer).toBe("可见回答");
  });

  it("tracks activityDetail from LlmCallStarted and RunActivity", () => {
    let state = reduceChat(
      {
        question: "q",
        answer: "",
        answerDeltas: [],
        status: "running",
        phase: "collaborating",
        files: [],
        pendingSteps: new Map(),
        committedAnswer: "",
      },
      stamp(1, { type: "LlmCallStarted", step: 1, model: "qwen-plus" }),
    );
    expect(state.activityDetail).toContain("qwen-plus");

    state = reduceChat(
      state,
      stamp(2, {
        type: "RunActivity",
        phase: "tool_running",
        step: 1,
        detail: "执行工具 sandbox_execute…",
        seq: 0,
      }),
    );
    expect(state.activityDetail).toBe("执行工具 sandbox_execute…");
  });
});

