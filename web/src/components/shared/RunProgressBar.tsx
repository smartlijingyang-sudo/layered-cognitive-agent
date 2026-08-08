import { cn } from "../../lib/cn";
import type { RunPhase } from "../../projectors";

const PHASES: readonly { readonly key: RunPhase; readonly label: string }[] = [
  { key: "casting", label: "智能选角" },
  { key: "collaborating", label: "团队协作" },
  { key: "synthesizing", label: "收口综合" },
  { key: "completed", label: "完成" },
];

function phaseIndex(phase: RunPhase): number {
  if (phase === "idle" || phase === "casting") return 0;
  if (phase === "collaborating") return 1;
  if (phase === "synthesizing") return 2;
  if (phase === "completed") return 3;
  return -1;
}

export function RunProgressBar({
  phase,
  compact,
}: {
  readonly phase: RunPhase;
  readonly compact?: boolean;
}) {
  if (phase === "idle" || phase === "failed") return null;

  if (compact) {
    const label = PHASES.find((s) => s.key === phase)?.label ?? phaseStatusLabel(phase);
    return (
      <span
        className="inline-flex items-center gap-1.5 text-[11px] text-text-muted"
        role="status"
        aria-live="polite"
      >
        <span className="inline-block size-1.5 animate-pulse rounded-full bg-accent" />
        {label}
      </span>
    );
  }

  const active = phaseIndex(phase);

  return (
    <div
      className={cn("flex flex-wrap items-center gap-2", compact ? "text-xs" : "text-sm")}
      role="status"
      aria-live="polite"
      aria-label="运行进度"
    >
      {PHASES.map((step, index) => {
        const done = active > index;
        const current = active === index;
        return (
          <div key={step.key} className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 transition-colors",
                done && "border-run/40 bg-run/10 text-run",
                current && "border-accent bg-accent/10 text-text animate-pulse",
                !done && !current && "border-border text-text-muted",
              )}
            >
              <span
                className={cn(
                  "inline-block size-1.5 rounded-full",
                  done && "bg-run",
                  current && "bg-accent",
                  !done && !current && "bg-border",
                )}
              />
              {step.label}
            </span>
            {index < PHASES.length - 1 ? (
              <span className="text-text-muted" aria-hidden="true">
                →
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function phaseStatusLabel(phase: RunPhase): string {
  switch (phase) {
    case "casting":
      return "正在选角…";
    case "collaborating":
      return "团队协作中…";
    case "synthesizing":
      return "收口综合中…";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return "等待中";
  }
}
