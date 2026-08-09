import { useMemo } from "react";
import { cn } from "../../lib/cn";

/**
 * Lightweight ANSI strip + presentational terminal output.
 * Full SGR color mapping is optional; we strip escape sequences for clean UX.
 */
const ANSI_RE =
  // eslint-disable-next-line no-control-regex
  /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;

export function stripAnsi(text: string): string {
  return text.replace(ANSI_RE, "");
}

export function AnsiOutput({
  text,
  className,
  maxHeightClass = "max-h-[200px]",
  tone = "default",
}: {
  readonly text: string;
  readonly className?: string;
  readonly maxHeightClass?: string;
  readonly tone?: "default" | "error";
}) {
  const cleaned = useMemo(() => stripAnsi(text), [text]);
  if (!cleaned.trim()) return null;

  return (
    <pre
      className={cn(
        "m-0 overflow-auto rounded-[var(--radius-sm)] border border-[var(--border-subtle)] p-2",
        maxHeightClass,
        "font-mono text-xs leading-[1.6] whitespace-pre-wrap break-words",
        "bg-[var(--fill-secondary)]",
        tone === "error" ? "text-[var(--color-danger)]" : "text-[var(--text)]",
        className,
      )}
    >
      {cleaned}
    </pre>
  );
}
