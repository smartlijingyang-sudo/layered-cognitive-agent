"""lca-ops observation run-explain —— 像人写的诊断报告。

输入:run_id
输出:FailureExplanation JSON / human。
错误优先结构:summary → root_cause_chain → graph_overview → next_actions。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer

from lca.contracts.observability.observation import (
    ControlTrace,
    DiffReport,
    FailureExplanation,
    NodeExit,
    PlanBlueprint,
)
from lca.plugins.diagnosis.failure_explainer.plugin import explain_failure

_LOG = logging.getLogger(__name__)


def register(app: typer.Typer) -> None:
    @app.command(
        name="run-explain",
        help="Run explanation —— 像人写的诊断:summary → root_cause → next_actions。",
    )
    def run_explain_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        json_mode: bool = typer.Option(True, "--json/--human", help="默认 --json"),
    ) -> None:
        facts = _load_facts(run_id)
        if not facts:
            typer.echo(f"no facts for run_id={run_id}", err=True)
            raise typer.Exit(code=1)

        blueprint = _find_blueprint(facts)
        diff, ctrl_traces = _build_diff_and_ctrl(facts, blueprint)
        explanation = explain_failure(run_id=run_id, diff=diff, control_traces=ctrl_traces)
        report = _compose_agent_report(explanation, diff, blueprint)

        if json_mode:
            typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _render_human(report)


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
        if (obj.get("execution_point") or "").startswith(("observation.", "diagnosis.")):
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


def _build_diff_and_ctrl(
    facts: list[dict[str, Any]], blueprint: PlanBlueprint | None
) -> tuple[DiffReport, list[ControlTrace]]:
    exits: list[NodeExit] = []
    ctrls: list[ControlTrace] = []
    for f in facts:
        ep = f.get("execution_point", "")
        if ep == "observation.node_exit":
            try:
                exits.append(NodeExit.model_validate(f["payload"]))
            except Exception as exc:
                _LOG.debug("malformed fact: %s", exc)
                continue
        elif ep == "observation.control":
            try:
                ctrls.append(ControlTrace.model_validate(f["payload"]))
            except Exception as exc:
                _LOG.debug("malformed fact: %s", exc)
                continue

    if blueprint is None:
        return DiffReport(run_id="", plan_ref="", diffed_at=""), ctrls

    from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
        diff_blueprint_trajectory,
    )

    diff = diff_blueprint_trajectory(
        run_id=blueprint.plan_ref, blueprint=blueprint, node_exits=exits
    )
    return diff, ctrls


def _compose_agent_report(
    explanation: FailureExplanation,
    diff: DiffReport,
    blueprint: PlanBlueprint | None,
) -> dict[str, Any]:
    next_actions: list[str] = [h.command for h in explanation.remediation_hints if h.command]
    if not next_actions and blueprint is not None:
        next_actions.append(f"lca-ops observation plan-show {blueprint.plan_ref}")

    return {
        "run_id": explanation.run_id,
        "outcome": explanation.outcome,
        "summary": explanation.summary,
        "root_cause_chain": [s.model_dump() for s in explanation.root_cause_chain],
        "graph_overview": (
            {
                "plan_ref": blueprint.plan_ref if blueprint else None,
                "nodes_total": len(blueprint.nodes) if blueprint else 0,
                "nodes_missing": [m.node_id for m in diff.missing_nodes],
                "first_failure_node": (
                    explanation.root_cause_chain[0].evidence_node_id
                    if explanation.root_cause_chain
                    else None
                ),
            }
            if blueprint is not None
            else None
        ),
        "next_actions": next_actions,
        "details_available": {
            "missing_nodes": len(diff.missing_nodes),
            "contract_violations": len(diff.contract_violations),
            "control_denies": sum(
                1 for c in explanation.root_cause_chain if "DENIED" in c.statement
            ),
        },
    }


def _render_human(report: dict[str, Any]) -> None:
    typer.echo(f"[outcome] {report['outcome']}")
    typer.echo(f"[summary] {report['summary']}")
    if report.get("root_cause_chain"):
        typer.echo("[root cause]")
        for s in report["root_cause_chain"]:
            typer.echo(f"  {s['step_index']}. {s['statement']}")
    if report.get("graph_overview"):
        ov = report["graph_overview"]
        typer.echo(
            f"[graph] plan_ref={ov.get('plan_ref')} nodes_total={ov.get('nodes_total')} "
            f"missing={ov.get('nodes_missing')}"
        )
    if report.get("next_actions"):
        typer.echo("[next actions]")
        for a in report["next_actions"]:
            typer.echo(f"  $ {a}")


__all__ = ["register"]
