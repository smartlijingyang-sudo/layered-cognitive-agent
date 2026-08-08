import type {
  DecisionMade,
  DelegationIssued,
  JournalEvent,
  LlmCallCompleted,
  RunInsight,
  ToolInvoked,
} from "../contracts";
import type { GeneratedFile } from "../domain/generated-file";

export type Verbosity = "minimal" | "standard" | "verbose";

/** 用户可见的运行阶段（由 journal 事件驱动）。 */
export type RunPhase =
  | "idle"
  | "casting"
  | "collaborating"
  | "synthesizing"
  | "completed"
  | "failed";

export interface CastingInfo {
  readonly governanceKind: string;
  readonly leadRole: string;
  readonly selectedRoles: readonly string[];
  readonly rationale: string;
}

export interface RunInfo {
  readonly runId: string;
  readonly role: string;
  readonly status?: string;
  readonly steps?: number;
  readonly llmCalls?: number;
  readonly toolCalls?: number;
}

/**
 * 同一 (run_id, step) 的 StepTextDelta 归约结果。
 * journal 保持 token 级真相；轨迹投影只暴露合并后的流（ADR-0041）。
 */
export interface StepTextStream {
  readonly key: string;
  readonly runId: string;
  readonly step: number;
  readonly agentRole: string;
  readonly text: string;
  readonly chunkCount: number;
  /** StepTextDelta.seq 最大值，供兜底排序校验。 */
  readonly lastDeltaSeq: number;
  /** 首条 delta 的 journal seq，作为时间线锚点与稳定 React key。 */
  readonly anchorJournalSeq: number;
  readonly domain: string;
  /** 按 delta.seq 索引的分片，供乱序到达时重拼。 */
  readonly deltas: ReadonlyMap<number, string>;
}

/**
 * 同一 (run_id, invocation_id, stream) 的 SandboxOutputDelta 归约结果（ADR-0044）。
 * ToolInvoked(invocation_id) 到达后 sealed，不再接受新分片。
 */
export interface SandboxOutputStream {
  readonly key: string;
  readonly runId: string;
  readonly invocationId: string;
  readonly stream: "stdout" | "stderr" | string;
  readonly agentRole: string;
  readonly text: string;
  readonly chunkCount: number;
  readonly lastDeltaSeq: number;
  readonly anchorJournalSeq: number;
  readonly domain: string;
  readonly sealed: boolean;
  readonly deltas: ReadonlyMap<number, string>;
}

export interface TraceState {
  readonly phase: RunPhase;
  readonly casting?: CastingInfo;
  readonly castingError?: string;
  readonly teamRun?: {
    readonly teamId: string;
    readonly mandate: string;
    readonly members: readonly string[];
    readonly objectivePreview: string;
  };
  readonly runs: ReadonlyMap<string, RunInfo>;
  readonly delegations: readonly DelegationIssued[];
  readonly decisions: readonly DecisionMade[];
  readonly toolCalls: readonly ToolInvoked[];
  readonly llmCalls: readonly LlmCallCompleted[];
  /** 按首现顺序的合并文本流（非逐 token 列表）。 */
  readonly stepStreams: readonly StepTextStream[];
  /** 沙箱执行期 stdout/stderr 合并流。 */
  readonly sandboxStreams: readonly SandboxOutputStream[];
  readonly insights: readonly RunInsight[];
  readonly synthesisText?: string;
  readonly status?: string;
}

export const EMPTY_TRACE_STATE: TraceState = {
  phase: "idle",
  runs: new Map(),
  delegations: [],
  decisions: [],
  toolCalls: [],
  llmCalls: [],
  stepStreams: [],
  sandboxStreams: [],
  insights: [],
};

export interface ChatState {
  readonly question: string;
  readonly answer: string;
  readonly answerDeltas: readonly string[];
  readonly status: "idle" | "running" | "completed" | "failed";
  readonly phase: RunPhase;
  readonly errorMessage?: string;
  readonly teamId?: string;
  /** File products projected from write_file / A2A file parts (Phase C). */
  readonly files: readonly GeneratedFile[];
}

export const EMPTY_CHAT_STATE: ChatState = {
  question: "",
  answer: "",
  answerDeltas: [],
  status: "idle",
  phase: "idle",
  files: [],
};

export function shouldShowEvent(eventType: JournalEvent["type"], verbosity: Verbosity): boolean {
  if (verbosity === "verbose") return true;
  if (verbosity === "minimal") {
    return (
      eventType === "CastingStarted" ||
      eventType === "CastingCompleted" ||
      eventType === "CastingFailed" ||
      eventType === "TeamRunStarted" ||
      eventType === "TeamRunFinished" ||
      eventType === "AgentRunFinished" ||
      eventType === "RunInsight"
    );
  }
  // standard：StepTextDelta 仅 verbose；SandboxOutputDelta 默认可见（过程可见性）
  if (eventType === "StepTextDelta") return false;
  return eventType !== "StepCompleted" && eventType !== "ActionDegraded";
}
