"""thinking.* Session 词表经真实 SessionStore.append 的 round-trip。"""

from __future__ import annotations

from lca.contracts.harness.memory.events import ThinkingCompleted, ThinkingDelta
from lca.contracts.harness.tasks.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.harness.session.store import SessionStore


def _session() -> SessionStore:
    return SessionStore(
        SessionHeader(version=SESSION_FORMAT_VERSION, id="ses-thinking", created_at=0)
    )


async def test_append_thinking_events_round_trips_through_store() -> None:
    store = _session()
    delta_event = await store.append(ThinkingDelta(turn=1, step=2, text_delta="想", seq=0))
    done_event = await store.append(
        ThinkingCompleted(turn=1, step=2, duration_ms=12, content_preview="想一下")
    )

    assert delta_event.type == "thinking.delta.v1"
    assert delta_event.visibility == "audit"
    assert delta_event.data == {"turn": 1, "step": 2, "text_delta": "想", "seq": 0}
    assert done_event.type == "thinking.completed.v1"
    assert done_event.visibility == "audit"
    assert done_event.data == {
        "turn": 1,
        "step": 2,
        "duration_ms": 12,
        "content_preview": "想一下",
    }
    assert (delta_event.seq, done_event.seq) == (0, 1)
