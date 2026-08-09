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

// ── Turn timeline (LobeHub-style process + final answer) ──────────────

export type TurnBlockStatus = "pending" | "running" | "done" | "error";

export interface CastingBlock {
  readonly kind: "casting";
  readonly id: string;
  readonly status: TurnBlockStatus;
  readonly objectivePreview?: string;
  readonly governanceKind?: string;
  readonly leadRole?: string;
  readonly selectedRoles?: readonly string[];
  readonly rationale?: string;
  readonly error?: string;
}

export interface ThinkingBlock {
  readonly kind: "thinking";
  readonly id: string;
  readonly status: "running" | "done";
  readonly content: string;
  readonly durationMs?: number;
}

export interface ToolBlock {
  readonly kind: "tool";
  readonly id: string;
  readonly status: TurnBlockStatus;
  readonly toolName: string;
  readonly argumentsPreview: string;
  readonly resultPreview: string;
  readonly ok?: boolean;
  readonly latencyMs?: number;
  readonly error?: string;
  readonly invocationId: string;
  readonly agentRole?: string;
}

export interface SandboxBlock {
  readonly kind: "sandbox";
  readonly id: string;
  readonly status: TurnBlockStatus;
  readonly invocationId: string;
  readonly stdout: string;
  readonly stderr: string;
  readonly sealed: boolean;
  readonly agentRole?: string;
}

export interface DelegationBlock {
  readonly kind: "delegation";
  readonly id: string;
  readonly status: TurnBlockStatus;
  readonly calleeRole: string;
  readonly subtaskPreview: string;
  readonly fromRole?: string;
  readonly resultPreview?: string;
}

export interface DecisionProcessBlock {
  readonly kind: "decision";
  readonly id: string;
  readonly status: "done";
  readonly step: number;
  readonly actionType: string;
  readonly toolName?: string;
  readonly delegateTarget?: string;
  readonly rationalePreview?: string;
  readonly agentRole?: string;
  readonly confidence?: number;
}

export interface InsightBlock {
  readonly kind: "insight";
  readonly id: string;
  readonly status: "done";
  readonly insightKind: string;
  readonly summary: string;
  readonly detail: string;
}

/** Process-side blocks (everything except final answer). */
export type TurnProcessBlock =
  | CastingBlock
  | ThinkingBlock
  | ToolBlock
  | SandboxBlock
  | DelegationBlock
  | DecisionProcessBlock
  | InsightBlock;

/**
 * Journal → user-facing turn layout (LobeHub ProcessFold + final answer).
 * Pure projection; never invents semantics beyond journal facts.
 */
export interface TurnTimeline {
  readonly process: readonly TurnProcessBlock[];
  readonly finalAnswer: string;
  readonly finalAnswerStreaming: boolean;
  readonly stepCount: number;
  readonly durationMs?: number;
  readonly phase: RunPhase;
  readonly status: "idle" | "running" | "completed" | "failed";
  readonly errorMessage?: string;
  readonly files: readonly GeneratedFile[];
  /** Whether ProcessFold should collapse process under one header. */
  readonly foldProcess: boolean;
}

export const EMPTY_TURN_TIMELINE: TurnTimeline = {
  process: [],
  finalAnswer: "",
  finalAnswerStreaming: false,
  stepCount: 0,
  phase: "idle",
  status: "idle",
  files: [],
  foldProcess: false,
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
  // standard：token 级 delta 仅 verbose；过程事件默认可见
  if (eventType === "StepTextDelta" || eventType === "ReasoningDelta") return false;
  return eventType !== "StepCompleted" && eventType !== "ActionDegraded";
}
