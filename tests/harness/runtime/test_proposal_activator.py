"""PlanProposal activation closure tests (ADR-0199 §4 / P4-04 + I-HPC-10).

Behavioral coverage:

- Activation returns a fresh SessionActivation (no mutation of proposal).
- Activation binds to proposal.candidate_plan_ref; old activation_ref
  is not rebound.
- activation_ref is deterministic (C8) and depends on all 4 inputs.
- Trust envelope is the empty sentinel by default.
- compiled_plan is optional and round-trips when supplied.
- Required metadata is non-empty (ProposalActivationError on empties).
- is_proposal_activatable: closed-set mapping per P4-03 lifecycle.
- The module is pure (no I/O imports).
"""

from __future__ import annotations

import inspect

import pytest

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.plan_proposal import PlanProposal, build_proposal
from lca.contracts.runtime.trust import EMPTY_TRUST_ENVELOPE, TrustEnvelope
from lca.harness.runtime.activation_ref import (
    _ACTIVATION_HASH_NAMESPACE,
    compute_activation_ref,
    is_activation_ref,
)
from lca.harness.runtime.proposal_activator import (
    ProposalActivationError,
    activate_proposal,
    is_proposal_activatable,
)

_SOURCE_ACTIVATION_REF = "lca.activation.v1:" + "a" * 64
_CANDIDATE_PLAN_REF = "lca.plan.v1:" + "b" * 64
_SESSION_ID = "session-abc-001"
_PROFILE_PATH = "/abs/path/to/profiles/web-standard.yaml"
_GRAPH_REF = "lca.graph.v1:" + "c" * 64
_PLUGIN_SET_REF = "lca.plugin_set.v1:" + "d" * 64


def _make_proposal(
    *,
    source_activation_ref: str = _SOURCE_ACTIVATION_REF,
    candidate_plan_ref: str = _CANDIDATE_PLAN_REF,
    status: str = "accepted",
) -> PlanProposal:
    """Build a deterministic PlanProposal for tests."""
    return build_proposal(
        source_activation_ref=source_activation_ref,
        candidate_plan_ref=candidate_plan_ref,
        proposed_changes={"reason": "self-improve"},
        status=status,
        rationale="unit-test",
    )


def _fake_compiled_plan() -> object:
    """A opaque sentinel stand-in for CompiledRunPlan.

    SessionActivation accepts ``CompiledRunPlan | None``; we don't need
    a real compiled plan for these unit tests — just a stable sentinel.
    """
    return object()


# ---------------------------------------------------------------------------
# Activation closure: shape + immutability + binding semantics
# ---------------------------------------------------------------------------


class TestActivateProposalShape:
    """activate_proposal returns a fresh SessionActivation with the
    right shape and does not mutate the proposal."""

    def test_activate_proposal_returns_new_activation(self) -> None:
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert isinstance(activation, SessionActivation)
        assert isinstance(activation.activation_ref, str)
        assert activation.activation_ref  # non-empty

    def test_activate_proposal_does_not_mutate_input(self) -> None:
        proposal = _make_proposal()
        original_proposal_ref = proposal.proposal_ref
        original_status = proposal.status
        original_candidate = proposal.candidate_plan_ref
        original_source = proposal.source_activation_ref
        original_changes = proposal.proposed_changes

        activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )

        # Frozen dataclass: assigning would raise FrozenInstanceError.
        # We also assert identity-stable field values to be explicit.
        assert proposal.proposal_ref == original_proposal_ref
        assert proposal.status == original_status
        assert proposal.candidate_plan_ref == original_candidate
        assert proposal.source_activation_ref == original_source
        assert proposal.proposed_changes == original_changes

        with pytest.raises((AttributeError, Exception)):
            # FrozenInstanceError is the canonical type, but Exception
            # broadens if slots/frozen semantics evolve.
            proposal.status = "activated"  # type: ignore[misc]

    def test_activate_proposal_binds_to_candidate_plan_ref(self) -> None:
        """Per I-HPC-10: the new activation is bound to the proposal's
        candidate_plan_ref (the new plan_ref), NOT to the proposal's
        source activation_ref."""
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert activation.plan_ref == proposal.candidate_plan_ref
        # The proposal's source_activation_ref must NOT leak into the
        # new activation's plan_ref.
        assert activation.plan_ref != proposal.source_activation_ref


