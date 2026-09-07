"""Behavioral tests for ``lca.contracts.runtime.plan_proposal`` (PR-0199-P4-03).

Covers the ``PlanProposal`` frozen dataclass, the ``ProposalStatus``
lifecycle enum, and the deterministic ``compute_proposal_ref`` /
``build_proposal`` helpers per ADR-0199 §4 (self-improving loop) and
I-HPC-10 (immutable proposal; activation produces a new plan_ref, never
re-binds the active one).

Per C8 determinism: ``proposal_ref`` is a content-addressed hash of the
canonical JSON of ``(source_activation_ref, candidate_plan_ref,
proposed_changes)``. Same content -> same ref; same ref -> same content
(via the hash collision resistance of SHA-256).
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.contracts.runtime.plan_proposal import (
    PlanProposal,
    ProposalStatus,
    build_proposal,
    compute_proposal_ref,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_KWARGS: dict[str, object] = {
    "source_activation_ref": "act-abc-123",
    "candidate_plan_ref": "plan-xyz-789",
    "proposed_changes": {"step": "1", "phase": "think"},
    "rationale": "test rationale",
    "status": "draft",
    "created_at_seq": 0,
}


def _build(**overrides: object) -> PlanProposal:
    """Build a valid ``PlanProposal`` with overridable kwargs."""
    kwargs: dict[str, object] = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return build_proposal(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_build_proposal_returns_plan_proposal() -> None:
    """``build_proposal`` returns a ``PlanProposal`` instance."""
    proposal = _build()
    assert isinstance(proposal, PlanProposal)
    # The class was decorated with ``@dataclasses.dataclass`` (frozen+slots).
    # Re-deriving via dataclasses.fields confirms the decorator ran.
    fields = {f.name for f in dataclasses.fields(proposal)}
    assert "proposal_ref" in fields
    assert "source_activation_ref" in fields
    assert "candidate_plan_ref" in fields
    assert "proposed_changes" in fields
    assert "status" in fields


def test_build_proposal_auto_computes_ref() -> None:
    """``build_proposal`` populates ``proposal_ref`` automatically."""
    proposal = _build()
    expected_ref = compute_proposal_ref(
        source_activation_ref="act-abc-123",
        candidate_plan_ref="plan-xyz-789",
        proposed_changes={"step": "1", "phase": "think"},
    )
    assert proposal.proposal_ref == expected_ref
    assert proposal.proposal_ref != ""


def test_plan_proposal_status_defaults_to_draft() -> None:
    """``status`` defaults to ``draft`` when not provided."""
    proposal = build_proposal(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
    )
    assert proposal.status == "draft"
    assert proposal.rationale == ""
    assert proposal.created_at_seq == 0
    assert proposal.proposed_changes == ()


# ---------------------------------------------------------------------------
# compute_proposal_ref — determinism + sensitivity
# ---------------------------------------------------------------------------


def test_compute_proposal_ref_deterministic() -> None:
    """Same input -> same ref (C8 determinism)."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"k": "v"},
    )
    b = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"k": "v"},
    )
    assert a == b


def test_same_inputs_same_proposal_ref_across_calls() -> None:
    """``build_proposal`` produces the same ref on repeated calls (C8)."""
    a = _build()
    b = _build()
    assert a.proposal_ref == b.proposal_ref


def test_compute_proposal_ref_differs_for_different_source() -> None:
    """Different ``source_activation_ref`` -> different ref."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
    )
    b = compute_proposal_ref(
        source_activation_ref="act-2",
        candidate_plan_ref="plan-1",
    )
    assert a != b


def test_compute_proposal_ref_differs_for_different_candidate_plan() -> None:
    """Different ``candidate_plan_ref`` -> different ref."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
    )
    b = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-2",
    )
    assert a != b


def test_compute_proposal_ref_differs_for_different_changes() -> None:
    """Different ``proposed_changes`` -> different ref."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"k": "v1"},
    )
    b = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"k": "v2"},
    )
    assert a != b


def test_compute_proposal_ref_independent_of_dict_insertion_order() -> None:
    """Hash uses sorted keys, so dict insertion order does not affect ref."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"a": "1", "b": "2", "c": "3"},
    )
    b = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={"c": "3", "a": "1", "b": "2"},
    )
    assert a == b


def test_compute_proposal_ref_none_treated_as_empty() -> None:
    """``proposed_changes=None`` is treated as the empty mapping."""
    a = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes=None,
    )
    b = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
        proposed_changes={},
    )
    assert a == b


# ---------------------------------------------------------------------------
# proposal_ref format
# ---------------------------------------------------------------------------


def test_proposal_ref_format() -> None:
    """``proposal_ref`` starts with the namespaced prefix."""
    ref = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
    )
    assert ref.startswith("lca.plan_proposal.v1:")


