"""publish_via_session helper 单测（ADR-0183）。

helper 行为契约:
1. 无 active Session 时 → RuntimeError(fail-loud;须 set_publish_session / run bind);
2. 有 active Session 时 → Session.append(payload, producer=...),返回 Session 给的 EventRef;
3. ContextVar set/reset 隔离:跨 token reset 行为正确;
4. Session.append 拿到的 payload/producer 与调用方传入一致;
5. append 前走 EventBus registry S1 鉴权。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    publish_via_session,
    reset_publish_session,
    set_publish_session,
)
from lca_kernel.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    from lca_kernel.events.test_catalog import build_test_bus

    return build_test_bus(config_dir)


def _sp_payload(execution_point: str, channel: str = "fact") -> Any:
    from lca_kernel.events.payloads import Category, SpineEventPayload

    return SpineEventPayload(
        category=Category("spine.cognition.brain.perceive.start"),
        execution_point=execution_point,
        channel=channel,
        payload={"state_id": "s1"},
    )


# ── ContextVar 单测 ────────────────────────────────────────────────────────


def test_current_publish_session_default_none() -> None:
    """未 set 时 current_publish_session 返回 None。"""
    assert current_publish_session() is None


def test_set_reset_publish_session_roundtrip() -> None:
    """set/reset token 后回到 default None。"""
    sentinel = MagicMock(name="Session")
    token = set_publish_session(sentinel)
    try:
        assert current_publish_session() is sentinel
    finally:
        reset_publish_session(token)
    assert current_publish_session() is None


# ── 无 Session → fail-loud ─────────────────────────────────────────────────


def test_publish_via_session_requires_bound_session() -> None:
    """无 Session 时 → RuntimeError,不走 EventBus.publish。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    assert current_publish_session() is None
    with pytest.raises(RuntimeError, match="set_publish_session"):
        publish_via_session(
            _sp_payload("brain.perceive.start"),
            producer=ReflectorClass,
        )


# ── Session 路径 ─────────────────────────────────────────────────────────


def test_publish_via_session_delegates_to_session_when_set(bus: EventBus) -> None:
    """有 Session 时 → Session.append(payload, producer=...) 被调用,且 payload/producer 不变。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    captured: dict[str, Any] = {}

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> Any:
            captured["payload"] = payload
            captured["producer"] = producer
            return MagicMock(name="SessionRef")

    payload = _sp_payload("brain.perceive.start")
    EventBus.set_default(bus)
    token = set_publish_session(FakeSession())
    try:
        ref = publish_via_session(payload, producer=ReflectorClass)
    finally:
        reset_publish_session(token)
        EventBus.set_default(None)

    assert captured["payload"] is payload
    assert captured["producer"] is ReflectorClass
    assert ref is not None


def test_publish_via_session_does_not_call_eventbus_when_session_set(
    bus: EventBus,
) -> None:
    """Session 已注入时,鉴权后走 Session.append,不触达 EventBus.publish。"""
    from lca_kernel.events.payloads import Category, SpineEventPayload

    # 不装载 sink,EventBus 走 zero-sink strict 路径会抛 ——
    # 但 Session 路径不走 EventBus.publish,所以此 publish 应无异常。
    payload = SpineEventPayload(
        category=Category("spine.cognition.brain.perceive.start"),
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> Any:
            return MagicMock(name="SessionRef")

    EventBus.set_default(bus)
    token = set_publish_session(FakeSession())
    try:
        from lca.plugins.events.publishers.spine_reflector_cognition.plugin import ReflectorClass

        ref = publish_via_session(payload, producer=ReflectorClass)
        assert ref is not None
    finally:
        reset_publish_session(token)
        EventBus.set_default(None)


# ── ContextVar 隔离 ─────────────────────────────────────────────────────


def test_contextvar_isolation_across_tasks() -> None:
    """两个并发 asyncio Task 内 current_publish_session 互不污染。"""
    import asyncio

    from lca.plugins.events.publishers._session_publish import (
        current_publish_session,
        reset_publish_session,
        set_publish_session,
    )

    sentinel_a = MagicMock(name="A")
    sentinel_b = MagicMock(name="B")

    async def run(sentinel: Any) -> Any:
        token = set_publish_session(sentinel)
        try:
            await asyncio.sleep(0)
            assert current_publish_session() is sentinel
            return current_publish_session()
        finally:
            reset_publish_session(token)

    async def gather_two() -> tuple[Any, Any]:
        return await asyncio.gather(run(sentinel_a), run(sentinel_b))

    a, b = asyncio.run(gather_two())
    assert a is sentinel_a
    assert b is sentinel_b
    assert current_publish_session() is None


# ── runtime Session 自动包装 ─────────────────────────────────────────────


class _Producer:
    """publisher 鉴权用 marker；Session 路径不读它。"""


def test_set_publish_session_wraps_runtime_session(bus: EventBus) -> None:
    """runtime Session 装载后 current 是 facade，append 写入 Session 日志。"""
    from lca.contracts.event import TeamDelegationCacheHit
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade
    from lca.plugins.session.runtime.session import Session

    session = Session("pub-wrap")
    EventBus.set_default(bus)
    token = set_publish_session(session)
    try:
        bound = current_publish_session()
        assert isinstance(bound, SessionBusFacade)
        assert bound.session is session

        payload = TeamDelegationCacheHit(callee_role="worker", subtask="t", step=1)
        ref = publish_via_session(payload, producer=DelegationCachePlugin)
        assert ref.category == "team.delegation.cache_hit"
        assert ref.event_id == "pub-wrap:0"
        event = session.event_at(0)
        assert event is not None
        assert event.type == "team.delegation.cache_hit"
        assert event.data["callee_role"] == "worker"
        assert "category" not in event.data
    finally:
        reset_publish_session(token)
        EventBus.set_default(None)


def test_set_publish_session_does_not_rewrap_facade() -> None:
    from lca.plugins.session.runtime.bus_facade import SessionBusFacade
    from lca.plugins.session.runtime.session import Session

    facade = SessionBusFacade(Session("pub-once"))
    token = set_publish_session(facade)
    try:
        assert current_publish_session() is facade
    finally:
        reset_publish_session(token)
