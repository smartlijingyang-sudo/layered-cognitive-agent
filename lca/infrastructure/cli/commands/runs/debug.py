"""``lca-ops runs debug`` —— 一次性诊断编排器。

按 layer 切分,默认 graph layer。agent 拿 JSON 输出含 ``next_layer_hint``,
告诉它下一步该看什么。

设计边界:
- 只读 spine + observation facts,纯观察面(AGENTS.md §2.3)。
- 每个 layer 是独立 projection 函数;orchestrator 只调度,不持有逻辑。
- 旧命令(``observation plan-show`` / ``trace-show`` / ``run-replay`` /
  ``run-explain`` / ``debug-graph``)完全保留;新命令是**增量入口**,非合并。
- PR-1 / Task 1.6: per-layer ad-hoc 判定被 ``fold_run_health`` 取代;
  每个 layer 在原有 raw 视图上挂一个 ``health_summary`` 字段,且
  ``anomalies_present`` / ``root_cause_present`` / hint 都从
  ``RunHealthReport.summary`` 派生。这恢复了 AGENTS.md §3 C13
  (information bloodline closure):所有 layer 共享一个 SSOT。
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
    spine_filename_for_run_cwd,
)
from lca.plugins.observability.health.run_health_fold import fold_run_health

_TRACES_ROOT_DEFAULT = Path("traces")

_LAYERS = ("summary", "graph", "events", "diff", "explain")
_DEFAULT_LAYER = "graph"

# agent-friendly default:JSON + graph layer
_DEFAULT_OUTPUT = OutputMode.JSON

# Per-layer next-step hint: tells an agent which layer to fetch next based on
# what this layer surfaced (e.g. anomaly found → explain).
_NEXT_HINT: dict[str, dict[str, str]] = {
    "summary": {
        "anomalies_present": "next_layer=explain to root-cause via RunHealthReport",
        "no_anomalies": "next_layer=events to inspect raw spine rows",
        "spine_missing": "stop: run never produced a spine; check runs create receipt",
    },
    "graph": {
        "anomalies_present": "next_layer=explain to root-cause the failed condition",
        "no_anomalies": "next_layer=summary for run-level counts",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "events": {
        "rows_present": "next_layer=graph for skeleton view, or filter --domain <name>",
        "rows_empty": "next_layer=summary to confirm the run reached the spine",
        "health_failed": "next_layer=explain to root-cause via RunHealthReport",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "diff": {
        "blueprint_missing": "next_layer=summary: plan not materialised; only execution trace available",
        "deviations_present": "next_layer=explain to root-cause unexpected nodes",
        "no_deviations": "next_layer=summary for run-level verdict",
        "health_failed": "next_layer=explain to root-cause via RunHealthReport",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
    "explain": {
        "root_cause_present": "next_layer=events to walk the offending step in raw form",
        "no_root_cause": "next_layer=summary for run-level counts",
        "spine_missing": "stop: spine ledger not found under traces/runs/",
    },
}


def _resolve_spine_path(events: list[SpineRow]) -> Path | None:
    """Resolve the spine file backing the loaded ``events``.

    Reads ``run_id`` from the first row and looks under the default
    traces root (``traces/runs/<run_id>/<run_id>.spine.jsonl``).
    Returns ``None`` if events is empty (the CLI surface already
    handles the "spine missing" branch before this helper fires).
    """
    if not events:
        return None
    run_id = events[0].get("run_id") or ""
    if not run_id:
        return None
    return spine_filename_for_run_cwd(run_id)


def _fold_health(events: list[SpineRow]):
    """Fold the run's spine once per layer invocation.

    Memoising across layers is the orchestrator's job; per-layer
    fold is cheap (8 derivers, sub-millisecond on a 1k-event spine).
    """
    spine_path = _resolve_spine_path(events)
    if spine_path is None or not spine_path.exists():
        # No spine file (events were loaded from a different path or
        # the producer never wrote one). Return a frozen empty
        # report so per-layer code can still access ``.summary``
        # without conditional checks.
        from lca.contracts.observability.health.report import (
            RunHealthReport,
            RunHealthSummary,
        )

        return RunHealthReport(
            schema_version="1.0",
            run_id="",
            generated_at=0.0,
            conditions=(),
            summary=RunHealthSummary(
                conditions_ok=0,
                conditions_degraded=0,
                conditions_failed=0,
                conditions_unknown=0,
                by_type={},
            ),
        )
    return fold_run_health(spine_path)


def _health_summary_block(health) -> dict[str, Any]:
    """Serialise ``report.summary`` + the overall worst status for JSON output."""
    overall = "ok"
    if health.summary.conditions_failed > 0:
        overall = "failed"
    elif health.summary.conditions_degraded > 0:
        overall = "degraded"
    elif health.summary.conditions_unknown > 0:
        overall = "unknown"
    return {
        "overall": overall,
        "by_type": dict(health.summary.by_type),
        "conditions_ok": health.summary.conditions_ok,
        "conditions_degraded": health.summary.conditions_degraded,
        "conditions_failed": health.summary.conditions_failed,
        "conditions_unknown": health.summary.conditions_unknown,
    }


def _layer_summary(events: list[SpineRow]) -> dict[str, Any]:
    """Run-level summary; verdict comes from ``RunHealthReport.summary``.

    Pre-PR-1 logic inspected ``kernel.run.stop.outcome`` for "fail"-ish
    strings only. PR-1 / Task 1.6: the verdict comes from
    ``report.summary.conditions_failed`` (failed > degraded > unknown
    > ok). The terminal outcome is still surfaced for human readers
    but no longer drives ``anomalies_present``.
    """
    counts = {d: len(filter_by_domain(events, d)) for d in ("llm", "tool", "graph", "phase")}
    lifecycle = next((e for e in events if e.get("execution_point") == "kernel.run.stop"), None)
    terminal = (lifecycle.get("payload") or {}).get("outcome") if lifecycle is not None else None
    health = _fold_health(events)
    health_summary = _health_summary_block(health)
    anomalies = health.summary.conditions_failed > 0 or health.summary.conditions_degraded > 0
    return {
        "layer": "summary",
        "run_id": events[0].get("run_id") if events else None,
        "total_events": len(events),
        "domain_counts": counts,
        "terminal_outcome": terminal,
        "anomalies_present": anomalies,
        "health_summary": health_summary,
        "hint": (
            _NEXT_HINT["summary"]["anomalies_present"] if anomalies
            else _NEXT_HINT["summary"]["no_anomalies"]
        ),
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

    health = _fold_health(events)
    health_summary = _health_summary_block(health)
    health_anomalies = (
        health.summary.conditions_failed > 0 or health.summary.conditions_degraded > 0
    )
    raw_anomalies = bool(report.get("anomalies"))

    report["layer"] = "graph"
    report["anomalies_present"] = raw_anomalies or health_anomalies
    report["edges"] = edges
    report["data_flow"] = [
        {"from": frm, "to": to} for frm, tos in flow_edges.items() for to in tos
    ]
    report["llm_prompts"] = llm_prompts
    report["health_summary"] = health_summary
    if health_anomalies and not raw_anomalies:
        # Health surfaced a condition the raw graph missed (B-1 case):
        # steer the agent toward ``explain`` instead of leaving a flat
        # "no_anomalies" verdict.
        report["hint"] = _NEXT_HINT["graph"]["anomalies_present"]
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
    """Raw spine rows + ``health_summary`` so agents can correlate."""
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
    health = _fold_health(events)
    health_summary = _health_summary_block(health)
    rows_present = bool(rows)
    health_failed = health.summary.conditions_failed > 0
    if health_failed:
        hint = _NEXT_HINT["events"]["health_failed"]
    elif rows_present:
        hint = _NEXT_HINT["events"]["rows_present"]
    else:
        hint = _NEXT_HINT["events"]["rows_empty"]
    return {
        "layer": "events",
        "run_id": events[0].get("run_id") if events else None,
        "rows": rows,
        "rows_present": rows_present,
        "health_summary": health_summary,
        "hint": hint,
    }


def _layer_diff(events: list[SpineRow]) -> dict[str, Any]:
    """PlanBlueprint vs executed nodes. Reads blueprint.json from run_dir."""
    import json

    run_id = events[0].get("run_id", "") if events else ""
    blueprint_path = _TRACES_ROOT_DEFAULT / "runs" / run_id / "blueprint.json"
    health = _fold_health(events)
    health_summary = _health_summary_block(health)
    health_failed = health.summary.conditions_failed > 0
    if not blueprint_path.exists():
        return {
            "layer": "diff",
            "blueprint_missing": True,
            "deviations_present": False,
            "health_summary": health_summary,
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
    deviations = bool(missing or unexpected)
    if health_failed:
        hint = _NEXT_HINT["diff"]["health_failed"]
    elif deviations:
        hint = _NEXT_HINT["diff"]["deviations_present"]
    else:
        hint = _NEXT_HINT["diff"]["no_deviations"]
    return {
        "layer": "diff",
        "blueprint_missing": False,
        "deviations_present": deviations,
        "missing_nodes": missing,
        "unexpected_nodes": unexpected,
        "health_summary": health_summary,
        "hint": hint,
    }


def _layer_explain(events: list[SpineRow]) -> dict[str, Any]:
    """Root-cause narrative grounded in ``RunHealthReport``.

    PR-1 / Task 1.6: the primary verdict comes from
    ``report.summary.conditions_failed`` (B-1 case: ``llm.status=failed``
    even when ``kernel.run.stop.outcome="success"`` and no node failed).
    We keep the legacy raw-walk as a *secondary* narrative for reducer
    teardown, but it is no longer the entry point for
    ``root_cause_present``.
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

    health = _fold_health(events)
    health_summary = _health_summary_block(health)
    failed_types = sorted(
        t for t, s in health.summary.by_type.items() if s == "failed"
    )
    degraded_types = sorted(
        t for t, s in health.summary.by_type.items() if s == "degraded"
    )

    if failed_types:
        first_ref = next(
            (ref for c in health.conditions if c.status == "failed" for ref in c.evidence_refs),
            None,
        )
        return {
            "layer": "explain",
            "root_cause_present": True,
            "root_cause_kind": "health_conditions_failed",
            "summary": (
                f"RunHealthReport reports failed conditions: "
                f"{', '.join(failed_types)}. See evidence_refs to jump to spine."
            ),
            "failed_types": failed_types,
            "degraded_types": degraded_types,
            "first_evidence": (
                {
                    "event_id": first_ref.event_id,
                    "execution_point": first_ref.execution_point,
                    "seq": first_ref.seq,
                }
                if first_ref is not None
                else None
            ),
            "health_summary": health_summary,
            "next_actions": [
                "next_layer=events to grep for the failed condition's evidence_refs[*].event_id",
                "next_layer=graph to see the spine topology around the failure",
            ],
            "hint": _NEXT_HINT["explain"]["root_cause_present"],
        }

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
            "health_summary": health_summary,
            "next_actions": [
                "next_layer=events to grep for this node_id and surrounding rows",
                "next_layer=graph to see effects attached to this node",
            ],
            "hint": _NEXT_HINT["explain"]["root_cause_present"],
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
            "health_summary": health_summary,
            "next_actions": actions,
            "hint": actions[0],
        }

    return {
        "layer": "explain",
        "root_cause_present": False,
        "summary": "no failed conditions; all derivers ok/unknown/degraded",
        "terminal_outcome": (
            (terminal.get("payload") or {}).get("outcome") if terminal else None
        ),
        "health_summary": health_summary,
        "next_actions": ["next_layer=summary to confirm run reached terminal"],
        "hint": _NEXT_HINT["explain"]["no_root_cause"],
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
