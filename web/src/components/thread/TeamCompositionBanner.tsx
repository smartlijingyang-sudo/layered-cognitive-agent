import type { CastingInfo } from "../../projectors";
import { cn } from "../../lib/cn";
import { elevatedSurface, mutedText } from "../../lib/ui";

export function TeamCompositionBanner({
  casting,
}: {
  readonly casting: CastingInfo;
}) {
  return (
    <div className={cn(elevatedSurface, "border border-team/25 bg-team/5 px-3 py-2.5")}>
      <p className="m-0 text-sm font-medium text-team">已组建团队</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {casting.selectedRoles.map((role) => (
          <span
            key={role}
            className="rounded-full border border-border bg-surface px-2 py-0.5 text-xs text-text"
          >
            {role}
          </span>
        ))}
      </div>
      <p className={cn("m-0 mt-2 text-xs", mutedText)}>
        协作方式 · {casting.governanceKind}
        {casting.leadRole ? ` · 主导 ${casting.leadRole}` : ""}
      </p>
    </div>
  );
}
