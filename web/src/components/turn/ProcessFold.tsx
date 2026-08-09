import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

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
        <span className="min-w-0 flex-1 text-sm text-[var(--text-muted)]">{title}</span>
        <ChevronDown
          size={14}
          className={cn(
            "shrink-0 text-[var(--text-faint)] transition-transform",
            open ? "rotate-180" : "",
          )}
          aria-hidden
        />
      </button>
      {open ? <div className="mt-2 grid gap-3 animate-fade-in">{children}</div> : null}
    </div>
  );
}
