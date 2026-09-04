# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine deriver；PR-8 shim 走 events/subscribers/spine_* 包装；
# 本模块保留至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.derivers" lca/ = 0 触发）。
#
# COMPAT(delete-when: ADR-0186 PR-3g SSE 投影迁 Session observer,
#        tracking: ADR-0186 PR-3g)
# live_tail 是唯一仍需要实时 on_event → ring buffer 的 deriver:SSE
# 消费者依赖 LiveTail.subscribe 的 register-first-replay-then-live 语义。
# PR-3g 收口时改为 Session observer 直接推送 StampedEvent,ring buffer
# 不再需要 EventSpine.subscribe 桥接。当前保留 subscribe 通路不破坏 SSE。

"""LiveTailDeriver — wraps ``LiveTail`` as a spine deriver (Task 2.2).

PR-2 parallel-write phase: the deriver exists alongside the legacy
``LiveTail`` ring buffer and is subscribed to ``EventSpine`` so the
framework has a structural hook for the eventual spine-native live tail.
For now ``on_event`` converts each ``EventRecord`` into the minimum
``StampedEvent`` shape the legacy ring buffer accepts and forwards it;
SSE subscribers see the same ring-buffer semantics as before.

The deriver does NOT remove or redirect any existing call site: both
legacy ``LiveTail`` instances and ``LiveTailDeriver`` instances feed
their own subscribers independently.

COMPAT(delete-when: ADR-0170 §D3 LiveTail 单身份重构完成,
       tracking: ADR-0170 §"删除条件" / issue 待开)
# 当前保留 ``_to_stamped`` 是因为 ``LiveTail.on_event`` 仍只接受
# ``StampedEvent``;LiveTail 改为接收 ``EventRecord`` + 单一身份后,
# 本文件 + ``live_tail._to_stamped`` 整体迁出,deriver 直接转发。
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

    # ── pass-through convenience for boot wiring ──
    def subscribe(self, *args: object, **kwargs: object):
        """Pass through to the wrapped tail's subscribe.

        COMPAT(delete-when: ADR-0186 PR-3g SSE 投影迁 Session observer,
               tracking: ADR-0186 PR-3g)
        SSE 消费者经本方法拿到 LiveTail 的 register-replay-live 迭代器。
        PR-3g 收口后 Session observer 直接推送,本方法随 LiveTailDeriver 整体删除。
        """
        return self._tail.subscribe(*args, **kwargs)

    def close(self) -> None:
        """Pass through to the wrapped tail's close."""
        self._tail.close()


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
