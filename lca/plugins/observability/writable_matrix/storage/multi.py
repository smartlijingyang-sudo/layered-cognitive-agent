"""``writable.storage.multi`` —— Fan-out Storage 替换实现。

把同一份 bytes payload 写到多个子 storage。可在归档 profile 同时落：
- 默认 RoutingFileStorage（per-run spine ledger）
- S3 / SQLite / Kafka 子 storage（由 patch / config 注入）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass
class MultiStorage:
    _sinks: list[Any] = field(default_factory=list)

    def add(self, sink: Any) -> None:
        self._sinks.append(sink)

    def write(self, payload: bytes) -> None:
        for s in self._sinks:
            s.write(payload)

    def close(self) -> None:
        for s in self._sinks:
            s.close()


@plugin(
    id="writable.storage.multi",
    provides=("storage",),
    layer="L0",
    kind=PluginKind.SEAM,
    description="Fan-out storage; collects multiple EventStorage.",
)
def setup(ctx: PluginContext, config: Any) -> None:
    ms = MultiStorage()
    for child in config.get("children", []):
        ms.add(child)
    ctx.provide("storage", ms)
