"""_shared.attach_store_observers canonical 顺序契约（RA-019）。

钉住本轮裁定的 canonical 顺序 require-first：``require_observer_hook``
fail-loud 发生在遍历现存 Session 之前，钩子缺失的 store 上零部分挂入
（原先四家 list-first 会先挂完现存 Session 再抛，留下半接线状态）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from lca.plugins.session._shared import attach_store_observers
from lca.plugins.session.runtime.store.store import SessionStore


class _FakeSession:
    def __init__(self, sid: str) -> None:
        self.id = sid


class _HooklessStore:
    """有现存 Session 但无 ``add_observer_hook`` 的 store。"""

    def __init__(self, sessions: list[_FakeSession]) -> None:
        self._sessions = list(sessions)

    def list(self) -> list[_FakeSession]:
        return list(self._sessions)


def test_require_first_no_partial_attach_on_missing_hook() -> None:
    """缺钩子时 fail-loud 在先：TypeError，且没有任何 Session 被挂入。"""
    store = _HooklessStore([_FakeSession("s1"), _FakeSession("s2")])
    attached: list[Any] = []

    def attach_one(session: Any) -> None:
        attached.append(session)

    with pytest.raises(TypeError, match="add_observer_hook"):
        attach_store_observers(store, attach_one)
    assert attached == []


def test_attaches_existing_and_future_sessions_and_stashes_cancel() -> None:
    """现存 Session 逐个挂入；未来 create 经钩子接管；cancel 存入 sink。"""
    store = SessionStore()
    existing = store.create("s-existing")
    attached: list[Any] = []

    def attach_one(session: Any) -> None:
        attached.append(session)

    sink: list[Callable[[], None]] = []
    attach_store_observers(store, attach_one, sink)

    assert attached == [existing]
    assert len(sink) == 1 and callable(sink[0])

    future = store.create("s-future")
    assert attached == [existing, future]

    sink[0]()
    store.create("s-after-cancel")
    assert attached == [existing, future]


def test_hooks_sink_none_discards_cancel() -> None:
    """无 ``_store_hooks`` 的 plugin（spine_anomaly / projection_registry）：
    hooks_sink 缺省即丢弃 cancel，但接管未来 Session 不受影响。"""
    store = SessionStore()
    existing = store.create("s-existing")
    attached: list[Any] = []

    def attach_one(session: Any) -> None:
        attached.append(session)

    attach_store_observers(store, attach_one)

    future = store.create("s-future")
    assert attached == [existing, future]
