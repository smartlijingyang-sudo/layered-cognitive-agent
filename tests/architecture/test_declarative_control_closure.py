"""Architecture tests for the declarative control binding seam."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    ControlEntry,
    DeclarativeValidationError,
    PhaseBinding,
    PhaseContribution,
    SemanticPhase,
    ValidationIssue,
    ValidationReport,
)
from lca.harness.declarative.controls.validation import (
    is_validation_valid,
    require_valid,
    validate_control_binding_closure,
    validation_errors,
    validation_warnings,
)


def test_validation_report_is_pure_data_and_harness_owns_its_behavior() -> None:
    report = ValidationReport(
        issues=(
            ValidationIssue("PG-010", "missing control binding"),
            ValidationIssue("PG-011", "deprecated contribution", severity="warning"),
        )
    )

    assert [issue.code for issue in validation_errors(report)] == ["PG-010"]
    assert [issue.code for issue in validation_warnings(report)] == ["PG-011"]
    assert not is_validation_valid(report)
    with pytest.raises(DeclarativeValidationError, match="missing control binding"):
        require_valid(report)


def test_validation_report_without_errors_is_accepted_by_harness() -> None:
    report = ValidationReport((ValidationIssue("PG-011", "deprecated", severity="warning"),))

    assert is_validation_valid(report)
    require_valid(report)


def _control_contribution() -> PhaseContribution:
    return PhaseContribution(
        phase=SemanticPhase.ACT,
        role=ContributionRole.GOVERN,
        executor="control.act.authorize",
        output="act.authorize",
        order=0,
        aggregation="deny-on-any-deny",
    )


def _entry() -> ControlEntry:
    return ControlEntry(
        phase=SemanticPhase.ACT,
        executor_capability="control.act.authorize",
        predicate="true",
        aggregation="deny-on-any-deny",
    )


def test_control_binding_closure_accepts_complete_projection() -> None:
    contribution = _control_contribution()
    spec = SimpleNamespace(id="control.act.authorize", contributes=(contribution,))
    binding = PhaseBinding(
        node_id="act.main",
        semantic_phase=SemanticPhase.ACT,
        executor_capability="phase.act",
        contributions=(contribution,),
    )

    report = validate_control_binding_closure((spec,), (binding,), (_entry(),))

    assert is_validation_valid(report)


def test_control_binding_closure_rejects_dropped_declared_contribution() -> None:
    contribution = _control_contribution()
    spec = SimpleNamespace(id="control.act.authorize", contributes=(contribution,))
    binding = PhaseBinding(
        node_id="act.main",
        semantic_phase=SemanticPhase.ACT,
        executor_capability="phase.act",
    )

    report = validate_control_binding_closure((spec,), (binding,), ())

    assert not is_validation_valid(report)
    errors = validation_errors(report)
    assert errors[0].code == "PG-010"
    assert "no executable phase binding" in errors[0].message


def test_control_binding_closure_rejects_unbacked_entry() -> None:
    report = validate_control_binding_closure((), (), (_entry(),))

    assert not is_validation_valid(report)
    errors = validation_errors(report)
    assert errors[0].code == "PG-010"
    assert "no executable control contribution" in errors[0].message


def test_capability_plan_options_reject_non_boolean_flags() -> None:
    from lca.harness.profile.capability_plan_resolver import CapabilityPlanOptions

    with pytest.raises(TypeError, match="include_disabled must be a boolean"):
        CapabilityPlanOptions(include_disabled="false")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validate_targets must be a boolean"):
        CapabilityPlanOptions(validate_targets=1)  # type: ignore[arg-type]
