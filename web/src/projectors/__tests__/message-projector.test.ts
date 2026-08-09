// web/src/projectors/__tests__/message-projector.test.ts
import { describe, it, expect } from "vitest";
import { MessageProjector } from "../message-projector";
import type { StampedEvent } from "../../contracts/stamped";
import type { JournalEvent, RunScope } from "../../contracts/journal.generated";
import type { Message } from "../message-types";

/* ── Test helpers ───────────────────────────────────────────────── */

const defaultScope: RunScope = {
  trace_id: "trace-1",
  run_id: "run-1",
  parent_run_id: null,
  delegation_id: null,
  agent_role: "researcher",
};

function makeStamped(
  event: Partial<JournalEvent> & { type: JournalEvent["type"] },
  overrides: { ts?: number; scope?: Partial<RunScope> } = {},
): StampedEvent {
  const scope: RunScope = { ...defaultScope, ...overrides.scope };
  return {
    seq: 0,
    ts: overrides.ts ?? 1000,
    scope,
    event: event as JournalEvent,
  };
}

/** Find the first message matching kind (and optionally id substring). */
function findByKind(
  msgs: readonly Message[],
  kind: string,
  idSubstring?: string,
): Message | undefined {
  return msgs.find(
    (m) => m.kind === kind && (idSubstring === undefined || m.id.includes(idSubstring)),
  );
}

/* ── Tests ──────────────────────────────────────────────────────── */

