import type { StampedEvent } from "../../contracts";
import type { Turn } from "../../domain/conversation";
import { MarkdownContent } from "../shared/MarkdownContent";
import { ProgressiveReveal } from "../shared/ProgressiveReveal";
import { TraceAccordion } from "../trace/TraceAccordion";
import type { TraceState, Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { elevatedSurface, mutedText } from "../../lib/ui";

export function AssistantBubble({
  turn,
  events,
  trace,
  verbosity,
  developerMode,
}: {
  readonly turn: Turn;
  readonly events: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
}) {
  const streaming = turn.status === "running" || turn.status === "pending";
  const body =
    turn.status === "running" && !developerMode ? (
      <ProgressiveReveal text={turn.answer} active={streaming} />
    ) : (
      turn.answer
    );

  return (
    <article className={cn(elevatedSurface, "border-l-[3px] border-l-run px-4 py-3.5")}>
      <header className={cn("mb-1.5 text-xs", mutedText)}>助手 · {turn.status}</header>
      {developerMode || turn.status === "completed" ? (
        <MarkdownContent text={turn.answer} />
      ) : (
        <div className="markdown-body">
          <p className="m-0">{body}</p>
        </div>
      )}
      <TraceAccordion events={events} trace={trace} verbosity={verbosity} />
    </article>
  );
}
