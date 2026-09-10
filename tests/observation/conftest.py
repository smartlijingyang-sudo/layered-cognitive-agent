"""observation tests 共享 fixture + factory。

设计原则: 工厂函数(fixture)统一一处,所有 test 引用,不重写。
命名按语义,不按 module 编号。
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest

from lca.contracts.observability.observation import (
    ControlTrace,
    DecisionTrace,
    NodeEnter,
    NodeExit,
    PlanBlueprint,
    PlanEdgeSpec,
    PlanNodeSpec,
)


def make_blueprint(
    *,
    node_ids: tuple[str, ...] = (
        "perceive.main",
        "think.main",
        "act.main",
    ),
    phases: tuple[str, ...] = ("perceive", "think", "act"),
    actions_authorized: tuple[str, ...] = ("use_TOOL",),
    bindings: tuple[str | None, ...] | None = None,
) -> PlanBlueprint:
    """Factory —— 测试按需构造蓝图,不重写样板。"""
    nodes: list[PlanNodeSpec] = []
    for i, nid in enumerate(node_ids):
        nodes.append(
            PlanNodeSpec(
                id=nid,
                phase=phases[i] if i < len(phases) else "perceive",
                binding=(bindings[i] if bindings and i < len(bindings) else None),
            )
        )
    edges: list[PlanEdgeSpec] = []
    for a, b in pairwise(node_ids):
        edges.append(PlanEdgeSpec(**{"from": a, "to": b}))
    return PlanBlueprint(
        plan_ref="plan-test",
        profile_path="profiles/web-standard.yaml",
        plan_version="v1",
        revision="r1",
        nodes=tuple(nodes),
        edges=tuple(edges),
        actions_authorized=actions_authorized,
        compiled_at="2026-09-10T00:00:00+00:00",
    )


def make_exit(
    node_id: str,
    phase: str,
    *,
    outputs: dict[str, Any] | None = None,
    exit_status: str = "success",
    elapsed_ms: int = 0,
) -> NodeExit:
    return NodeExit(
        run_id="run-test",
        node_id=node_id,
        phase=phase,
        exit_status=exit_status,
        elapsed_ms=elapsed_ms,
        outputs=outputs or {},
        exited_at="2026-09-10T00:00:00+00:00",
    )


def make_enter(
    node_id: str,
    phase: str,
    *,
    inputs: dict[str, Any] | None = None,
) -> NodeEnter:
    return NodeEnter(
        run_id="run-test",
        node_id=node_id,
        phase=phase,
        inputs=inputs or {},
        entered_at="2026-09-10T00:00:00+00:00",
    )


def make_control(
    source_node_id: str,
    *,
    verdict: str = "deny",
    control_slot: str = "act.authorize",
    reason: str | None = None,
    contract_clause: str | None = None,
) -> ControlTrace:
    return ControlTrace(
        run_id="run-test",
        source_node_id=source_node_id,
        control_slot=control_slot,
        verdict=verdict,
        reason=reason,
        contract_clause=contract_clause,
        occurred_at="2026-09-10T00:00:00+00:00",
    )


def make_decision(
    source_node_id: str,
    *,
    accepted: bool = True,
    action_type: str | None = None,
) -> DecisionTrace:
    return DecisionTrace(
        run_id="run-test",
        decision_id="d-test",
        source_node_id=source_node_id,
        accepted=accepted,
        action_type=action_type,
        occurred_at="2026-09-10T00:00:00+00:00",
    )


@pytest.fixture
def blueprint_three_phase() -> PlanBlueprint:
    return make_blueprint()


@pytest.fixture
def h6_exit_set() -> list[NodeExit]:
    """H6 fixture: perceive 完, act 被拒, think 从未进入。"""
    return [
        make_exit("perceive.main", "perceive"),
        make_exit("act.main", "act", outputs={"decision": None}),
    ]


@pytest.fixture
def h6_control_set() -> list[ControlTrace]:
    return [
        make_control(
            "act.main",
            verdict="deny",
            reason="action type is not authorized",
            contract_clause="art.action.action_type",
        )
    ]
