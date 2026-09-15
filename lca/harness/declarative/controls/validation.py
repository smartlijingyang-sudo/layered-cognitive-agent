"""Validation policy for declarative plans and assembled control bindings.

The contracts package owns serializable values and schema-level invariants. This
module owns cross-value validation that depends on the compiled plan and its
runtime seam, keeping behavior close to the harness test surface.

ADR-0221 P3 retired ``spec.contributes`` / ``ContributionRole`` /
``PhaseContribution`` / the v1 declarative ``phase_graph`` /
``phase_bindings`` region. ``validate_control_binding_closure`` was
deleted in the same PR (no callers; the executable control projection
is owned by ``PlanInterpreter`` + ``NodeExecutor`` subgraphs).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    PluginSpecKind,
    RelationType,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import PluginSpec


def validation_errors(report: ValidationReport) -> tuple[ValidationIssue, ...]:
    """Return error-severity findings from a serializable validation report."""

    return tuple(item for item in report.issues if item.severity == ValidationSeverity.ERROR)


def validation_warnings(report: ValidationReport) -> tuple[ValidationIssue, ...]:
    """Return non-error findings from a serializable validation report."""

    return tuple(item for item in report.issues if item.severity != ValidationSeverity.ERROR)


def is_validation_valid(report: ValidationReport) -> bool:
    """Whether a report contains no error-severity findings."""

    return not validation_errors(report)


def require_valid(report: ValidationReport) -> None:
    """Raise the first stable validation error for an invalid compiled plan."""

    errors = validation_errors(report)
    if errors:
        first = errors[0]
        raise DeclarativeValidationError(first.code, first.message)


class PluginSpecValidator:
    """Validate plugin schema and relationships before plan compilation."""

    def validate(self, specs: Sequence[PluginSpec]) -> ValidationReport:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        provided: dict[str, list[PluginSpec]] = defaultdict(list)
        ids = {spec.id for spec in specs}
        capability_keys: set[str] = set()
        for spec in specs:
            if spec.id in seen:
                issues.append(ValidationIssue("PS-001", f"duplicate plugin id: {spec.id}", spec.id))
            seen.add(spec.id)
            for offer in spec.provides:
                provided[offer.key].append(spec)
                capability_keys.add(offer.key)
        for spec in specs:
            for requirement in spec.requires:
                if requirement.cardinality != "optional" and requirement.key not in provided:
                    issues.append(
                        ValidationIssue(
                            "PS-002",
                            f"required capability has no provider: {requirement.key}",
                            spec.id,
                        )
                    )
            for relation in spec.relations:
                target_known = relation.target in ids or relation.target in capability_keys
                if relation.target.startswith("phase."):
                    target_known = True
                if not target_known:
                    issues.append(
                        ValidationIssue(
                            "PS-003", f"relation target does not exist: {relation.target}", spec.id
                        )
                    )
                if relation.type is RelationType.REPLACES:
                    target = next((item for item in specs if item.id == relation.target), None)
                    if target is not None and not _protocols_compatible(spec, target):
                        issues.append(
                            ValidationIssue(
                                "PS-004",
                                f"replacement is protocol-incompatible with {relation.target}",
                                spec.id,
                            )
                        )
                if relation.type is RelationType.SCOPED_BY:
                    parent = next((item for item in specs if item.id == relation.target), None)
                    if parent is not None and not _grants_monotonic(spec, parent):
                        issues.append(
                            ValidationIssue(
                                "PS-005", f"grant exceeds parent scope: {relation.target}", spec.id
                            )
                        )
            if any(effect != "none" for effect in spec.effects) and spec.kind not in {
                PluginSpecKind.EFFECT_HANDLER,
                PluginSpecKind.PROVIDER,
            }:
                issues.append(
                    ValidationIssue(
                        "PS-006", "effectful plugin kind has no gateway-compatible role", spec.id
                    )
                )
        for capability, providers in provided.items():
            if (
                len(providers) > 1
                and any(
                    offer.cardinality == "one"
                    for provider in providers
                    for offer in provider.provides
                    if offer.key == capability
                )
                and not any(
                    relation.type is RelationType.REPLACES
                    for provider in providers
                    for relation in provider.relations
                )
            ):
                issues.append(
                    ValidationIssue(
                        "PS-002", f"capability cardinality conflict: {capability}", capability
                    )
                )
        return ValidationReport(tuple(issues))


def _protocols_compatible(source: PluginSpec, target: PluginSpec) -> bool:
    source_protocols = {(item.key, item.protocol) for item in source.provides}
    target_protocols = {(item.key, item.protocol) for item in target.provides}
    return not target_protocols or bool(source_protocols & target_protocols)


def _grants_monotonic(child: PluginSpec, parent: PluginSpec) -> bool:
    child_grants = {grant for requirement in child.requires for grant in requirement.grant}
    parent_grants = {grant for offer in parent.provides for grant in offer.grant}
    return child_grants.issubset(parent_grants)


__all__ = [
    "PluginSpecValidator",
    "is_validation_valid",
    "require_valid",
    "validation_errors",
    "validation_warnings",
]
