"""Regression locks for the IterationReason close-set consolidation (criterion #5).

Two close-set enums were historically declared in two files:
  - ``lca.contracts.observability.loop_cursor.IterationReason`` — the
    canonical 5-value union (``tool_retry``, ``gate_retry``,
    ``checkpoint_resume``, ``subagent_resume``, ``user_replay``)
  - ``lca.contracts.observability.resume.IterationReason`` — a 3-value
    subset defined twice for historic reasons.

After consolidation, ``resume.IterationReason`` is the same alias as
``loop_cursor.IterationReason`` — both refer to the same ``__args__``
tuple. This module locks the consolidation against regressions:

1. Identity test — both modules expose the same ``__args__`` and
   ``__origin__`` (typing.Literal close-set).
2. Close-set rejection — ``ResumeSpec.iteration_reason`` is a string
   type-annotated field; a value outside the close-set does NOT raise
   at construction (dataclass fields do not validate), so we lock the
   negative contract by invoking the IterationReason union
   structurally: an out-of-set string is not in
   ``get_args(IterationReason)``.

The test does NOT mutate any global state and does not import the
spine (lightweight, CI-friendly).
"""

from __future__ import annotations

from typing import get_args

from lca.contracts.observability import resume as resume_module
from lca.contracts.observability.loop_cursor import IterationReason as CanonicalReason


def test_iteration_reason_alias_is_loop_cursor_symbol() -> None:
    """``resume.IterationReason`` must be the same typing alias."""
    assert resume_module.IterationReason is CanonicalReason, (
        "resume.IterationReason must re-export the canonical "
        "loop_cursor.IterationReason symbol — not redeclare a subset."
    )


def test_iteration_reason_close_set_is_stable() -> None:
    """The Literal union has the 5 agreed values."""
    canonical = set(get_args(CanonicalReason))
    expected = {
        "tool_retry",
        "gate_retry",
        "checkpoint_resume",
        "subagent_resume",
        "user_replay",
    }
    assert canonical == expected, (
        f"IterationReason close-set changed: {canonical}; "
        f"this is a breaking-type change. Update ADR-0169 §D3."
    )


def test_iteration_reason_rejects_unknown_value() -> None:
    """``get_args`` returns the close-set; an unknown value is not in it."""
    canonical = get_args(CanonicalReason)
    assert "checkpoint_resume" in canonical
    assert "user_replay" in canonical
    assert "subagent_resume" in canonical
    assert "not-a-real-reason" not in canonical, (
        "Unknown reason must not appear in the close-set; if this "
        "fails, the Literal was widened without an ADR."
    )


def test_resume_spec_default_iteration_reason_is_known() -> None:
    """``ResumeSpec.iteration_reason`` defaults to a known close-set value."""
    from lca.contracts.observability.resume import ResumeSpec

    spec = ResumeSpec(
        run_id="r",
        plan_ref="p",
        incarnation_seq=1,
        iteration=0,
        step_index=0,
        phase="perceive",
    )
    assert spec.iteration_reason == "checkpoint_resume"
    assert spec.iteration_reason in get_args(CanonicalReason)
