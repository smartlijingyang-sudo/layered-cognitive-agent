import type { CreateRunRequest, CreateRunResponse, Mode, RunStatus } from "../contracts/catalog.generated";

export type { CreateRunRequest, CreateRunResponse, Mode, RunStatus };
export type TrackChoice = "auto" | "real" | "scripted";

export interface LlmHealth {
  readonly llmAvailable: boolean;
  readonly defaultTrack: TrackChoice;
}

export async function fetchHealth(): Promise<LlmHealth> {
  const response = await fetch("/health");
  if (!response.ok) {
    return { llmAvailable: false, defaultTrack: "scripted" };
  }
  const data = (await response.json()) as {
    llm_available?: boolean;
    default_track?: string;
  };
  const track = data.default_track;
  const defaultTrack: TrackChoice =
    track === "real" || track === "scripted" || track === "auto" ? track : "scripted";
  return {
    llmAvailable: Boolean(data.llm_available),
    defaultTrack,
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
    const err = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `HTTP ${response.status}`);
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

export async function fetchRunStatus(runId: string): Promise<RunStatus | null> {
  const response = await fetch(`/runs/${runId}`);
  if (!response.ok) return null;
  const data = (await response.json()) as { status?: RunStatus };
  return data.status ?? null;
}
