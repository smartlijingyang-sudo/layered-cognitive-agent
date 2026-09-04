# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine deriver；PR-8 shim 走 events/subscribers/spine_* 包装；
# 本模块保留至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.derivers" lca/ = 0 触发）。
#
# COMPAT(delete-when: ADR-0186 PR-3g SSE 投影迁 Session observer,
#        tracking: ADR-0186 PR-3g)
# live_tail.subscribe 是 SSE carrier fan-out（LiveTail ring buffer 的
# register-replay-live 迭代器透传），不是 I-SESSION-5 fold 派生主路径，
# 也不是 EventSpine.subscribe 回调累积。生产 SSE 读 session.tail；
# 本 Deriver 的 on_event 仅作 EventRecord→StampedEvent 桥。收口时改为
# Session observer 直接推送 StampedEvent，再删本桥接。

"""LiveTailDeriver — SSE carrier wrapper around ``LiveTail`` (not a fold deriver).

I-SESSION-5 / ADR-0186 PR-3g: production step_tree 走 ``StepTreeFoldDeriver``。
本模块的 ``subscribe()`` 是 transport fan-out（透传 ``LiveTail.subscribe``），
**不是** ``EventSpine.subscribe`` 派生主路径，也不得当作 fold 未完成的证据。

``on_event`` 把 ``EventRecord`` 转成 ring buffer 需要的最小 ``StampedEvent``
并转发；SSE 消费者经 ``subscribe()`` 拿到 register-first-replay-then-live
语义。生产 run 的 ``session.tail`` 来自 RunJournalFactory 的 ``LiveTail``，
与本 capability 实例独立。

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

    # ── SSE carrier fan-out（非 EventSpine.subscribe / 非 fold）──
    def subscribe(self, *args: object, **kwargs: object):
        """Pass through to ``LiveTail.subscribe`` (SSE carrier, not fold).

        COMPAT(delete-when: ADR-0186 PR-3g SSE 投影迁 Session observer,
               tracking: ADR-0186 PR-3g)
        返回 ring buffer 的 register-replay-live 迭代器。本方法不是
        I-SESSION-5 派生主路径；生产 SSE 亦可直接读 ``session.tail``。
        Session observer 直推收口后随 ``LiveTailDeriver`` 删除。
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
