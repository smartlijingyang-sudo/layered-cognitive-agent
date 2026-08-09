import { useEffect, useRef, useState } from "react";
import { Atom, ChevronDown, Loader2 } from "lucide-react";
import type { ThinkingBlock } from "../../projectors/types";
import { formatThinkingSeconds } from "../../lib/format-duration";
import { MarkdownContent } from "../shared/MarkdownContent";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

/**
 * LobeHub Thinking accordion — 「深度思考中…」 / 「已深度思考（用时 X 秒）」.
 */
export function ThinkingPanel({ block }: { readonly block: ThinkingBlock }) {
  const running = block.status === "running";
  const [open, setOpen] = useState(running);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (running) setOpen(true);
  }, [running]);

  useEffect(() => {
    if (!running || !open || !bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [block.content, running, open]);

  const title = running
    ? "深度思考中…"
    : block.durationMs != null && block.durationMs >= 100
      ? `已深度思考（用时 ${formatThinkingSeconds(block.durationMs)} 秒）`
      : "已深度思考";

  return (
    <div className="min-w-0">
      <button
        type="button"
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 border-0 bg-transparent py-1 text-left",
          focusRing,
        )}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span
          className={cn(
            "inline-flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-[var(--border)]",
            open && !running ? "text-[var(--color-thinking)]" : "text-[var(--text-muted)]",
          )}
        >
          {running ? (
            <Loader2 size={12} className="animate-spin" aria-hidden />
          ) : (
            <Atom size={12} aria-hidden />
          )}
        </span>
        <span
          className={cn(
            "min-w-0 flex-1 text-sm",
            running ? "thinking-shiny text-[var(--text-muted)]" : "text-[var(--text-muted)]",
          )}
        >
          {title}
        </span>
        <ChevronDown
          size={14}
          className={cn(
            "shrink-0 text-[var(--text-faint)] transition-transform",
            open ? "rotate-180" : "",
          )}
          aria-hidden
        />
      </button>
      {open ? (
        <div
          ref={bodyRef}
          className={cn(
            "mt-1 max-h-[min(40vh,320px)] overflow-y-auto rounded-[var(--radius-md)]",
            "border border-transparent px-2 py-1 text-sm text-[var(--text-muted)]",
          )}
        >
          {block.content ? (
            <div className="thinking-content">
              <MarkdownContent text={block.content} streaming={running} />
            </div>
          ) : (
            <p className="m-0 text-sm text-[var(--text-faint)]">…</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
