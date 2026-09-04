"""publishers 测试共享 fixture。

publish_via_session 在无绑定 Session 时 fail-loud(ADR-0186);``bound_session``
绑定测试 EventBus + 最小 fake Session,让 emit_* 走完整 Session 路径。
显式非 autouse:test_session_publish.py 专测"无 Session → fail-loud"语义,
其 ``current_publish_session() is None`` 断言不能被污染。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca_kernel.events.bus import EventBus, EventRef
from lca_kernel.events.test_catalog import build_test_bus


class FakePublishSession:
    """最小测试 Session:append 委托 EventBus.publish。

    鉴权保留两道:``_authorize_producer`` 在 append 前跑一次,
    ``bus.publish`` 内部再跑一次;返回的 :class:`EventRef` 保持
    ``bus.publish`` 的形状(ref.category / ref.event_id)。
    """

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def append(self, payload: Any, *, producer: Any = None) -> EventRef:
        return self.bus.publish(payload, producer=producer)


@pytest.fixture
def bus() -> EventBus:
    """注入测试 catalog 的 EventBus;与生产 boot 路径等价。"""
    return build_test_bus()


@pytest.fixture
def bound_session(bus: EventBus) -> Iterator[FakePublishSession]:
    """绑定 default EventBus + fake Session;teardown 复位两者。"""
    session = FakePublishSession(bus)
    EventBus.set_default(bus)
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)
        EventBus.set_default(None)
