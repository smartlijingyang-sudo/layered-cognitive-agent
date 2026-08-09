/**
 * Turn timeline projector — journal events → LobeHub-style process blocks + final answer.
 *
 * Architecture (mirrors LobeHub AssistantGroup segments, not their message store):
 * - process[]: casting / thinking / tools / sandbox / delegations / intermediate decisions
 * - finalAnswer: ADR-0045 canonical response_text / run output (always outside ProcessFold)
 * - foldProcess: after turn ends, collapse process under "共运行 N 步"
 */

import type { StampedEvent } from "../contracts/stamped";
import type { GeneratedFile } from "../domain/generated-file";
import { extractUserFacingAnswer } from "../lib/extract-decision-text";
import { filesFromToolInvoked } from "../lib/parse-generated-file";
import { USER_FACING_TERMINAL_ACTIONS } from "./chat-projector";
import type {
  CastingBlock,
  DecisionProcessBlock,
  DelegationBlock,
  InsightBlock,
  RunPhase,
  SandboxBlock,
  ThinkingBlock,
  ToolBlock,
  TurnProcessBlock,
  TurnTimeline,
} from "./types";
import { EMPTY_TURN_TIMELINE } from "./types";

const THINKING_ID = "thinking:main";
const CASTING_ID = "casting:main";

interface ToolEntry {
  readonly id: string;
  readonly toolName: string;
  readonly argumentsPreview: string;
  readonly resultPreview: string;
  readonly status: ToolBlock["status"];
  readonly ok?: boolean;
  readonly latencyMs?: number;
  readonly error?: string;
  readonly invocationId: string;
  readonly agentRole?: string;
  readonly order: number;
}

interface SandboxEntry {
  readonly id: string;
  readonly invocationId: string;
  readonly stdout: string;
  readonly stderr: string;
  readonly sealed: boolean;
  readonly agentRole?: string;
  readonly order: number;
  readonly stdoutDeltas: ReadonlyMap<number, string>;
  readonly stderrDeltas: ReadonlyMap<number, string>;
}

interface DelegationEntry {
  readonly id: string;
  readonly delegationId: string;
  readonly calleeRole: string;
  readonly subtaskPreview: string;
  readonly fromRole?: string;
  readonly resultPreview?: string;
  readonly status: DelegationBlock["status"];
  readonly order: number;
}

interface DecisionEntry {
  readonly id: string;
  readonly step: number;
  readonly actionType: string;
  readonly toolName?: string;
  readonly delegateTarget?: string;
  readonly rationalePreview?: string;
  readonly agentRole?: string;
  readonly confidence?: number;
  readonly order: number;
}

interface InsightEntry {
  readonly id: string;
  readonly insightKind: string;
  readonly summary: string;
  readonly detail: string;
  readonly order: number;
}

interface InternalState {
  readonly phase: RunPhase;
  readonly status: TurnTimeline["status"];
  readonly errorMessage?: string;
  readonly casting?: CastingBlock;
  readonly thinkingContent: string;
  readonly thinkingStatus: ThinkingBlock["status"] | "idle";
  readonly thinkingStartedTs?: number;
  readonly thinkingEndedTs?: number;
  /** True once ReasoningDelta arrived — prefer model reasoning over synthetic text. */
  readonly hasModelReasoning: boolean;
  readonly tools: ReadonlyMap<string, ToolEntry>;
  readonly sandboxes: ReadonlyMap<string, SandboxEntry>;
  readonly delegations: ReadonlyMap<string, DelegationEntry>;
  readonly decisions: readonly DecisionEntry[];
  readonly insights: readonly InsightEntry[];
  readonly finalAnswer: string;
  readonly committedAnswer: string;
  readonly pendingStepText: ReadonlyMap<string, string>;
  readonly files: readonly GeneratedFile[];
  readonly startedTs?: number;
  readonly endedTs?: number;
  readonly orderSeq: number;
  readonly assistantStepIds: ReadonlySet<string>;
}

