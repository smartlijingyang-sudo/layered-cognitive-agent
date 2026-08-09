import { useEffect, useRef } from "react";
import { Terminal } from "lucide-react";
import type { SandboxBlock } from "../../projectors/types";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { NeuralNetworkLoading } from "../shared/NeuralNetworkLoading";
import { AnsiOutput } from "./AnsiOutput";

/**
 * Live sandbox stdout/stderr panel (ADR-0044 stream projection).
 * LobeHub RunCommand-adjacent terminal chrome.
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
      className={cn(
        "overflow-hidden rounded-[var(--radius-md)] border border-[var(--border)]",
        compact ? "bg-transparent" : "bg-[var(--surface)]",
      )}
    >
      <div className="flex items-center gap-1.5 border-b border-[var(--border-subtle)] px-2.5 py-1.5">
        <LobeIcon icon={Terminal} size="xs" className="text-[var(--text-faint)]" />
        <span className="text-xs text-[var(--text-muted)]">
          沙箱 {live ? "· 执行中" : "· 完成"}
          {block.agentRole ? ` · ${block.agentRole}` : ""}
        </span>
        {live ? <NeuralNetworkLoading size={14} className="ml-auto" /> : null}
      </div>
      <div ref={ref} className="max-h-56 overflow-auto p-2">
        {block.stdout.trim() ? <AnsiOutput text={block.stdout} /> : null}
        {block.stderr.trim() ? (
          <div className={block.stdout.trim() ? "mt-2" : undefined}>
            <AnsiOutput text={block.stderr} tone="error" />
          </div>
        ) : null}
        {!hasOut ? (
          <p className="m-0 font-mono text-xs text-[var(--text-faint)]">{live ? "…" : "(empty)"}</p>
        ) : null}
      </div>
    </div>
  );
}
