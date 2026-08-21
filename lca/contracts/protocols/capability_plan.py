"""CapabilityPlan 数据契约（ADR-0068 §一 + ADR-0074 PR-2.5）。

CapabilityPlan 是 CompiledRunPlan 三子 plan 之一（其他两个：
ControlPlan + ScopePlan，PR-3 落地），本 PR-2.5 只交付数据面 + Resolve
解析；runtime 编译留 PR-3 PlanCompiler。

CapabilityPlan 字段：

- ``profile_path`` — 来源 profile 路径（与 ControlPlan 一致）
- ``provider_bindings`` — capability key → owner plugin id（ADR-0061
  已实现；本字段镜像现有 ``ResolvedProfile.dag_edges``）
- ``relations`` — 11 关系代数 typed 列表（ADR-0069 §三）
- ``revision`` — ``CapabilityPlan`` 版本字符串（用于 plan_ref 绑定）

PR-2.5 阶段：Resolve 输出 ``CapabilityPlan``，含 provider_bindings
（5 老关系 derived from ``provides`` / ``requires``） + 用户在
plugin ``meta.relations:`` 段声明的 11 关系；runtime 不消费
（PR-3 PlanCompiler 才把 CapabilityPlan 编译为 CompiledRunPlan）。

ADR-0015 contracts 纯类型契约：``CapabilityPlan`` 不放方法，访问器
module-level 函数（``capability_plan_to_dict`` /
``capability_plan_hash`` / ``relations_of_kind`` /
``relations_from_plugin`` / ``relations_to_plugin``）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.relation import Relation, parse_relation
from lca.contracts.protocols.relation import TypedRelation


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """capability key → owner plugin id + effect class。

    ADR-0061 capabilities DAG + ADR-0062 effect class 的合流表达。
    """

    capability: str
    owner_plugin: str
    effect_class: str = "none"
    revision: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.capability, str) or not self.capability:
            raise ValueError(
                f"ProviderBinding.capability must be non-empty str, got {self.capability!r}"
            )
        if not isinstance(self.owner_plugin, str) or not self.owner_plugin:
            raise ValueError(
                f"ProviderBinding.owner_plugin must be non-empty str, got {self.owner_plugin!r}"
            )


@dataclass(frozen=True, slots=True)
class CapabilityPlan:
    """CapabilityPlan 数据契约（ADR-0068 §一 + ADR-0074 PR-2.5）。

    5 老关系 (provides / requires / contributes_to / reads_fact /
    emits_fact) 由 ResolvedProfile 提供者关系自动派生；6 新关系
    (governs / executes / delegates / projects / revises / evaluates)
    由 plugin ``meta.relations:`` 显式声明；二者合并入
    ``CapabilityPlan.relations``。
    """

    profile_path: str
    provider_bindings: tuple[ProviderBinding, ...]
    relations: tuple[TypedRelation, ...]
    revision: str = "v1"

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("CapabilityPlan.profile_path must be non-empty")
        if not isinstance(self.provider_bindings, tuple):
            raise ValueError("CapabilityPlan.provider_bindings must be tuple")
        if not isinstance(self.relations, tuple):
            raise ValueError("CapabilityPlan.relations must be tuple")


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def capability_plan_hash(plan: CapabilityPlan) -> str:
    """CapabilityPlan 稳定摘要（PR-3 / PR-6 引用；PR-2.5 仅为诊断值）。

    同 profile + 同 bindings + 同 relations → 同 hash。bindings 与
    relations 都先按稳定 key 排序避免 dict 顺序敏感性。
    """
    sorted_bindings = sorted(
        plan.provider_bindings,
        key=lambda b: (b.capability, b.owner_plugin),
    )
    sorted_relations = sorted(
        plan.relations,
        key=lambda r: (r.source, r.target, r.kind.value),
    )
    payload = {
        "profile_path": plan.profile_path,
        "revision": plan.revision,
        "provider_bindings": [
            {
                "capability": b.capability,
                "owner_plugin": b.owner_plugin,
                "effect_class": b.effect_class,
                "revision": b.revision,
            }
            for b in sorted_bindings
        ],
        "relations": [
            {
                "source": r.source,
                "target": r.target,
                "kind": r.kind.value,
                "evidence": sorted(r.evidence),
                "scope": r.scope.value if r.scope is not None else None,
                "weight": r.weight,
            }
            for r in sorted_relations
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def relations_of_kind(plan: CapabilityPlan, kind: str | Relation) -> tuple[TypedRelation, ...]:
    """按关系类型查询；未命中返回空元组。"""
    target_kind = parse_relation(kind)
    return tuple(r for r in plan.relations if r.kind is target_kind)


def relations_from_plugin(plan: CapabilityPlan, plugin_id: str) -> tuple[TypedRelation, ...]:
    """从某个 plugin 出发的全部关系。"""
    return tuple(r for r in plan.relations if r.source == plugin_id)


def relations_to_plugin(plan: CapabilityPlan, plugin_id: str) -> tuple[TypedRelation, ...]:
    """进入某个 plugin 的全部关系。"""
    return tuple(r for r in plan.relations if r.target == plugin_id)


def capability_plan_to_dict(plan: CapabilityPlan) -> dict[str, Any]:
    """JSON 友好字典。"""
    return {
        "profile_path": plan.profile_path,
        "revision": plan.revision,
        "plan_hash": capability_plan_hash(plan),
        "provider_bindings": [
            {
                "capability": b.capability,
                "owner_plugin": b.owner_plugin,
                "effect_class": b.effect_class,
                "revision": b.revision,
            }
            for b in plan.provider_bindings
        ],
        "relations": [
            {
                "source": r.source,
                "target": r.target,
                "kind": r.kind.value,
                "evidence": list(r.evidence),
                "scope": r.scope.value if r.scope is not None else None,
                "weight": r.weight,
            }
            for r in plan.relations
        ],
    }


def provider_bindings_from_iter(
    values: Iterable[Any],
) -> tuple[ProviderBinding, ...]:
    """从 raw 列表构造 ``tuple[ProviderBinding, ...]``，每条 raw 校验。

    接受 dict / ProviderBinding 两种输入。dict 缺字段或字段非法 →
    ``ValueError``。
    """
    out: list[ProviderBinding] = []
    for idx, raw in enumerate(values):
        if isinstance(raw, ProviderBinding):
            out.append(raw)
            continue
        if not isinstance(raw, dict):
            raise ValueError(
                f"binding[{idx}] must be dict or ProviderBinding, got {type(raw).__name__}"
            )
        if "capability" not in raw or "owner_plugin" not in raw:
            raise ValueError(
                f"binding[{idx}] missing required field (need capability / owner_plugin)"
            )
        out.append(
            ProviderBinding(
                capability=str(raw["capability"]),
                owner_plugin=str(raw["owner_plugin"]),
                effect_class=str(raw.get("effect_class", "none")),
                revision=str(raw.get("revision", "")),
            )
        )
    return tuple(out)


__all__ = [
    "CapabilityPlan",
    "ProviderBinding",
    "capability_plan_hash",
    "capability_plan_to_dict",
    "provider_bindings_from_iter",
    "relations_from_plugin",
    "relations_of_kind",
    "relations_to_plugin",
]
