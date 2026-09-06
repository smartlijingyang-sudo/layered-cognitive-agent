"""A2ATransport + MCPTransport 测试 —— 协议合规、结构校验、mock HTTP。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import AgentTransport
from lca.infrastructure.transport.a2a_transport import A2ATransport
from lca.infrastructure.transport.mcp_transport import MCPTransport


class TestA2ATransportProtocol(unittest.TestCase):
    """A2ATransport 满足 AgentTransport Protocol。"""

    def test_satisfies_protocol(self) -> None:
        transport = A2ATransport()
        self.assertIsInstance(transport, AgentTransport)

    def test_protocol_name(self) -> None:
        transport = A2ATransport()
        self.assertEqual(transport.protocol_name, "a2a")


class TestA2ATransportEndpointResolution(unittest.TestCase):
    """AgentCard 端点解析。"""

    def test_string_agent_card(self) -> None:
        transport = A2ATransport()
        self.assertEqual(
            transport._resolve_endpoint("http://localhost:8080"), "http://localhost:8080"
        )

    def test_object_with_url(self) -> None:
        transport = A2ATransport()
        card = MagicMock()
        card.url = "http://agent.example.com"
        self.assertEqual(transport._resolve_endpoint(card), "http://agent.example.com")

    def test_object_with_endpoint(self) -> None:
        transport = A2ATransport()
        card = MagicMock(spec=[])
        card.endpoint = "http://agent.example.com/a2a"
        self.assertEqual(transport._resolve_endpoint(card), "http://agent.example.com/a2a")

    def test_default_endpoint_fallback(self) -> None:
        transport = A2ATransport(default_endpoint="http://default:8080")
        card = MagicMock(spec=[])
        self.assertEqual(transport._resolve_endpoint(card), "http://default:8080")

    def test_no_endpoint_raises(self) -> None:
        transport = A2ATransport()
        card = MagicMock(spec=[])
        with self.assertRaises(ValueError):
            transport._resolve_endpoint(card)


class TestA2ATransportSendTask(unittest.IsolatedAsyncioTestCase):
    """send_task 行为（mock HTTP）。"""

    async def test_send_task_posts_to_endpoint(self) -> None:
        transport = A2ATransport()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        transport._client = mock_client

        task_id = await transport.send_task("http://agent:8080", "do something", [])

        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        self.assertIn("/tasks/send", call_args[0][0])
        self.assertTrue(task_id.startswith("a2a_task_"))

    async def test_send_task_with_context_refs(self) -> None:
        transport = A2ATransport()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        transport._client = mock_client

        await transport.send_task("http://agent:8080", "task", ["ref1", "ref2"])

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        parts = payload["message"]["parts"]
        ref_parts = [p for p in parts if p.get("kind") == "reference"]
        self.assertEqual(len(ref_parts), 2)

    async def test_send_task_http_error_stored(self) -> None:
        import httpx

        transport = A2ATransport()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        transport._client = mock_client

        task_id = await transport.send_task("http://agent:8080", "task", [])

        status = await transport.poll_status(task_id)
        self.assertEqual(status, "failed")


class TestA2ATransportPollAndReceive(unittest.IsolatedAsyncioTestCase):
    """poll_status + receive_result（mock HTTP）。"""

    async def test_poll_completed(self) -> None:
        transport = A2ATransport()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={"status": {"state": "completed"}, "artifacts": []}
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        transport._client = mock_client
        transport._task_endpoints["task_1"] = "http://agent:8080"

        status = await transport.poll_status("task_1")
        self.assertEqual(status, "completed")

    async def test_receive_result_extracts_text(self) -> None:
        transport = A2ATransport()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "status": {"state": "completed"},
                "artifacts": [
                    {"parts": [{"kind": "text", "text": "Hello from A2A"}]},
                ],
            }
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        transport._client = mock_client
        transport._task_endpoints["task_1"] = "http://agent:8080"

        obs = await transport.receive_result("task_1")
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "Hello from A2A")

    async def test_receive_result_extracts_file_parts(self) -> None:
        transport = A2ATransport()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "status": {"state": "completed"},
                "artifacts": [
                    {
                        "parts": [
                            {"kind": "text", "text": "see file"},
                            {
                                "kind": "file",
                                "file": {
                                    "name": "chart.html",
                                    "mimeType": "text/html",
                                    "uri": "https://cdn.example/chart.html",
                                    "sizeBytes": 42,
                                },
                            },
                        ]
                    },
                ],
            }
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        transport._client = mock_client
        transport._task_endpoints["task_file"] = "http://agent:8080"

        obs = await transport.receive_result("task_file")
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload, "see file")
        files = obs.extra.get("files")
        self.assertIsInstance(files, list)
        self.assertEqual(files[0]["name"], "chart.html")
        self.assertEqual(files[0]["mimeType"], "text/html")
        self.assertEqual(files[0]["url"], "https://cdn.example/chart.html")


class TestMCPTransportProtocol(unittest.TestCase):
    """MCPTransport 满足 AgentTransport Protocol。"""

    def test_satisfies_protocol(self) -> None:
        transport = MCPTransport()
        self.assertIsInstance(transport, AgentTransport)

    def test_protocol_name(self) -> None:
        transport = MCPTransport()
        self.assertEqual(transport.protocol_name, "mcp")


class TestMCPTransportConfig(unittest.TestCase):
    """AgentCard 配置解析。"""

    def test_string_agent_card(self) -> None:
        transport = MCPTransport()
        url, tool = transport._resolve_config("http://mcp-server:8080")
        self.assertEqual(url, "http://mcp-server:8080")
        self.assertEqual(tool, "execute_task")

    def test_object_with_server_url(self) -> None:
        transport = MCPTransport()
        card = MagicMock()
        card.server_url = "http://mcp:8080"
        card.tool_name = "my_tool"
        url, tool = transport._resolve_config(card)
        self.assertEqual(url, "http://mcp:8080")
        self.assertEqual(tool, "my_tool")

    def test_no_url_raises(self) -> None:
        transport = MCPTransport()
        card = MagicMock(spec=[])
        with self.assertRaises(ValueError):
            transport._resolve_config(card)


class TestMCPTransportWithoutSDK(unittest.IsolatedAsyncioTestCase):
    """MCP SDK 未安装时的行为。"""

    async def test_send_task_raises_without_sdk(self) -> None:
        transport = MCPTransport()

        with patch.dict(
            "sys.modules", {"mcp": None, "mcp.client": None, "mcp.client.streamable_http": None}
        ):
            with self.assertRaises(NotImplementedError) as ctx:
                await transport.send_task("http://mcp:8080", "task", [])
            self.assertIn("mcp", str(ctx.exception).lower())


class TestTransportRegistration(unittest.TestCase):
    """A2A/MCP 已注册到默认 TransportRegistry。"""

    def test_a2a_registered(self) -> None:
        from lca.plugins.composer.collaboration.team_transport import (
            build_default_transport_registry,
        )

        registry = build_default_transport_registry()
        transport = registry.resolve("a2a")
        self.assertIsInstance(transport, A2ATransport)

    def test_mcp_registered(self) -> None:
        from lca.plugins.composer.collaboration.team_transport import (
            build_default_transport_registry,
        )

        registry = build_default_transport_registry()
        transport = registry.resolve("mcp")
        self.assertIsInstance(transport, MCPTransport)


if __name__ == "__main__":
    unittest.main()
