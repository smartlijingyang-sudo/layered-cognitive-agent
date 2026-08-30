"""编译计划的散列、来源与可解释性投影服务。

``CompiledRunPlan`` 保持在 contracts 中作为不可变数据载体；本模块拥有
对该数据进行散列、序列化和解释的运行时行为。这样计划的事实形状不会再同时
承担策略与展示职责，Harness、CLI 与运行时也共享唯一的 canonical plan_ref。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, cast

from lca.contracts.protocols.perceive.capability_plan import CapabilityPlan, capability_plan_hash
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    CognitivePhaseGraphPlan,
    PluginSpec,
    ValidationReport,
    ValidationSeverity,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.contracts.protocols.state.scope_plan import ScopePlan, scope_plan_hash


def canonical_json(value: Any) -> str:
    """Serialize plan data deterministically across Python processes."""

    return json.dumps(
        _canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def declarative_plan_hash(value: Any) -> str:
    """Return the stable digest used by declarative sub-plan diagnostics."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:32]


def compiled_run_plan_ref(plan: CompiledRunPlan) -> str:
    """Compute the cross-process stable canonical reference for a compiled plan."""

    payload = {
        "capability": capability_sub_plan_hash(plan),
        "control": control_entries_sub_plan_hash(plan),
        "scope": scope_sub_plan_hash(plan),
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "revision": plan.revision,
        "input_provenance": sorted((kind, path) for kind, path in plan.input_provenance),
        "declarative": _declarative_payload(plan),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def capability_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """Return the stable reference of the capability sub-plan."""

    return str(capability_plan_hash(plan.capability))


def control_entries_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """Return the stable reference of the executable declarative control projection."""

    return declarative_plan_hash(
        {
            "profile_path": plan.profile_path,
            "control_entries": plan.control_entries,
        }
    )


def scope_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """Return the stable reference of the scope sub-plan."""

    return str(scope_plan_hash(plan.scope))


def compiled_run_plan_to_dict(plan: CompiledRunPlan) -> dict[str, Any]:
    """Build the complete JSON-ready diagnostic projection for a compiled plan."""

    result: dict[str, Any] = {
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "schema_version": plan.plan_version,
        "plan_ref": compiled_run_plan_ref(plan),
        "plan_hash": compiled_run_plan_ref(plan),
        "revision": plan.revision,
        "input_provenance": [{"kind": kind, "path": path} for kind, path in plan.input_provenance],
        "capability": _capability_plan_to_dict(plan.capability),
        "control": _control_entries_to_dict(plan),
        "scope": _scope_plan_to_dict(plan.scope),
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
    """Construct stable provenance from profile, bundle, patch, task, and environment inputs."""

    out: list[tuple[str, str]] = [("profile", str(profile_path))]
    out.extend(("bundle", str(bundle)) for bundle in bundles)
    out.extend(("patch", str(patch)) for patch in patches)
    if task_id is not None:
        out.append(("task", str(task_id)))
    if env_fingerprint is not None:
        out.append(("env", str(env_fingerprint)))
    return tuple(out)


def plugin_spec_to_dict(spec: PluginSpec) -> dict[str, Any]:
    """Project a plugin specification to deterministic JSON-ready data."""

    return cast("dict[str, Any]", _canonicalize(spec))


def phase_graph_to_dict(graph: CognitivePhaseGraphPlan) -> dict[str, Any]:
    """Project a phase graph to deterministic JSON-ready data."""

    return cast("dict[str, Any]", _canonicalize(graph))


def validation_report_to_dict(report: ValidationReport) -> dict[str, Any]:
    """Project a validation report to deterministic JSON-ready data."""

    errors = tuple(item for item in report.issues if item.severity == ValidationSeverity.ERROR)
    warnings = tuple(item for item in report.issues if item.severity != ValidationSeverity.ERROR)
    return {
        "valid": not errors,
        "errors": [_canonicalize(item) for item in errors],
        "warnings": [_canonicalize(item) for item in warnings],
    }


def _capability_plan_to_dict(plan: CapabilityPlan) -> dict[str, Any]:
    return {
        "profile_path": plan.profile_path,
        "revision": plan.revision,
        "plan_hash": capability_plan_hash(plan),
        "binding_count": len(plan.provider_bindings),
        "relation_count": len(plan.relations),
    }


def _control_entries_to_dict(plan: CompiledRunPlan) -> dict[str, Any]:
    return {
        "plan_hash": control_entries_sub_plan_hash(plan),
        "entry_count": len(plan.control_entries),
        "covered_phases": sorted({entry.phase.value for entry in plan.control_entries}),
    }


def _scope_plan_to_dict(plan: ScopePlan) -> dict[str, Any]:
    return {
        "profile_path": plan.profile_path,
        "lifecycle": plan.lifecycle.value,
        "visibility": [scope.value for scope in plan.visibility],
        "acl_grants": list(plan.acl_grants),
        "budget_ceiling": {
            "max_tokens": plan.budget_ceiling.max_tokens,
            "max_wall_clock_seconds": plan.budget_ceiling.max_wall_clock_seconds,
            "max_tool_calls": plan.budget_ceiling.max_tool_calls,
            "max_steps": plan.budget_ceiling.max_steps,
            "max_cost_cents": plan.budget_ceiling.max_cost_cents,
        },
        "plan_hash": scope_plan_hash(plan),
    }


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
            "gateway_capability": plan.effect_policy.gateway_capability
            if plan.effect_policy
            else "",
            "allowed_effects": list(plan.effect_policy.allowed_effects)
            if plan.effect_policy
            else [],
            "approval_required": list(plan.effect_policy.approval_required)
            if plan.effect_policy
            else [],
            "idempotency_required": list(plan.effect_policy.idempotency_required)
            if plan.effect_policy
            else [],
        },
        "action_authority": _canonicalize(plan.action_authority) if plan.action_authority else {},
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


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _canonicalize(item) for key, item in asdict(cast("Any", value)).items()}
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalize(item) for item in value), key=canonical_json)
    return value


__all__ = [
    "build_input_provenance",
    "canonical_json",
    "capability_sub_plan_hash",
    "compiled_run_plan_ref",
    "compiled_run_plan_to_dict",
    "control_entries_sub_plan_hash",
    "declarative_plan_hash",
    "phase_graph_to_dict",
    "plugin_spec_to_dict",
    "scope_sub_plan_hash",
    "validation_report_to_dict",
]
