import type { CreateRunRequest, CreateRunResponse, RunStatus } from "../contracts/runs.generated";
import type { Mode } from "../contracts/modes.generated";

export type { CreateRunRequest, CreateRunResponse, Mode, RunStatus };

export interface LlmHealth {
  readonly llmAvailable: boolean;
}

export async function fetchHealth(): Promise<LlmHealth> {
  const response = await fetch("/health");
  if (!response.ok) {
    return { llmAvailable: false };
  }
  const data = (await response.json()) as { llm_available?: boolean };
  return {
    llmAvailable: Boolean(data.llm_available),
  };
}

export async function createRun(
  body: CreateRunRequest & { conversation_id?: string },
): Promise<CreateRunResponse> {
  const response = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = (await response.json().catch(() => ({}))) as {
      error?: string;
      detail?: string;
    };
    const message = err.detail ?? err.error ?? `HTTP ${response.status}`;
    throw new Error(message);
  }
  return (await response.json()) as CreateRunResponse;
}

export async function cancelRun(runId: string): Promise<RunStatus> {
  const response = await fetch(`/runs/${runId}/cancel`, { method: "POST" });
  if (!response.ok) {
    const err = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `HTTP ${response.status}`);
  }
  const data = (await response.json()) as { status?: RunStatus };
  return data.status ?? "canceled";
}

export async function fetchRunSummary(
  runId: string,
): Promise<{ readonly status: RunStatus; readonly error?: string } | null> {
  const response = await fetch(`/runs/${runId}`);
  if (!response.ok) return null;
  const data = (await response.json()) as { status?: RunStatus; error?: string };
  if (!data.status) return null;
  return { status: data.status, error: data.error };
}

export async function fetchRunStatus(runId: string): Promise<RunStatus | null> {
  const summary = await fetchRunSummary(runId);
  return summary?.status ?? null;
}
