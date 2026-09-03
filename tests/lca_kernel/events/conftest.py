"""共用 fixture：每个测试用独立的机制实例（避免 singleton 串扰）。"""

from __future__ import annotations

import pytest

from lca_kernel.events import EventMechanism
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    """独立 mechanism 实例（按默认 yaml 加载）。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventMechanism(registry)


@pytest.fixture(autouse=True)
def _reset_singleton():
    EventMechanism.reset_singleton()
    yield
    EventMechanism.reset_singleton()
