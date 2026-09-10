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
    ) -> None:
        facts = _load_facts(run_id)
        if not facts:
            typer.echo(f"no facts for run_id={run_id}", err=True)
            raise typer.Exit(code=1)

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
        typer.echo(
            f"  [{marker}] step={step.step:2d} {step.node_id or '-':30s} "
            f"phase={step.phase or '-':10s} anomalies={list(step.anomalies)}"
        )


__all__ = ["register"]
