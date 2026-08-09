/** Merge decision + answer channel buffers for one (run_id, step). */

export function stepChannelKey(runId: string, step: number, channel = "decision"): string {
  return `${runId}:${step}:${channel}`;
}

export function mergedStepChannelText(
  buffers: ReadonlyMap<string, string>,
  runId: string,
  step: number,
): string {
  const decision = buffers.get(stepChannelKey(runId, step, "decision")) ?? "";
  const answer = buffers.get(stepChannelKey(runId, step, "answer")) ?? "";
  return decision + answer;
}

interface DeltaBuffer {
  readonly deltas: ReadonlyMap<number, string>;
}

export function mergedStepChannelTextFromDeltas(
  buffers: ReadonlyMap<string, DeltaBuffer>,
  runId: string,
  step: number,
): string {
  const ordered = (key: string): string =>
    [...(buffers.get(key)?.deltas.entries() ?? [])]
      .sort(([a], [b]) => a - b)
      .map(([, text]) => text)
      .join("");
  return (
    ordered(stepChannelKey(runId, step, "decision")) + ordered(stepChannelKey(runId, step, "answer"))
  );
}
