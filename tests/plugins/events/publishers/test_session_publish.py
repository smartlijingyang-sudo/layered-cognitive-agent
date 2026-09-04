"""publish_via_session helper 单测（ADR-0183 PR-3d-sample）。

helper 行为契约:
1. 无 active Session 时 → fallback EventBus.default().publish,返回真实 EventRef;
2. 有 active Session 时 → Session.append(payload, producer=...),返回 Session 给的 EventRef;
3. ContextVar set/reset 隔离:跨 token reset 行为正确;
4. Session.append 拿到的 payload/producer 与调用方传入一致。

helper 不做鉴权 / schema 校验;鉴权由 EventBus 在 fallback 路径负责。
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


# ── fallback 路径(无 Session) ─────────────────────────────────────────────


def test_publish_via_session_falls_back_to_eventbus(bus: EventBus) -> None:
    """无 Session 时 → 走 EventBus.default().publish,返回真实 EventRef。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    EventBus.set_default(bus)
    try:
        ref = publish_via_session(
            _sp_payload("brain.perceive.start"),
            producer=ReflectorClass,
        )
        assert ref.category == "spine.cognition.brain.perceive.start"
        assert ref.event_id
    finally:
        EventBus.set_default(None)


# ── Session 路径 ─────────────────────────────────────────────────────────


def test_publish_via_session_delegates_to_session_when_set(bus: EventBus) -> None:
    """有 Session 时 → Session.append(payload, producer=...) 被调用,且 payload/producer 不变。"""
    from lca.plugins.events.publishers.spine_loop_cursor.plugin import (
        LoopCursorPlugin,
    )

    captured: dict[str, Any] = {}

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> Any:
            captured["payload"] = payload
            captured["producer"] = producer
            return MagicMock(name="SessionRef")

    payload = _sp_payload("brain.perceive.start")
    token = set_publish_session(FakeSession())
    try:
        ref = publish_via_session(payload, producer=LoopCursorPlugin)
    finally:
        reset_publish_session(token)

    assert captured["payload"] is payload
    assert captured["producer"] is LoopCursorPlugin
    assert ref is not None


def test_publish_via_session_does_not_call_eventbus_when_session_set(
    bus: EventBus,
) -> None:
    """Session 已注入时,EventBus.default() 不应被触达。"""
    from lca_kernel.events.payloads import Category, SpineEventPayload

    # 不装载 sink,EventBus 走 zero-sink strict 路径会抛 ——
    # 但 Session 路径不走 EventBus,所以此 publish 应无异常。
    payload = SpineEventPayload(
        category=Category("spine.cognition.brain.perceive.start"),
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )

    class FakeSession:
        def append(self, payload: Any, *, producer: Any) -> Any:
            return MagicMock(name="SessionRef")

    token = set_publish_session(FakeSession())
    try:
        # 不应抛错,也不应触达 EventBus(EventNoSinkError 是 fallback 路径才会看到的)。
        ref = publish_via_session(payload, producer=FakeSession)
        assert ref is not None
    finally:
        reset_publish_session(token)


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
