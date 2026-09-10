"""lca-ops observation plan-show —— 打印 plan 蓝图。

输入:profile 路径或 plan_ref hash。
当前实现:从 ``traces/runs/<run_id>/blueprint.json`` 读(observation.lifecycle
.plan_compile 落盘);profile 路径 → latest run 使用此 profile 的 PlanBlueprint。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer


def register(app: typer.Typer) -> None:
    @app.command(
        name="plan-show",
        help="Show PlanBlueprint —— plan 应该长什么样的 SSOT 表达。",
    )
    def plan_show_cmd(
        ref: str = typer.Argument(
            ...,
            help="profile 路径 (profiles/xxx.yaml) 或 plan_ref hash。",
        ),
        json_mode: bool = typer.Option(True, "--json/--human", help="默认 --json"),
    ) -> None:
        from lca.infrastructure.cli.commands.kernel._shared import (
            find_latest_run_id,
        )

        plan: dict[str, Any] | None = None
        run_dir = Path("traces/runs") / find_latest_run_id()
        bp_path = run_dir / "blueprint.json"
        if bp_path.exists():
            plan = json.loads(bp_path.read_text(encoding="utf-8"))

        if plan is None:
            typer.echo(
                f"no blueprint found. ref={ref}; run_dir={run_dir}",
                err=True,
            )
            raise typer.Exit(code=1)

        if json_mode:
            typer.echo(json.dumps(plan, ensure_ascii=False, indent=2))
        else:
            _render_plan_human(plan)


def _render_plan_human(plan: dict[str, Any]) -> None:
    typer.echo(f"plan_ref     : {plan.get('plan_ref')}")
    typer.echo(f"profile_path : {plan.get('profile_path')}")
    typer.echo(f"plan_version : {plan.get('plan_version')}")
    typer.echo(f"revision     : {plan.get('revision')}")
    typer.echo(f"nodes ({len(plan.get('nodes', []))}):")
    for n in plan.get("nodes", []):
        typer.echo(f"  - {n.get('id'):30s} phase={n.get('phase'):10s} binding={n.get('binding')}")
    typer.echo(f"edges ({len(plan.get('edges', []))}):")
    for e in plan.get("edges", []):
        typer.echo(f"  - {e.get('from')} → {e.get('to')}")
    typer.echo(f"actions_authorized: {', '.join(plan.get('actions_authorized', []))}")


__all__ = ["register"]
