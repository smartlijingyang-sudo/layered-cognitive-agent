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

export interface RunInfo {
  readonly runId: string;
  readonly role: string;
  readonly status?: string;
  readonly steps?: number;
  readonly llmCalls?: number;
  readonly toolCalls?: number;
}

export interface TraceState {
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
  readonly teamId?: string;
}

export const EMPTY_CHAT_STATE: ChatState = {
  question: "",
  answer: "",
  answerDeltas: [],
  status: "idle",
};

export function shouldShowEvent(eventType: JournalEvent["type"], verbosity: Verbosity): boolean {
  if (verbosity === "verbose") return true;
  if (verbosity === "minimal") {
    return (
      eventType === "TeamRunStarted" ||
      eventType === "TeamRunFinished" ||
      eventType === "AgentRunFinished" ||
      eventType === "RunInsight"
    );
  }
  if (eventType === "StepTextDelta") return verbosity === "verbose";
  return eventType !== "StepCompleted" && eventType !== "ActionDegraded";
}
