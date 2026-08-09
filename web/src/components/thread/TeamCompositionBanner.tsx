import { Users } from "lucide-react";
import type { CastingInfo } from "../../projectors";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { mutedText } from "../../lib/ui";

export function TeamCompositionBanner({
  casting,
}: {
  readonly casting: CastingInfo;
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]",
        "px-3 py-2.5 shadow-[var(--shadow-card)]",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
          <LobeIcon icon={Users} size="xs" />
          已组队
        </span>
        {casting.selectedRoles.map((role) => (
          <span
            key={role}
            className={cn(
              "rounded-full border border-[var(--border-subtle)] bg-[var(--fill-secondary)]",
              "px-2 py-0.5 text-[11px] font-medium text-[var(--text)]",
            )}
          >
            {role}
          </span>
        ))}
      </div>
      <p className={cn("m-0 mt-1.5 text-[11px]", mutedText)}>
        {casting.governanceKind}
        {casting.leadRole ? ` · 主导 ${casting.leadRole}` : ""}
        {casting.rationale ? ` · ${casting.rationale}` : ""}
      </p>
    </div>
  );
}
