"""CapabilityPlan 数据契约与稳定访问器。

CapabilityPlan 是 CompiledRunPlan 的 Capability 子计划，记录 Profile 派生的
provider binding 与插件关系。未类型化的 Profile 元数据必须由 harness/profile
解码；本模块只保留跨层不可变契约、稳定摘要和只读访问器。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.relation import Relation, parse_relation
from lca.contracts.protocols.relation import TypedRelation


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """capability key 到 owner plugin 的不可变绑定契约。

    ``resolution_key``、``required_in_production``、``fallback_policy``、
    ``owner_kind``、``scope`` 与 ``provenance`` 共同描述运行闭合、运行时
    接缝、所有权、可见范围和可追溯来源。
    """

    capability: str
    owner_plugin: str
    resolution_key: str = ""
    effect_class: str = "none"
    revision: str = ""
    required_in_production: bool = False
    fallback_policy: str = "production"
    owner_kind: str = "unique"
    scope: str = "run"
    provenance: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.capability, str) or not self.capability:
            raise ValueError(
                f"ProviderBinding.capability must be non-empty str, got {self.capability!r}"
            )
        if not isinstance(self.owner_plugin, str) or not self.owner_plugin:
            raise ValueError(
                f"ProviderBinding.owner_plugin must be non-empty str, got {self.owner_plugin!r}"
            )
        if not isinstance(self.resolution_key, str):
            raise ValueError(
                f"ProviderBinding.resolution_key must be a string, got {self.resolution_key!r}"
            )
        if not self.resolution_key:
            object.__setattr__(self, "resolution_key", self.capability)
        if not isinstance(self.fallback_policy, str) or not self.fallback_policy:
            raise ValueError("ProviderBinding.fallback_policy must be a non-empty string")
        if self.owner_kind not in {"unique", "contributor", "replica"}:
            raise ValueError(
                "ProviderBinding.owner_kind must be one of "
                f"'unique' / 'contributor' / 'replica', got {self.owner_kind!r}"
            )


@dataclass(frozen=True, slots=True)
class CapabilityPlan:
    """Profile 编译出的能力绑定与关系数据契约。"""

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


def _provider_binding_payload(binding: ProviderBinding) -> dict[str, str | bool]:
    """Project a binding's full, hash-relevant semantics."""
    return {
        "capability": binding.capability,
        "owner_plugin": binding.owner_plugin,
        "resolution_key": binding.resolution_key,
        "effect_class": binding.effect_class,
        "revision": binding.revision,
        "required_in_production": binding.required_in_production,
        "fallback_policy": binding.fallback_policy,
        "owner_kind": binding.owner_kind,
        "scope": binding.scope,
        "provenance": binding.provenance,
    }


def capability_plan_hash(plan: CapabilityPlan) -> str:
    """Return the order-independent stable identity of a capability plan."""
    sorted_bindings = sorted(
        plan.provider_bindings,
        key=lambda binding: (
            binding.capability,
            binding.owner_plugin,
            binding.resolution_key,
            binding.effect_class,
            binding.revision,
            binding.required_in_production,
            binding.fallback_policy,
            binding.owner_kind,
            binding.scope,
            binding.provenance,
        ),
    )
    sorted_relations = sorted(
        plan.relations,
        key=lambda relation: (relation.source, relation.target, relation.kind.value),
    )
    payload = {
        "profile_path": plan.profile_path,
        "revision": plan.revision,
        "provider_bindings": [_provider_binding_payload(binding) for binding in sorted_bindings],
        "relations": [
            {
                "source": relation.source,
                "target": relation.target,
                "kind": relation.kind.value,
                "evidence": sorted(relation.evidence),
                "scope": relation.scope.value if relation.scope is not None else None,
                "weight": relation.weight,
            }
            for relation in sorted_relations
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def relations_of_kind(plan: CapabilityPlan, kind: str | Relation) -> tuple[TypedRelation, ...]:
    """Return all relations of the requested kind."""
    target_kind = parse_relation(kind)
    return tuple(relation for relation in plan.relations if relation.kind is target_kind)


def relations_from_plugin(plan: CapabilityPlan, plugin_id: str) -> tuple[TypedRelation, ...]:
    """Return all relations sourced by a plugin."""
    return tuple(relation for relation in plan.relations if relation.source == plugin_id)


def relations_to_plugin(plan: CapabilityPlan, plugin_id: str) -> tuple[TypedRelation, ...]:
    """Return all relations targeting a plugin."""
    return tuple(relation for relation in plan.relations if relation.target == plugin_id)


def capability_plan_to_dict(plan: CapabilityPlan) -> dict[str, Any]:
    """Project a capability plan to a JSON-friendly mapping."""
    return {
        "profile_path": plan.profile_path,
        "revision": plan.revision,
        "plan_hash": capability_plan_hash(plan),
        "provider_bindings": [
            _provider_binding_payload(binding) for binding in plan.provider_bindings
        ],
        "relations": [
            {
                "source": relation.source,
                "target": relation.target,
                "kind": relation.kind.value,
                "evidence": list(relation.evidence),
                "scope": relation.scope.value if relation.scope is not None else None,
                "weight": relation.weight,
            }
            for relation in plan.relations
        ],
    }


__all__ = [
    "CapabilityPlan",
    "ProviderBinding",
    "capability_plan_hash",
    "capability_plan_to_dict",
    "relations_from_plugin",
    "relations_of_kind",
    "relations_to_plugin",
]
