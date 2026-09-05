"""tests/integration 专属 fixtures。

只新增;不改动既有测试行为。现有 fixtures 见 ``tests/conftest.py``。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from lca_kernel.events.bus import EventBus

# ADR-0186: spine_port_append 要求 Session hook 绑定。
# integration tests 直接使用 EventSpine 的需此 fixture。
from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
)
from tests.observability.spine.conftest import SyncPassthroughHook


@pytest.fixture(autouse=True)
def _integration_spine_hook() -> Iterator[None]:
    """为 integration tests 绑定 passthrough hook(ADR-0186)。"""
    token = bind_session_append_hook(SyncPassthroughHook())
    try:
        yield
    finally:
        reset_session_append_hook(token)


@pytest.fixture
def event_singletons_reset() -> Iterator[None]:
    """EventBus 进程级单例测试前后对称重置。

    ``EventBus.default()`` 是进程级单例;
    集成测试之间不可共享鉴权矩阵、订阅表或已装载的 pipeline 状态。
    """
    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()
