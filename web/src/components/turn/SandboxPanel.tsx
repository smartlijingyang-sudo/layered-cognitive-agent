import { useEffect, useRef } from "react";
import type { SandboxBlock } from "../../projectors/types";
import { cn } from "../../lib/cn";
import { NeuralNetworkLoading } from "../shared/NeuralNetworkLoading";
import { AnsiOutput } from "./AnsiOutput";

/**
 * Live command stdout/stderr (LobeHub RunCommand Render — no "sandbox" chrome).
 */
export function SandboxPanel({
  block,
  compact = false,
}: {
  readonly block: SandboxBlock;
  readonly compact?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const live = !block.sealed;

  useEffect(() => {
    if (!live || !ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [block.stdout, block.stderr, live]);

  const hasOut = Boolean(block.stdout.trim() || block.stderr.trim());

  return (
    <div
      ref={ref}
      className={cn(
        "lobe-run-command-block overflow-hidden rounded-[var(--radius-md)] border border-[var(--border-subtle)]",
        compact ? "bg-transparent" : "bg-[var(--surface)] p-2",
      )}
    >
      {block.stdout.trim() ? <AnsiOutput text={block.stdout} /> : null}
      {block.stderr.trim() ? (
        <div className={block.stdout.trim() ? "mt-2" : undefined}>
          <AnsiOutput text={block.stderr} tone="error" />
        </div>
      ) : null}
      {!hasOut && live ? (
        <div className="flex items-center gap-2 px-1 py-0.5">
          <NeuralNetworkLoading size={14} />
          <span className="font-mono text-xs text-[var(--text-faint)]">…</span>
        </div>
      ) : null}
    </div>
  );
}
