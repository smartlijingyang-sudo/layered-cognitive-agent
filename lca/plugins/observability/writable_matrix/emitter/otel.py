"""``writable.emitter.otel`` —— OTel 风格 Emitter 替换实现。

与默认 ``SpineEmitter`` 不同：本 emitter 不直接 append 到 EventSpine，
而是把事件桥接到已装配的 OTLP exporter（profile / bundle 注入）。
默认 web-standard profile 不装；要审计 / 跨服务追踪时通过 patch 启用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.event_record import EventRecord


@dataclass
class OTelEmitter:
    """OTel 风格 Emitter；桥接已装配的 OTLP delegate。

    delegate 由 profile 注入；未注入时是 no-op（仍占面位置）。
    """

    _delegate: Any = None

    def bind_delegate(self, delegate: Any) -> None:
        self._delegate = delegate

    def emit(self, record: EventRecord) -> None:
        if self._delegate is not None:
            self._delegate.emit(record)


@plugin(
    id="writable.emitter.otel",
    provides=("emitter",),
    layer="L0",
    kind=PluginKind.SEAM,
    description="OTel-style emitter; defers to an attached OTLP delegate.",
)
def setup(ctx: PluginContext, config: Any) -> None:
    ctx.provide("emitter", OTelEmitter())
