"""M1 — Plan blueprint (期望 / compile-time).

Producer:  observation.lifecycle.plan_compile
Consumers: diagnosis.blueprint_trajectory_differ, lca-ops plan show
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanNodeSpec(BaseModel):
    """单节点蓝图:identity + phase + binding + 子图嵌套 + 边界条件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    phase: str
    binding: str | None = None
    sub_spec_ref: dict[str, Any] | None = None
    max_visits: int = 8
    entry: bool = False
    terminal: bool = False
    preconditions: tuple[str, ...] = ()
    terminal_predicates: tuple[str, ...] = ()


class PlanEdgeSpec(BaseModel):
    """单边蓝图:from → to,带 when 条件 DSL。"""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    when: str = "true"
    priority: int = 0


class PlanBlueprint(BaseModel):
    """完整图蓝图:节点表 + 边表 + 绑定 + 授权表 + profile 来源。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_ref: str
    profile_path: str
    plan_version: str
    revision: str
    nodes: tuple[PlanNodeSpec, ...]
    edges: tuple[PlanEdgeSpec, ...]
    actions_authorized: tuple[str, ...] = ()
    capabilities_granted: tuple[str, ...] = ()
    effect_policy: dict[str, Any] = Field(default_factory=dict)
    compiled_at: str


__all__ = ["PlanBlueprint", "PlanEdgeSpec", "PlanNodeSpec"]