const EMPTY_INTERNAL: InternalState = {
  phase: "idle",
  status: "idle",
  thinkingContent: "",
  thinkingStatus: "idle",
  hasModelReasoning: false,
  tools: new Map(),
  sandboxes: new Map(),
  delegations: new Map(),
  decisions: [],
  insights: [],
  finalAnswer: "",
  committedAnswer: "",
  pendingStepText: new Map(),
  files: [],
  orderSeq: 0,
  assistantStepIds: new Set(),
};

function nextOrder(state: InternalState): { order: number; orderSeq: number } {
  return { order: state.orderSeq, orderSeq: state.orderSeq + 1 };
}

function stepKey(runId: string, step: number): string {
  return `${runId}:${step}`;
}

function toolKey(invocationId: string, toolName: string, fallback: string): string {
  if (invocationId) return `tool:${invocationId}`;
  return `tool:${toolName}:${fallback}`;
}

function sandboxKey(invocationId: string): string {
  return `sandbox:${invocationId || "unknown"}`;
}

function orderedText(deltas: ReadonlyMap<number, string>): string {
  return [...deltas.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, t]) => t)
    .join("");
}

function appendThinking(
  state: InternalState,
  chunk: string,
  ts: number,
  options: { readonly fromModel?: boolean; readonly rawAppend?: boolean } = {},
): InternalState {
  const fromModel = options.fromModel ?? false;
  const rawAppend = options.rawAppend ?? false;
  const text = rawAppend ? chunk : chunk.trim();
  if (!text) return state;
  // Once true model reasoning exists, ignore synthetic casting/delegation prose.
  if (state.hasModelReasoning && !fromModel) return state;
  const content = state.thinkingContent
    ? state.thinkingContent.endsWith("\n") || rawAppend
      ? `${state.thinkingContent}${text}`
      : `${state.thinkingContent}\n${text}`
    : text;
  return {
    ...state,
    thinkingContent: content,
    thinkingStatus: state.thinkingStatus === "done" && !fromModel ? "done" : "running",
    thinkingStartedTs: state.thinkingStartedTs ?? ts,
    hasModelReasoning: state.hasModelReasoning || fromModel,
  };
}

function finishThinking(state: InternalState, ts: number): InternalState {
  if (state.thinkingStatus !== "running" && !state.thinkingContent) return state;
  if (!state.thinkingContent && state.thinkingStatus === "idle") return state;
  return {
    ...state,
    thinkingStatus: state.thinkingContent ? "done" : "idle",
    thinkingEndedTs: state.thinkingEndedTs ?? ts,
  };
}

function fileKey(f: GeneratedFile): string {
  return f.url || `${f.name}:${f.mimeType}`;
}

function mergeFiles(
  existing: readonly GeneratedFile[],
  added: readonly GeneratedFile[],
): readonly GeneratedFile[] {
  if (!added.length) return existing;
  const seen = new Set(existing.map(fileKey));
  const next = [...existing];
  for (const f of added) {
    const key = fileKey(f);
    if (!seen.has(key)) {
      seen.add(key);
      next.push(f);
    }
  }
  return next;
}

function markAssistantStep(state: InternalState, runId: string, step: number): InternalState {
  const id = stepKey(runId, step);
  if (state.assistantStepIds.has(id)) return state;
  const next = new Set(state.assistantStepIds);
  next.add(id);
  return { ...state, assistantStepIds: next };
}

