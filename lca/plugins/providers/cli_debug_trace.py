"""lca-ops debug trace 插件（ADR-0063 PR-9）。

把现有 stub 改为：调用 ``TraceInspector`` + 支持 `--from-file` / `--focus` /
`--explain-failure` / `--bottlenecks` / `--plugin-graph` / `--minimal-reproduction`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.cli_debug_command import CliDebugCommand
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _DebugTraceCommand:
    name = "trace"
    description = "render run-scoped journal via TraceInspector"

    def run(self, **kwargs: Any) -> int:
        from lca.layer0_infra.observability import TraceInspector, read_journal

        from_file: Path | None = kwargs.get("from_file")
        run_id: str | None = kwargs.get("run_id")
        focus: str = kwargs.get("focus") or "all"
        explain_failure: bool = bool(kwargs.get("explain_failure"))
        bottlenecks: bool = bool(kwargs.get("bottlenecks"))
        plugin_graph: bool = bool(kwargs.get("plugin_graph"))
        minimal_reproduction: bool = bool(kwargs.get("minimal_reproduction"))
        limit: int = int(kwargs.get("limit") or 5)

        path = from_file
        if path is None and run_id is not None:
            path = Path("traces/runs") / f"{run_id}.journal"
        if path is None or not path.exists():
            print("debug trace requires --from-file or --run-id (journal not found)")
            return 1

        events = read_journal(path)
        if not events:
            print(f"journal empty: {path}")
            return 1

        inspector = TraceInspector(events)
        if explain_failure:
            report = inspector.explain_failure()
        elif minimal_reproduction:
            payload = inspector.export_minimal_reproduction()
            print(json.dumps(list(payload), ensure_ascii=False))
            return 0
        elif bottlenecks:
            print(json.dumps(inspector.find_optimization_candidates(limit=limit), ensure_ascii=False))
            return 0
        elif plugin_graph:
            print(inspector.plugin_interaction_graph())
            return 0
        else:
            report = inspector.inspect_trace(focus=focus)  # type: ignore[arg-type]
        print(
            json.dumps(
                {
                    "trace_id": report.trace_id,
                    "event_count": report.event_count,
                    "summary": report.summary,
                    "causal_chain": list(report.causal_chain),
                    "bottlenecks": list(report.bottlenecks),
                    "plugin_graph": report.plugin_graph,
                    "events": [event for event in report.events],
                },
                ensure_ascii=False,
            )
        )
        return 0


def _render_event(stamped: Any) -> dict[str, Any]:
    return {
        "seq": stamped.seq,
        "ts": stamped.ts,
        "event_type": stamped.event_type,
        "scope": stamped.scope,
        "data": stamped.data,
    }


@plugin(
    id="lca-cli-debug-trace",
    requires=["cli_debug_command"],
    implements=[CliDebugCommand],
    layer="L0",
    effects="none",
    description="lca-ops debug trace handler via TraceInspector (PR-9).",
    test_suite="tests/test_cli_debug_trace.py::test_trace_command_registered",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    registry: NamedRegistry = ctx.require("cli_debug_command")
    registry.register("trace", _DebugTraceCommand())