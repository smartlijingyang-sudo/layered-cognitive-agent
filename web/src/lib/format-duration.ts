/** Format milliseconds for LobeHub-style process / thinking titles. */

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;

/** Thinking title: "3.2" seconds with one decimal. */
export function formatThinkingSeconds(ms: number): string {
  const seconds = Math.max(0, ms) / MS_PER_SECOND;
  return seconds.toFixed(1);
}

/**
 * Process fold duration: "12s" | "3m 12s" | "1m".
 * Returns undefined when duration is too short to show (< 1s).
 */
export function formatProcessDuration(ms: number): string | undefined {
  if (!Number.isFinite(ms) || ms < MS_PER_SECOND) return undefined;
  const totalSeconds = Math.floor(ms / MS_PER_SECOND);
  if (totalSeconds < SECONDS_PER_MINUTE) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / SECONDS_PER_MINUTE);
  const seconds = totalSeconds % SECONDS_PER_MINUTE;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}
