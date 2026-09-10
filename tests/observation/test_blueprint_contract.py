"""M1 — PlanBlueprint schema contract tests.

Pydantic frozen + extra="forbid" 硬约束(AGENTS.md C13)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    PlanBlueprint,
    PlanEdgeSpec,
    PlanNodeSpec,
)


def test_plan_node_spec_defaults() -> None:
    n = PlanNodeSpec(id="perceive.main", phase="perceive")
    assert n.max_visits == 8
    assert n.entry is False
    assert n.binding is None
    assert n.sub_spec_ref is None


def test_plan_edge_spec_uses_alias() -> None:
    e = PlanEdgeSpec(**{"from": "perceive.main", "to": "think.main"})
    assert e.from_node == "perceive.main"
    assert e.to_node == "think.main"


def test_plan_edge_spec_priority_default() -> None:
    e = PlanEdgeSpec(**{"from": "a", "to": "b"})
    assert e.priority == 0
    assert e.when == "true"


def test_plan_blueprint_round_trip() -> None:
    bp = PlanBlueprint(
        plan_ref="abc",
        profile_path="p",
        plan_version="v1",
        revision="r1",
        nodes=(PlanNodeSpec(id="perceive.main", phase="perceive"),),
        edges=(PlanEdgeSpec(**{"from": "perceive.main", "to": "think.main"}),),
        actions_authorized=("use_TOOL",),
        compiled_at="t",
    )
    data = bp.model_dump(mode="json")
    bp2 = PlanBlueprint.model_validate(data)
    assert bp2.plan_ref == "abc"
    assert bp2.actions_authorized == ("use_TOOL",)


def test_plan_blueprint_frozen() -> None:
    bp = PlanBlueprint(
        plan_ref="x",
        profile_path="p",
        plan_version="v",
        revision="r",
        nodes=(),
        edges=(),
        compiled_at="t",
    )
    with pytest.raises(ValidationError):
        bp.plan_ref = "mutated"  # type: ignore[misc]


def test_plan_blueprint_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        PlanBlueprint(
            plan_ref="x",
            profile_path="p",
            plan_version="v",
            revision="r",
            nodes=(),
            edges=(),
            compiled_at="t",
            unknown_field="nope",  # type: ignore[call-arg]
        )
