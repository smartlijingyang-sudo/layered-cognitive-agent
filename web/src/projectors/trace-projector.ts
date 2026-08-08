import type { StampedEvent } from "../contracts/stamped";
import type { SandboxOutputDelta, StepTextDelta, ToolInvoked } from "../contracts";
import {
  EMPTY_TRACE_STATE,
  type RunInfo,
  type SandboxOutputStream,
  type StepTextStream,
  type TraceState,
  type Verbosity,
  shouldShowEvent,
} from "./types";

function cloneRuns(runs: TraceState["runs"]): Map<string, RunInfo> {
  return new Map(runs);
}

export function stepStreamKey(runId: string, step: number): string {
  return `${runId}:${step}`;
}

export function sandboxStreamKey(runId: string, invocationId: string, stream: string): string {
  return `${runId}:${invocationId}:${stream}`;
}

function materializeStepStream(
  base: Omit<StepTextStream, "text" | "chunkCount" | "lastDeltaSeq"> & {
    readonly deltas: ReadonlyMap<number, string>;
  },
): StepTextStream {
  const ordered = [...base.deltas.entries()].sort(([a], [b]) => a - b);
  return {
    ...base,
    text: ordered.map(([, text]) => text).join(""),
    chunkCount: ordered.length,
    lastDeltaSeq: ordered.length > 0 ? ordered[ordered.length - 1]![0] : 0,
  };
}

function materializeSandboxStream(
  base: Omit<SandboxOutputStream, "text" | "chunkCount" | "lastDeltaSeq"> & {
    readonly deltas: ReadonlyMap<number, string>;
  },
): SandboxOutputStream {
  const ordered = [...base.deltas.entries()].sort(([a], [b]) => a - b);
  return {
    ...base,
    text: ordered.map(([, text]) => text).join(""),
    chunkCount: ordered.length,
    lastDeltaSeq: ordered.length > 0 ? ordered[ordered.length - 1]![0] : 0,
  };
}

/** 将一条 StepTextDelta 归入 (run_id, step) 流；乱序 seq 按序号重拼。 */
export function upsertStepStream(
  streams: readonly StepTextStream[],
  stamped: StampedEvent,
  event: StepTextDelta,
): readonly StepTextStream[] {
  const key = stepStreamKey(stamped.scope.run_id, event.step);
  const index = streams.findIndex((stream) => stream.key === key);
  if (index < 0) {
    const deltas = new Map<number, string>([[event.seq, event.text_delta]]);
    return [
      ...streams,
      materializeStepStream({
        key,
        runId: stamped.scope.run_id,
        step: event.step,
        agentRole: stamped.scope.agent_role,
        anchorJournalSeq: stamped.seq,
        domain: stamped.domain ?? "resource",
        deltas,
      }),
    ];
  }
  const prev = streams[index]!;
  const deltas = new Map(prev.deltas);
  deltas.set(event.seq, event.text_delta);
  const next = materializeStepStream({
    key: prev.key,
    runId: prev.runId,
    step: prev.step,
    agentRole: prev.agentRole || stamped.scope.agent_role,
    anchorJournalSeq: prev.anchorJournalSeq,
    domain: prev.domain || (stamped.domain ?? "resource"),
    deltas,
  });
  const copy = streams.slice();
  copy[index] = next;
  return copy;
}

