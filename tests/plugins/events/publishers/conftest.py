"""publishers 测试共享 fixture.

FactGateway 路径需要 runtime Session writer (``set_publish_session``).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


@pytest.fixture
def bus():
    """注入测试 catalog 的 EventBus;与生产 boot 路径等价。"""
    from lca_kernel.events.test.catalog import build_test_bus

    return build_test_bus()


@pytest.fixture
def bound_session() -> Iterator[Session]:
    """绑定 runtime Session for FactGateway spine emit tests."""
    session = Session("test-reflector-publisher")
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)
