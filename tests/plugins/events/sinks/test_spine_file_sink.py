"""spine_file_sink publisher 端到端测试（ADR-0181 PR-8）。

shim 实现：旧 FileSink 包成 EventMechanism callback；接收
SpineEventPayload 时调旧 ``FileSink.write(EventRecord)``，磁盘格式不变。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_spine_file_sink_stub(mechanism: EventMechanism) -> None:
    """shim 入口点 + 字段推导（不全量集成，旧 sink 内部路径 PR-9 再清）。"""
    from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink

    sink = SpineFileSink()
    assert sink is not None
    assert hasattr(sink, "__call__")
    assert callable(sink)
