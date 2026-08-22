"""统一的不可变 ``CompiledRunPlan``（ADR-0068 / ADR-0075）。

v2 在保留 capability、control 与 scope 子计划的同时，将 PluginSpec、phase graph、
phase binding、replacement、effect policy 与 validation report 纳入**同一**可哈希
计划。运行期不能修改计划；任何变更都必须重新编译为新的 plan_ref。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.capability_plan import CapabilityPlan, capability_plan_hash
from lca.contracts.protocols.control_plan import ControlPlan, compute_control_plan_hash
from lca.contracts.protocols.declarative_phase_graph import (
    DECLARATIVE_PLAN_VERSION,
    CapabilityBinding,
    CognitivePhaseGraphPlan,
    EffectPolicyPlan,
    PhaseBinding,
    PlanProvenance,
    PluginSpec,
    ReplacementDecision,
    ValidationReport,
    canonical_json,
    phase_graph_to_dict,
    plugin_spec_to_dict,
    validation_report_to_dict,
)
from lca.contracts.protocols.declarative_phase_graph import (
    ControlEntry as DeclarativeControlEntry,
)
from lca.contracts.protocols.scope_plan import ScopePlan, scope_plan_hash

# Schema version for CompiledRunPlan. v2 evolves v1; it is not a parallel plan.
COMPILED_RUN_PLAN_VERSION: str = DECLARATIVE_PLAN_VERSION


@dataclass(frozen=True, slots=True)
class CompiledRunPlan:
    """运行时唯一可读输入。

    ``capability`` / ``control`` / ``scope`` 保留为 ADR-0068 已落地的数据区域，
    ADR-0075 新区域和它们一起参与 canonical hash。``phase_graph`` 为 ``None``
    仅用于旧的直接构造测试；生产 ``compile_plan`` 必须提供完整声明式区域。
    """

    profile_path: str
    capability: CapabilityPlan
    control: ControlPlan
    scope: ScopePlan
    plan_version: str = COMPILED_RUN_PLAN_VERSION
    input_provenance: tuple[tuple[str, str], ...] = ()
    revision: str = "v1"
    plugin_specs: tuple[PluginSpec, ...] = ()
    capability_bindings: tuple[CapabilityBinding, ...] = ()
    phase_graph: CognitivePhaseGraphPlan | None = None
    phase_bindings: tuple[PhaseBinding, ...] = ()
    control_entries: tuple[DeclarativeControlEntry, ...] = ()
    replacement_map: tuple[ReplacementDecision, ...] = ()
    effect_policy: EffectPolicyPlan | None = None
    provenance: PlanProvenance | None = None
    validation_report: ValidationReport = field(default_factory=ValidationReport)

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("CompiledRunPlan.profile_path must be non-empty")
        if not isinstance(self.input_provenance, tuple):
            object.__setattr__(self, "input_provenance", tuple(self.input_provenance))
        normalized: list[tuple[str, str]] = []
        for item in self.input_provenance:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(f"input_provenance item must be (kind, path) tuple, got {item!r}")
            kind, path = item
            normalized.append((str(kind), str(path)))
        object.__setattr__(self, "input_provenance", tuple(normalized))
        for name in (
            "plugin_specs",
            "capability_bindings",
            "phase_bindings",
            "control_entries",
            "replacement_map",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))

    @property
    def schema_version(self) -> str:
        """ADR-0075 的明确 schema 名称。"""
        return self.plan_version

    @property
    def plan_hash(self) -> str:
        """可读别名；历史 Journal 仍使用兼容的 ``plan_ref``。"""
        return compiled_run_plan_ref(self)

    @property
    def is_declarative(self) -> bool:
        return self.phase_graph is not None and bool(self.phase_bindings)


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def compiled_run_plan_ref(plan: CompiledRunPlan) -> str:
    """以所有生效输入计算跨进程稳定的 canonical plan_ref。"""
    cap_hash = capability_plan_hash(plan.capability)
    control_hash = compute_control_plan_hash(plan.control.entries, plan.control.profile_path)
    scope_hash = scope_plan_hash(plan.scope)
    payload = {
        "capability": cap_hash,
        "control": control_hash,
        "scope": scope_hash,
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "revision": plan.revision,
        "input_provenance": sorted((kind, path) for kind, path in plan.input_provenance),
        "declarative": _declarative_payload(plan),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def capability_sub_plan_hash(plan: CompiledRunPlan) -> str:
    return str(capability_plan_hash(plan.capability))


def control_sub_plan_hash(plan: CompiledRunPlan) -> str:
    return str(compute_control_plan_hash(plan.control.entries, plan.control.profile_path))


def scope_sub_plan_hash(plan: CompiledRunPlan) -> str:
    return str(scope_plan_hash(plan.scope))


def plan_ref_of(plan: CompiledRunPlan) -> str:
    return compiled_run_plan_ref(plan)


def compiled_run_plan_to_dict(plan: CompiledRunPlan) -> dict[str, Any]:
    """完整 JSON 友好计划摘要，包含可解释的 ADR-0075 区域。"""
    result: dict[str, Any] = {
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "schema_version": plan.schema_version,
        "plan_ref": compiled_run_plan_ref(plan),
        "plan_hash": plan.plan_hash,
        "revision": plan.revision,
        "input_provenance": [{"kind": kind, "path": path} for kind, path in plan.input_provenance],
        "capability": {
            "profile_path": plan.capability.profile_path,
            "revision": plan.capability.revision,
            "plan_hash": capability_plan_hash(plan.capability),
            "binding_count": len(plan.capability.provider_bindings),
            "relation_count": len(plan.capability.relations),
        },
        "control": {
            "profile_path": plan.control.profile_path,
            "plan_hash": compute_control_plan_hash(plan.control.entries, plan.control.profile_path),
            "entry_count": len(plan.control.entries),
            "covered_slots": sorted(slot.value for slot in plan.control.by_slot),
        },
        "scope": {
            "profile_path": plan.scope.profile_path,
            "lifecycle": plan.scope.lifecycle.value,
            "visibility": [scope.value for scope in plan.scope.visibility],
            "acl_grants": list(plan.scope.acl_grants),
            "budget_ceiling": {
                "max_tokens": plan.scope.budget_ceiling.max_tokens,
                "max_wall_clock_seconds": plan.scope.budget_ceiling.max_wall_clock_seconds,
                "max_tool_calls": plan.scope.budget_ceiling.max_tool_calls,
                "max_steps": plan.scope.budget_ceiling.max_steps,
                "max_cost_cents": plan.scope.budget_ceiling.max_cost_cents,
            },
            "plan_hash": scope_plan_hash(plan.scope),
        },
    }
    if plan.phase_graph is not None:
        result["declarative"] = _declarative_payload(plan)
    return result


def build_input_provenance(
    profile_path: str,
    bundles: Iterable[str],
    patches: Iterable[str] = (),
    task_id: str | None = None,
    env_fingerprint: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """从 Profile / Bundle / patch / task 构建稳定 provenance。"""
    out: list[tuple[str, str]] = [("profile", str(profile_path))]
    out.extend(("bundle", str(bundle)) for bundle in bundles)
    out.extend(("patch", str(patch)) for patch in patches)
    if task_id is not None:
        out.append(("task", str(task_id)))
    if env_fingerprint is not None:
        out.append(("env", str(env_fingerprint)))
    return tuple(out)


def _declarative_payload(plan: CompiledRunPlan) -> dict[str, Any]:
    if plan.phase_graph is None:
        return {}
    return {
        "plugin_specs": [plugin_spec_to_dict(spec) for spec in plan.plugin_specs],
        "capability_bindings": [
            {
                "capability": binding.capability,
                "provider": binding.provider,
                "cardinality": binding.cardinality,
                "scope": binding.scope,
                "grant": list(binding.grant),
                "provenance": list(binding.provenance),
            }
            for binding in plan.capability_bindings
        ],
        "phase_graph": phase_graph_to_dict(plan.phase_graph),
        "phase_bindings": [
            {
                "node_id": binding.node_id,
                "semantic_phase": binding.semantic_phase.value,
                "executor_capability": binding.executor_capability,
                "contributions": [
                    {
                        "phase": contribution.phase.value,
                        "role": contribution.role.value,
                        "executor": contribution.executor,
                        "output": contribution.output,
                        "order": contribution.order,
                        "aggregation": contribution.aggregation,
                    }
                    for contribution in binding.contributions
                ],
            }
            for binding in plan.phase_bindings
        ],
        "control_entries": [
            {
                "phase": entry.phase.value,
                "executor_capability": entry.executor_capability,
                "predicate": entry.predicate,
                "aggregation": entry.aggregation,
                "evidence_required": entry.evidence_required,
            }
            for entry in plan.control_entries
        ],
        "replacement_map": [
            {
                "target": decision.target,
                "winner": decision.winner,
                "mode": decision.mode,
                "reason": decision.reason,
                "candidates": list(decision.candidates),
            }
            for decision in plan.replacement_map
        ],
        "effect_policy": {
            "gateway_capability": plan.effect_policy.gateway_capability if plan.effect_policy else "",
            "allowed_effects": list(plan.effect_policy.allowed_effects) if plan.effect_policy else [],
            "approval_required": list(plan.effect_policy.approval_required) if plan.effect_policy else [],
            "idempotency_required": list(plan.effect_policy.idempotency_required) if plan.effect_policy else [],
        },
        "provenance": {
            "profile_path": plan.provenance.profile_path if plan.provenance else plan.profile_path,
            "bundles": list(plan.provenance.bundles) if plan.provenance else [],
            "plugin_revisions": list(plan.provenance.plugin_revisions) if plan.provenance else [],
            "task_contract": plan.provenance.task_contract if plan.provenance else "",
            "environment": plan.provenance.environment if plan.provenance else "",
            "actor_grant": list(plan.provenance.actor_grant) if plan.provenance else [],
        },
        "validation_report": validation_report_to_dict(plan.validation_report),
    }


__all__ = [
    "COMPILED_RUN_PLAN_VERSION",
    "CompiledRunPlan",
    "build_input_provenance",
    "capability_sub_plan_hash",
    "compiled_run_plan_ref",
    "compiled_run_plan_to_dict",
    "control_sub_plan_hash",
    "plan_ref_of",
    "scope_sub_plan_hash",
]
