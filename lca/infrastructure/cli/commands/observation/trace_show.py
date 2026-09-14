"""lca-ops observation trace-show —— 查看 run 的 observation + graph facts。

输入:run_id
过滤:--node <id> / --kind <payload.kind> / --seq <n> / --filter <ep 子串>
输出:默认 --json(agent 直接消费,全量 payload);--human 走 graph_timeline 紧凑投影。

``--json`` 是 agent 路径,因此它必须给出未经截断的 ``inputs`` / ``outputs``;
``--human`` 是人路径,只给端口名与计时。两个受众共用
:mod:`lca.infrastructure.observability.graph_timeline` 的同一条投影规则,
与 live console sink 输出的行字节一致。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.observability.graph_timeline import is_graph_event, render_record


def register(app: typer.Typer) -> None:
    @app.command(
        name="trace-show",
        help="Show observation facts —— 节点 / 决策 / 控制 / 工具 / LLM / reducer 全量。",
    )
    def trace_show_cmd(
        run_id: str = typer.Argument(..., help="run_id (例: run_xxx)"),
        node: str = typer.Option("", "--node", help="只看指定 node_id 的 facts"),
        kind: str = typer.Option("", "--kind", help="按 payload.kind 精确过滤,例:--kind visit_end"),
        seq: str = typer.Option("", "--seq", help="只看 event_id 尾部序号等于该值的 fact"),
        filter_ep: str = typer.Option(
            "", "--filter", help="execution_point 子串匹配,例:--filter phase_graph.subgraph"
        ),
        full: bool = typer.Option(
            False, "--full", help="--human 模式下附带该条 fact 的完整 payload"
        ),
        json_mode: bool = typer.Option(True, "--json/--human", help="默认 --json"),
    ) -> None:
        spine_path = _spine_path(run_id)
        if not spine_path.exists():
            typer.echo(f"no spine file at {spine_path}", err=True)
            raise typer.Exit(code=1)

        facts = _load_facts(run_id)
        if node:
            facts = [f for f in facts if _payload_of(f).get("node_id") == node]
        if kind:
            facts = [f for f in facts if _payload_of(f).get("kind") == kind]
        if seq:
            facts = [f for f in facts if _seq_of(f) == seq]
        if filter_ep:
            facts = [f for f in facts if filter_ep in _ep_of(f)]

        if json_mode:
            typer.echo(json.dumps(facts, ensure_ascii=False, indent=2))
        else:
            _render_trace_human(facts, full=full)


def _spine_path(run_id: str) -> Path:
    return Path("traces/runs") / run_id / f"{run_id}.spine.jsonl"


def _ep_of(record: dict[str, Any]) -> str:
    return str(record.get("execution_point") or record.get("event_type") or "")


def _payload_of(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _seq_of(record: dict[str, Any]) -> str:
    """Trailing sequence of ``event_id``, which the spine writes as ``<run_id>:<seq>``."""
    event_id = str(record.get("event_id") or "")
    return event_id.rsplit(":", 1)[-1] if ":" in event_id else ""


def _load_facts(run_id: str) -> list[dict[str, Any]]:
    """从 trace spine SSOT 读 observation.* / diagnosis.* / phase_graph.* facts。"""
    spine_path = _spine_path(run_id)
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
        if not isinstance(obj, dict):
            continue
        ep = _ep_of(obj)
        if ep.startswith("observation.") or ep.startswith("diagnosis.") or is_graph_event(ep):
            out.append(obj)
    return out


def _render_trace_human(facts: list[dict[str, Any]], *, full: bool = False) -> None:
    if not facts:
        typer.echo("(no facts match filter)")
        return
    for f in facts:
        ep = _ep_of(f)
        if is_graph_event(ep):
            typer.echo(f"  {render_record(f)}")
        else:
            payload = _payload_of(f)
            node_id = (
                payload.get("node_id")
                or payload.get("source_node_id")
                or payload.get("owner_node_id")
                or "-"
            )
            typer.echo(f"  {ep:48s}  node={node_id}")
        if full:
            typer.echo(" " * 2 + json.dumps(_payload_of(f), ensure_ascii=False, sort_keys=True))


__all__ = ["register"]
