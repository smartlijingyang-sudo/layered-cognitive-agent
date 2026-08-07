/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */

export type RunStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export interface CreateRunRequest {
  readonly question: string;
  readonly mode: string;
  readonly conversation_id: string | null;
}

export interface CreateRunResponse {
  readonly run_id: string;
  readonly trace_id: string;
}

