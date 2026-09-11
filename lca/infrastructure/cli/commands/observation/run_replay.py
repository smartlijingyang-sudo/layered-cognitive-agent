"""lca-ops observation run-replay —— 时间序 replay steps,agent 可按步 walk。

输入:run_id
输出:RunReplay JSON / human,含每节点 inputs / outputs / decisions /
control / tool / llm / anomalies。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer

from lca.contracts.observability.observation import (
    ControlTrace,
    DecisionTrace,
    LLMCallTrace,
    PlanBlueprint,
    RunReplay,
    ToolCallTrace,
)
from lca.plugins.diagnosis.run_replay.plugin import build_run_replay

_LOG = logging.getLogger(__name__)


def register(app: typer.Typer) -> None:
    @app.command(
        name="run-replay",
        help="Run replay —— 按步 walk:node + inputs + outputs + decisions + 控制/工具/LLM.",
    )
    def run_replay_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        json_mode: bool = typer.Option(True, "--json/--human", help="默认 --json"),
        show_graph: bool = typer.Option(
            False, "--show-graph", help="Print phase_graph node/subgraph timeline from spine."
        ),
    ) -> None:
        facts = _load_facts(run_id)
        if not facts:
            typer.echo(f"no facts for run_id={run_id}", err=True)
            raise typer.Exit(code=1)

        if show_graph:
            _render_graph_timeline(facts)
            return

        blueprint = _find_blueprint(facts)
        if blueprint is None:
            typer.echo(f"no blueprint fact for run_id={run_id}", err=True)
            raise typer.Exit(code=1)

        replay = build_run_replay(
            run_id=run_id,
            blueprint=blueprint,
            node_enters=_collect(facts, "observation.node_enter"),
            node_exits=_collect(facts, "observation.node_exit"),
            decision_traces=_typed(facts, "observation.decision", DecisionTrace),
            control_traces=_typed(facts, "observation.control", ControlTrace),
            tool_calls=_typed(facts, "observation.tool_call", ToolCallTrace),
            llm_calls=_typed(facts, "observation.llm_call", LLMCallTrace),
        )

        if json_mode:
            typer.echo(json.dumps(replay.model_dump(), ensure_ascii=False, indent=2))
        else:
            _render_human(replay)


def _load_facts(run_id: str) -> list[dict[str, Any]]:
    spine_path = Path("traces/runs") / run_id / f"{run_id}.spine.jsonl"
    if not spine_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in spine_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = obj.get("execution_point") or ""
        if ep.startswith(("observation.", "diagnosis.", "phase_graph.")):
            out.append(obj)
    return out


def _find_blueprint(facts: list[dict[str, Any]]) -> PlanBlueprint | None:
    for f in facts:
        if (f.get("execution_point") or "") == "observation.plan_blueprint":
            try:
                return PlanBlueprint.model_validate(f["payload"])
            except Exception as exc:
                _LOG.debug("malformed fact: %s", exc)
                continue
    return None


def _collect(facts: list[dict[str, Any]], ep: str) -> list[Any]:
    return [f["payload"] for f in facts if (f.get("execution_point") or "") == ep]


def _typed(facts: list[dict[str, Any]], ep: str, model: type) -> list:
    out: list[Any] = []
    for f in facts:
        if (f.get("execution_point") or "") != ep:
            continue
        try:
            out.append(model.model_validate(f["payload"]))
        except Exception as exc:
            _LOG.debug("malformed fact: %s", exc)
            continue
    return out


def _render_graph_timeline(facts: list[dict[str, Any]]) -> None:
    """Print a timeline of phase_graph node and subgraph events from spine."""
    graph_events = [f for f in facts if (f.get("execution_point") or "").startswith("phase_graph.")]
    if not graph_events:
        typer.echo("no phase_graph events in spine")
        return
    typer.echo(f"[graph] {len(graph_events)} phase_graph events")
    for f in graph_events:
        ep = f.get("execution_point", "")
        payload = f.get("payload") or f.get("data") or {}
        if ep == "phase_graph.node.start":
            typer.echo(f"  ▶ node.start  node={payload.get('node_id', '?')}")
        elif ep == "phase_graph.node.end":
            outcome = payload.get("outcome", "?")
            marker = "✓" if outcome == "success" else "✗"
            error = payload.get("exception_message", "")
            line = f"  {marker} node.end    node={payload.get('node_id', '?')} outcome={outcome}"
            if error:
                line += f" error={error}"
            typer.echo(line)
        elif ep == "phase_graph.subgraph.enter":
            typer.echo(
                f"  ➤ subgraph.enter plan={payload.get('plan_ref', '?')} "
                f"entry={payload.get('entry_node', '?')} depth={payload.get('depth', 0)}"
            )
        elif ep == "phase_graph.subgraph.exit":
            outcome = payload.get("outcome", "?")
            typer.echo(
                f"  ◼ subgraph.exit  plan={payload.get('plan_ref', '?')} "
                f"outcome={outcome} depth={payload.get('depth', 0)}"
            )


def _render_human(replay: RunReplay) -> None:
    typer.echo(
        f"[replay] run_id={replay.run_id} plan_ref={replay.plan_ref} "
        f"steps={len(replay.replay_steps)}"
    )
    s = replay.diff_summary
    typer.echo(
        f"[summary] nodes_total={s.nodes_total} visited={len(s.nodes_visited)} "
        f"missing={len(s.nodes_missing)} first_failure={s.first_failure_node}"
    )
    for step in replay.replay_steps:
        marker = "✓" if step.status == "visited" else "✗"
        sub_graph = step.node_id or "-"
        # Show subgraph nesting when sub_graph_id is present in the payload
        anomalies = list(step.anomalies)
        typer.echo(
            f"  [{marker}] step={step.step:2d} {sub_graph:30s} "
            f"phase={step.phase or '-':10s} anomalies={anomalies}"
        )


__all__ = ["register"]
