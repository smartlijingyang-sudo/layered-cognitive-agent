import type {
  DecisionMade,
  DelegationIssued,
  JournalEvent,
  LlmCallCompleted,
  RunInsight,
  StepTextDelta,
  ToolInvoked,
} from "../contracts";

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
  readonly stepTextDeltas: readonly StepTextDelta[];
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
  stepTextDeltas: [],
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
}

export const EMPTY_CHAT_STATE: ChatState = {
  question: "",
  answer: "",
  answerDeltas: [],
  status: "idle",
  phase: "idle",
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
  // 此处 verbosity 已被收窄为 "standard"：StepTextDelta 仅 verbose 档可见
  if (eventType === "StepTextDelta") return false;
  return eventType !== "StepCompleted" && eventType !== "ActionDegraded";
}
