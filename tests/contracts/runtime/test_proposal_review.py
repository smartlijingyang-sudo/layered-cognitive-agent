"""Behavioral tests for ``lca.contracts.runtime.proposal_review`` (PR-0199-P4-06).

Covers the ``ProposalReviewPort`` runtime-checkable Protocol and the
``ProposalReviewDecision`` value carrier per ADR-0199 §4 (self-improving
loop) and I-HPC-10 (no auto-activate; explicit accept / reject only).

The contract is Protocol-only — no concrete implementation is asserted
here. Stubs in this file exercise structural typing (the
``@runtime_checkable`` machinery) and the value semantics of the
decision carrier.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from lca.contracts.runtime.plan_proposal import (
    PlanProposal,
    ProposalStatus,
    build_proposal,
)
from lca.contracts.runtime.proposal_review import (
    ProposalReviewDecision,
    ProposalReviewPort,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_STATUSES: tuple[ProposalStatus, ...] = (
    "draft",
    "reviewing",
    "accepted",
    "rejected",
    "activated",
    "superseded",
    "expired",
)


def _build_proposal(**overrides: object) -> PlanProposal:
    """Build a valid ``PlanProposal`` for use as a review input."""
    kwargs: dict[str, object] = {
        "source_activation_ref": "act-abc-123",
        "candidate_plan_ref": "plan-xyz-789",
        "proposed_changes": {"step": "1"},
        "rationale": "test",
    }
    kwargs.update(overrides)
    return build_proposal(**kwargs)  # type: ignore[arg-type]


class _StubReviewer:
    """Concrete class structurally satisfying ``ProposalReviewPort``."""

    async def review(self, proposal: PlanProposal) -> ProposalReviewDecision:
        return ProposalReviewDecision(
            proposal_ref=proposal.proposal_ref,
            new_status="accepted",
            rationale="stub-approved",
            reviewer="stub",
        )


class _StubMissingReview:
    """Concrete class missing the ``review`` method — must fail Protocol."""


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


def test_proposal_review_port_is_protocol() -> None:
    """``ProposalReviewPort`` exposes ``__protocol_attrs__`` (set by Protocol)."""
    assert hasattr(ProposalReviewPort, "__protocol_attrs__")


def test_proposal_review_port_is_runtime_checkable() -> None:
    """``isinstance`` works for any class implementing ``review`` (structural)."""
    # ``@runtime_checkable`` flips this attribute on the Protocol class.
    assert getattr(ProposalReviewPort, "_is_runtime_protocol", False) is True


def test_stub_with_review_method_satisfies_protocol() -> None:
    """A stub exposing ``review`` passes ``isinstance(..., ProposalReviewPort)``."""
    assert isinstance(_StubReviewer(), ProposalReviewPort)


def test_stub_without_review_method_fails_protocol() -> None:
    """A stub lacking ``review`` does NOT satisfy the Protocol."""
    assert not isinstance(_StubMissingReview(), ProposalReviewPort)


def test_non_class_object_fails_protocol() -> None:
    """Non-class objects do not satisfy the Protocol (defensive)."""
    assert not isinstance(object(), ProposalReviewPort)
    assert not isinstance("not-a-reviewer", ProposalReviewPort)
    assert not isinstance(42, ProposalReviewPort)


def test_async_review_signature() -> None:
    """``review`` is declared ``async`` and takes one ``PlanProposal``."""
    method = ProposalReviewPort.review
    assert inspect.iscoroutinefunction(method), "review must be a coroutine function"
    sig = inspect.signature(method)
    # Protocol methods carry ``self`` as the first parameter.
    assert list(sig.parameters) == ["self", "proposal"]
    # Return annotation is the literal string under ``from __future__ import annotations``.
    assert sig.return_annotation == "ProposalReviewDecision"


# ---------------------------------------------------------------------------
# ProposalReviewDecision — value semantics
# ---------------------------------------------------------------------------


def test_proposal_review_decision_construct() -> None:
    """Constructor binds all four attributes verbatim."""
    decision = ProposalReviewDecision(
        proposal_ref="lca.plan_proposal.v1:" + "a" * 64,
        new_status="accepted",
        rationale="looks good",
        reviewer="human:alice",
    )
    assert decision.proposal_ref == "lca.plan_proposal.v1:" + "a" * 64
    assert decision.new_status == "accepted"
    assert decision.rationale == "looks good"
    assert decision.reviewer == "human:alice"


def test_proposal_review_decision_equality() -> None:
    """Two decisions with identical fields compare equal."""
    a = ProposalReviewDecision(
        proposal_ref="p1",
        new_status="accepted",
        rationale="r",
        reviewer="x",
    )
    b = ProposalReviewDecision(
        proposal_ref="p1",
        new_status="accepted",
        rationale="r",
        reviewer="x",
    )
    assert a == b


def test_proposal_review_decision_inequality_when_proposal_ref_differs() -> None:
    """Different ``proposal_ref`` -> unequal decisions."""
    a = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    b = ProposalReviewDecision(proposal_ref="p2", new_status="accepted")
    assert a != b


def test_proposal_review_decision_inequality_when_status_differs() -> None:
    """Different ``new_status`` -> unequal decisions."""
    a = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    b = ProposalReviewDecision(proposal_ref="p1", new_status="rejected")
    assert a != b


def test_proposal_review_decision_inequality_against_non_decision() -> None:
    """A decision compared to a non-decision is unequal (returns False, not NotImplemented)."""
    decision = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    # ``__eq__`` returns NotImplemented for non-decision; Python then falls back to ``is``,
    # so the boolean result of the ``==`` expression must be False.
    assert (decision == "not-a-decision") is False
    assert (decision == 42) is False
    assert (decision == None) is False  # noqa: E711  (explicit None comparison on purpose)


def test_proposal_review_decision_repr_format() -> None:
    """``repr`` is stable and includes proposal_ref / new_status / reviewer."""
    decision = ProposalReviewDecision(
        proposal_ref="p1",
        new_status="rejected",
        rationale="unsafe",
        reviewer="artifact-gate",
    )
    rendered = repr(decision)
    assert "ProposalReviewDecision(" in rendered
    assert "proposal_ref='p1'" in rendered
    assert "new_status='rejected'" in rendered
    assert "reviewer='artifact-gate'" in rendered


def test_proposal_review_decision_hashable() -> None:
    """Decisions are hashable and equal-value instances share a hash (set dedup)."""
    a = ProposalReviewDecision(proposal_ref="p1", new_status="accepted", rationale="r")
    b = ProposalReviewDecision(proposal_ref="p1", new_status="accepted", rationale="r")
    assert hash(a) == hash(b)
    seen = {a, b}
    assert len(seen) == 1


def test_proposal_review_decision_hash_changes_with_status() -> None:
    """Different status -> different hash (not guaranteed but expected for distinct decisions)."""
    a = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    b = ProposalReviewDecision(proposal_ref="p1", new_status="rejected")
    assert hash(a) != hash(b)


def test_proposal_review_decision_default_rationale_empty() -> None:
    """``rationale`` defaults to the empty string."""
    decision = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    assert decision.rationale == ""


def test_proposal_review_decision_default_reviewer_anonymous() -> None:
    """``reviewer`` defaults to ``"anonymous"`` when not provided."""
    decision = ProposalReviewDecision(proposal_ref="p1", new_status="accepted")
    assert decision.reviewer == "anonymous"


@pytest.mark.parametrize("status", _ALL_STATUSES)
def test_proposal_review_decision_supports_all_proposal_statuses(
    status: ProposalStatus,
) -> None:
    """Every closed-set ``ProposalStatus`` is accepted as ``new_status``."""
    decision = ProposalReviewDecision(proposal_ref="p1", new_status=status)
    assert decision.new_status == status


# ---------------------------------------------------------------------------
# End-to-end: stub reviewer round-trip on a real PlanProposal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio  # type: ignore[misc]
async def test_stub_reviewer_returns_decision_for_real_proposal() -> None:
    """The Protocol is usable end-to-end with a real ``PlanProposal`` input."""
    proposal = _build_proposal()
    decision = await _StubReviewer().review(proposal)
    assert isinstance(decision, ProposalReviewDecision)
    assert decision.proposal_ref == proposal.proposal_ref
    assert decision.new_status == "accepted"


# ---------------------------------------------------------------------------
# Module purity (contracts layer must not import upper layers)
# ---------------------------------------------------------------------------

_UPPER_LAYER_FORBIDDEN: tuple[str, ...] = (
    "lca.infrastructure",
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
    "lca.harness",
    "lca.plugins",
)


def _collect_module_level_imports(path: Path) -> list[tuple[str, str | None]]:
    """Return ``(module, name)`` pairs from the module's top-level imports.

    Mirrors the helper in ``test_runtime_facade_protocol.py``: descends
    into ``if TYPE_CHECKING:`` blocks too so type-only upper-layer
    imports are still flagged.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[tuple[str, str | None]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append((module, alias.name))
        elif isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                for child in node.body:
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            imports.append((alias.name, None))
                    elif isinstance(child, ast.ImportFrom):
                        module = child.module or ""
                        for alias in child.names:
                            imports.append((module, alias.name))
    return imports


def test_no_io_imports_in_module() -> None:
    """``lca/contracts/runtime/proposal_review.py`` must not import any
    forbidden upper-layer module (contracts purity / I-HPC-1 /
    importlinter contract #3).

    Forbidden: ``lca.infrastructure``, ``lca.cognition``, ``lca.runtime``,
    ``lca.agent``, ``lca.application``, ``lca.harness``, ``lca.plugins``.
    Also forbidden are any stdlib I/O / logging / env reads (``os``,
    ``sys``, ``logging``, ``pathlib``, ...) since the contract is pure data.
    """
    module_path = (
        Path(__file__).resolve().parents[3] / "lca" / "contracts" / "runtime" / "proposal_review.py"
    )
    assert module_path.is_file(), module_path

    # Forbidden upper-layer LCA modules.
    upper_layer_offenders = [
        (module, name)
        for module, name in _collect_module_level_imports(module_path)
        if any(
            module == forbidden or module.startswith(forbidden + ".")
            for forbidden in _UPPER_LAYER_FORBIDDEN
        )
    ]
    assert upper_layer_offenders == [], (
        f"{module_path} imports upper-layer modules; offenders: {upper_layer_offenders!r}"
    )

    # Forbidden stdlib I/O / side-effect modules — the contract is pure data.
    forbidden_stdlib: tuple[str, ...] = (
        "os",
        "sys",
        "logging",
        "pathlib",
        "io",
        "tempfile",
        "subprocess",
    )
    stdlib_offenders = [
        (module, name)
        for module, name in _collect_module_level_imports(module_path)
        if module in forbidden_stdlib
        or any(module.startswith(prefix + ".") for prefix in forbidden_stdlib)
    ]
    assert stdlib_offenders == [], (
        f"{module_path} imports side-effect stdlib modules; offenders: {stdlib_offenders!r}"
    )
