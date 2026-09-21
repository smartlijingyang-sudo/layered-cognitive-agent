# tests/reflect/test_fallback_memory_filter.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from lca.contracts.protocols.memory.filter import FilterDecision
from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter


@pytest.mark.asyncio
async def test_fallback_on_typesafe_error():
    primary = AsyncMock()
    primary.evaluate.side_effect = RuntimeError("429 Too Many Requests: Quota Exceeded")
    fallback = AsyncMock()
    fallback.evaluate.return_value = FilterDecision(True, "matched_tokens:我是", "regex", 0.8)

    filter_ = FallbackMemoryFilter(
        primary=primary,
        fallback=fallback,
        enabled=True,
        circuit_breaker_seconds=600.0,
    )
    decision = await filter_.evaluate("我是测试")

    assert decision.source == "circuit_breaker"
    assert "tripped_circuit_fallback" in decision.reason
    assert filter_.is_circuit_open() is True
    assert primary.evaluate.call_count == 1
    assert fallback.evaluate.call_count == 1

    # 第二次直接走熔断保底，不调 primary
    decision2 = await filter_.evaluate("第二次测试")
    assert decision2.source == "circuit_breaker"
    assert "circuit_open_fallback" in decision2.reason
    assert primary.evaluate.call_count == 1
    assert fallback.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_fallback_when_disabled():
    primary = AsyncMock()
    fallback = AsyncMock()
    fallback.evaluate.return_value = FilterDecision(True, "matched", "regex", 0.8)

    filter_ = FallbackMemoryFilter(primary=primary, fallback=fallback, enabled=False)
    decision = await filter_.evaluate("测试")

    assert decision.source == "regex"
    assert primary.evaluate.call_count == 0
    assert fallback.evaluate.call_count == 1


@pytest.mark.asyncio
async def test_fallback_when_no_api_key_and_no_primary(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    fallback = AsyncMock()
    fallback.evaluate.return_value = FilterDecision(False, "none", "regex", 0.0)

    filter_ = FallbackMemoryFilter(primary=None, fallback=fallback, enabled=True)
    decision = await filter_.evaluate("测试")

    assert decision.source == "regex"
    assert fallback.evaluate.call_count == 1


@pytest.mark.asyncio
async def test_circuit_recovery_after_cooldown():
    primary = AsyncMock()
    # 第一次报错，第二次恢复成功
    primary.evaluate.side_effect = [
        RuntimeError("Timeout"),
        FilterDecision(True, "noul_prob:0.90", "typesafe", 0.90),
    ]
    fallback = AsyncMock()
    fallback.evaluate.return_value = FilterDecision(True, "regex", "regex", 0.8)

    # 极短熔断时间 0.01 秒
    filter_ = FallbackMemoryFilter(
        primary=primary,
        fallback=fallback,
        enabled=True,
        circuit_breaker_seconds=0.01,
    )
    # 第一次报错触发熔断
    d1 = await filter_.evaluate("测试1")
    assert d1.source == "circuit_breaker"
    assert filter_.is_circuit_open() is True

    # 等待熔断结束
    import asyncio

    await asyncio.sleep(0.02)
    assert filter_.is_circuit_open() is False

    # 第二次尝试，恢复正常
    d2 = await filter_.evaluate("测试2")
    assert d2.source == "typesafe"
    assert d2.confidence == 0.90
