import type { CastingInfo } from "../../projectors";
import { cn } from "../../lib/cn";
import { mutedText } from "../../lib/ui";

export function TeamCompositionBanner({
  casting,
}: {
  readonly casting: CastingInfo;
}) {
  return (
    <div className={cn("rounded-[var(--radius-md)] border border-team/20 bg-team/5 px-3 py-2")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-medium text-team">已组队</span>
        {casting.selectedRoles.map((role) => (
          <span
            key={role}
            className="rounded-full border border-border/60 bg-surface/80 px-2 py-0.5 text-[11px] text-text"
          >
            {role}
          </span>
        ))}
      </div>
      <p className={cn("m-0 mt-1.5 text-[11px]", mutedText)}>
        {casting.governanceKind}
        {casting.leadRole ? ` · ${casting.leadRole}` : ""}
      </p>
    </div>
  );
}
