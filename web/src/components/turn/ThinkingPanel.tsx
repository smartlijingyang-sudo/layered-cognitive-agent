import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { ThinkingBlock } from "../../projectors/types";
import { formatThinkingSeconds } from "../../lib/format-duration";
import { LobeIcon } from "../../lib/icons";
import { MarkdownContent } from "../shared/MarkdownContent";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";
import { StatusBlock } from "./StatusBlock";
import { THINKING_BODY_MAX_HEIGHT_CSS, WORKFLOW_EASE_CSS } from "./workflow-constants";

/**
 * LobeHub Thinking accordion —
 * streaming: shiny「深度思考中…」auto-open + scroll
 * done: Atom + 「已深度思考（用时 X.X 秒）」muted markdown body
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
    <div className="lobe-accordion min-w-0">
      <button
        type="button"
        className={cn(
          "lobe-accordion-trigger flex w-full cursor-pointer items-center gap-1.5",
          "border-0 bg-transparent py-1 text-left",
          focusRing,
        )}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <StatusBlock
          variant={
            running ? "thinking" : open ? "thinking-done-active" : "thinking-done"
          }
        />
        <span
          className={cn(
            "min-w-0 flex-1 text-[13px] leading-snug",
            running ? "lobe-shiny" : open ? "text-[var(--text)]" : "text-[var(--text-muted)]",
          )}
        >
          {title}
        </span>
        <LobeIcon
          icon={ChevronDown}
          size="sm"
          className={cn(
            "shrink-0 text-[var(--text-faint)] transition-transform",
            open ? "rotate-180" : "",
          )}
          style={{ transitionDuration: "180ms", transitionTimingFunction: WORKFLOW_EASE_CSS }}
        />
      </button>

      <div
        className={cn(
          "lobe-accordion-panel grid transition-[grid-template-rows,opacity]",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        style={{
          transitionDuration: "200ms",
          transitionTimingFunction: WORKFLOW_EASE_CSS,
        }}
      >
        <div className="min-h-0 overflow-hidden">
          <div
            ref={bodyRef}
            className={cn(
              "lobe-thinking-scroll mt-1 overflow-y-auto px-2 py-1",
              "text-sm text-[var(--text-muted)]",
            )}
            style={{ maxHeight: THINKING_BODY_MAX_HEIGHT_CSS }}
          >
            {block.content ? (
              <div className="thinking-content">
                <MarkdownContent text={block.content} streaming={running} />
              </div>
            ) : (
              <p className="m-0 text-sm text-[var(--text-faint)]">…</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
