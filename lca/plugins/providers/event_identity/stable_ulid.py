"""event identity via ULID —— ADR-0097 + ADR-0096 MVA-2.

每个 ``derive(run_id, seq, event_type)`` 调用产一个 ULID。
ULID 自带 ms 级单调时间戳（I3 不变量:不接调用方传入的 ts）。
"""

from __future__ import annotations

from ulid import ULID

from lca.contracts.observability.event_identity import EventIdentityProvider


class StableUlidIdentity(EventIdentityProvider):
    """I3 + ADR-0097: event_id 派生 = ULID(monotonic time + random)。

    兼容 ulid-py 1.x (``monotonic.new()``) 与 ulid-py 4.x (``ULID()``)；
    ulid-py 2.x/3.x 中间版本可能用 ``default_generator().generate()``,
    这里选 ``ULID()`` —— 4.x 推荐 API,也是当前依赖锁定的版本。
    """

    def derive(self, *, run_id: str, seq: int, event_type: str) -> str:
        # ULID 仅依赖调用时刻的 monotonic time;不接调用方传入的 ts
        return str(ULID())
