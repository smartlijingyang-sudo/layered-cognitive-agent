import type { StampedEvent } from "../../contracts";
import { domainColor } from "../../renderers/domain-colors";
import type { VocabDomain } from "../../contracts";

export function JournalRail({
  events,
  onSelect,
}: {
  readonly events: readonly StampedEvent[];
  readonly onSelect: (seq: number) => void;
}) {
  return (
    <div className="journal-rail" aria-label="Journal 时间轨道">
      {events.map((stamped) => (
        <button
          key={stamped.seq}
          type="button"
          className="journal-rail-mark"
          style={{ background: domainColor((stamped.domain ?? "event") as VocabDomain) }}
          title={`#${stamped.seq} ${stamped.event.type}`}
          onClick={() => onSelect(stamped.seq)}
        />
      ))}
    </div>
  );
}
