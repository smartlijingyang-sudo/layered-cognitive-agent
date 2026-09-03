"""共用 fixture：每个测试用独立的 EventBus 实例（避免 singleton 串扰）。"""

from __future__ import annotations

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.test_catalog import build_test_bus


@pytest.fixture
def bus() -> EventBus:
    """PR-5：测试路径下 catalog 已注入的 EventBus（与生产路径同形态）。

    通过 :func:`lca_kernel.events.test_catalog.build_test_bus` 构造；catalog
    项来自 marker class import，与 profile resolve 路径注入的内容一致。
    """
    return build_test_bus()


@pytest.fixture(autouse=True)
def _reset_singleton():
    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()