/** Pure reducer for one stamped journal event. */
export function reduceTurnTimeline(state: InternalState, stamped: StampedEvent): InternalState {
  const e = stamped.event;
  const ts = stamped.ts;
  const runId = stamped.scope.run_id;
  const role = stamped.scope.agent_role;

  switch (e.type) {
    case "CastingStarted": {
      const { order, orderSeq } = nextOrder(state);
      void order;
      return {
        ...state,
        orderSeq,
        status: "running",
        phase: "casting",
        startedTs: state.startedTs ?? ts,
        casting: {
          kind: "casting",
          id: CASTING_ID,
          status: "running",
          objectivePreview: e.objective_preview,
        },
        thinkingStatus: "running",
        thinkingStartedTs: state.thinkingStartedTs ?? ts,
        thinkingContent: state.thinkingContent || "正在分析问题并挑选合适团队…",
      };
    }
    case "CastingCompleted": {
      return finishThinking(
        {
          ...state,
          status: "running",
          phase: "collaborating",
          casting: {
            kind: "casting",
            id: CASTING_ID,
            status: "done",
            governanceKind: e.governance_kind,
            leadRole: e.lead_role,
            selectedRoles: e.selected_roles,
            rationale: e.rationale,
          },
          thinkingContent: e.rationale
            ? appendThinking(state, e.rationale, ts).thinkingContent
            : state.thinkingContent,
        },
        ts,
      );
    }
    case "CastingFailed":
      return {
        ...state,
        status: "failed",
        phase: "failed",
        errorMessage: e.error || "自动组队失败",
        casting: {
          kind: "casting",
          id: CASTING_ID,
          status: "error",
          error: e.error,
        },
        thinkingStatus: "idle",
        endedTs: ts,
      };
    case "TeamRunStarted":
    case "AgentRunStarted":
      return {
        ...state,
        status: "running",
        phase: state.phase === "casting" ? "collaborating" : state.phase === "idle" ? "collaborating" : state.phase,
        startedTs: state.startedTs ?? ts,
        thinkingStatus: state.thinkingStatus === "idle" ? "running" : state.thinkingStatus,
        thinkingStartedTs: state.thinkingStartedTs ?? ts,
      };
    case "TeamRunFinished":
    case "AgentRunFinished": {
      const finished = finishThinking(state, ts);
      const status = e.status === "completed" ? "completed" : "failed";
      const answer =
        extractUserFacingAnswer(e.output_text || finished.committedAnswer || finished.finalAnswer) ||
        e.output_text ||
        finished.committedAnswer ||
        finished.finalAnswer;
      return {
        ...finished,
        status,
        phase: status === "completed" ? "completed" : "failed",
        finalAnswer: answer,
        committedAnswer: answer,
        errorMessage: e.error || finished.errorMessage,
        endedTs: ts,
        pendingStepText: new Map(),
      };
    }
    case "SynthesisCompleted": {
      const answer =
        extractUserFacingAnswer(e.output_text || state.committedAnswer) ||
        e.output_text ||
        state.committedAnswer;
      return finishThinking(
        {
          ...state,
          phase: "synthesizing",
          finalAnswer: answer,
          committedAnswer: answer,
        },
        ts,
      );
    }
    case "StepTextDelta": {
      const key = stepKey(runId, e.step);
      const prev = state.pendingStepText.get(key) ?? "";
      const nextPending = new Map(state.pendingStepText);
      nextPending.set(key, prev + e.text_delta);
      const raw = nextPending.get(key) ?? "";
      const preview = extractUserFacingAnswer(raw, { allowPartial: true });
      let next: InternalState = {
        ...state,
        pendingStepText: nextPending,
        status: "running",
        startedTs: state.startedTs ?? ts,
        thinkingStatus: state.thinkingStatus === "idle" ? "running" : state.thinkingStatus,
        thinkingStartedTs: state.thinkingStartedTs ?? ts,
      };
      next = markAssistantStep(next, runId, e.step);
      if (preview) {
        const answer = state.committedAnswer ? `${state.committedAnswer}${preview}` : preview;
        return { ...next, finalAnswer: answer };
      }
      return next;
    }
    case "ReasoningDelta": {
      return appendThinking(
        {
          ...state,
          status: "running",
          startedTs: state.startedTs ?? ts,
        },
        e.text_delta,
        ts,
        { fromModel: true, rawAppend: true },
      );
    }
    case "ReasoningCompleted": {
      let next = state;
      if (e.content_preview?.trim() && !state.thinkingContent.trim()) {
        next = appendThinking(next, e.content_preview, ts, { fromModel: true });
      }
      const ended =
        next.thinkingStartedTs != null && e.duration_ms > 0
          ? next.thinkingStartedTs + e.duration_ms
          : ts;
      return {
        ...finishThinking(next, ended),
        thinkingEndedTs: ended,
        hasModelReasoning: next.hasModelReasoning || Boolean(e.content_preview?.trim()),
      };
    }
    case "DecisionMade": {
      let next = markAssistantStep(state, runId, e.step);
      const pendingKey = stepKey(runId, e.step);
      const nextPending = new Map(next.pendingStepText);
      nextPending.delete(pendingKey);

      if (e.rationale_preview?.trim()) {
        next = appendThinking(next, e.rationale_preview.trim(), ts);
      }

      if (USER_FACING_TERMINAL_ACTIONS.has(e.action_type)) {
        const canonical = e.response_text?.trim() ?? "";
        const fromPending = state.pendingStepText.get(pendingKey);
        const fallback = fromPending
          ? (extractUserFacingAnswer(fromPending) ?? fromPending)
          : "";
        const text = canonical || fallback;
        const committed = text
          ? next.committedAnswer
            ? `${next.committedAnswer}${text}`
            : text
          : next.committedAnswer;
        return finishThinking(
          {
            ...next,
            pendingStepText: nextPending,
            committedAnswer: committed,
            finalAnswer: committed,
          },
          ts,
        );
      }

      // Intermediate decision → process block
      const { order, orderSeq } = nextOrder(next);
      const decision: DecisionEntry = {
        id: `decision:${runId}:${e.step}:${order}`,
        step: e.step,
        actionType: e.action_type,
        toolName: e.tool_name || undefined,
        delegateTarget: e.delegate_target || undefined,
        rationalePreview: e.rationale_preview || undefined,
        agentRole: role || undefined,
        confidence: e.confidence,
        order,
      };
      return {
        ...next,
        orderSeq,
        pendingStepText: nextPending,
        decisions: [...next.decisions, decision],
        finalAnswer: next.committedAnswer,
      };
    }
    case "SandboxOutputDelta": {
      const id = sandboxKey(e.invocation_id);
      const prev = state.sandboxes.get(id);
      const stdoutDeltas = new Map(prev?.stdoutDeltas ?? []);
      const stderrDeltas = new Map(prev?.stderrDeltas ?? []);
      if (e.stream === "stderr") {
        stderrDeltas.set(e.seq, e.text_delta);
      } else {
        stdoutDeltas.set(e.seq, e.text_delta);
      }
      const { order, orderSeq } = prev
        ? { order: prev.order, orderSeq: state.orderSeq }
        : nextOrder(state);
      const entry: SandboxEntry = {
        id,
        invocationId: e.invocation_id,
        stdout: orderedText(stdoutDeltas),
        stderr: orderedText(stderrDeltas),
        sealed: prev?.sealed ?? false,
        agentRole: role || prev?.agentRole,
        order,
        stdoutDeltas,
        stderrDeltas,
      };
      const sandboxes = new Map(state.sandboxes);
      sandboxes.set(id, entry);

      // Ensure a running tool shell exists for live sandbox before ToolInvoked.
      let tools: Map<string, ToolEntry> = new Map(state.tools);
      let nextOrderSeq = orderSeq;
      if (e.invocation_id && !tools.has(`tool:${e.invocation_id}`)) {
        const tOrder = nextOrderSeq;
        nextOrderSeq += 1;
        tools.set(`tool:${e.invocation_id}`, {
          id: `tool:${e.invocation_id}`,
          toolName: "run_code",
          argumentsPreview: "",
          resultPreview: "",
          status: "running",
          invocationId: e.invocation_id,
          agentRole: role || undefined,
          order: tOrder,
        });
      }

      return {
        ...state,
        orderSeq: nextOrderSeq,
        sandboxes,
        tools,
        status: "running",
        startedTs: state.startedTs ?? ts,
        thinkingStatus: state.thinkingStatus === "idle" ? "running" : state.thinkingStatus,
        thinkingStartedTs: state.thinkingStartedTs ?? ts,
      };
    }
    case "ToolStarted": {
      const key = toolKey(e.invocation_id, e.tool_name, `${ts}:${state.orderSeq}`);
      const prev = state.tools.get(key) ?? state.tools.get(`tool:${e.invocation_id}`);
      const { order, orderSeq } = prev
        ? { order: prev.order, orderSeq: state.orderSeq }
        : nextOrder(state);
      const entry: ToolEntry = {
        id: key,
        toolName: e.tool_name,
        argumentsPreview: e.arguments_preview || prev?.argumentsPreview || "",
        resultPreview: prev?.resultPreview || "",
        status: "running",
        invocationId: e.invocation_id || prev?.invocationId || "",
        agentRole: role || prev?.agentRole,
        order,
      };
      const tools = new Map(state.tools);
      if (prev && prev.id !== key) tools.delete(prev.id);
      tools.set(entry.id, entry);
      return {
        ...state,
        orderSeq,
        tools,
        status: "running",
        startedTs: state.startedTs ?? ts,
      };
    }
    case "ToolInvoked": {
      const key = toolKey(e.invocation_id, e.tool_name, `${ts}:${state.orderSeq}`);
      const prev = state.tools.get(key) ?? state.tools.get(`tool:${e.invocation_id}`);
      const { order, orderSeq } = prev
        ? { order: prev.order, orderSeq: state.orderSeq }
        : nextOrder(state);
      const entry: ToolEntry = {
        id: key,
        toolName: e.tool_name,
        argumentsPreview: e.arguments_preview,
        resultPreview: e.result_preview,
        status: e.ok ? "done" : "error",
        ok: e.ok,
        latencyMs: e.latency_ms,
        error: e.error || undefined,
        invocationId: e.invocation_id || prev?.invocationId || "",
        agentRole: role || prev?.agentRole,
        order,
      };
      const tools = new Map(state.tools);
      if (prev && prev.id !== key) tools.delete(prev.id);
      tools.set(entry.id, entry);

      let sandboxes: Map<string, SandboxEntry> = new Map(state.sandboxes);
      if (entry.invocationId) {
        const sk = sandboxKey(entry.invocationId);
        const sb = sandboxes.get(sk);
        if (sb && !sb.sealed) {
          sandboxes.set(sk, { ...sb, sealed: true });
        }
      }

      const extracted = filesFromToolInvoked({
        toolName: e.tool_name,
        resultPreview: e.result_preview,
        ok: e.ok,
        files: e.files,
      });
      return {
        ...state,
        orderSeq,
        tools,
        sandboxes,
        files: mergeFiles(state.files, extracted),
        status: "running",
      };
    }
    case "ToolDenied": {
      const { order, orderSeq } = nextOrder(state);
      const id = `tool-denied:${e.tool_name}:${order}`;
      const tools = new Map(state.tools);
      tools.set(id, {
        id,
        toolName: e.tool_name,
        argumentsPreview: "",
        resultPreview: "",
        status: "error",
        ok: false,
        error: e.reason,
        invocationId: "",
        agentRole: role || undefined,
        order,
      });
      return { ...state, orderSeq, tools };
    }
    case "DelegationIssued": {
      const { order, orderSeq } = nextOrder(state);
      const id = `delegation:${e.delegation_id || order}`;
      const delegations = new Map(state.delegations);
      delegations.set(id, {
        id,
        delegationId: e.delegation_id,
        calleeRole: e.callee_role,
        subtaskPreview: e.subtask_preview,
        fromRole: e.caller_role || role || undefined,
        status: "running",
        order,
      });
      return appendThinking(
        { ...state, orderSeq, delegations, status: "running", phase: "collaborating" },
        `委派 → ${e.callee_role}${e.subtask_preview ? `：${e.subtask_preview}` : ""}`,
        ts,
      );
    }
    case "DelegationCompleted": {
      const delegations = new Map(state.delegations);
      let matchId: string | undefined;
      for (const [id, d] of delegations) {
        if (e.delegation_id && d.delegationId === e.delegation_id) {
          matchId = id;
          break;
        }
      }
      if (!matchId) {
        for (const [id, d] of delegations) {
          if (d.status === "running") {
            matchId = id;
            break;
          }
        }
      }
      if (matchId) {
        const prev = delegations.get(matchId)!;
        delegations.set(matchId, {
          ...prev,
          status: e.ok ? "done" : "error",
          resultPreview: e.output_text,
        });
        return { ...state, delegations };
      }
      const { order, orderSeq } = nextOrder(state);
      const id = `delegation-done:${e.delegation_id || order}`;
      delegations.set(id, {
        id,
        delegationId: e.delegation_id,
        calleeRole: "",
        subtaskPreview: "",
        resultPreview: e.output_text,
        status: e.ok ? "done" : "error",
        order,
      });
      return { ...state, orderSeq, delegations };
    }
    case "RunInsight": {
      const { order, orderSeq } = nextOrder(state);
      const insight: InsightEntry = {
        id: `insight:${order}`,
        insightKind: e.kind,
        summary: e.summary,
        detail: e.detail,
        order,
      };
      return { ...state, orderSeq, insights: [...state.insights, insight] };
    }
    case "LlmCallCompleted": {
      // Lightweight thinking signal when we only have call meta
      if (state.thinkingStatus === "idle" && state.status === "running") {
        return {
          ...state,
          thinkingStatus: "running",
          thinkingStartedTs: state.thinkingStartedTs ?? ts - e.latency_ms,
        };
      }
      return state;
    }
    default:
      return state;
  }
}

