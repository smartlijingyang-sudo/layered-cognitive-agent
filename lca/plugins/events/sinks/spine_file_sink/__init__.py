"""spine_file_sink — ADR-0181 PR-8 / ADR-0183 PR-7 / plugin-universe PR-4。

file_sink 全迁：从 lca.infrastructure.observability.spine.sinks.file_sink
迁移到 lca.plugins.events.sinks.spine_file_sink。

shim 形式：保留旧 FileSink 逻辑，通过 ``__call__(payload, ref)`` 适配
EventBus callback 签名；EventRecord 字段从 SpineEventPayload +
EventRef 推导（旧接口兼容，header 不变）。

删-when：PR-9 旧 spine 全退役（rg FileSink lca/infrastructure/ = 0 触发）。

PR-4 可见性：re-export ``setup_spine_file_sink`` 为 ``setup``，使
``bundles/event-bus-components.yaml`` 的 ``$module`` 能被 profile resolver
经 ``getattr(module, "setup")`` 取到 plugin Manifest。
"""

from lca.plugins.events.sinks.spine_file_sink.manifest import setup
from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink

__all__ = ["SpineFileSink", "setup"]
