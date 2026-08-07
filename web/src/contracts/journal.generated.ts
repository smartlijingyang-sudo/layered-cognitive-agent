/** AUTO-GENERATED — scripts/generate_journal_contracts.py */

export type VocabDomain = "run" | "team" | "cognitive" | "resource" | "event";

export interface RunScope {
  readonly trace_id: string;
  readonly run_id: string;
  readonly parent_run_id: string | null;
  readonly delegation_id: string | null;
  readonly agent_role: string;
}

export interface StampedRecord<E = JournalEvent> {
  readonly schema: "journal.v1";
  readonly seq: number;
  readonly ts: number;
  readonly scope: RunScope;
  readonly event_type: JournalEventType;
  readonly event: E;
  readonly domain?: VocabDomain;
}

export interface TeamRunStarted {
  readonly type: "TeamRunStarted";
  readonly team_id: string;
  readonly strategy_key: string;
  readonly mandate: string;
  readonly lead_role: string;
  readonly members: readonly string[];
  readonly objective: string;
  readonly objective_preview: string;
  readonly plan_steps: string;
}

export interface TeamRunFinished {
  readonly type: "TeamRunFinished";
  readonly status: string;
  readonly output_preview: string;
  readonly steps: number;
  readonly error: string;
}

export interface AgentRunStarted {
  readonly type: "AgentRunStarted";
  readonly agent_role: string;
  readonly strategy_key: string;
  readonly objective: string;
  readonly objective_preview: string;
  readonly from_role: string;
}

export interface AgentRunFinished {
  readonly type: "AgentRunFinished";
  readonly status: string;
  readonly output_preview: string;
  readonly steps: number;
  readonly error: string;
}

export interface DelegationIssued {
  readonly type: "DelegationIssued";
  readonly delegation_id: string;
  readonly caller_role: string;
  readonly callee_role: string;
  readonly subtask_preview: string;
  readonly mechanism: "delegate" | "handoff" | "member_invoke";
  readonly parallel_group: string;
}

export interface DelegationCompleted {
  readonly type: "DelegationCompleted";
  readonly delegation_id: string;
  readonly ok: boolean;
  readonly status: string;
  readonly output_preview: string;
  readonly task_id: string;
}

export interface DelegationCacheHit {
  readonly type: "DelegationCacheHit";
  readonly callee_role: string;
  readonly subtask_preview: string;
  readonly step: number;
}

export interface SynthesisCompleted {
  readonly type: "SynthesisCompleted";
  readonly method: string;
  readonly candidate_count: number;
  readonly output_preview: string;
}

export interface DecisionMade {
  readonly type: "DecisionMade";
  readonly step: number;
  readonly action_type: string;
  readonly rationale_preview: string;
  readonly delegate_target: string;
  readonly delegate_count: number;
  readonly tool_name: string;
  readonly confidence: number;
}

export interface StepCompleted {
  readonly type: "StepCompleted";
  readonly step: number;
  readonly status: string;
  readonly action_type: string;
}

export interface ActionDegraded {
  readonly type: "ActionDegraded";
  readonly original_action_type: string;
  readonly degraded_to: string;
  readonly step: number;
}

export interface LlmCallCompleted {
  readonly type: "LlmCallCompleted";
  readonly model: string;
  readonly ok: boolean;
  readonly latency_ms: number;
  readonly prompt_preview: string;
  readonly response_preview: string;
  readonly prompt_tokens: number;
  readonly completion_tokens: number;
  readonly stream: boolean;
}

export interface ToolInvoked {
  readonly type: "ToolInvoked";
  readonly tool_name: string;
  readonly arguments_preview: string;
  readonly result_preview: string;
  readonly ok: boolean;
  readonly latency_ms: number;
  readonly attempt: number;
  readonly error: string;
}

export interface ToolDenied {
  readonly type: "ToolDenied";
  readonly tool_name: string;
  readonly reason: string;
}

export interface RunInsight {
  readonly type: "RunInsight";
  readonly kind: string;
  readonly summary: string;
  readonly detail: string;
}

export type JournalEvent = TeamRunStarted | TeamRunFinished | AgentRunStarted | AgentRunFinished | DelegationIssued | DelegationCompleted | DelegationCacheHit | SynthesisCompleted | DecisionMade | StepCompleted | ActionDegraded | LlmCallCompleted | ToolInvoked | ToolDenied | RunInsight;
export type JournalEventType = JournalEvent["type"];
export const JOURNAL_EVENT_TYPES = ['TeamRunStarted', 'TeamRunFinished', 'AgentRunStarted', 'AgentRunFinished', 'DelegationIssued', 'DelegationCompleted', 'DelegationCacheHit', 'SynthesisCompleted', 'DecisionMade', 'StepCompleted', 'ActionDegraded', 'LlmCallCompleted', 'ToolInvoked', 'ToolDenied', 'RunInsight'] as const;

export const EVENT_DOMAINS: Record<JournalEventType, VocabDomain> = {
  ActionDegraded: "event",
  AgentRunFinished: "run",
  AgentRunStarted: "run",
  DecisionMade: "event",
  DelegationCacheHit: "team",
  DelegationCompleted: "team",
  DelegationIssued: "team",
  LlmCallCompleted: "resource",
  RunInsight: "event",
  StepCompleted: "event",
  SynthesisCompleted: "team",
  TeamRunFinished: "run",
  TeamRunStarted: "run",
  ToolDenied: "resource",
  ToolInvoked: "resource",
};

export type DelegationMechanism = "delegate" | "handoff" | "member_invoke";
