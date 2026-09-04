"""assistant.webserver_bridge tests（ADR-0187 §3 D7/D12 前端投影）。

覆盖：

- ``_extract_agent_id`` 解析 superjson TRPC 响应（正常 / 缺字段 / 非 JSON）；
- ``register`` 未启用（``lobehub_url`` 空）⇒ 返回 ``None``（fail-soft）；
- ``register`` 200 + 合法响应 ⇒ 返回 ``agt_*``；
- ``register`` 非 200 / 网络错误 ⇒ 返回 ``None``（不抛、不阻断创建）；
- 请求体形状：TRPC createAgent + ``agencyConfig.lcaAssistantId`` 映射。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from lca.plugins.assistant.webserver_bridge import (
    AssistantFrontendBridge,
    _extract_agent_id,
)


class TestExtractAgentId:
    def test_extracts_from_superjson_envelope(self) -> None:
        text = '{"result": {"data": {"json": {"agentId": "agt_abc123"}}}}'
        assert _extract_agent_id(text) == "agt_abc123"

    def test_returns_none_when_agent_id_missing(self) -> None:
        assert _extract_agent_id('{"result": {"data": {"json": {}}}}') is None

    def test_returns_none_for_invalid_json(self) -> None:
        assert _extract_agent_id("not json") is None

    def test_returns_none_for_empty_agent_id(self) -> None:
        text = '{"result": {"data": {"json": {"agentId": ""}}}}'
        assert _extract_agent_id(text) is None


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


@pytest.fixture
def bridge() -> AssistantFrontendBridge:
    return AssistantFrontendBridge(lobehub_url="http://127.0.0.1:3010")


class TestRegister:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self) -> None:
        disabled = AssistantFrontendBridge(lobehub_url="")
        result = await disabled.register(
            assistant_id="asst_x", name="n", description="d", emoji="🤖", system_role="s"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_agent_id(self, bridge: AssistantFrontendBridge) -> None:
        ok = _FakeResponse(200, '{"result": {"data": {"json": {"agentId": "agt_ok"}}}}')
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=ok)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=fake_client):
            result = await bridge.register(
                assistant_id="asst_x", name="n", description="d", emoji="🔍", system_role="s"
            )
        assert result == "agt_ok"

    @pytest.mark.asyncio
    async def test_request_body_carries_mapping(self, bridge: AssistantFrontendBridge) -> None:
        ok = _FakeResponse(200, '{"result": {"data": {"json": {"agentId": "agt_ok"}}}}')
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=ok)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=fake_client):
            await bridge.register(
                assistant_id="asst_map",
                name="研究",
                description="研究职责",
                emoji="🔍",
                system_role="SOUL 内容",
            )
        _, kwargs = fake_client.post.call_args
        body: dict[str, Any] = kwargs["json"]
        config = body["json"]["config"]
        assert config["title"] == "研究"
        assert config["avatar"] == "🔍"
        assert config["model"] == "solo"
        assert config["agencyConfig"]["lcaAssistantId"] == "asst_map"
        assert config["systemRole"] == "SOUL 内容"

    @pytest.mark.asyncio
    async def test_bad_status_returns_none(self, bridge: AssistantFrontendBridge) -> None:
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=_FakeResponse(500, "boom"))
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=fake_client):
            result = await bridge.register(
                assistant_id="asst_x", name="n", description="d", emoji="🤖", system_role="s"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self, bridge: AssistantFrontendBridge) -> None:
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(side_effect=RuntimeError("connection refused"))
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=fake_client):
            result = await bridge.register(
                assistant_id="asst_x", name="n", description="d", emoji="🤖", system_role="s"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_system_role_truncated(self, bridge: AssistantFrontendBridge) -> None:
        ok = _FakeResponse(200, '{"result": {"data": {"json": {"agentId": "agt_ok"}}}}')
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=ok)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=fake_client):
            await bridge.register(
                assistant_id="asst_x",
                name="n",
                description="d",
                emoji="🤖",
                system_role="字" * 5000,
            )
        _, kwargs = fake_client.post.call_args
        assert len(kwargs["json"]["json"]["config"]["systemRole"]) <= 2000
