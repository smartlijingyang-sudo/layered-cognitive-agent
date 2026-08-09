// web/src/projectors/message-types.ts
export type MessageKind =
  | "casting"
  | "thinking"
  | "tool_call"
  | "sandbox"
  | "delegation"
  | "synthesis"
  | "answer"
  | "error"
  | "insight";

export interface MessageMetadata {
  readonly toolName?: string;
  readonly argumentsPreview?: string;
  readonly resultPreview?: string;
  readonly latencyMs?: number;
  readonly ok?: boolean;
  readonly error?: string;
  readonly invocationId?: string;
  readonly durationMs?: number;
  readonly governanceKind?: string;
  readonly leadRole?: string;
  readonly selectedRoles?: readonly string[];
  readonly rationale?: string;
  readonly objectivePreview?: string;
  readonly calleeRole?: string;
  readonly subtaskPreview?: string;
  readonly delegationId?: string;
  readonly fromRole?: string;
  readonly stdout?: string;
  readonly stderr?: string;
  readonly sealed?: boolean;
  readonly errorMessage?: string;
  readonly insightKind?: string;
  readonly summary?: string;
  readonly detail?: string;
  readonly method?: string;
  readonly candidateCount?: number;
}

export interface Message {
  readonly id: string;
  readonly kind: MessageKind;
  readonly agentRole?: string;
  readonly content: string;
  readonly streaming: boolean;
  readonly status: "running" | "done" | "error";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly metadata?: MessageMetadata;
}

export interface Turn {
  readonly id: string;
  readonly runId: string;
  readonly question: string;
  readonly mode: "solo" | "team";
  readonly messages: readonly Message[];
  readonly status: "running" | "completed" | "failed";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly teamId?: string;
  readonly errorMessage?: string;
}
