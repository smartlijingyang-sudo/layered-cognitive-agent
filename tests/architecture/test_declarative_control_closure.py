"""Architecture tests for the declarative control binding seam.

ADR-0221 P3 retired ``validate_control_binding_closure`` along with the
v1 ``spec.contributes`` / ``ContributionRole`` / ``PhaseContribution`` /
``phase_graph`` / ``phase_bindings`` surface. The control projection is
now owned by ``PlanInterpreter`` + ``NodeExecutor`` subgraphs and is
exercised end-to-end in ``tests/integration``. Only the capability-plan
contract invariants remain in this file.
"""

from __future__ import annotations

import pytest


def test_capability_plan_options_reject_non_boolean_flags() -> None:
    from lca.harness.profile.resolve.capability_plan_resolver import CapabilityPlanOptions

    with pytest.raises(TypeError, match="include_disabled must be a boolean"):
        CapabilityPlanOptions(include_disabled="false")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validate_targets must be a boolean"):
        CapabilityPlanOptions(validate_targets=1)  # type: ignore[arg-type]
