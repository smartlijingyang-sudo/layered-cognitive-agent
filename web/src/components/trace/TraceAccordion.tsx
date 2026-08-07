import { useMemo, useState, useEffect, useRef } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import mermaid from "mermaid";
import type { StampedEvent } from "../../contracts";
import type { TraceState, Verbosity } from "../../projectors";
import { shouldShowEvent } from "../../projectors";
import { renderSequenceDiagram } from "../../domain/sequence-diagram";
import { InsightSummary } from "./InsightSummary";
import { JournalRail } from "./JournalRail";
import { TracePanel } from "../../renderers/trace-panel";

function traceSummary(trace: TraceState): string {
  const parts = [
    trace.teamRun ? `${trace.teamRun.teamId} · ${trace.teamRun.mandate}` : null,
    trace.status ? `状态 ${trace.status}` : null,
    trace.delegations.length ? `委派 ${trace.delegations.length}` : null,
    trace.insights.length ? `洞察 ${trace.insights.length}` : null,
  ].filter(Boolean);
  return parts.join(" · ") || "查看团队协作轨迹";
}

export function TraceAccordion({
  events,
  trace,
  verbosity,
}: {
  readonly events: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
}) {
  const [open, setOpen] = useState(false);
  const visible = useMemo(
    () => events.filter((e) => shouldShowEvent(e.event.type, verbosity)),
    [events, verbosity],
  );
  const diagram = useMemo(() => renderSequenceDiagram(events), [events]);
  const diagramRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: "dark" });
  }, []);

  useEffect(() => {
    if (!open || !diagram || !diagramRef.current) return;
    const render = async () => {
      const { svg } = await mermaid.render(`seq-${Date.now()}`, diagram);
      if (diagramRef.current) diagramRef.current.innerHTML = svg;
    };
    void render();
  }, [open, diagram]);

  if (events.length === 0) return null;

  return (
    <div className={`trace-accordion ${open ? "open" : ""}`}>
      <button type="button" className="trace-accordion-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "收起轨迹" : traceSummary(trace)}
      </button>
      {open ? (
        <div className="trace-accordion-body">
          <InsightSummary insights={trace.insights} />
          <Tabs.Root defaultValue="timeline">
            <Tabs.List className="trace-tabs">
              <Tabs.Trigger value="timeline">事件流</Tabs.Trigger>
              {diagram ? <Tabs.Trigger value="sequence">协作时序图</Tabs.Trigger> : null}
            </Tabs.List>
            <Tabs.Content value="timeline" className="trace-tab-panel">
              <div className="trace-with-rail">
                <JournalRail events={visible} onSelect={() => undefined} />
                <TracePanel events={events} trace={trace} verbosity={verbosity} />
              </div>
            </Tabs.Content>
            {diagram ? (
              <Tabs.Content value="sequence" className="trace-tab-panel">
                <div ref={diagramRef} className="mermaid-panel" />
              </Tabs.Content>
            ) : null}
          </Tabs.Root>
        </div>
      ) : null}
    </div>
  );
}
