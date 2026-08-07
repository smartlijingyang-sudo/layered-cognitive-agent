import type { StampedEvent } from "../../contracts";
import { domainColor } from "../../renderers/domain-colors";
import type { VocabDomain } from "../../contracts";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

export function JournalRail({
  events,
  onSelect,
}: {
  readonly events: readonly StampedEvent[];
  readonly onSelect: (seq: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1 pt-1" aria-label="Journal 时间轨道">
      {events.map((stamped) => (
        <button
          key={stamped.seq}
          type="button"
          className={cn(
            "h-[18px] w-1 cursor-pointer rounded-full opacity-75 hover:opacity-100",
            focusRing,
          )}
          style={{ background: domainColor((stamped.domain ?? "event") as VocabDomain) }}
          title={`#${stamped.seq} ${stamped.event.type}`}
          onClick={() => onSelect(stamped.seq)}
        />
      ))}
    </div>
  );
}
