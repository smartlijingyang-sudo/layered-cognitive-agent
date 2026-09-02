"""``writable.coalescer.passthrough`` —— 无缓冲 Coalescer 替换实现。

默认 ``LineCoalescer`` 会聚合 buffer；测试 / 流式场景想要「不做任何
合并、每条立即走完链」时启用本 plugin。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass
class PassthroughCoalescer:
    _pending: list[Any] = field(default_factory=list)

    def feed(self, channel: str, payload: Any) -> None:
        del channel
        self._pending.append(payload)

    def flush(self) -> tuple[Any, ...]:
        out = tuple(self._pending)
        self._pending.clear()
        return out


@plugin(
    id="writable.coalescer.passthrough",
    provides=("coalescer",),
    layer="L0",
    kind=PluginKind.SEAM,
    description="Coalescer replacement: no buffering / windowing.",
)
def setup(ctx: PluginContext, config: Any) -> None:
    ctx.provide("coalescer", PassthroughCoalescer())
