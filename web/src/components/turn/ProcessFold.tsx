import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { focusRing } from "../../lib/ui";
import { WORKFLOW_EASE_CSS } from "./workflow-constants";

/**
 * LobeHub Codex-style process fold — 「共运行 N 步 (duration)」.
 * Final answer must stay outside this component.
 */
export function ProcessFold({
  stepCount,
  durationText,
  defaultExpanded = false,
  children,
}: {
  readonly stepCount: number;
  readonly durationText?: string;
  readonly defaultExpanded?: boolean;
  readonly children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultExpanded);
  const title = durationText
    ? `共运行 ${stepCount} 步 (${durationText})`
    : `共运行 ${stepCount} 步`;

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
        <span className="min-w-0 flex-1 text-sm text-[var(--text-muted)]">{title}</span>
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
          "grid transition-[grid-template-rows,opacity]",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        style={{
          transitionDuration: "220ms",
          transitionTimingFunction: WORKFLOW_EASE_CSS,
        }}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="mt-2 grid gap-3 animate-fade-in">{children}</div>
        </div>
      </div>
    </div>
  );
}
