import { useEffect, useRef } from "react";
import { Terminal } from "lucide-react";
import type { SandboxBlock } from "../../projectors/types";
import { cn } from "../../lib/cn";

/**
 * Live sandbox stdout/stderr panel (ADR-0044 stream projection).
 */
export function SandboxPanel({
  block,
  compact = false,
}: {
  readonly block: SandboxBlock;
  readonly compact?: boolean;
}) {
  const ref = useRef<HTMLPreElement>(null);
  const live = !block.sealed;

  useEffect(() => {
    if (!live || !ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [block.stdout, block.stderr, live]);

  const text =
    [block.stdout, block.stderr ? `--- stderr ---\n${block.stderr}` : ""]
      .filter(Boolean)
      .join("\n") || (live ? "…" : "(empty)");

  return (
    <div
      className={cn(
        "overflow-hidden rounded-[var(--radius-md)] border border-[var(--border)]",
        compact ? "" : "bg-[var(--surface)]",
      )}
    >
      <div className="flex items-center gap-1.5 border-b border-[var(--border-subtle)] px-2.5 py-1.5">
        <Terminal size={12} className="text-[var(--text-faint)]" aria-hidden />
        <span className="text-xs text-[var(--text-muted)]">
          沙箱 {live ? "· 执行中" : "· 完成"}
        </span>
      </div>
      <pre
        ref={ref}
        className={cn(
          "m-0 max-h-56 overflow-auto bg-black/40 p-2.5 font-mono text-xs leading-relaxed",
          "text-[var(--text-muted)] whitespace-pre-wrap break-all",
          block.stderr && !block.stdout ? "text-[var(--color-danger)]" : "",
        )}
      >
        {text}
      </pre>
    </div>
  );
}
