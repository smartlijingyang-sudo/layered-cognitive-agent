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
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "diff": {
        "blueprint_missing": "next_layer=summary: plan not materialised; only execution trace available",
        "deviations_present": "next_layer=explain to root-cause unexpected nodes",
        "no_deviations": "next_layer=summary for run-level verdict",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "explain": {
        "root_cause_present": "next_layer=events to walk the offending step in raw form",
        "no_root_cause": "next_layer=summary for run-level counts",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
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
    """Chain + effect + data-flow projection.

    Builds on `build_debug_graph` for node-level fields (marker, elapsed,
    dispatch, outputs summary), then joins four cross-node views that the
    plain debug-graph cannot surface:

    - edges: phase_graph.edge.transit + subgraph enter/exit
    - effects: llm.call.* / body.tool.* / phase.tool.* / body.sandbox.* /
      think.gate.* / runtime.reducer.apply, attached to the producing
      node by ts proximity
    - data_flow: a node's outputs become the next node's inputs (joined
      by name when input_keys match output keys, ts-ordered)
    - llm_prompts: full messages + tools from llm.request.header
      attached to the node that called LLM
    """
    from lca.infrastructure.cli.commands.observation.debug_graph import (
        build_debug_graph,
    )

    decorated = _inject_node_windows(events)
    report = build_debug_graph(decorated)
    base_nodes = report["nodes"]

    edges = _extract_edges(events)
    effects_by_node = _attach_effects(events, base_nodes)
    flow_edges = _join_data_flow(base_nodes, effects_by_node)
    llm_prompts = _extract_llm_prompts(events)

    for node in base_nodes:
        nid = node["node_id"]
        node["effects"] = effects_by_node.get(nid, [])
        node["produced_for"] = flow_edges.get(nid, [])
        outs = node.get("outputs") or {}
        ts_in = outs.pop("_ts_in", None)
        ts_out = outs.pop("_ts_out", None)
        if ts_in or ts_out:
            node["ts_in"] = ts_in
            node["ts_out"] = ts_out

    report["layer"] = "graph"
    report["anomalies_present"] = bool(report.get("anomalies"))
    report["edges"] = edges
    report["data_flow"] = [
        {"from": frm, "to": to} for frm, tos in flow_edges.items() for to in tos
    ]
    report["llm_prompts"] = llm_prompts
    return report


def _inject_node_windows(events: list[SpineRow]) -> list[SpineRow]:
    """Pair phase_graph.node.{start,end} by (node_id, visit_index) and
    nest _ts_in / _ts_out into end.payload.outputs. build_debug_graph
    surfaces these on each node entry; cross-node joiner reads them back.
    """
    starts: dict[tuple[str, int], str] = {}
    for ev in events:
        ep = ev.get("execution_point")
        p = ev.get("payload") or {}
        if ep == "phase_graph.node.start":
            key = (p.get("node_id") or "", p.get("visit_index", 1))
            starts[key] = str(ev.get("ts") or "")
    decorated: list[SpineRow] = []
    for ev in events:
        copy = dict(ev)
        ep = copy.get("execution_point")
        p = dict(copy.get("payload") or {})
        if ep == "phase_graph.node.end":
            key = (p.get("node_id") or "", p.get("visit_index", 1))
            ts_in = starts.get(key)
            outs = dict(p.get("outputs") or {})
            if ts_in:
                outs["_ts_in"] = ts_in
            outs["_ts_out"] = copy.get("ts")
            p["outputs"] = outs
        copy["payload"] = p
        decorated.append(copy)
    return decorated


def _extract_edges(events: list[SpineRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in events:
        ep = e.get("execution_point")
        p = e.get("payload") or {}
        if ep == "phase_graph.edge.transit":
            out.append({
                "kind": "edge",
                "from": p.get("from_node") or "",
                "to": _edge_to_node(p.get("edge_id") or ""),
                "edge_id": p.get("edge_id") or "",
                "predicate": (p.get("metadata") or {}).get("when") or "",
                "ts": e.get("ts"),
            })
        elif ep == "phase_graph.subgraph.enter":
            out.append({
                "kind": "subgraph_enter",
                "node": p.get("node_id") or "",
                "depth": p.get("depth"),
                "ts": e.get("ts"),
            })
        elif ep == "phase_graph.subgraph.exit":
            out.append({
                "kind": "subgraph_exit",
                "node": p.get("node_id") or "",
                "depth": p.get("depth"),
                "ts": e.get("ts"),
            })
    out.sort(key=lambda e: str(e.get("ts") or ""))
    return out


def _edge_to_node(edge_id: str) -> str:
    if "->" in edge_id:
        return edge_id.split("->", 1)[1].strip()
    return ""


def _attach_effects(
    events: list[SpineRow],
    nodes: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map each effect EP to its producing node by ts proximity.

    Each node has ts_in (start) and ts_out (end) inferred from
    phase_graph.node.{start,end}. Effects whose ts falls in that window
    belong to the node.
    """
    from datetime import datetime

    def parse(ts: object) -> float:
        s = str(ts or "")
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    windows: list[tuple[float, float, str]] = []
    for n in nodes:
        ts_in = parse((n.get("outputs") or {}).get("_ts_in"))
        ts_out = parse((n.get("outputs") or {}).get("_ts_out"))
        if ts_in and ts_out:
            windows.append((ts_in, ts_out, n["node_id"]))

    out: dict[str, list[dict[str, Any]]] = {n["node_id"]: [] for n in nodes}
    for e in events:
        ep = e.get("execution_point")
        if not _is_effect_ep(ep):
            continue
        p = e.get("payload") or {}
        ts = parse(e.get("ts"))
        owner = None
        for ts_in, ts_out, nid in windows:
            if ts_in <= ts <= ts_out:
                owner = nid
                break
        if owner is None and windows:
            owner = min(windows, key=lambda w: abs(w[0] - ts))[2]

        effect = _effect_from_ep(ep, p, e)
        if owner is not None:
            out[owner].append(effect)

    return out


def _is_effect_ep(ep: object) -> bool:
    s = str(ep or "")
    return s.startswith("llm.") or s.startswith("body.tool.") or s.startswith(
        "phase.tool."
    ) or s.startswith("body.sandbox.") or s.startswith("think.gate.") or s in {
        "runtime.reducer.apply",
        "phase.think.fold",
        "phase.perceive.fold",
    }


def _effect_from_ep(ep: object, p: dict[str, Any], e: SpineRow) -> dict[str, Any]:
    s = str(ep or "")
    if s.startswith("llm.call."):
        out = {"kind": "llm_call", "phase": s.split(".")[-1],
               "model": p.get("model"), "ts": e.get("ts")}
        if "latency_ms" in p:
            out["latency_ms"] = p.get("latency_ms")
        if "usage" in p:
            out["usage"] = p.get("usage")
        if "prompt_tokens" in p or "completion_tokens" in p:
            out["tokens"] = {
                "prompt": p.get("prompt_tokens"),
                "completion": p.get("completion_tokens"),
            }
        if "outcome" in p:
            out["outcome"] = p.get("outcome")
        return out
    if s.startswith("llm.request.header"):
        return {"kind": "llm_request", "model": (p.get("config") or {}).get("model"),
                "step_id": p.get("step_id"), "reason": p.get("reason"),
                "ts": e.get("ts")}
    if s.startswith("llm.stream."):
        return {"kind": "llm_stream", "stream_phase": s.split(".")[-1],
                "ts": e.get("ts")}
    if s.startswith("body.tool.execute."):
        return {"kind": "tool_exec", "phase": s.split(".")[-1],
                "tool_name": p.get("name") or p.get("tool_name"),
                "ts": e.get("ts")}
    if s.startswith("phase.tool.call."):
        verdict = p.get("verdict") or p.get("outcome") or ""
        return {"kind": "tool_call", "phase": s.split(".")[-1],
                "tool_name": p.get("name") or p.get("tool_name"),
                "verdict": verdict, "ts": e.get("ts")}
    if s.startswith("body.sandbox."):
        return {"kind": "sandbox", "phase": s.split(".")[-1],
                "ts": e.get("ts")}
    if s.startswith("think.gate."):
        return {"kind": "gate", "phase": s.split(".")[-1],
                "ts": e.get("ts")}
    if s == "runtime.reducer.apply":
        return {"kind": "reducer", "method": p.get("method"),
                "phase": p.get("phase"), "outcome": p.get("outcome"),
                "ts": e.get("ts")}
    if s.startswith("phase.") and s.endswith(".fold"):
        return {"kind": "phase_fold",
                "phase": s.split(".")[1] if "." in s else "",
                "ts": e.get("ts")}
    return {"kind": "other", "ep": s, "ts": e.get("ts")}


def _join_data_flow(
    nodes: list[dict[str, Any]],
    effects_by_node: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    """For each node, find downstream nodes whose input_keys overlap with
    this node's outputs keys. Output is a mapping from node_id -> list of
    downstream node_ids.
    """
    out: dict[str, list[str]] = {n["node_id"]: [] for n in nodes}
    for src in nodes:
        src_outputs = set((src.get("outputs") or {}).keys())
        src_outputs.discard("_ts_in")
        src_outputs.discard("_ts_out")
        if not src_outputs:
            continue
        for dst in nodes:
            if dst["node_id"] == src["node_id"]:
                continue
            dst_inputs = set(dst.get("input_keys") or [])
            if dst_inputs & src_outputs:
                out[src["node_id"]].append(dst["node_id"])
    return out


def _extract_llm_prompts(events: list[SpineRow]) -> list[dict[str, Any]]:
    """Pull llm.request.header payloads so an agent can read the prompt."""
    out: list[dict[str, Any]] = []
    for e in events:
        if e.get("execution_point") != "llm.request.header":
            continue
        p = e.get("payload") or {}
        out.append({
            "step_id": p.get("step_id"),
            "reason": p.get("reason"),
            "messages": p.get("messages") or [],
            "tools": p.get("tools") or [],
            "system": p.get("system"),
            "ts": e.get("ts"),
        })
    return out


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
    rows.sort(key=lambda r: (r["seq"] or 0, str(r["when"] or "")))
    return {
        "layer": "events",
        "run_id": events[0].get("run_id") if events else None,
        "rows": rows,
        "rows_present": bool(rows),
        "hint": (
            "next_layer=graph for skeleton view, or filter --domain <name>"
            if rows
            else "next_layer=summary to confirm the run reached the spine"
        ),
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
    """Root-cause narrative grounded in actual evidence.

    Walks the spine for:
    1. node-level failures (phase_graph.node.end with outcome=fail)
    2. reducer teardown sequence (apply_error -> apply_stop ->
       apply_terminal_outcome) when no node failed but the run still
       terminated as failure (C12 normal teardown path)
    3. llm.request.header to surface the prompt when an LLM call's
       outcome is error (rare; most LLM failures arrive via node outcome)

    The summary is concrete: it names the earliest failure signal and
    points the agent at the events layer for raw context.
    """
    def _is_fail(v: object) -> bool:
        return isinstance(v, str) and v.lower() in {"fail", "failed", "failure", "error"}

    def _ts(e: SpineRow) -> str:
        return str(e.get("ts") or e.get("when") or "")

    sorted_events = sorted(events, key=_ts)

    terminal = next(
        (e for e in sorted_events if e.get("execution_point") == "kernel.run.stop"),
        None,
    )
    terminal_failed = (
        terminal is not None
        and _is_fail((terminal.get("payload") or {}).get("outcome"))
    )

    node_failures = [
        e for e in sorted_events
        if e.get("execution_point") == "phase_graph.node.end"
        and _is_fail((e.get("payload") or {}).get("outcome"))
    ]

    if node_failures:
        first = node_failures[0]
        payload = first.get("payload") or {}
        return {
            "layer": "explain",
            "root_cause_present": True,
            "root_cause_kind": "node_failure",
            "first_failed": {
                "execution_point": first.get("execution_point"),
                "node_id": payload.get("node_id"),
                "ts": first.get("ts"),
                "outcome": payload.get("outcome"),
                "error": payload.get("error"),
            },
            "next_actions": [
                "next_layer=events to grep for this node_id and surrounding rows",
                "next_layer=graph to see effects attached to this node",
            ],
            "hint": "next_layer=events to grep for this node_id",
        }

    if terminal_failed:
        reducer_seq = [
            e for e in sorted_events
            if e.get("execution_point") == "runtime.reducer.apply"
        ]
        first_reducer = reducer_seq[0] if reducer_seq else None
        reducer_method = (
            (first_reducer.get("payload") or {}).get("method") if first_reducer else None
        )
        llm_errors = [
            e for e in sorted_events
            if str(e.get("execution_point") or "").startswith("llm.call.")
            and _is_fail((e.get("payload") or {}).get("outcome"))
        ]
        prompt_summary = _first_llm_prompt_summary(sorted_events)
        actions = [
            "next_layer=graph to inspect reducer_sequence + node effects",
            "next_layer=events to walk ts-ordered rows from kernel.run.start",
        ]
        if prompt_summary is not None:
            actions.insert(0, "next_layer=graph to read llm_prompts[0]")
        return {
            "layer": "explain",
            "root_cause_present": True,
            "root_cause_kind": "reducer_teardown",
            "summary": (
                f"run terminated as failure via reducer (first call: {reducer_method}). "
                f"No node-level failure found; cause lives in reducer preconditions "
                f"or upstream context."
            ),
            "reducer_method": reducer_method,
            "reducer_calls": [
                {
                    "method": (e.get("payload") or {}).get("method"),
                    "phase": (e.get("payload") or {}).get("phase"),
                    "outcome": (e.get("payload") or {}).get("outcome"),
                    "ts": e.get("ts"),
                }
                for e in reducer_seq
            ],
            "llm_errors": [
                {"ts": e.get("ts"), "outcome": (e.get("payload") or {}).get("outcome")}
                for e in llm_errors
            ],
            "first_prompt": prompt_summary,
            "terminal_outcome": (terminal.get("payload") or {}).get("outcome"),
            "next_actions": actions,
            "hint": actions[0],
        }

    return {
        "layer": "explain",
        "root_cause_present": False,
        "summary": "no failed nodes / lifecycle events in spine",
        "terminal_outcome": (
            (terminal.get("payload") or {}).get("outcome") if terminal else None
        ),
        "next_actions": ["next_layer=summary to confirm run reached terminal"],
        "hint": "next_layer=summary to confirm run reached terminal",
    }


def _first_llm_prompt_summary(events: list[SpineRow]) -> dict[str, Any] | None:
    for e in events:
        if e.get("execution_point") != "llm.request.header":
            continue
        p = e.get("payload") or {}
        msgs = p.get("messages") or []
        first_user = next(
            (m for m in msgs if (m or {}).get("role") == "user"), None
        )
        return {
            "step_id": p.get("step_id"),
            "reason": p.get("reason"),
            "user_message_preview": (
                str((first_user or {}).get("content") or "")[:160]
            ),
            "messages_count": len(msgs),
            "tools_count": len(p.get("tools") or []),
        }
    return None


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
            from lca.infrastructure.cli.commands._shared.projection import (
                spine_filename_for_run_cwd,
            )

            spine_path = spine_filename_for_run_cwd(run_id)
            if spine_path.exists():
                payload = {
                    "layer": layer,
                    "run_id": run_id,
                    "spine_empty": True,
                    "spine_path": str(spine_path),
                    "hint": (
                        "stop: spine file exists but contains no parseable "
                        "rows; check kernel logs for write errors"
                    ),
                }
            else:
                payload = {
                    "layer": layer,
                    "run_id": run_id,
                    "spine_missing": True,
                    "hint": _NEXT_HINT[layer].get(
                        "spine_missing", "stop: spine ledger not found"
                    ),
                }
            emit(output, payload, human_renderer=_human)
            raise typer.Exit(code=1)

        projection = _LAYER_DISPATCH[layer]
        payload = projection(events)
        if "hint" not in payload or not payload["hint"]:
            default_key = (
                "anomalies_present"
                if payload.get("anomalies_present") or payload.get("deviations_present")
                or payload.get("root_cause_present")
                else "no_anomalies"
            )
            payload["hint"] = _NEXT_HINT[layer].get(default_key, "")

        emit(output, payload, human_renderer=_human)


__all__ = ["register"]
