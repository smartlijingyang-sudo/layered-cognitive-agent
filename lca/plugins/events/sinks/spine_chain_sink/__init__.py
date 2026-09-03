"""spine_chain_sink — 试点 1 个 sink plugin（ADR-0181 D6 + D2）。

落盘时算 hash chain（替代旧 ``lca/infrastructure/observability/spine/sinks/file_sink``
的 chain 部分）。试点仅 1 个 sink，PR-7 迁余下 3 个 sink。
"""

from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink

__all__ = ["SpineChainSink"]
