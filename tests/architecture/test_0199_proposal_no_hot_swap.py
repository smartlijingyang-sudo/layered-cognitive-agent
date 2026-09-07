"""I-HPC-10 architectural guard: PlanProposal cannot hot-swap active plan (ADR-0199 §4 / P4-08).

Per ADR-0199 §4 + I-HPC-10: a PlanProposal activation MUST produce a NEW
SessionActivation bound to ``proposal.candidate_plan_ref``. The OLD
activation remains bound to its OLD ``plan_ref``. The active ``plan_ref``
is NEVER mutated by proposal activation.

This test exercises the full ``build_proposal`` -> ``activate_proposal``
loop end-to-end and asserts the non-mutation invariant. It is the
architectural guard that prevents future PRs from introducing hot-swap
behaviour.
"""

from __future__ import annotations

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.plan_proposal import build_proposal
from lca.harness.runtime.activation_ref import compute_activation_ref
from lca.harness.runtime.proposal_activator import activate_proposal


class TestProposalNoHotSwap:
    """I-HPC-10: PlanProposal activation produces a NEW activation; old is unchanged."""

    def test_activate_proposal_produces_new_activation(self) -> None:
        """``activate_proposal`` returns a fresh ``SessionActivation``."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "a" * 64,
            candidate_plan_ref="plan_new",
        )
        activation = activate_proposal(
            proposal,
            session_id="sess_new",
            profile_path="/abs/profiles/sample.yaml",
            graph_ref="graph_new",
            plugin_set_ref="plugin_set_new",
        )
        assert isinstance(activation, SessionActivation)
        assert activation.plan_ref == "plan_new"

    def test_active_plan_ref_after_activation_matches_candidate(self) -> None:
        """The new activation's ``plan_ref`` == ``proposal.candidate_plan_ref``."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "b" * 64,
            candidate_plan_ref="plan_X",
        )
        activation = activate_proposal(
            proposal,
            session_id="sess_1",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        assert activation.plan_ref == proposal.candidate_plan_ref == "plan_X"

    def test_old_activation_not_mutated_by_proposal_activation(self) -> None:
        """The old activation's ``plan_ref`` is unchanged after activating a new proposal."""
        old_proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "c" * 64,
            candidate_plan_ref="plan_OLD",
        )
        old_activation = activate_proposal(
            old_proposal,
            session_id="sess_old",
            profile_path="/abs/profiles/old.yaml",
            graph_ref="graph_old",
            plugin_set_ref="plugin_set_old",
        )
        old_plan_ref = old_activation.plan_ref

        new_proposal = build_proposal(
            source_activation_ref=old_activation.activation_ref,
            candidate_plan_ref="plan_NEW",
        )
        new_activation = activate_proposal(
            new_proposal,
            session_id="sess_new",
            profile_path="/abs/profiles/new.yaml",
            graph_ref="graph_new",
            plugin_set_ref="plugin_set_new",
        )

        assert old_activation.plan_ref == old_plan_ref == "plan_OLD"
        assert new_activation.plan_ref == "plan_NEW"
        assert old_activation is not new_activation
        assert old_activation.activation_ref != new_activation.activation_ref

    def test_same_candidate_plan_ref_different_session_yields_different_activation_ref(
        self,
    ) -> None:
        """Same candidate plan_ref with different sessions -> distinct activation_refs."""
        proposal_a = build_proposal(
            source_activation_ref="lca.activation.v1:" + "d" * 64,
            candidate_plan_ref="plan_SHARED",
        )
        proposal_b = build_proposal(
            source_activation_ref="lca.activation.v1:" + "e" * 64,
            candidate_plan_ref="plan_SHARED",
        )
        act_a = activate_proposal(
            proposal_a,
            session_id="sess_A",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        act_b = activate_proposal(
            proposal_b,
            session_id="sess_B",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        assert act_a.plan_ref == act_b.plan_ref == "plan_SHARED"
        assert act_a.activation_ref != act_b.activation_ref

    def test_activating_same_proposal_twice_does_not_mutate_first(self) -> None:
        """Re-activating a proposal does NOT mutate the previously-produced activation."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "f" * 64,
            candidate_plan_ref="plan_REUSE",
        )
        act_1 = activate_proposal(
            proposal,
            session_id="sess_1",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        ref_1 = act_1.activation_ref
        plan_ref_1 = act_1.plan_ref

        act_2 = activate_proposal(
            proposal,
            session_id="sess_2",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )

        assert act_1.activation_ref == ref_1
        assert act_1.plan_ref == plan_ref_1
        assert act_2.activation_ref != ref_1
        assert act_1 is not act_2

    def test_activating_does_not_change_proposal_status(self) -> None:
        """The proposal's ``status`` field is unchanged after activation."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "1" * 64,
            candidate_plan_ref="plan_Z",
            status="accepted",
        )
        original_status = proposal.status
        activate_proposal(
            proposal,
            session_id="sess_Z",
            profile_path="/abs/profiles/z.yaml",
            graph_ref="graph_Z",
            plugin_set_ref="plugin_set_Z",
        )
        assert proposal.status == original_status == "accepted"

    def test_new_activation_session_id_matches_input(self) -> None:
        """The new activation's ``session_id`` matches the input."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "2" * 64,
            candidate_plan_ref="plan_session_test",
        )
        act = activate_proposal(
            proposal,
            session_id="sess_SPECIFIC",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        assert act.session_id == "sess_SPECIFIC"

    def test_new_activation_activation_ref_uses_candidate_plan(self) -> None:
        """The ``activation_ref`` is computed from ``candidate_plan_ref``, NOT source."""
        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "3" * 64,
            candidate_plan_ref="plan_CANDIDATE",
        )
        act = activate_proposal(
            proposal,
            session_id="sess_X",
            profile_path="/abs/profiles/x.yaml",
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
        )
        expected_ref = compute_activation_ref(
            plan_ref=proposal.candidate_plan_ref,
            graph_ref="graph_X",
            plugin_set_ref="plugin_set_X",
            session_id="sess_X",
        )
        assert act.activation_ref == expected_ref
