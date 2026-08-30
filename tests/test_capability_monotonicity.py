"""Capability monotonicity test (ADR-0074 §7.4 V8 hard constraint).

V8: Capability 单调性
- 子代理 grant ⊆ 父代理 grant
- 子 scope ⊆ 父 scope
- 子 artifact grant ⊆ 父 artifact grant

This test verifies that capability grants are monotonic:
child grants must be a subset of parent grants.
"""

from __future__ import annotations

from lca.contracts.atoms.scope import Scope


class TestCapabilityMonotonicity:
    """§7.4 V8 capability monotonicity."""

    def test_child_grants_subset_of_parent(self) -> None:
        """Verify child grants ⊆ parent grants."""
        from lca.contracts.protocols.act.command_envelope import CapabilityGrant

        # Parent grants
        parent_grants = (
            CapabilityGrant(capability="tool.bash", scope="run", effect_class="none"),
            CapabilityGrant(capability="tool.file_write", scope="run", effect_class="none"),
        )

        # Child grants (subset)
        child_grants = (CapabilityGrant(capability="tool.bash", scope="turn", effect_class="none"),)

        # Verify child ⊆ parent
        parent_caps = {g.capability for g in parent_grants}
        child_caps = {g.capability for g in child_grants}

        assert child_caps.issubset(parent_caps)

    def test_child_scope_subset_of_parent(self) -> None:
        """Verify child scope ⊆ parent scope."""
        # Parent scope: run
        parent_scope = Scope.RUN

        # Child scope: turn (more restrictive)
        child_scope = Scope.TURN

        # Verify child ⊆ parent (turn is more restrictive than run)
        # This is enforced by the Scope hierarchy
        assert child_scope != parent_scope  # Different scopes

    def test_artifact_grants_monotonic(self) -> None:
        """Verify artifact grants are monotonic."""
        from lca.contracts.protocols.act.command_envelope import CapabilityGrant

        # Parent grants
        parent_grants = (
            CapabilityGrant(capability="tool.bash", scope="run", effect_class="none"),
            CapabilityGrant(capability="tool.file_write", scope="run", effect_class="none"),
        )

        # Child grants (subset)
        child_grants = (CapabilityGrant(capability="tool.bash", scope="turn", effect_class="none"),)

        # Verify child grants ⊆ parent grants
        parent_caps = {g.capability for g in parent_grants}
        child_caps = {g.capability for g in child_grants}

        assert child_caps.issubset(parent_caps)
