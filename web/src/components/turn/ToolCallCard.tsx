import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Loader2,
  Wrench,
  XCircle,
} from "lucide-react";
import type { SandboxBlock, ToolBlock } from "../../projectors/types";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";
import { SandboxPanel } from "./SandboxPanel";

const TOOL_LABELS: Record<string, string> = {
  run_code: "运行代码",
  run_sandbox_code: "沙箱执行",
  calculator: "计算器",
  write_file: "写入文件",
  read_file: "读取文件",
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

function StatusDot({ status }: { readonly status: ToolBlock["status"] }) {
  if (status === "running" || status === "pending") {
    return <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" aria-hidden />;
  }
  if (status === "error") {
    return <XCircle size={14} className="text-[var(--color-danger)]" aria-hidden />;
  }
  return <CheckCircle2 size={14} className="text-[var(--color-success)]" aria-hidden />;
}

function formatJsonish(raw: string): string {
  if (!raw.trim()) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

/**
 * LobeHub-style tool accordion: status + title + latency; expand args/result + nested sandbox.
 */
export function ToolCallCard({
  block,
  sandbox,
}: {
  readonly block: ToolBlock;
  readonly sandbox?: SandboxBlock;
}) {
  const running = block.status === "running" || block.status === "pending";
  const hasBody =
    Boolean(block.argumentsPreview?.trim()) ||
    Boolean(block.resultPreview?.trim()) ||
    Boolean(block.error?.trim()) ||
    Boolean(sandbox);
  const [open, setOpen] = useState(running || Boolean(sandbox && !sandbox.sealed));

  useEffect(() => {
    if (running || (sandbox && !sandbox.sealed)) setOpen(true);
  }, [running, sandbox]);

  const latency =
    block.latencyMs != null && block.latencyMs > 0
      ? block.latencyMs >= 1000
        ? `${(block.latencyMs / 1000).toFixed(1)}s`
        : `${block.latencyMs}ms`
      : null;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)]",
        "bg-[var(--surface)]",
      )}
    >
      <button
        type="button"
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 border-0 bg-transparent px-3 py-2 text-left",
          "hover:bg-[var(--fill-hover)]",
          focusRing,
        )}
        onClick={() => hasBody && setOpen((v) => !v)}
        aria-expanded={open}
        disabled={!hasBody}
      >
        <StatusDot status={block.status} />
        <Wrench size={13} className="shrink-0 text-[var(--text-faint)]" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm text-[var(--text)]">
          {toolLabel(block.toolName)}
          {block.agentRole ? (
            <span className="text-[var(--text-faint)]"> · {block.agentRole}</span>
          ) : null}
        </span>
        {latency ? (
          <span className="shrink-0 text-xs text-[var(--text-faint)]">{latency}</span>
        ) : null}
        {hasBody ? (
          <ChevronDown
            size={14}
            className={cn(
              "shrink-0 text-[var(--text-faint)] transition-transform",
              open ? "rotate-180" : "",
            )}
            aria-hidden
          />
        ) : null}
      </button>

      {open && hasBody ? (
        <div className="grid gap-2 border-t border-[var(--border-subtle)] px-3 py-2.5">
          {block.argumentsPreview?.trim() ? (
            <section>
              <h4 className="m-0 mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
                参数
              </h4>
              <pre
                className={cn(
                  "m-0 max-h-40 overflow-auto rounded-[var(--radius-md)] bg-[var(--fill-hover)]",
                  "p-2 font-mono text-xs text-[var(--text-muted)] whitespace-pre-wrap break-all",
                )}
              >
                {formatJsonish(block.argumentsPreview)}
              </pre>
            </section>
          ) : null}

          {sandbox ? <SandboxPanel block={sandbox} compact /> : null}

          {block.error?.trim() ? (
            <p className="m-0 text-sm text-[var(--color-danger)]">{block.error}</p>
          ) : null}

          {block.resultPreview?.trim() ? (
            <section>
              <h4 className="m-0 mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
                结果
              </h4>
              <pre
                className={cn(
                  "m-0 max-h-48 overflow-auto rounded-[var(--radius-md)] bg-[var(--fill-hover)]",
                  "p-2 font-mono text-xs text-[var(--text-muted)] whitespace-pre-wrap break-all",
                )}
              >
                {formatJsonish(block.resultPreview)}
              </pre>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
