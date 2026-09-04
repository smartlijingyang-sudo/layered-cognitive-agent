# COMPAT(delete-when: ADR-0186 PR-3g SSE 投影迁 Session observer,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# ``subscribe()`` 是 SSE carrier fan-out（LiveTail register-replay-live
# 透传），不是 I-SESSION-5 fold 派生，也不是 EventSpine.subscribe 累积。
# 生产 SSE 可读 session.tail；本 Deriver.on_event 仅作
# EventRecord→StampedEvent 桥。Session observer 直推 StampedEvent 后删桥接。
# 在此之前保留 ``subscribe()`` API（不得当作 fold 未完成的证据）。

"""LiveTailDeriver — SSE carrier wrapper around ``LiveTail`` (not a fold deriver).

``subscribe()`` passes through ``LiveTail.subscribe`` (transport fan-out).
``on_event`` converts ``EventRecord`` → ``StampedEvent`` for the ring buffer.
Production step_tree uses ``StepTreeFoldDeriver`` (I-SESSION-5).
"""

from __future__ import annotations

import logging
from datetime import timezone

from lca.contracts.models.observability.journal import (
    RunScope as _RunScope,
)
from lca.contracts.models.observability.journal import (
    StampedEvent,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


class LiveTailDeriver(Deriver):
    """Deriver that delegates to a wrapped ``LiveTail`` ring buffer.

    The ring buffer's ``on_event`` accepts ``StampedEvent``; the spine
    produces ``EventRecord``.  The deriver performs the minimum viable
    conversion (``sequence`` → ``seq``, ``when`` → ``ts``,
    ``run_id``/``trace_id``/``step_id`` → ``RunScope``) and a stub
    ``RuntimeObserved`` payload so SSE consumers that filter on event
    class names keep working.
    """

    def __init__(self, tail: LiveTail) -> None:
        self._tail = tail

    @property
    def tail(self) -> LiveTail:
        """Wrapped ring buffer (test seam + boot wiring convenience)."""
        return self._tail

    def on_event(self, event: EventRecord) -> None:
        """Forward a spine event into the wrapped ``LiveTail`` ring buffer."""
        try:
            self._tail.on_event(_to_stamped(event))
        except Exception as exc:
            # FD-2 already contains spine subscribers, but the deriver may
            # be invoked directly (e.g. tests).  Never propagate.
            log.warning(
                "live_tail_deriver.on_event failed execution_point=%s err=%s",
                event.execution_point,
                exc,
                exc_info=True,
            )

    # ── SSE carrier fan-out（非 EventSpine.subscribe / 非 fold）──
    def subscribe(self, *args: object, **kwargs: object):
        """Pass through to ``LiveTail.subscribe`` (SSE carrier, not fold).

        Returns the ring buffer's register-replay-live iterator. Not the
        I-SESSION-5 derivation path; see module-level COMPAT for delete-when.
        """
        return self._tail.subscribe(*args, **kwargs)

    def close(self) -> None:
        """Pass through to the wrapped tail's close."""
        self._tail.close()


# COMPAT(delete-when: ADR-0170 §D3 LiveTail 单身份重构完成,
#        tracking: ADR-0170 §"删除条件" / issue 待开)
# ``_to_stamped`` 保留因 ``LiveTail.on_event`` 仍只接受 ``StampedEvent``；
# LiveTail 改为接收 ``EventRecord`` 后，本桥接整体迁出。
def _to_stamped(event: EventRecord) -> StampedEvent:
    """Build a ``StampedEvent`` carrying the spine event's
    sequence/timestamp/scope plus a stub ``RuntimeObserved`` payload.

    The conversion is intentionally minimal: only ``seq`` and ``ts``
    are read by ``LiveTail.on_event`` (for ring eviction and ordering).
    The stub payload preserves the ``event_type`` so SSE consumers that
    filter on ``event_type`` continue to see the execution point.
    """
    from lca.contracts.models.observability.journal import RuntimeObserved

    payload = RuntimeObserved(
        operation=event.execution_point,
        source="spine",
        attributes={
            "execution_point": event.execution_point,
            "channel": event.channel,
            "sequence": event.sequence,
            "span_id": event.span_id,
        },
    )
    scope = _RunScope(
        trace_id=event.run_id,  # spine run_id maps to legacy trace_id
        run_id=event.run_id,
        agent_role="",
    )
    ts = (
        event.when.astimezone(timezone.utc).timestamp()
        if event.when.tzinfo
        else event.when.timestamp()
    )
    return StampedEvent(
        seq=event.sequence,
        ts=ts,
        scope=scope,
        event=payload,
        event_type="RuntimeObserved",
        data={
            "execution_point": event.execution_point,
            "channel": event.channel,
            "payload": event.payload,
        },
    )


__all__ = ["LiveTailDeriver"]
