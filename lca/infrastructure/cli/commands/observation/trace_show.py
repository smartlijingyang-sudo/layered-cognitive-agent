"""lca-ops observation trace-show —— 查看 run 的所有 observation facts。

输入:run_id
过滤:--node <id> / --filter kind=<kind>
输出:默认 --json,可用 --human 投影。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer


def register(app: typer.Typer) -> None:
    @app.command(
        name="trace-show",
        help="Show observation facts —— 节点 / 决策 / 控制 / 工具 / LLM / reducer 全量。",
    )
    def trace_show_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        node: str = typer.Option("", "--node", help="只看指定 node_id 的 facts"),
        filter_kind: str = typer.Option(
            "", "--filter", help="kind=<observation.kind>, e.g. kind=control"
        ),
        json_mode: bool = typer.Option(True, "--json/--human", help="默认 --json"),
    ) -> None:
        facts = _load_observation_facts(run_id)
        if node:
            facts = [f for f in facts if f.get("payload", {}).get("node_id") == node]
        if filter_kind:
            kind = filter_kind.replace("kind=", "")
            facts = [f for f in facts if kind in f.get("execution_point", "")]

        if json_mode:
            typer.echo(json.dumps(facts, ensure_ascii=False, indent=2))
        else:
            _render_trace_human(facts)


def _load_observation_facts(run_id: str) -> list[dict[str, Any]]:
    """从 trace spine SSOT 读 observation.* / diagnosis.* facts。"""
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
        ep = obj.get("execution_point") or obj.get("event_type", "")
        if ep.startswith("observation.") or ep.startswith("diagnosis."):
            out.append(obj)
    return out


def _render_trace_human(facts: list[dict[str, Any]]) -> None:
    if not facts:
        typer.echo("(no facts match filter)")
        return
    for f in facts:
        ep = f.get("execution_point") or f.get("event_type", "?")
        payload = f.get("payload", {})
        node_id = (
            payload.get("node_id")
            or payload.get("source_node_id")
            or payload.get("owner_node_id")
            or "-"
        )
        typer.echo(f"  {ep:48s}  node={node_id}")


__all__ = ["register"]