# ---------------------------------------------------------------------------
# activation_ref determinism (C8)
# ---------------------------------------------------------------------------


class TestActivationRefDeterminism:
    """activation_ref is C8-deterministic and depends on all 4 inputs."""

    def test_activate_proposal_computes_fresh_activation_ref(self) -> None:
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        expected = compute_activation_ref(
            plan_ref=_CANDIDATE_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert activation.activation_ref == expected
        assert is_activation_ref(activation.activation_ref)
        assert activation.activation_ref.startswith(_ACTIVATION_HASH_NAMESPACE + ":")

    def test_activate_proposal_activation_ref_is_deterministic(self) -> None:
        proposal = _make_proposal()
        a1 = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        a2 = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert a1.activation_ref == a2.activation_ref
        assert a1 == a2

    def test_activate_proposal_different_session_id_yields_different_activation_ref(self) -> None:
        proposal = _make_proposal()
        a1 = activate_proposal(
            proposal,
            session_id="session-A",
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        a2 = activate_proposal(
            proposal,
            session_id="session-B",
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert a1.activation_ref != a2.activation_ref

    def test_activate_proposal_different_graph_ref_yields_different_activation_ref(self) -> None:
        proposal = _make_proposal()
        a1 = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref="lca.graph.v1:" + "1" * 64,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        a2 = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref="lca.graph.v1:" + "2" * 64,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert a1.activation_ref != a2.activation_ref


# ---------------------------------------------------------------------------
# Trust envelope + compiled_plan propagation
# ---------------------------------------------------------------------------


class TestActivationFieldPropagation:
    """Trust envelope and optional compiled_plan propagate correctly."""

    def test_activate_proposal_carries_empty_trust_envelope(self) -> None:
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert activation.trust_envelope is EMPTY_TRUST_ENVELOPE
        # The empty envelope is a real TrustEnvelope (frozen + invariant-passing).
        assert isinstance(activation.trust_envelope, TrustEnvelope)

    def test_activate_proposal_carries_compiled_plan_when_provided(self) -> None:
        proposal = _make_proposal()
        sentinel = _fake_compiled_plan()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            compiled_plan=sentinel,  # type: ignore[arg-type]
        )
        assert activation.compiled_plan is sentinel

    def test_activate_proposal_compiled_plan_optional(self) -> None:
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert activation.compiled_plan is None

    def test_activate_proposal_carries_metadata(self) -> None:
        proposal = _make_proposal()
        activation = activate_proposal(
            proposal,
            session_id=_SESSION_ID,
            profile_path=_PROFILE_PATH,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
        )
        assert activation.profile_path == _PROFILE_PATH
        assert activation.session_id == _SESSION_ID
        assert activation.graph_ref == _GRAPH_REF
        assert activation.plugin_set_ref == _PLUGIN_SET_REF


# ---------------------------------------------------------------------------
# Input validation (fail-closed)
# ---------------------------------------------------------------------------


class TestActivationInputValidation:
    """Required metadata is non-empty; ProposalActivationError on empties."""

    def test_activate_proposal_raises_on_empty_session_id(self) -> None:
        proposal = _make_proposal()
        with pytest.raises(ProposalActivationError, match="session_id"):
            activate_proposal(
                proposal,
                session_id="",
                profile_path=_PROFILE_PATH,
                graph_ref=_GRAPH_REF,
                plugin_set_ref=_PLUGIN_SET_REF,
            )

    def test_activate_proposal_raises_on_empty_profile_path(self) -> None:
        proposal = _make_proposal()
        with pytest.raises(ProposalActivationError, match="profile_path"):
            activate_proposal(
                proposal,
                session_id=_SESSION_ID,
                profile_path="",
                graph_ref=_GRAPH_REF,
                plugin_set_ref=_PLUGIN_SET_REF,
            )

    def test_activate_proposal_raises_on_empty_graph_ref(self) -> None:
        proposal = _make_proposal()
        with pytest.raises(ProposalActivationError, match="graph_ref"):
            activate_proposal(
                proposal,
                session_id=_SESSION_ID,
                profile_path=_PROFILE_PATH,
                graph_ref="",
                plugin_set_ref=_PLUGIN_SET_REF,
            )

    def test_activate_proposal_raises_on_empty_plugin_set_ref(self) -> None:
        proposal = _make_proposal()
        with pytest.raises(ProposalActivationError, match="plugin_set_ref"):
            activate_proposal(
                proposal,
                session_id=_SESSION_ID,
                profile_path=_PROFILE_PATH,
                graph_ref=_GRAPH_REF,
                plugin_set_ref="",
            )


# ---------------------------------------------------------------------------
# is_proposal_activatable: lifecycle closed-set mapping
# ---------------------------------------------------------------------------


class TestIsProposalActivatable:
    """Lifecycle closed-set mapping per P4-03."""

    def test_is_proposal_activatable_true_for_accepted(self) -> None:
        proposal = _make_proposal(status="accepted")
        assert is_proposal_activatable(proposal) is True

    def test_is_proposal_activatable_true_for_activated(self) -> None:
        proposal = _make_proposal(status="activated")
        assert is_proposal_activatable(proposal) is True

    def test_is_proposal_activatable_false_for_draft(self) -> None:
        proposal = _make_proposal(status="draft")
        assert is_proposal_activatable(proposal) is False

    def test_is_proposal_activatable_false_for_reviewing(self) -> None:
        proposal = _make_proposal(status="reviewing")
        assert is_proposal_activatable(proposal) is False

    def test_is_proposal_activatable_false_for_rejected(self) -> None:
        proposal = _make_proposal(status="rejected")
        assert is_proposal_activatable(proposal) is False

    def test_is_proposal_activatable_false_for_superseded(self) -> None:
        proposal = _make_proposal(status="superseded")
        assert is_proposal_activatable(proposal) is False

    def test_is_proposal_activatable_false_for_expired(self) -> None:
        proposal = _make_proposal(status="expired")
        assert is_proposal_activatable(proposal) is False


# ---------------------------------------------------------------------------
# Module purity (no I/O imports)
# ---------------------------------------------------------------------------


class TestModulePurity:
    """The module must be a pure function — no I/O, no env, no logging."""

    def test_no_io_imports(self) -> None:
        from lca.harness.runtime import proposal_activator

        source = inspect.getsource(proposal_activator)
        module = inspect.getmodule(proposal_activator.activate_proposal)
        assert module is proposal_activator

        # The module source must not import any I/O, env, time, or logging
        # facade. We grep the inspected source conservatively.
        forbidden_substrings = (
            "import os",
            "from os",
            "import sys",
            "from sys",
            "import logging",
            "from logging",
            "import time",
            "from time",
            "import socket",
            "from socket",
            "import urllib",
            "from urllib",
            "import requests",
            "from requests",
            "import http",
            "from http",
            "open(",
            ".read(",
            ".write(",
            "print(",
        )
        for forbidden in forbidden_substrings:
            assert forbidden not in source, (
                f"proposal_activator module source must not contain {forbidden!r}; "
                "the activation seam must remain a pure projection"
            )

    def test_module_does_not_import_session_or_kernel(self) -> None:
        """The seam must not import the Session persistence component,
        the cordis Context, or the kernel. (Importing
        :class:`SessionActivation` from the contracts layer is required
        and therefore allowed.)
        """
        import ast

        from lca.harness.runtime import proposal_activator

        module_source = inspect.getsource(proposal_activator)
        tree = ast.parse(module_source)

        # Forbidden top-level imports (full dotted module path).
        forbidden_modules = {
            "lca.runtime.session",
            "lca.contracts.session",
            "lca.infrastructure.session",
            "lca.contracts.protocols.session",
            "lca_kernel",
            "cordis",
        }
        forbidden_names = {"fact_gateway"}

        offending: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    full = f"{module}.{alias.name}" if module else alias.name
                    for forbidden in forbidden_modules:
                        if full == forbidden or full.startswith(forbidden + "."):
                            offending.append(f"from {module} import {alias.name}")
                    if alias.name in forbidden_names:
                        offending.append(f"from {module} import {alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                            offending.append(f"import {alias.name}")

        assert not offending, (
            f"proposal_activator must not import Session / kernel / cordis; found: {offending!r}"
        )
