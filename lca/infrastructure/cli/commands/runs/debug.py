"""``lca-ops runs debug`` —— 一次性诊断编排器。

按 layer 切分,默认 graph layer。agent 拿 JSON 输出含 ``next_layer_hint``,
告诉它下一步该看什么。

设计边界:
- 只读 spine + observation facts,纯观察面(AGENTS.md §2.3)。
- 每个 layer 是独立 projection 函数;orchestrator 只调度,不持有逻辑。
- 旧命令(``observation plan-show`` / ``trace-show`` / ``run-replay`` /
  ``run-explain`` / ``debug-graph``)完全保留;新命令是**增量入口**,非合并。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.commands._shared.output import (
    OutputMode,
    emit,
    output_option,
)
from lca.infrastructure.cli.commands._shared.projection import (
    SpineRow,
    filter_by_domain,
    load_spine_events,
)

_TRACES_ROOT_DEFAULT = Path("traces")

_LAYERS = ("summary", "graph", "events", "diff", "explain")
_DEFAULT_LAYER = "graph"

# agent-friendly default:JSON + graph layer
_DEFAULT_OUTPUT = OutputMode.JSON

# Per-layer next-step hint: tells an agent which layer to fetch next based on
# what this layer surfaced (e.g. anomaly found → explain).
_NEXT_HINT: dict[str, dict[str, str]] = {
    "summary": {
        "anomalies_present": "next_layer=explain to get a root-cause narrative",
        "no_anomalies": "next_layer=events to inspect raw spine rows",
        "spine_missing": "stop: run never produced a spine; check runs create receipt",
    },
    "graph": {
        "anomalies_present": "next_layer=explain to root-cause the failed node",
        "no_anomalies": "next_layer=summary for run-level counts",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "events": {
        "rows_present": "next_layer=graph for skeleton view, or filter --domain <name>",
        "rows_empty": "next_layer=summary to confirm the run reached the spine",
    },
    "diff": {
        "blueprint_missing": "next_layer=summary: plan not materialised; only execution trace available",
        "deviations_present": "next_layer=explain to root-cause unexpected nodes",
        "no_deviations": "next_layer=summary for run-level verdict",
    },
    "explain": {
        "root_cause_present": "next_layer=events to walk the offending step in raw form",
        "no_root_cause": "next_layer=summary for run-level counts",
    },
}


def _layer_summary(events: list[SpineRow]) -> dict[str, Any]:
    counts = {d: len(filter_by_domain(events, d)) for d in ("llm", "tool", "graph", "phase")}
    lifecycle = next((e for e in events if e.get("execution_point") == "kernel.run.stop"), None)
    terminal = None
    anomalies = False
    if lifecycle is not None:
        payload = lifecycle.get("payload") or {}
        terminal = payload.get("outcome")
        if isinstance(terminal, str) and terminal.lower() in {"fail", "failed", "failure", "error"}:
            anomalies = True
    return {
        "layer": "summary",
        "run_id": events[0].get("run_id") if events else None,
        "total_events": len(events),
        "domain_counts": counts,
        "terminal_outcome": terminal,
        "anomalies_present": anomalies,
    }


def _layer_graph(events: list[SpineRow]) -> dict[str, Any]:
    from lca.infrastructure.cli.commands.observation.debug_graph import (
        build_debug_graph,
    )

    report = build_debug_graph(events)
    report["layer"] = "graph"
    report["anomalies_present"] = bool(report.get("anomalies"))
    return report


def _layer_events(events: list[SpineRow]) -> dict[str, Any]:
    rows = [
        {
            "seq": e.get("sequence") or e.get("event_seq") or 0,
            "execution_point": e.get("execution_point", ""),
            "outcome": e.get("outcome"),
            "when": e.get("when") or e.get("ts"),
            "payload_keys": sorted((e.get("payload") or {}).keys()),
        }
        for e in events
    ]
    rows.sort(key=lambda r: r["seq"] or 0)
    return {
        "layer": "events",
        "run_id": events[0].get("run_id") if events else None,
        "rows": rows,
        "rows_present": bool(rows),
    }


def _layer_diff(events: list[SpineRow]) -> dict[str, Any]:
    """PlanBlueprint vs executed nodes. Reads blueprint.json from run_dir."""
    import json

    run_id = events[0].get("run_id", "") if events else ""
    blueprint_path = _TRACES_ROOT_DEFAULT / "runs" / run_id / "blueprint.json"
    if not blueprint_path.exists():
        return {
            "layer": "diff",
            "blueprint_missing": True,
            "deviations_present": False,
            "hint": _NEXT_HINT["diff"]["blueprint_missing"],
        }
    blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
    expected_nodes = {n["id"] for n in blueprint.get("nodes", [])}
    executed_nodes = {
        (e.get("payload") or {}).get("node_id")
        for e in events
        if e.get("execution_point") == "phase_graph.node.end"
    }
    executed_nodes.discard(None)
    missing = sorted(expected_nodes - executed_nodes)
    unexpected = sorted(executed_nodes - expected_nodes)
    return {
        "layer": "diff",
        "blueprint_missing": False,
        "deviations_present": bool(missing or unexpected),
        "missing_nodes": missing,
        "unexpected_nodes": unexpected,
        "hint": _NEXT_HINT["diff"]["deviations_present" if missing or unexpected else "no_deviations"],
    }


def _layer_explain(events: list[SpineRow]) -> dict[str, Any]:
    """Root-cause narrative. Walks the spine for failed nodes / lifecycle events."""
    failed: list[SpineRow] = []

    def _is_fail(v: object) -> bool:
        return isinstance(v, str) and v.lower() in {"fail", "failed", "failure", "error"}

    for e in events:
        payload_outcome = (e.get("payload") or {}).get("outcome")
        ep_outcome = e.get("outcome")
        if _is_fail(payload_outcome) or _is_fail(ep_outcome):
            failed.append(e)
    if not failed:
        return {
            "layer": "explain",
            "root_cause_present": False,
            "summary": "no failed nodes / lifecycle events in spine",
            "next_actions": ["next_layer=summary to confirm run reached terminal"],
        }
    first = failed[0]
    return {
        "layer": "explain",
        "root_cause_present": True,
        "first_failed": {
            "execution_point": first.get("execution_point"),
            "seq": first.get("sequence") or first.get("event_seq") or 0,
            "outcome": first.get("outcome") or (first.get("payload") or {}).get("outcome"),
            "error": (first.get("payload") or {}).get("error"),
        },
        "next_actions": ["next_layer=events to walk the offending step in raw form"],
    }


_LAYER_DISPATCH: dict[str, Any] = {
    "summary": _layer_summary,
    "graph": _layer_graph,
    "events": _layer_events,
    "diff": _layer_diff,
    "explain": _layer_explain,
}


def _human(payload: dict[str, Any]) -> str:
    layer = payload.get("layer", "?")
    out = [f"=== runs debug layer={layer} ==="]
    for k, v in payload.items():
        if k == "layer":
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out.append(f"{k}:")
            for item in v[:10]:
                out.append(f"  - {item}")
        else:
            out.append(f"{k}: {v}")
    return "\n".join(out)


def register(app: typer.Typer) -> None:
    """Mount `runs debug` (and `runs debug-graph` alias) under the runs sub-app."""

    @app.command(
        name="debug",
        help=(
            "One-shot run debugger: pick a layer (summary|graph|events|diff|explain) "
            "and read the spine directly. JSON output carries `next_layer_hint` "
            "for agent callers."
        ),
    )
    def debug_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        layer: str = typer.Option(
            _DEFAULT_LAYER,
            "--layer",
            help=f"One of: {', '.join(_LAYERS)}. Default: {_DEFAULT_LAYER}",
        ),
        output: OutputMode = output_option(_DEFAULT_OUTPUT),
    ) -> None:
        if layer not in _LAYERS:
            typer.echo(
                f"unknown layer {layer!r}; valid: {', '.join(_LAYERS)}",
                err=True,
            )
            raise typer.Exit(code=2)

        events = load_spine_events(run_id)
        if not events:
            payload = {
                "layer": layer,
                "run_id": run_id,
                "spine_missing": True,
                "hint": _NEXT_HINT[layer]["spine_missing"],
            }
            emit(output, payload, human_renderer=_human)
            return

        projection = _LAYER_DISPATCH[layer]
        payload = projection(events)
        if "hint" not in payload and not payload.get("anomalies_present"):
            payload["hint"] = _NEXT_HINT[layer].get("no_anomalies", "")
        elif "hint" not in payload and payload.get("anomalies_present"):
            payload["hint"] = _NEXT_HINT[layer].get("anomalies_present", "")

        emit(output, payload, human_renderer=_human)


__all__ = ["register"]