def test_proposal_ref_length_64_hex_after_prefix() -> None:
    """The digest portion is 64 lowercase hex characters (SHA-256)."""
    ref = compute_proposal_ref(
        source_activation_ref="act-1",
        candidate_plan_ref="plan-1",
    )
    digest = ref.split(":", 1)[1]
    assert len(digest) == 64
    int(digest, 16)  # raises if not valid hex


# ---------------------------------------------------------------------------
# proposed_changes sorted
# ---------------------------------------------------------------------------


def test_proposed_changes_sorted_internally() -> None:
    """Input dict (unsorted) -> stored tuple sorted by key."""
    proposal = _build(proposed_changes={"b": "2", "a": "1", "c": "3"})
    assert proposal.proposed_changes == (("a", "1"), ("b", "2"), ("c", "3"))


def test_proposed_changes_empty() -> None:
    """Empty / None ``proposed_changes`` -> empty tuple."""
    proposal = _build(proposed_changes=None)
    assert proposal.proposed_changes == ()

    proposal = _build(proposed_changes={})
    assert proposal.proposed_changes == ()


# ---------------------------------------------------------------------------
# Lifecycle / is_terminal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["activated", "rejected", "superseded", "expired"],
)
def test_plan_proposal_is_terminal_for_terminal_statuses(
    status: ProposalStatus,
) -> None:
    """Terminal statuses (activated/rejected/superseded/expired) -> True."""
    proposal = _build(status=status)
    assert proposal.is_terminal() is True


@pytest.mark.parametrize("status", ["draft", "reviewing", "accepted"])
def test_plan_proposal_not_terminal_for_non_terminal_statuses(
    status: ProposalStatus,
) -> None:
    """Non-terminal statuses (draft/reviewing/accepted) -> False."""
    proposal = _build(status=status)
    assert proposal.is_terminal() is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_status_rejected() -> None:
    """Unknown ``status`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="status invalid"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=(),
            status="not-a-status",  # type: ignore[arg-type]
        )


def test_empty_proposal_ref_rejected() -> None:
    """Empty ``proposal_ref`` is rejected."""
    with pytest.raises(ValueError, match="proposal_ref"):
        PlanProposal(
            proposal_ref="",
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=(),
        )


def test_empty_source_activation_ref_rejected() -> None:
    """Empty ``source_activation_ref`` is rejected."""
    with pytest.raises(ValueError, match="source_activation_ref"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="",
            candidate_plan_ref="plan-1",
            proposed_changes=(),
        )


def test_empty_candidate_plan_ref_rejected() -> None:
    """Empty ``candidate_plan_ref`` is rejected."""
    with pytest.raises(ValueError, match="candidate_plan_ref"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="",
            proposed_changes=(),
        )


def test_negative_created_at_seq_rejected() -> None:
    """Negative ``created_at_seq`` is rejected."""
    with pytest.raises(ValueError, match="created_at_seq"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=(),
            created_at_seq=-1,
        )


def test_bool_created_at_seq_rejected() -> None:
    """``bool`` is not a valid ``created_at_seq`` (must be ``int``, not ``bool``)."""
    with pytest.raises(TypeError, match="created_at_seq"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=(),
            created_at_seq=True,  # type: ignore[arg-type]
        )


def test_invalid_proposed_changes_type_rejected() -> None:
    """Non-tuple ``proposed_changes`` is rejected."""
    with pytest.raises(TypeError, match="proposed_changes"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=[("a", "1")],  # type: ignore[arg-type]
        )


def test_invalid_proposed_changes_pair_shape_rejected() -> None:
    """``proposed_changes`` with malformed pair is rejected."""
    with pytest.raises(TypeError, match="proposed_changes"):
        PlanProposal(
            proposal_ref="lca.plan_proposal.v1:" + "0" * 64,
            source_activation_ref="act-1",
            candidate_plan_ref="plan-1",
            proposed_changes=(("a", "1", "extra"),),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Frozen / slots guarantees
# ---------------------------------------------------------------------------


def test_frozen_blocks_mutation() -> None:
    """``frozen=True`` rejects attribute assignment."""
    proposal = _build()
    with pytest.raises(dataclasses.FrozenInstanceError):
        proposal.status = "accepted"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        proposal.rationale = "overwrite"  # type: ignore[misc]


def test_slots_blocks_arbitrary_attributes() -> None:
    """``slots=True`` rejects unknown attributes at runtime."""
    proposal = _build()
    with pytest.raises((AttributeError, TypeError)):
        proposal.not_a_field = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Equality
# ---------------------------------------------------------------------------


def test_equality_on_same_contents() -> None:
    """Two proposals with identical contents compare equal."""
    a = _build()
    b = _build()
    assert a == b


def test_inequality_when_status_differs() -> None:
    """Different ``status`` -> unequal proposals."""
    a = _build(status="draft")
    b = _build(status="accepted")
    assert a != b


def test_inequality_when_rationale_differs() -> None:
    """Different ``rationale`` -> unequal proposals."""
    a = _build(rationale="first")
    b = _build(rationale="second")
    assert a != b