/** 将一条 SandboxOutputDelta 归入 (run_id, invocation_id, stream)；sealed 后忽略。 */
export function upsertSandboxStream(
  streams: readonly SandboxOutputStream[],
  stamped: StampedEvent,
  event: SandboxOutputDelta,
): readonly SandboxOutputStream[] {
  const key = sandboxStreamKey(stamped.scope.run_id, event.invocation_id, event.stream);
  const index = streams.findIndex((stream) => stream.key === key);
  if (index < 0) {
    const deltas = new Map<number, string>([[event.seq, event.text_delta]]);
    return [
      ...streams,
      materializeSandboxStream({
        key,
        runId: stamped.scope.run_id,
        invocationId: event.invocation_id,
        stream: event.stream,
        agentRole: stamped.scope.agent_role,
        anchorJournalSeq: stamped.seq,
        domain: stamped.domain ?? "resource",
        sealed: false,
        deltas,
      }),
    ];
  }
  const prev = streams[index]!;
  if (prev.sealed) return streams;
  const deltas = new Map(prev.deltas);
  deltas.set(event.seq, event.text_delta);
  const next = materializeSandboxStream({
    key: prev.key,
    runId: prev.runId,
    invocationId: prev.invocationId,
    stream: prev.stream,
    agentRole: prev.agentRole || stamped.scope.agent_role,
    anchorJournalSeq: prev.anchorJournalSeq,
    domain: prev.domain || (stamped.domain ?? "resource"),
    sealed: false,
    deltas,
  });
  const copy = streams.slice();
  copy[index] = next;
  return copy;
}

/** ToolInvoked 到达：锁定同 invocation_id 的全部 sandbox 流。 */
export function sealSandboxStreams(
  streams: readonly SandboxOutputStream[],
  stamped: StampedEvent,
  event: ToolInvoked,
): readonly SandboxOutputStream[] {
  const invocationId = event.invocation_id?.trim();
  if (!invocationId) return streams;
  const runId = stamped.scope.run_id;
  let changed = false;
  const next = streams.map((stream) => {
    if (stream.runId !== runId || stream.invocationId !== invocationId || stream.sealed) {
      return stream;
    }
    changed = true;
    return { ...stream, sealed: true };
  });
  return changed ? next : streams;
}

/** 时间线项：非 delta 事件原样；同 key 的 delta 折叠为一条流。 */
export type TraceTimelineItem =
  | { readonly kind: "event"; readonly stamped: StampedEvent }
  | { readonly kind: "step_stream"; readonly stream: StepTextStream }
  | { readonly kind: "sandbox_stream"; readonly stream: SandboxOutputStream };

/**
 * 从原始 journal 事件 + 归约后的流构建可渲染时间线。
 * 流卡片锚定在该流首条 delta 的位置，后续分片只更新同一卡片。
 */
export function buildTraceTimeline(
  events: readonly StampedEvent[],
  stepStreams: readonly StepTextStream[],
  verbosity: Verbosity,
  sandboxStreams: readonly SandboxOutputStream[] = [],
): readonly TraceTimelineItem[] {
  const stepByKey = new Map(stepStreams.map((stream) => [stream.key, stream]));
  const sandboxByKey = new Map(sandboxStreams.map((stream) => [stream.key, stream]));
  const placed = new Set<string>();
  const items: TraceTimelineItem[] = [];
  for (const stamped of events) {
    if (!shouldShowEvent(stamped.event.type, verbosity)) continue;
    if (stamped.event.type === "StepTextDelta") {
      const key = stepStreamKey(stamped.scope.run_id, stamped.event.step);
      if (placed.has(key)) continue;
      placed.add(key);
      const stream = stepByKey.get(key);
      if (stream) items.push({ kind: "step_stream", stream });
      continue;
    }
    if (stamped.event.type === "SandboxOutputDelta") {
      const key = sandboxStreamKey(
        stamped.scope.run_id,
        stamped.event.invocation_id,
        stamped.event.stream,
      );
      if (placed.has(key)) continue;
      placed.add(key);
      const stream = sandboxByKey.get(key);
      if (stream) items.push({ kind: "sandbox_stream", stream });
      continue;
    }
    items.push({ kind: "event", stamped });
  }
  return items;
}

