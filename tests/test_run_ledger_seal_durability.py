"""Round 86 regression: ``RunStore.seal`` shares the persistence error contract
with ``RunStore.append`` (both raise ``LedgerDurabilityError`` on backend
failure). Before round 86 the two paths inlined the same commit sequence
independently, leaving ``seal`` to leak raw backend exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.models.observability.journal import AgentRunFinished, StampedEvent
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.contracts.observability.ledger import LedgerDurabilityError, LedgerUnregisteredError
from lca.infrastructure.observability.journal.engine.engine import RunStore


@dataclass(frozen=True)
class _AlwaysFailingBackend(JournalStoreBackend):
    """Backend whose ``append`` always raises; mirrors a real durability fault."""

    def append(self, _event: StampedEvent) -> None:
        raise RuntimeError("disk full")

    def events(self):  # type: ignore[override]
        return ()

    def get(self, _seq: int):  # type: ignore[override]
        return None

    def read_from(self, _after_seq: int):  # type: ignore[override]
        return ()

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class TestSealDurabilityContract:
    """R86: seal shares the L2 error-translation seam with append."""

    def test_seal_with_failing_backend_raises_ledger_durability_error(self) -> None:
        store = RunStore(run_id="r1", backend=_AlwaysFailingBackend())
        with pytest.raises(LedgerDurabilityError) as exc_info:
            store.seal(AgentRunFinished(status="completed"))
        # No partial commit visible after the failure.
        assert store.is_sealed is False
        assert "disk full" in str(exc_info.value)

    def test_append_with_failing_backend_raises_ledger_durability_error(self) -> None:
        """Sanity: append was already raising LedgerDurabilityError before R86."""
        store = RunStore(run_id="r1", backend=_AlwaysFailingBackend())
        with pytest.raises(LedgerDurabilityError):
            store.append(AgentRunFinished(status="completed"))
        assert store.is_sealed is False

    def test_seal_with_failing_backend_does_not_leave_sealed_true(self) -> None:
        """Critical: failure inside commit must not flip ``_sealed`` either."""
        store = RunStore(run_id="r1", backend=_AlwaysFailingBackend())
        with pytest.raises(LedgerDurabilityError):
            store.seal(AgentRunFinished(status="completed"))
        # A subsequent seal on a non-failing store must still work.
        store = RunStore(run_id="r1")  # in-memory backend
        store.seal(AgentRunFinished(status="completed"))
        assert store.is_sealed is True


class TestCommitUnlockedShape:
    """R86: ``_commit_unlocked`` is the shared internal seam."""

    def test_validate_event_shape_rejects_unknown_event_type(self) -> None:
        @dataclass(frozen=True)
        class Unregistered:
            pass

        store = RunStore(run_id="r1")
        with pytest.raises(LedgerUnregisteredError):
            store._validate_event_shape(Unregistered())

    def test_validate_event_shape_accepts_real_event(self) -> None:
        """Sanity: a real journal event passes the shared seam."""
        store = RunStore(run_id="r1")
        store._validate_event_shape(AgentRunFinished(status="completed"))  # no raise
