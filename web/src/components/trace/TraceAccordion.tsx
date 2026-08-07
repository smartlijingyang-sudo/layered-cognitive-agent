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
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

function traceSummary(trace: TraceState): string {
  if (trace.phase === "casting") return "◎ 正在智能选角…";
  if (trace.casting) {
    const roles = trace.casting.selectedRoles.join("、");
    return `✓ 已组队 · ${trace.casting.governanceKind} · ${roles}`;
  }
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
    <div className="mt-3 border-t border-border pt-2">
      <button
        type="button"
        className={cn(
          "w-full cursor-pointer border-0 bg-transparent py-1 text-left text-sm",
          mutedText,
          focusRing,
        )}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起轨迹" : traceSummary(trace)}
      </button>
      {open ? (
        <div className="animate-fade-in grid gap-3">
          <InsightSummary insights={trace.insights} />
          <Tabs.Root defaultValue="timeline">
            <Tabs.List className="mb-2 flex gap-2">
              <Tabs.Trigger
                value="timeline"
                className={cn(
                  "cursor-pointer rounded-full border border-border px-2.5 py-1 text-sm text-text-muted",
                  "data-[state=active]:border-accent data-[state=active]:text-text",
                  focusRing,
                )}
              >
                事件流
              </Tabs.Trigger>
              {diagram ? (
                <Tabs.Trigger
                  value="sequence"
                  className={cn(
                    "cursor-pointer rounded-full border border-border px-2.5 py-1 text-sm text-text-muted",
                    "data-[state=active]:border-accent data-[state=active]:text-text",
                    focusRing,
                  )}
                >
                  协作时序图
                </Tabs.Trigger>
              ) : null}
            </Tabs.List>
            <Tabs.Content value="timeline" className="outline-none">
              <div className="grid grid-cols-[12px_minmax(0,1fr)] gap-3">
                <JournalRail events={visible} onSelect={() => undefined} />
                <TracePanel events={events} trace={trace} verbosity={verbosity} />
              </div>
            </Tabs.Content>
            {diagram ? (
              <Tabs.Content value="sequence" className="outline-none">
                <div ref={diagramRef} className="overflow-x-auto" />
              </Tabs.Content>
            ) : null}
          </Tabs.Root>
        </div>
      ) : null}
    </div>
  );
}
