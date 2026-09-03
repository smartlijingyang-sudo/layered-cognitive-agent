"""tests/integration 专属 fixtures。

只新增;不改动既有测试行为。现有 fixtures 见 ``tests/conftest.py``。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from lca_kernel.events.bus import EventBus


@pytest.fixture
def event_singletons_reset() -> Iterator[None]:
    """EventBus 进程级单例测试前后对称重置。

    ``EventBus.default()`` 是进程级单例;
    集成测试之间不可共享鉴权矩阵、订阅表或已装载的 pipeline 状态。
    """
    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()
