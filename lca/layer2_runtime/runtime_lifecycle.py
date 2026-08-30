"""Kernel-owned runtime lifecycle facts shared by every Profile-selected loop."""

from __future__ import annotations

from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.observability.journal import RunResumed
from lca.layer0_infra.observability import record


def record_run_resumed(snapshot: StateSnapshot) -> None:
    """Append the canonical resume fact before any selected runtime executes.

    The Agent boundary invokes this L2 helper after it has established the
    ``RunScope``. Keeping the event's sole emitter in Layer 2 preserves the
    Journal catalog invariant while preventing a custom Runtime plugin from
    silently omitting recovery observability.
    """

    record(RunResumed(step=snapshot.step, reason=snapshot.reason.value))


__all__ = ["record_run_resumed"]
