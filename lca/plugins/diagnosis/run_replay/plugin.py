"""diagnosis.run_replay —— 时间序 replay(纯函数)。

module M9: lca/contracts/observability/observation/m9_replay/

设计模式: 纯函数 fold —— 把所有 trajectory facts 按 node_id 折叠成
ReplayStep 数组,补上 missing / unexpected 节点。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import (
    ControlTrace,
    DecisionTrace,
    LLMCallTrace,
    PlanBlueprint,
    ReplayDiffSummary,
    ReplayStep,
    RunReplay,
    ToolCallTrace,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_REPLAY = "diagnosis.run_replay"
_OBSERVER_ACTOR = "diagnosis"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_run_replay(
    *,
    run_id: str,
    blueprint: PlanBlueprint,
    node_enters: Iterable[Any],
    node_exits: Iterable[Any],
    decision_traces: Iterable[DecisionTrace],
    control_traces: Iterable[ControlTrace],
    tool_calls: Iterable[ToolCallTrace],
    llm_calls: Iterable[LLMCallTrace],
) -> RunReplay:
    """Pure fold —— 把所有 facts 按 node_id 折叠成 steps。"""
    exits_list = list(node_exits)
    enters_list = list(node_enters)
    dec_list = list(decision_traces)
    ctrl_list = list(control_traces)
    tool_list = list(tool_calls)
    llm_list = list(llm_calls)

    def _attr(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    entered_map = {_attr(e, "node_id"): e for e in enters_list}
    exit_map = {_attr(x, "node_id"): x for x in exits_list}

    visited: list[str] = []
    missing: list[str] = []
    first_failure: str | None = None
    steps: list[ReplayStep] = []
    step_no = 0

    for node in blueprint.nodes:
        step_no += 1
        enter = entered_map.get(node.id)
        exit = exit_map.get(node.id)
        if exit is None and enter is None:
            missing.append(node.id)
            steps.append(
                ReplayStep(
                    step=step_no,
                    node_id=node.id,
                    phase=node.phase,
                    binding=node.binding,
                    status="missing",
                    anomalies=("node never entered",),
                )
            )
            continue
        visited.append(node.id)
        outputs = _attr(exit, "outputs") if exit else {}
        outputs_dict = (
            outputs
            if isinstance(outputs, dict)
            else (outputs.model_dump() if outputs is not None else {})
        )
        inputs = _attr(enter, "inputs") if enter else {}
        inputs_dict = (
            inputs
            if isinstance(inputs, dict)
            else (inputs.model_dump() if inputs is not None else {})
        )
        decision_obj = next(
            (d for d in dec_list if _attr(d, "source_node_id") == node.id),
            None,
        )
        ctrl_objs = [c.model_dump() for c in ctrl_list if _attr(c, "source_node_id") == node.id]
        tool_objs = [t.model_dump() for t in tool_list if _attr(t, "source_node_id") == node.id]
        llm_objs = [ll.model_dump() for ll in llm_list if _attr(ll, "source_node_id") == node.id]
        anomalies: list[str] = []
        if exit is not None and _attr(exit, "exit_status") == "error":
            anomalies.append("exit_status=error")
            if first_failure is None:
                first_failure = node.id
        if decision_obj is None and node.phase in ("think", "act"):
            anomalies.append(f"no decision for {node.phase} node")
            if first_failure is None:
                first_failure = node.id
        for c in ctrl_objs:
            if c.get("verdict") == "deny":
                anomalies.append(f"control {c.get('control_slot')} denied")
                if first_failure is None:
                    first_failure = node.id

        steps.append(
            ReplayStep(
                step=step_no,
                node_id=node.id,
                phase=node.phase,
                binding=node.binding,
                status="visited",
                entered_at=_attr(enter, "entered_at"),
                exited_at=_attr(exit, "exited_at") if exit else None,
                inputs=inputs_dict,
                outputs=outputs_dict,
                decision=decision_obj.model_dump() if decision_obj else None,
                control_verdicts=tuple(ctrl_objs),
                tool_calls=tuple(tool_objs),
                llm_calls=tuple(llm_objs),
                anomalies=tuple(anomalies),
            )
        )

    return RunReplay(
        run_id=run_id,
        plan_ref=blueprint.plan_ref,
        replay_steps=tuple(steps),
        diff_summary=ReplayDiffSummary(
            nodes_total=len(blueprint.nodes),
            nodes_visited=tuple(visited),
            nodes_missing=tuple(missing),
            first_failure_node=first_failure,
        ),
        replayed_at=_now_iso(),
    )


def observe_replay(
    *,
    run_id: str,
    blueprint: PlanBlueprint,
    node_enters: Iterable[Any],
    node_exits: Iterable[Any],
    decision_traces: Iterable[DecisionTrace],
    control_traces: Iterable[ControlTrace],
    tool_calls: Iterable[ToolCallTrace],
    llm_calls: Iterable[LLMCallTrace],
) -> RunReplay:
    """Caller-facing wrapper:计算 + emit。"""
    replay = build_run_replay(
        run_id=run_id,
        blueprint=blueprint,
        node_enters=node_enters,
        node_exits=node_exits,
        decision_traces=decision_traces,
        control_traces=control_traces,
        tool_calls=tool_calls,
        llm_calls=llm_calls,
    )
    append_surface_bound(
        _EV_REPLAY,
        replay.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )
    return replay


@plugin(
    id="diagnosis.run_replay",
    provides=("diagnosis.replay",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Run replay —— pure fold facts → RunReplay; agent 可按步 walk.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("diagnosis.replay", observe_replay)


__all__ = ["build_run_replay", "observe_replay", "setup"]
