"""event identity via ULID —— ADR-0097 + ADR-0096 MVA-2.

每个 ``derive(run_id, seq, event_type)`` 调用产一个 ULID。
ULID 自带 ms 级单调时间戳（I3 不变量:不接调用方传入的 ts）。
"""

from __future__ import annotations

from ulid import monotonic

from lca.contracts.observability.event_identity import EventIdentityProvider


class StableUlidIdentity(EventIdentityProvider):
    """I3 + ADR-0097: event_id 派生 = ULID(monotonic time + random)。

    依赖锁定 ``ulid-py==1.1.0``：无参 ``ULID()`` 会抛
    ``MemoryView.__init__() missing ... 'buffer'``。1.x 正确 API 是
    ``ulid.monotonic.new()``（单调时钟，满足 I3）。
    """

    def derive(self, *, run_id: str, seq: int, event_type: str) -> str:
        # ULID 仅依赖调用时刻的 monotonic time;不接调用方传入的 ts
        del run_id, seq, event_type
        return str(monotonic.new())