/** 镜像 ConsoleJournalProjector._TraceState 的前端归约器。 */
export function reduceTrace(state: TraceState, stamped: StampedEvent): TraceState {
  const e = stamped.event;
  const runs = cloneRuns(state.runs);

  switch (e.type) {
    case "CastingStarted":
      return { ...state, phase: "casting" };
    case "CastingCompleted":
      return {
        ...state,
        phase: "collaborating",
        casting: {
          governanceKind: e.governance_kind,
          leadRole: e.lead_role,
          selectedRoles: [...e.selected_roles],
          rationale: e.rationale,
        },
      };
    case "CastingFailed":
      return { ...state, phase: "failed", castingError: e.error };
    case "TeamRunStarted":
      return {
        ...state,
        phase: "collaborating",
        teamRun: {
          teamId: e.team_id,
          mandate: e.mandate,
          members: [...e.members],
          objectivePreview: e.objective_preview,
        },
        runs: new Map(runs).set(stamped.scope.run_id, {
          runId: stamped.scope.run_id,
          role: "(team)",
        }),
      };
    case "TeamRunFinished":
      return { ...state, status: e.status, phase: e.status === "completed" ? "completed" : "failed" };
    case "AgentRunStarted": {
      const next = new Map(runs);
      next.set(stamped.scope.run_id, {
        runId: stamped.scope.run_id,
        role: e.agent_role,
      });
      return { ...state, runs: next };
    }
    case "AgentRunFinished": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      next.set(stamped.scope.run_id, {
        runId: stamped.scope.run_id,
        role: prev?.role ?? stamped.scope.agent_role,
        status: e.status,
        steps: e.steps,
        llmCalls: prev?.llmCalls,
        toolCalls: prev?.toolCalls,
      });
      return { ...state, runs: next };
    }
    case "DelegationIssued":
      return { ...state, delegations: [...state.delegations, e] };
    case "DelegationCompleted":
      return state;
    case "DecisionMade":
      return { ...state, decisions: [...state.decisions, e] };
    case "ToolInvoked": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      if (prev) {
        next.set(stamped.scope.run_id, {
          ...prev,
          toolCalls: (prev.toolCalls ?? 0) + 1,
        });
      }
      return {
        ...state,
        runs: next,
        toolCalls: [...state.toolCalls, e],
        sandboxStreams: sealSandboxStreams(state.sandboxStreams, stamped, e),
      };
    }
    case "LlmCallCompleted": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      if (prev) {
        next.set(stamped.scope.run_id, {
          ...prev,
          llmCalls: (prev.llmCalls ?? 0) + 1,
        });
      }
      return { ...state, runs: next, llmCalls: [...state.llmCalls, e] };
    }
    case "StepTextDelta":
      return {
        ...state,
        stepStreams: upsertStepStream(state.stepStreams, stamped, e),
      };
    case "SandboxOutputDelta":
      return {
        ...state,
        sandboxStreams: upsertSandboxStream(state.sandboxStreams, stamped, e),
      };
    case "RunInsight":
      return { ...state, insights: [...state.insights, e] };
    case "SynthesisCompleted":
      return { ...state, synthesisText: e.output_text, phase: "synthesizing" };
    default:
      return state;
  }
}

export function buildTraceState(
  events: readonly StampedEvent[],
  verbosity: Verbosity = "standard",
): TraceState {
  return events.reduce((acc, stamped) => {
    if (!shouldShowEvent(stamped.event.type, verbosity)) return acc;
    return reduceTrace(acc, stamped);
  }, EMPTY_TRACE_STATE);
}

export class TraceProjector {
  private state: TraceState = EMPTY_TRACE_STATE;

  constructor(private readonly verbosity: Verbosity = "standard") {}

  onEvent(stamped: StampedEvent): TraceState {
    if (!shouldShowEvent(stamped.event.type, this.verbosity)) return this.state;
    this.state = reduceTrace(this.state, stamped);
    return this.state;
  }

  snapshot(): TraceState {
    return this.state;
  }

  reset(): void {
    this.state = EMPTY_TRACE_STATE;
  }
}
