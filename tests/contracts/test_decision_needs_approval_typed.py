"""ADR-0235 / PR-5 (L-2 / G-9): Decision.needs_approval is a typed field.

Before PR-5 the HITL signal was smuggled via
``decision.extra["needs_approval"]`` (``dict[str, Any]`` is the typed-port
anti-pattern). PR-5 promotes it to a typed ``needs_approval: bool = False``
field on the :class:`Decision` dataclass. This module pins the typed
contract so a future regression that drops the field fails loudly at the
test boundary.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import Decision


def test_decision_has_typed_needs_approval_field() -> None:
    """L-2: ``needs_approval`` is a typed boolean on ``Decision``."""
    d = Decision(
        decision_id="dec-1",
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
        needs_approval=True,
    )
    assert d.needs_approval is True


def test_decision_needs_approval_defaults_false() -> None:
    """``needs_approval`` defaults to ``False`` for backwards-compatible construction."""
    d = Decision(
        decision_id="dec-2",
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
    )
    assert d.needs_approval is False


def test_decision_needs_approval_false_round_trip() -> None:
    """``needs_approval=False`` round-trips through the dataclass."""
    d = Decision(
        decision_id="dec-3",
        action_type="respond",
        rationale="r",
        confidence=1.0,
        needs_approval=False,
    )
    assert d.needs_approval is False


def test_decision_extra_smuggling_is_no_longer_required() -> None:
    """The previous ``extra["needs_approval"]`` path is no longer required.

    The gate (``act.approve.gate``) reads ``decision.needs_approval``,
    not ``decision.extra``. Tests / producers that still wrote the flag
    to ``extra`` (legacy) must move to the typed field; this test
    documents that the typed field is the only contract.
    """
    d = Decision(
        decision_id="dec-4",
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
        needs_approval=True,
    )
    # The typed field is the source of truth; ``extra`` may still carry
    # unrelated keys but ``needs_approval`` is the typed path.
    assert d.needs_approval is True
    assert d.extra == {}
