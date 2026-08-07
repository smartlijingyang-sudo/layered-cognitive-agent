import type { StampedEvent } from "../../contracts";
import type { TraceState, Verbosity } from "../../projectors";
import { InsightSummary } from "./InsightSummary";
import { TracePanel } from "../../renderers/trace-panel";
import { btnSecondary, panelSurface } from "../../lib/ui";
import { cn } from "../../lib/cn";

export function DeveloperTracePanel({
  events,
  trace,
  verbosity,
}: {
  readonly events: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
}) {
  const downloadJsonl = () => {
    const lines = events.map((event) => JSON.stringify(event)).join("\n");
    const blob = new Blob([lines], { type: "application/jsonl" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "lca_journal_export.jsonl";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <aside className={cn(panelSurface, "flex flex-col gap-3 overflow-auto p-3.5")}>
      <header className="flex items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold">开发者轨迹</h2>
        <button type="button" className={btnSecondary} onClick={downloadJsonl}>
          下载 journal
        </button>
      </header>
      <InsightSummary insights={trace.insights} />
      <TracePanel events={events} trace={trace} verbosity={verbosity} />
    </aside>
  );
}
