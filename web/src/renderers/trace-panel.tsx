import { useMemo } from "react";
import type { StampedEvent } from "../contracts/stamped";
import type { TraceState, Verbosity } from "../projectors";
import { buildTraceTimeline } from "../projectors";
import { EVENT_RENDERERS } from "./registry";
import { InsightBadge, SandboxOutputStreamCard, StepTextStreamCard } from "./event-cards";
import { cn } from "../lib/cn";
import { mutedText, panelSurface } from "../lib/ui";

export function TracePanel({
  events,
  trace,
  verbosity,
  showHeader = true,
}: {
  readonly events: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  /** 嵌在折叠轨迹内时可关标题，避免重复。 */
  readonly showHeader?: boolean;
}) {
  const timeline = useMemo(
    () => buildTraceTimeline(events, trace.stepStreams, verbosity, trace.sandboxStreams),
    [events, trace.stepStreams, trace.sandboxStreams, verbosity],
  );

  return (
    <section className={cn(panelSurface, "overflow-auto p-3.5")}>
      {showHeader ? (
        <header>
          <h2 className="m-0 text-sm font-semibold">运行轨迹</h2>
          {trace.teamRun ? (
            <span className={cn("text-sm", mutedText)}>
              {trace.teamRun.teamId} · {trace.teamRun.mandate} · {trace.status ?? "…"}
            </span>
          ) : null}
        </header>
      ) : null}
      <div className="my-3 flex flex-col gap-2">
        {trace.insights.map((insight, index) => (
          <InsightBadge
            key={`${insight.kind}-${index}`}
            event={insight}
            scope={{
              trace_id: "",
              run_id: "",
              parent_run_id: null,
              delegation_id: null,
              agent_role: "",
            }}
            domain="event"
          />
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {timeline.map((item) => {
          if (item.kind === "step_stream") {
            return <StepTextStreamCard key={item.stream.key} stream={item.stream} />;
          }
          if (item.kind === "sandbox_stream") {
            return <SandboxOutputStreamCard key={item.stream.key} stream={item.stream} />;
          }
          const Renderer = EVENT_RENDERERS[item.stamped.event.type];
          return (
            <Renderer
              key={item.stamped.seq}
              event={item.stamped.event}
              scope={item.stamped.scope}
              domain={item.stamped.domain}
            />
          );
        })}
      </div>
    </section>
  );
}
