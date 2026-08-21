"""ScopePlan 数据契约（ADR-0068 §一 + ADR-0074 PR-3 + tracker §三裁剪）。

ScopePlan 是 CompiledRunPlan 三子 plan 之一（其他两个：CapabilityPlan +
ControlPlan）。本 PR-3 阶段是**最小版**（tracker §三裁剪）：

- ``lifecycle`` — process / profile / agent / run / turn / invocation /
  experiment / device 8 项 scope（ADR-0074 §三压缩；见 ``lca.contracts.atoms.scope.Scope``）
- ``visibility`` — plan-level visibility 集合（哪个 scope 能看见该 plan）
- ``acl`` — grant / capability ceiling 集合（capability 衰减，V8 单调）
- ``budget_ceiling`` — token / time / tool_calls / cost 上限（拒绝任何插件
  超过）

**未实现**：SpacetimeContext 5 子空间（tracker §三裁剪推迟）。plan 阶段
只需最小版：lifecycle + visibility + ACL + budget ceiling。TemporalContext
/ IdentitySpace / VisibilitySpace 子空间待 owner 协调规则明文化后
实现。

ADR-0015 contracts 纯类型契约：``ScopePlan`` 不放方法，访问器
module-level 函数（``scope_plan_hash`` / ``scope_plan_to_dict``）。

全局不变量（ADR-0069 §三 + V8）：

1. authority 仅可向子 scope 衰减（grant ⊆ 父代理）
2. 子代理 grant ⊆ 父代理（capability 单调）
3. budget_ceiling 不可被 plugin 修改（only top-down）
4. visibility 默认 = 所有 scope；用户可收紧
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.scope import Scope, parse_scope


@dataclass(frozen=True, slots=True)
class BudgetCeiling:
    """Plan 级预算上限（PR-3 最小版）。

    任意字段 ``None`` = 不限制该维度。``max_cost_cents`` / ``max_tokens``
    / ``max_wall_clock_seconds`` / ``max_tool_calls`` / ``max_steps``
    都是软上限：plugin 超过时由 ``act.budget`` slot verdict 拒绝
    （PR-4 落地后）。
    """

    max_tokens: int | None = None
    max_wall_clock_seconds: int | None = None
    max_tool_calls: int | None = None
    max_steps: int | None = None
    max_cost_cents: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("max_tokens", self.max_tokens),
            ("max_wall_clock_seconds", self.max_wall_clock_seconds),
            ("max_tool_calls", self.max_tool_calls),
            ("max_steps", self.max_steps),
            ("max_cost_cents", self.max_cost_cents),
        ):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(
                    f"BudgetCeiling.{name} must be non-negative int or None, got {value!r}"
                )


@dataclass(frozen=True, slots=True)
class ScopePlan:
    """ScopePlan 数据契约（ADR-0068 §一 + ADR-0074 PR-3 最小版）。

    字段：

    - ``profile_path`` — 来源 profile 路径
    - ``lifecycle`` — plan 生命周期 scope（agent / run / turn 等）
    - ``visibility`` — 可见性 scope 集合（默认 = 所有 scope）
    - ``acl_grants`` — capability grant ceiling（V8 单调：子代理 grant ⊆ 父代理）
    - ``budget_ceiling`` — 预算上限
    - ``revision`` — ScopePlan 版本字符串
    """

    profile_path: str
    lifecycle: Scope
    visibility: tuple[Scope, ...]
    acl_grants: tuple[str, ...]
    budget_ceiling: BudgetCeiling
    revision: str = "v1"

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("ScopePlan.profile_path must be non-empty")
        if not isinstance(self.lifecycle, Scope):
            object.__setattr__(self, "lifecycle", parse_scope(self.lifecycle))
        if not isinstance(self.visibility, tuple):
            object.__setattr__(self, "visibility", tuple(self.visibility))
        if not isinstance(self.acl_grants, tuple):
            object.__setattr__(self, "acl_grants", tuple(self.acl_grants))
        # visibility 归一化：去重 + 按 Scope 枚举顺序
        unique_visibility = sorted(
            {parse_scope(v) if not isinstance(v, Scope) else v for v in self.visibility},
            key=lambda s: list(Scope).index(s),
        )
        object.__setattr__(self, "visibility", tuple(unique_visibility))


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def scope_plan_hash(plan: ScopePlan) -> str:
    """ScopePlan 稳定摘要（PR-3 / PR-6 引用；PR-3 仅为诊断值）。

    跨运行 stable。visibility / acl_grants 都先按稳定顺序排序。
    """
    payload = {
        "profile_path": plan.profile_path,
        "lifecycle": plan.lifecycle.value,
        "visibility": [s.value for s in plan.visibility],
        "acl_grants": sorted(plan.acl_grants),
        "budget_ceiling": {
            "max_tokens": plan.budget_ceiling.max_tokens,
            "max_wall_clock_seconds": plan.budget_ceiling.max_wall_clock_seconds,
            "max_tool_calls": plan.budget_ceiling.max_tool_calls,
            "max_steps": plan.budget_ceiling.max_steps,
            "max_cost_cents": plan.budget_ceiling.max_cost_cents,
        },
        "revision": plan.revision,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def scope_plan_to_dict(plan: ScopePlan) -> dict[str, Any]:
    """JSON 友好字典。"""
    return {
        "profile_path": plan.profile_path,
        "lifecycle": plan.lifecycle.value,
        "visibility": [s.value for s in plan.visibility],
        "acl_grants": list(plan.acl_grants),
        "budget_ceiling": {
            "max_tokens": plan.budget_ceiling.max_tokens,
            "max_wall_clock_seconds": plan.budget_ceiling.max_wall_clock_seconds,
            "max_tool_calls": plan.budget_ceiling.max_tool_calls,
            "max_steps": plan.budget_ceiling.max_steps,
            "max_cost_cents": plan.budget_ceiling.max_cost_cents,
        },
        "revision": plan.revision,
        "plan_hash": scope_plan_hash(plan),
    }


def scope_plan_from_iter(
    lifecycle: str | Scope,
    visibility: Iterable[Any],
    acl_grants: Iterable[str],
    budget_ceiling: BudgetCeiling | dict[str, Any] | None,
    *,
    profile_path: str = "",
    revision: str = "v1",
) -> ScopePlan:
    """从 raw 列表构造 ``ScopePlan``，每个字段校验。

    接受 dict / BudgetCeiling 两种输入作为 budget_ceiling。
    """
    if isinstance(budget_ceiling, dict):
        budget_ceiling = BudgetCeiling(**budget_ceiling)
    elif budget_ceiling is None:
        budget_ceiling = BudgetCeiling()
    return ScopePlan(
        profile_path=profile_path,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        visibility=tuple(visibility),
        acl_grants=tuple(str(g) for g in acl_grants),
        budget_ceiling=budget_ceiling,
        revision=revision,
    )


__all__ = [
    "BudgetCeiling",
    "ScopePlan",
    "scope_plan_from_iter",
    "scope_plan_hash",
    "scope_plan_to_dict",
]