describe("MessageProjector", () => {
  /* 1. Thinking messages */
  describe("thinking messages", () => {
    it("should create a thinking message on ReasoningDelta and append text", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "Hello ", seq: 0 }),
      );
      proj.onEvent(
        makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "world", seq: 1 }),
      );

      const msgs = proj.getMessages();
      const thinking = findByKind(msgs, "thinking");
      expect(thinking).toBeDefined();
      expect(thinking!.content).toBe("Hello world");
      expect(thinking!.streaming).toBe(true);
      expect(thinking!.status).toBe("running");
      expect(thinking!.agentRole).toBe("researcher");
    });

    it("should create separate thinking messages per agent role", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped(
          { type: "ReasoningDelta", step: 1, text_delta: "A thinking", seq: 0 },
          { scope: { agent_role: "agent_a" } },
        ),
      );
      proj.onEvent(
        makeStamped(
          { type: "ReasoningDelta", step: 1, text_delta: "B thinking", seq: 0 },
          { scope: { agent_role: "agent_b" } },
        ),
      );

      const msgs = proj.getMessages();
      const thinkingMsgs = msgs.filter((m) => m.kind === "thinking");
      expect(thinkingMsgs).toHaveLength(2);
      expect(thinkingMsgs.find((m) => m.agentRole === "agent_a")!.content).toBe("A thinking");
      expect(thinkingMsgs.find((m) => m.agentRole === "agent_b")!.content).toBe("B thinking");
    });

    it("should finalize thinking on ReasoningCompleted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "thinking...", seq: 0 }),
      );
      proj.onEvent(
        makeStamped({ type: "ReasoningCompleted", step: 1, duration_ms: 500, content_preview: "" }),
      );

      const msgs = proj.getMessages();
      const thinking = findByKind(msgs, "thinking");
      expect(thinking).toBeDefined();
      expect(thinking!.streaming).toBe(false);
      expect(thinking!.status).toBe("done");
      expect(thinking!.metadata?.durationMs).toBe(500);
      expect(thinking!.completedAt).toBeDefined();
    });

    it("should use content_preview as fallback when no delta was received", () => {
      const proj = new MessageProjector();
      // ReasoningCompleted without any prior ReasoningDelta
      proj.onEvent(
        makeStamped({
          type: "ReasoningCompleted",
          step: 1,
          duration_ms: 300,
          content_preview: "preview text",
        }),
      );

      // No message was created since there was no delta — that's expected
      const msgs = proj.getMessages();
      expect(msgs.filter((m) => m.kind === "thinking")).toHaveLength(0);
    });

    it("should use content_preview when delta content is empty", () => {
      const proj = new MessageProjector();
      // Create a thinking message with empty content via a whitespace-only delta
      proj.onEvent(
        makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "   ", seq: 0 }),
      );
      proj.onEvent(
        makeStamped({
          type: "ReasoningCompleted",
          step: 1,
          duration_ms: 200,
          content_preview: "actual content",
        }),
      );

      const msgs = proj.getMessages();
      const thinking = findByKind(msgs, "thinking");
      expect(thinking).toBeDefined();
      // Whitespace-only delta means content is "   " which is falsy after .trim()
      // so content_preview should be used
      expect(thinking!.content).toBe("actual content");
    });
  });

  /* 2. Tool call messages */
  describe("tool call messages", () => {
    it("should create a running tool_call on ToolStarted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "ToolStarted",
          tool_name: "calculator",
          arguments_preview: "2+2",
          invocation_id: "inv-1",
        }),
      );

      const msgs = proj.getMessages();
      const tool = findByKind(msgs, "tool_call");
      expect(tool).toBeDefined();
      expect(tool!.status).toBe("running");
      expect(tool!.streaming).toBe(true);
      expect(tool!.metadata?.toolName).toBe("calculator");
      expect(tool!.metadata?.argumentsPreview).toBe("2+2");
      expect(tool!.metadata?.invocationId).toBe("inv-1");
    });

    it("should update tool_call to done on ToolInvoked (ok=true)", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "ToolStarted",
          tool_name: "calculator",
          arguments_preview: "2+2",
          invocation_id: "inv-1",
        }),
      );
      proj.onEvent(
        makeStamped(
          {
            type: "ToolInvoked",
            tool_name: "calculator",
            arguments_preview: "2+2",
            result_preview: "4",
            ok: true,
            latency_ms: 120,
            attempt: 1,
            error: "",
            invocation_id: "inv-1",
            files: [],
          },
          { ts: 1120 },
        ),
      );

      const msgs = proj.getMessages();
      const tool = findByKind(msgs, "tool_call");
      expect(tool).toBeDefined();
      expect(tool!.status).toBe("done");
      expect(tool!.streaming).toBe(false);
      expect(tool!.content).toBe("4");
      expect(tool!.metadata?.latencyMs).toBe(120);
      expect(tool!.metadata?.ok).toBe(true);
      expect(tool!.completedAt).toBe(1120);
    });

    it("should update tool_call to error on ToolInvoked (ok=false)", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "ToolStarted",
          tool_name: "web_search",
          arguments_preview: "query",
          invocation_id: "inv-2",
        }),
      );
      proj.onEvent(
        makeStamped({
          type: "ToolInvoked",
          tool_name: "web_search",
          arguments_preview: "query",
          result_preview: "",
          ok: false,
          latency_ms: 5000,
          attempt: 1,
          error: "timeout",
          invocation_id: "inv-2",
          files: [],
        }),
      );

      const msgs = proj.getMessages();
      const tool = findByKind(msgs, "tool_call");
      expect(tool).toBeDefined();
      expect(tool!.status).toBe("error");
      expect(tool!.metadata?.ok).toBe(false);
      expect(tool!.metadata?.error).toBe("timeout");
    });

    it("should create a tool message on ToolInvoked without prior ToolStarted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "ToolInvoked",
          tool_name: "orphan_tool",
          arguments_preview: "args",
          result_preview: "result",
          ok: true,
          latency_ms: 50,
          attempt: 1,
          error: "",
          invocation_id: "inv-orphan",
          files: [],
        }),
      );

      const msgs = proj.getMessages();
      const tool = findByKind(msgs, "tool_call");
      expect(tool).toBeDefined();
      expect(tool!.status).toBe("done");
      expect(tool!.metadata?.toolName).toBe("orphan_tool");
    });
  });

  /* 3. Answer messages */
  describe("answer messages", () => {
    it("should create a streaming answer on StepTextDelta", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "Hello ", seq: 0, channel: "decision" }),
      );
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "world", seq: 1, channel: "decision" }),
      );

      const msgs = proj.getMessages();
      const answer = findByKind(msgs, "answer");
      expect(answer).toBeDefined();
      expect(answer!.content).toBe("Hello world");
      expect(answer!.streaming).toBe(true);
      expect(answer!.status).toBe("running");
    });

    it("should aggregate decision + answer channels", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "decision ", seq: 0, channel: "decision" }),
      );
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "answer", seq: 0, channel: "answer" }),
      );

      const msgs = proj.getMessages();
      const answer = findByKind(msgs, "answer");
      expect(answer).toBeDefined();
      expect(answer!.content).toBe("decision answer");
    });

    it("should commit answer on DecisionMade with response_text", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "streaming...", seq: 0, channel: "decision" }),
      );
      proj.onEvent(
        makeStamped({
          type: "DecisionMade",
          step: 1,
          action_type: "respond",
          rationale_preview: "",
          delegate_target: "",
          delegate_count: 0,
          tool_name: "",
          confidence: 1,
          response_text: "Final answer",
          output_truncated: false,
        }),
      );

      const msgs = proj.getMessages();
      const answer = findByKind(msgs, "answer");
      expect(answer).toBeDefined();
      expect(answer!.streaming).toBe(false);
      expect(answer!.status).toBe("done");
      // Canonical response_text takes priority
      expect(answer!.content).toBe("Final answer");
    });

    it("should fall back to buffer when response_text is empty", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "buffered text", seq: 0, channel: "decision" }),
      );
      proj.onEvent(
        makeStamped({
          type: "DecisionMade",
          step: 1,
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

      const msgs = proj.getMessages();
      const answer = findByKind(msgs, "answer");
      expect(answer).toBeDefined();
      expect(answer!.streaming).toBe(false);
      expect(answer!.content).toBe("buffered text");
    });

    it("should create answer from DecisionMade without prior StepTextDelta", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "DecisionMade",
          step: 2,
          action_type: "stop",
          rationale_preview: "",
          delegate_target: "",
          delegate_count: 0,
          tool_name: "",
          confidence: 1,
          response_text: "Direct response",
          output_truncated: false,
        }),
      );

      const msgs = proj.getMessages();
      const answer = msgs.find((m) => m.id.includes("answer:run-1:2"));
      expect(answer).toBeDefined();
      expect(answer!.content).toBe("Direct response");
      expect(answer!.streaming).toBe(false);
      expect(answer!.status).toBe("done");
    });

    it("should NOT commit answer for non-terminal action types", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "StepTextDelta", step: 1, text_delta: "thinking out loud", seq: 0, channel: "decision" }),
      );
      proj.onEvent(
        makeStamped({
          type: "DecisionMade",
          step: 1,
          action_type: "use_tool", // not user-facing
          rationale_preview: "",
          delegate_target: "",
          delegate_count: 0,
          tool_name: "calculator",
          confidence: 1,
          response_text: "",
          output_truncated: false,
        }),
      );

      const msgs = proj.getMessages();
      const answer = findByKind(msgs, "answer");
      expect(answer).toBeDefined();
      // Should still be streaming — not committed
      expect(answer!.streaming).toBe(true);
      expect(answer!.status).toBe("running");
    });
  });

  /* 4. Casting messages */
  describe("casting messages", () => {
    it("should create a running casting message on CastingStarted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "CastingStarted", objective_preview: "Build a website" }),
      );

      const msgs = proj.getMessages();
      const casting = findByKind(msgs, "casting");
      expect(casting).toBeDefined();
      expect(casting!.status).toBe("running");
      expect(casting!.metadata?.objectivePreview).toBe("Build a website");
    });

    it("should update casting to done on CastingCompleted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "CastingStarted", objective_preview: "Build a website" }),
      );
      proj.onEvent(
        makeStamped({
          type: "CastingCompleted",
          governance_kind: "board",
          lead_role: "pm",
          selected_roles: ["dev", "designer"],
          rationale: "Need dev and design skills",
        }),
      );

      const msgs = proj.getMessages();
      const casting = findByKind(msgs, "casting");
      expect(casting).toBeDefined();
      expect(casting!.status).toBe("done");
      expect(casting!.streaming).toBe(false);
      expect(casting!.metadata?.governanceKind).toBe("board");
      expect(casting!.metadata?.leadRole).toBe("pm");
      expect(casting!.metadata?.selectedRoles).toEqual(["dev", "designer"]);
      expect(casting!.metadata?.rationale).toBe("Need dev and design skills");
    });

    it("should create an error message on CastingFailed", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "CastingStarted", objective_preview: "task" }),
      );
      proj.onEvent(
        makeStamped({ type: "CastingFailed", error: "No agents available" }),
      );

      const msgs = proj.getMessages();
      const error = findByKind(msgs, "error");
      expect(error).toBeDefined();
      expect(error!.content).toBe("No agents available");
      expect(error!.status).toBe("error");

      // Casting message should also be marked as error
      const casting = findByKind(msgs, "casting");
      expect(casting).toBeDefined();
      expect(casting!.status).toBe("error");
    });
  });

  /* 5. Delegation messages */
  describe("delegation messages", () => {
    it("should create a running delegation message on DelegationIssued", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "DelegationIssued",
          delegation_id: "del-1",
          caller_role: "pm",
          callee_role: "dev",
          subtask_preview: "Implement feature X",
          mechanism: "delegate",
          parallel_group: "",
        }),
      );

      const msgs = proj.getMessages();
      const delegation = findByKind(msgs, "delegation");
      expect(delegation).toBeDefined();
      expect(delegation!.status).toBe("running");
      expect(delegation!.metadata?.delegationId).toBe("del-1");
      expect(delegation!.metadata?.calleeRole).toBe("dev");
      expect(delegation!.metadata?.fromRole).toBe("pm");
      expect(delegation!.metadata?.subtaskPreview).toBe("Implement feature X");
    });

    it("should update delegation to done on DelegationCompleted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "DelegationIssued",
          delegation_id: "del-1",
          caller_role: "pm",
          callee_role: "dev",
          subtask_preview: "Implement feature X",
          mechanism: "delegate",
          parallel_group: "",
        }),
      );
      proj.onEvent(
        makeStamped({
          type: "DelegationCompleted",
          delegation_id: "del-1",
          ok: true,
          status: "completed",
          output_text: "Feature X implemented",
          output_truncated: false,
          task_id: "task-1",
        }),
      );

      const msgs = proj.getMessages();
      const delegation = findByKind(msgs, "delegation");
      expect(delegation).toBeDefined();
      expect(delegation!.status).toBe("done");
      expect(delegation!.streaming).toBe(false);
      expect(delegation!.content).toBe("Feature X implemented");
      expect(delegation!.metadata?.resultPreview).toBe("Feature X implemented");
    });

    it("should handle orphan DelegationCompleted (no prior Issued)", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "DelegationCompleted",
          delegation_id: "del-orphan",
          ok: true,
          status: "completed",
          output_text: "done",
          output_truncated: false,
          task_id: "task-1",
        }),
      );

      const msgs = proj.getMessages();
      const delegation = findByKind(msgs, "delegation", "del-orphan");
      expect(delegation).toBeDefined();
      expect(delegation!.status).toBe("done");
    });
  });

  /* 6. Turn status updates */
  describe("turn status updates", () => {
    it("should set team mode and teamId on TeamRunStarted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "TeamRunStarted",
          team_id: "team-alpha",
          strategy_key: "board",
          mandate: "consult",
          lead_role: "pm",
          members: ["dev", "designer"],
          objective: "Build something great",
          objective_preview: "Build something great",
          plan_steps: "1. Design 2. Build",
        }),
      );

      const turn = proj.buildTurn("turn-1");
      expect(turn.mode).toBe("team");
      expect(turn.teamId).toBe("team-alpha");
      expect(turn.question).toBe("Build something great");
      expect(turn.status).toBe("running");
    });

    it("should update question from AgentRunStarted if not yet set", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "AgentRunStarted",
          agent_role: "solo_dev",
          strategy_key: "react",
          objective: "Fix the bug",
          objective_preview: "Fix the bug",
          from_role: "",
        }),
      );

      const turn = proj.buildTurn("turn-2");
      expect(turn.question).toBe("Fix the bug");
      expect(turn.status).toBe("running");
    });

    it("should set completed status on TeamRunFinished", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "TeamRunFinished",
          status: "completed",
          output_text: "All done",
          output_truncated: false,
          steps: 5,
          error: "",
        }),
      );

      const turn = proj.buildTurn("turn-3");
      expect(turn.status).toBe("completed");
      expect(turn.completedAt).toBeDefined();
    });

    it("should set failed status on TeamRunFinished with error", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "TeamRunFinished",
          status: "failed",
          output_text: "",
          output_truncated: false,
          steps: 2,
          error: "Something went wrong",
        }),
      );

      const turn = proj.buildTurn("turn-4");
      expect(turn.status).toBe("failed");
      expect(turn.errorMessage).toBe("Something went wrong");
    });

    it("should set failed status on AgentRunFinished with non-completed status", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "AgentRunFinished",
          status: "failed",
          output_text: "",
          output_truncated: false,
          steps: 1,
          error: "Agent crashed",
        }),
      );

      const turn = proj.buildTurn("turn-5");
      expect(turn.status).toBe("failed");
      expect(turn.errorMessage).toBe("Agent crashed");
    });
  });

  /* 7. Synthesis and Insight */
  describe("synthesis and insight messages", () => {
    it("should create a synthesis message on SynthesisCompleted", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "SynthesisCompleted",
          method: "board_vote",
          candidate_count: 3,
          output_text: "Synthesized answer",
          output_truncated: false,
        }),
      );

      const msgs = proj.getMessages();
      const synth = findByKind(msgs, "synthesis");
      expect(synth).toBeDefined();
      expect(synth!.content).toBe("Synthesized answer");
      expect(synth!.status).toBe("done");
      expect(synth!.metadata?.method).toBe("board_vote");
      expect(synth!.metadata?.candidateCount).toBe(3);
    });

    it("should create an insight message on RunInsight", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "RunInsight",
          kind: "redundant_tool_call",
          summary: "Tool called twice",
          detail: "calculator was invoked at step 2 and 4 with same args",
        }),
      );

      const msgs = proj.getMessages();
      const insight = findByKind(msgs, "insight");
      expect(insight).toBeDefined();
      expect(insight!.content).toBe("Tool called twice");
      expect(insight!.status).toBe("done");
      expect(insight!.metadata?.insightKind).toBe("redundant_tool_call");
      expect(insight!.metadata?.detail).toBe("calculator was invoked at step 2 and 4 with same args");
    });
  });

  /* 8. Sandbox messages */
  describe("sandbox messages", () => {
    it("should create and accumulate sandbox messages on SandboxOutputDelta", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({
          type: "SandboxOutputDelta",
          invocation_id: "inv-sb",
          stream: "stdout",
          text_delta: "line 1\n",
          seq: 0,
        }),
      );
      proj.onEvent(
        makeStamped({
          type: "SandboxOutputDelta",
          invocation_id: "inv-sb",
          stream: "stdout",
          text_delta: "line 2\n",
          seq: 1,
        }),
      );
      proj.onEvent(
        makeStamped({
          type: "SandboxOutputDelta",
          invocation_id: "inv-sb",
          stream: "stderr",
          text_delta: "warning!",
          seq: 0,
        }),
      );

      const msgs = proj.getMessages();
      const stdout = msgs.find((m) => m.id.includes("sandbox:inv-sb:stdout"));
      const stderr = msgs.find((m) => m.id.includes("sandbox:inv-sb:stderr"));
      expect(stdout).toBeDefined();
      expect(stdout!.content).toContain("line 1\nline 2\n");
      expect(stderr).toBeDefined();
      expect(stderr!.content).toContain("warning!");
    });
  });

  /* 9. buildTurn produces sorted immutable snapshot */
  describe("buildTurn", () => {
    it("should return sorted messages without internal buffer field", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "CastingStarted", objective_preview: "task" }),
      );
      proj.onEvent(
        makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "thinking", seq: 0 }),
      );

      const turn = proj.buildTurn("turn-x");
      expect(turn.id).toBe("turn-x");
      expect(turn.messages.length).toBeGreaterThanOrEqual(2);
      // Verify no `buffer` field leaks into the snapshot
      for (const msg of turn.messages) {
        expect((msg as unknown as Record<string, unknown>).buffer).toBeUndefined();
      }
    });

    it("should reset state correctly", () => {
      const proj = new MessageProjector();
      proj.onEvent(
        makeStamped({ type: "CastingStarted", objective_preview: "task" }),
      );
      expect(proj.getMessages().length).toBe(1);

      proj.reset();
      expect(proj.getMessages()).toHaveLength(0);
    });
  });
});
