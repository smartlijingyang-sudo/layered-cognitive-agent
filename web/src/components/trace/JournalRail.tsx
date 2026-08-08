import { domainColor } from "../../renderers/domain-colors";
import type { VocabDomain } from "../../contracts";
import type { TraceTimelineItem } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

function railMark(item: TraceTimelineItem): {
  readonly key: string;
  readonly seq: number;
  readonly domain: string;
  readonly title: string;
} {
  if (item.kind === "step_stream") {
    const { stream } = item;
    return {
      key: stream.key,
      seq: stream.anchorJournalSeq,
      domain: stream.domain,
      title: `#${stream.anchorJournalSeq} Δ step ${stream.step} (${stream.chunkCount} chunks)`,
    };
  }
  if (item.kind === "sandbox_stream") {
    const { stream } = item;
    return {
      key: stream.key,
      seq: stream.anchorJournalSeq,
      domain: stream.domain,
      title: `#${stream.anchorJournalSeq} sandbox ${stream.stream} (${stream.chunkCount} chunks)`,
    };
  }
  return {
    key: String(item.stamped.seq),
    seq: item.stamped.seq,
    domain: item.stamped.domain ?? "event",
    title: `#${item.stamped.seq} ${item.stamped.event.type}`,
  };
}

export function JournalRail({
  timeline,
  onSelect,
}: {
  /** 与 TracePanel 同一条时间线（delta 已按 step 折叠）。 */
  readonly timeline: readonly TraceTimelineItem[];
  readonly onSelect: (seq: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1 pt-1" aria-label="Journal 时间轨道">
      {timeline.map((item) => {
        const mark = railMark(item);
        return (
          <button
            key={mark.key}
            type="button"
            className={cn(
              "h-[18px] w-1 cursor-pointer rounded-full opacity-75 hover:opacity-100",
              focusRing,
            )}
            style={{ background: domainColor(mark.domain as VocabDomain) }}
            title={mark.title}
            onClick={() => onSelect(mark.seq)}
          />
        );
      })}
    </div>
  );
}
