"""PhaseOutput outcome_kind + error field tests (ADR-0219 §10.11 item 3).

Contract:
- PhaseOutput remains frozen=True, extra="forbid".
- outcome_kind: ExecutionOutcome | None = None, error: str | None = None.
- Construction with non-None values is permitted.
- Construction with extra fields is rejected.
- model_copy(update={...}) is the only mutator path; it returns a new
  instance with the requested fields patched.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.framework.subgraph.plugins.channel import PhaseOutput


class TestPhaseOutputConstruction:
    def test_default_construction_is_all_none(self) -> None:
        out = PhaseOutput()
        assert out.decision is None
        assert out.observation is None
        assert out.reflection is None
        assert out.response is None
        assert out.outcome_kind is None
        assert out.error is None

    def test_outcome_kind_and_error_are_constructible(self) -> None:
        out = PhaseOutput(outcome_kind=ExecutionOutcome.FAILED, error="x")
        assert out.outcome_kind is ExecutionOutcome.FAILED
        assert out.error == "x"

    def test_outcome_kind_accepts_string_form(self) -> None:
        # str-based enum: PhaseOutput tolerates the string "failed" too.
        out = PhaseOutput(outcome_kind="failed")  # type: ignore[arg-type]
        assert out.outcome_kind is ExecutionOutcome.FAILED

    def test_frozen_enforced(self) -> None:
        out = PhaseOutput()
        with pytest.raises((ValidationError, AttributeError)):
            out.outcome_kind = ExecutionOutcome.FAILED  # type: ignore[misc]

    def test_extra_forbid_enforced(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            PhaseOutput(unknown_field="x")  # type: ignore[call-arg]
        assert "extra" in str(excinfo.value).lower() or "forbid" in str(excinfo.value).lower()


class TestPhaseOutputCopyUpdate:
    def test_model_copy_update_patches_outcome_kind(self) -> None:
        out = PhaseOutput()
        patched = out.model_copy(
            update={"outcome_kind": ExecutionOutcome.FAILED, "error": "boom"}
        )
        assert patched is not out
        assert patched.outcome_kind is ExecutionOutcome.FAILED
        assert patched.error == "boom"
        # original unchanged
        assert out.outcome_kind is None
        assert out.error is None

    def test_absorb_does_not_merge_failure_shape(self) -> None:
        """Per spec: terminal-run metadata is not mergeable payload.

        ``InMemoryPhaseOutputChannel.absorb`` reads only
        decision/observation/reflection/response; the new outcome_kind
        and error fields must NOT be carried into the absorbed
        snapshot. This test pins the design rule.
        """
        from lca.framework.subgraph.plugins.channel import (
            InMemoryPhaseOutputChannel,
        )

        channel = InMemoryPhaseOutputChannel()
        channel.publish(
            producer_node="think.reason",
            phase="phase:think",
            output=PhaseOutput(decision=None),
        )
        failed = PhaseOutput(
            outcome_kind=ExecutionOutcome.FAILED, error="inner failed"
        )
        channel.absorb(failed)
        # absorb reads only mergeable fields; outcome_kind is not one
        # of them, so the snapshot's stored PhaseOutput still has
        # outcome_kind=None.
        snap = channel.snapshot()
        assert len(snap) == 1
        stored = next(iter(snap.values()))
        assert stored.outcome_kind is None
        assert stored.error is None
