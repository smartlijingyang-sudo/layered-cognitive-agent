import { useMemo } from "react";
import type { StampedEvent } from "../contracts/stamped";
import type { TraceState, Verbosity } from "../projectors";
import { shouldShowEvent } from "../projectors";
import { EVENT_RENDERERS } from "./registry";

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
    <section className="trace-panel">
      <header className="trace-header">
        <h2>运行轨迹</h2>
        {trace.teamRun ? (
          <span className="trace-meta">
            {trace.teamRun.teamId} · {trace.teamRun.mandate} · {trace.status ?? "…"}
          </span>
        ) : null}
      </header>
      <div className="trace-list">
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
