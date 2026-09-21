# tests/reflect/test_typesafe_memory_filter.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lca.infrastructure.memory.pre_filter.typesafe_filter import TypeSafeMemoryFilter


@pytest.mark.asyncio
async def test_typesafe_filter_high_prob():
    mock_resp = AsyncMock()
    mock_resp.nouls = {"should_memorize": type("NoulResult", (), {"noul": 0.85})()}

    mock_client = AsyncMock()
    mock_client.system_one.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("lca.infrastructure.memory.pre_filter.typesafe_filter.AsyncTypeSafeClient", return_value=mock_client):
        filter_ = TypeSafeMemoryFilter(api_key="test_key", threshold=0.65)
        decision = await filter_.evaluate("以后关于架构的讨论都使用精简风格")
        assert decision.should_extract is True
        assert decision.source == "typesafe"
        assert decision.confidence == 0.85
        assert "noul_prob:0.85" in decision.reason


@pytest.mark.asyncio
async def test_typesafe_filter_low_prob():
    mock_resp = AsyncMock()
    mock_resp.nouls = {"should_memorize": type("NoulResult", (), {"noul": 0.20})()}

    mock_client = AsyncMock()
    mock_client.system_one.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("lca.infrastructure.memory.pre_filter.typesafe_filter.AsyncTypeSafeClient", return_value=mock_client):
        filter_ = TypeSafeMemoryFilter(api_key="test_key", threshold=0.65)
        decision = await filter_.evaluate("今天上海天气怎么样")
        assert decision.should_extract is False
        assert decision.source == "typesafe"
        assert decision.confidence == 0.20


@pytest.mark.asyncio
async def test_typesafe_filter_missing_key():
    filter_ = TypeSafeMemoryFilter(api_key="")
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        await filter_.evaluate("测试文本")
