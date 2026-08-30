"""Explainability projection for compiled declarative plans.

This module is intentionally separate from :mod:`plan_compiler`: compiling a
profile is a pure construction/validation concern, while explainability is a
read-only serialization concern consumed by CLI and diagnostics.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.validation import (
    is_validation_valid,
    validation_errors,
    validation_warnings,
)
from lca.harness.plan import (
    capability_sub_plan_hash,
    compiled_run_plan_ref,
    control_entries_sub_plan_hash,
    scope_sub_plan_hash,
)


def explain_compile_plan(plan: CompiledRunPlan) -> dict[str, Any]:
    """Return the complete explainability projection required by ADR-0075.

    The projection deliberately contains only plan data. It is therefore useful
    both to humans inspecting a profile and to tooling that needs to reconstruct
    why a phase, provider, relation, or replacement was selected.
    """
    phase_graph = plan.phase_graph
    provenance = plan.provenance
    phase_nodes = []
    phase_edges = []
    if phase_graph is not None:
        phase_nodes = [
            {
                "id": node.id,
                "semantic_phase": node.semantic_phase.value,
                "binding": node.binding,
                "max_visits": node.max_visits,
                "terminal": node.terminal,
            }
            for node in phase_graph.nodes
        ]
        phase_edges = [
            {
                "source": edge.source,
                "target": edge.target,
                "when": edge.when,
                "loop": (
                    {
                        "max_iterations": edge.loop.max_iterations,
                        "budget": edge.loop.budget,
                        "terminal_predicate": edge.loop.terminal_predicate,
                    }
                    if edge.loop is not None
                    else None
                ),
            }
            for edge in phase_graph.edges
        ]

    return {
        "profile_path": plan.profile_path,
        "plan_ref": compiled_run_plan_ref(plan),
        "plan_version": plan.plan_version,
        "revision": plan.revision,
        "input_provenance": [{"kind": kind, "path": path} for kind, path in plan.input_provenance],
        "declarative": {
            "schema_version": plan.plan_version,
            "plugin_count": len(plan.plugin_specs),
            "phase_graph": {
                "entry": phase_graph.entry if phase_graph is not None else "",
                "nodes": phase_nodes,
                "edges": phase_edges,
            },
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
            "phase_bindings": [
                {
                    "node": binding.node_id,
                    "phase": binding.semantic_phase.value,
                    "executor": binding.executor_capability,
                    "contributions": [
                        {
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
            "relations": [
                {
                    "source": spec.id,
                    "type": relation.type.value,
                    "target": relation.target,
                    "mode": relation.mode,
                }
                for spec in plan.plugin_specs
                for relation in spec.relations
            ],
            "replacement_map": [
                {
                    "target": item.target,
                    "winner": item.winner,
                    "mode": item.mode,
                    "reason": item.reason,
                    "candidates": list(item.candidates),
                }
                for item in plan.replacement_map
            ],
            "provenance": {
                "profile_path": provenance.profile_path if provenance else plan.profile_path,
                "bundles": list(provenance.bundles) if provenance else [],
                "plugin_revisions": [
                    {"plugin": plugin, "revision": revision}
                    for plugin, revision in provenance.plugin_revisions
                ]
                if provenance
                else [],
                "task_contract": provenance.task_contract if provenance else "",
                "environment": provenance.environment if provenance else "",
                "actor_grant": list(provenance.actor_grant) if provenance else [],
            },
            "effect_policy": {
                "gateway": plan.effect_policy.gateway_capability if plan.effect_policy else "",
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
            "validation": {
                "valid": is_validation_valid(plan.validation_report),
                "errors": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "location": issue.location,
                    }
                    for issue in validation_errors(plan.validation_report)
                ],
                "warnings": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "location": issue.location,
                    }
                    for issue in validation_warnings(plan.validation_report)
                ],
            },
        },
        "sub_plans": {
            "capability": {
                "plan_hash": capability_sub_plan_hash(plan),
                "binding_count": len(plan.capability.provider_bindings),
                "relation_count": len(plan.capability.relations),
            },
            "control": {
                "plan_hash": control_entries_sub_plan_hash(plan),
                "entry_count": len(plan.control_entries),
                "covered_phases": sorted({entry.phase.value for entry in plan.control_entries}),
            },
            "scope": {
                "plan_hash": scope_sub_plan_hash(plan),
                "lifecycle": plan.scope.lifecycle.value,
                "visibility": [s.value for s in plan.scope.visibility],
                "acl_grants": list(plan.scope.acl_grants),
            },
        },
    }


__all__ = ["explain_compile_plan"]