function buildProcess(state: InternalState): TurnProcessBlock[] {
  type Ordered = { order: number; block: TurnProcessBlock };
  const items: Ordered[] = [];

  if (state.casting) {
    items.push({ order: -100, block: state.casting });
  }

  if (state.thinkingStatus !== "idle" && (state.thinkingContent || state.thinkingStatus === "running")) {
    const durationMs =
      state.thinkingStatus === "done" && state.thinkingStartedTs != null
        ? (state.thinkingEndedTs ?? state.endedTs ?? state.thinkingStartedTs) - state.thinkingStartedTs
        : state.thinkingStatus === "running" && state.thinkingStartedTs != null
          ? undefined
          : undefined;
    const thinking: ThinkingBlock = {
      kind: "thinking",
      id: THINKING_ID,
      status: state.thinkingStatus === "done" ? "done" : "running",
      content: state.thinkingContent,
      durationMs:
        state.thinkingStatus === "done" && state.thinkingStartedTs != null
          ? Math.max(
              0,
              (state.thinkingEndedTs ?? state.endedTs ?? Date.now()) - state.thinkingStartedTs,
            )
          : undefined,
    };
    void durationMs;
    items.push({ order: -90, block: thinking });
  }

  for (const d of state.decisions) {
    const block: DecisionProcessBlock = {
      kind: "decision",
      id: d.id,
      status: "done",
      step: d.step,
      actionType: d.actionType,
      toolName: d.toolName,
      delegateTarget: d.delegateTarget,
      rationalePreview: d.rationalePreview,
      agentRole: d.agentRole,
      confidence: d.confidence,
    };
    items.push({ order: d.order, block });
  }

  for (const t of state.tools.values()) {
    const block: ToolBlock = {
      kind: "tool",
      id: t.id,
      status: t.status,
      toolName: t.toolName,
      argumentsPreview: t.argumentsPreview,
      resultPreview: t.resultPreview,
      ok: t.ok,
      latencyMs: t.latencyMs,
      error: t.error,
      invocationId: t.invocationId,
      agentRole: t.agentRole,
    };
    items.push({ order: t.order, block });
  }

  for (const s of state.sandboxes.values()) {
    const block: SandboxBlock = {
      kind: "sandbox",
      id: s.id,
      status: s.sealed ? "done" : "running",
      invocationId: s.invocationId,
      stdout: s.stdout,
      stderr: s.stderr,
      sealed: s.sealed,
      agentRole: s.agentRole,
    };
    // Nest under tool visually by ordering right after matching tool
    const tool = [...state.tools.values()].find((t) => t.invocationId === s.invocationId);
    items.push({ order: tool ? tool.order + 0.5 : s.order, block });
  }

  for (const d of state.delegations.values()) {
    const block: DelegationBlock = {
      kind: "delegation",
      id: d.id,
      status: d.status,
      calleeRole: d.calleeRole,
      subtaskPreview: d.subtaskPreview,
      fromRole: d.fromRole,
      resultPreview: d.resultPreview,
    };
    items.push({ order: d.order, block });
  }

  for (const i of state.insights) {
    const block: InsightBlock = {
      kind: "insight",
      id: i.id,
      status: "done",
      insightKind: i.insightKind,
      summary: i.summary,
      detail: i.detail,
    };
    items.push({ order: i.order + 1000, block });
  }

  return items.sort((a, b) => a.order - b.order).map((x) => x.block);
}

