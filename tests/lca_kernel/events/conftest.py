"""共用 fixture：每个测试用独立的 EventBus 实例（避免 singleton 串扰）。"""

from __future__ import annotations

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    """独立 EventBus 实例（按默认 yaml 加载）。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventBus(registry)


@pytest.fixture(autouse=True)
def _reset_singleton():
    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()
