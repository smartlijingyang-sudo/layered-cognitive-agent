import { useMemo } from "react";
import type { StampedEvent } from "../contracts/stamped";
import type { TraceState, Verbosity } from "../projectors";
import { shouldShowEvent } from "../projectors";
import { EVENT_RENDERERS } from "./registry";
import { InsightBadge } from "./event-cards";
import { cn } from "../lib/cn";
import { mutedText, panelSurface } from "../lib/ui";

export function TracePanel({
  events,
  trace,
  verbosity,
}: {
  readonly events: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
}) {
  const visible = useMemo(
    () => events.filter((e) => shouldShowEvent(e.event.type, verbosity)),
    [events, verbosity],
  );

  return (
    <section className={cn(panelSurface, "overflow-auto p-3.5")}>
      <header>
        <h2 className="m-0 text-sm font-semibold">运行轨迹</h2>
        {trace.teamRun ? (
          <span className={cn("text-sm", mutedText)}>
            {trace.teamRun.teamId} · {trace.teamRun.mandate} · {trace.status ?? "…"}
          </span>
        ) : null}
      </header>
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
        {visible.map((stamped) => {
          const Renderer = EVENT_RENDERERS[stamped.event.type];
          return (
            <Renderer
              key={stamped.seq}
              event={stamped.event}
              scope={stamped.scope}
              domain={stamped.domain}
            />
          );
        })}
      </div>
    </section>
  );
}