function countSteps(state: InternalState): number {
  return state.assistantStepIds.size + state.tools.size + state.delegations.size;
}

/**
 * Whether to fold process under ProcessFold (LobeHub shouldFoldProcess semantics).
 * Fold only after terminal status and when there is process content + a final answer.
 */
export function shouldFoldProcess(timeline: Pick<TurnTimeline, "process" | "finalAnswer" | "status">): boolean {
  if (timeline.status !== "completed" && timeline.status !== "failed") return false;
  if (!timeline.process.length) return false;
  if (!timeline.finalAnswer.trim() && timeline.status === "completed") return false;
  // Always fold when completed with process; failed may still fold if answer or process
  return true;
}

export function projectTurnTimeline(state: InternalState): TurnTimeline {
  const process = buildProcess(state);
  const durationMs =
    state.startedTs != null
      ? Math.max(0, (state.endedTs ?? (state.status === "running" ? Date.now() : state.startedTs)) - state.startedTs)
      : undefined;
  const finalAnswer = state.finalAnswer;
  const finalAnswerStreaming = state.status === "running" && !!finalAnswer;
  const timeline: TurnTimeline = {
    process,
    finalAnswer,
    finalAnswerStreaming,
    stepCount: countSteps(state),
    durationMs: state.endedTs != null ? durationMs : state.status === "running" ? durationMs : durationMs,
    phase: state.phase,
    status: state.status,
    errorMessage: state.errorMessage,
    files: state.files,
    foldProcess: false,
  };
  return {
    ...timeline,
    foldProcess: shouldFoldProcess(timeline),
  };
}

export class TurnTimelineProjector {
  private state: InternalState = EMPTY_INTERNAL;

  reset(): void {
    this.state = EMPTY_INTERNAL;
  }

  onEvent(stamped: StampedEvent): TurnTimeline {
    this.state = reduceTurnTimeline(this.state, stamped);
    return this.snapshot();
  }

  snapshot(): TurnTimeline {
    return projectTurnTimeline(this.state);
  }
}

/** Fold a full event list into a timeline (tests / replay). */
export function buildTurnTimeline(events: readonly StampedEvent[]): TurnTimeline {
  let state = EMPTY_INTERNAL;
  for (const event of events) {
    state = reduceTurnTimeline(state, event);
  }
  return projectTurnTimeline(state);
}

export type { InternalState as TurnTimelineInternalState };
export { EMPTY_TURN_TIMELINE };
