"""LiveTail does not translate Journal events — that is Transport's job."""

from __future__ import annotations

from lca.contracts.models.observability.journal import ReasoningDelta, RunScope, StampedEvent
from lca.layer0_infra.observability.journal.live_tail import LiveTail


def test_live_tail_does_not_translate() -> None:
    tail = LiveTail()
    stamped = StampedEvent(
        seq=1,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ReasoningDelta(step=0, text_delta="think", seq=0),
    )
    tail.on_event(stamped)
    assert tail.last_seq == 1
    replayed = tail._frames[0]
    assert replayed is stamped
    assert type(replayed.event).__name__ == "ReasoningDelta"
