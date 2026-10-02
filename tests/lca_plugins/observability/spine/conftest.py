"""Shared fixtures for lca_plugins spine tests.

ADR-0186 后 ``spine_port_append`` 要求 Session hook 绑定。
沿用 ``tests/observability/spine/conftest.py`` 的既有模式：
autouse fixture 为本目录所有测试绑定 passthrough hook，
模拟旧同步路径语义（stamp + write to sinks + notify subscribers）。
"""

from __future__ import annotations

import pytest

from lca.infrastructure.observability.loop_cursor.spine._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
)
from tests.observability.spine.conftest import SyncPassthroughHook


@pytest.fixture(autouse=True)
def sync_passthrough_hook():
    """自动绑定测试用 passthrough hook,测试结束后释放。"""
    token = bind_session_append_hook(SyncPassthroughHook())
    try:
        yield
    finally:
        reset_session_append_hook(token)
