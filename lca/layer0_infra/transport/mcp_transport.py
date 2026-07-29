"""MCPTransport —— Model Context Protocol 传输实现。

通过 MCP client SDK 与远程 MCP Server 通信，实现跨框架 Agent 互操作。
MCP 主要用于工具调用场景，此处将 Agent 任务映射为 MCP 工具调用。

依赖 mcp Python SDK（可选依赖，未安装时给出明确报错）。
"""

from __future__ import annotations

import contextlib
from typing import Any

from lca.contracts.decision import AgentCard, Observation
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentTransport

_MCP_SDK_MISSING_MSG = "MCP Python SDK 未安装。请运行: pip install mcp 或 uv add mcp"


class MCPTransport(AgentTransport):
    """MCP 协议传输实现。

    将 Agent 任务映射为 MCP 工具调用。agent_card 可以是：
    - 字符串：作为 MCP server URL 或 server name
    - 包含 server_url/tool_name 属性的对象

    注意：MCP SDK 是可选依赖，未安装时 send_task 会抛出明确错误。
    """

    protocol_name: str = "mcp"

    def __init__(
        self,
        default_server_url: str | None = None,
        default_tool_name: str = "execute_task",
    ) -> None:
        self._default_server_url = default_server_url
        self._default_tool_name = default_tool_name
        self._task_results: dict[str, Observation] = {}
        self._task_statuses: dict[str, str] = {}
        self._sessions: dict[str, Any] = {}

    def _resolve_config(self, agent_card: AgentCard | str) -> tuple[str, str]:
        """从 agent_card 解析 server_url 和 tool_name。"""
        if isinstance(agent_card, str):
            return agent_card, self._default_tool_name
        server_url = (
            getattr(agent_card, "server_url", None)
            or getattr(agent_card, "url", None)
            or self._default_server_url
        )
        tool_name = getattr(agent_card, "tool_name", self._default_tool_name)
        if server_url is None:
            raise ValueError(f"无法从 AgentCard 解析 MCP server URL: {agent_card!r}")
        return str(server_url), str(tool_name)

    async def _get_mcp_session(self, server_url: str) -> Any:
        """获取或创建 MCP client session。"""
        if server_url in self._sessions:
            return self._sessions[server_url]

        try:
            # mcp 是可选依赖，未安装时由 except ImportError 处理
            from mcp import ClientSession  # type: ignore[import-not-found]  # optional dep
            from mcp.client.streamable_http import (  # type: ignore[import-not-found]  # optional dep
                streamablehttp_client,
            )
        except ImportError as exc:
            raise NotImplementedError(_MCP_SDK_MISSING_MSG) from exc

        read_stream, write_stream, _ = await streamablehttp_client(server_url).__aenter__()
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        self._sessions[server_url] = session
        return session

    async def send_task(
        self, agent_card: AgentCard | str, subtask: str, context_refs: list[str]
    ) -> str:
        task_id = new_id("mcp_task")
        server_url, tool_name = self._resolve_config(agent_card)

        try:
            session = await self._get_mcp_session(server_url)
            arguments: dict[str, Any] = {"task": subtask}
            if context_refs:
                arguments["context_refs"] = context_refs

            result = await session.call_tool(tool_name, arguments=arguments)

            output_text = ""
            for content in result.content:
                if hasattr(content, "text"):
                    output_text += content.text

            is_error = getattr(result, "isError", False)
            self._task_results[task_id] = Observation(
                observation_id=new_id("obs"),
                success=not is_error,
                payload=output_text or None,
                error=output_text if is_error else None,
                extra={"mcp_tool": tool_name, "mcp_server": server_url},
            )
            self._task_statuses[task_id] = TaskStatus.COMPLETED

        except NotImplementedError:
            raise
        except Exception as exc:
            # Broad catch: MCP SDK may raise arbitrary transport errors;
            # convert to a failed Observation to avoid crashing the agent loop.
            self._task_results[task_id] = Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"MCP send_task failed: {exc}",
            )
            self._task_statuses[task_id] = TaskStatus.FAILED

        return task_id

    async def poll_status(self, task_id: str) -> str:
        return self._task_statuses.get(task_id, "completed")

    async def receive_result(self, task_id: str) -> Observation:
        return self._task_results.get(
            task_id,
            Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"MCP task not found: {task_id}",
            ),
        )

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        """MCP 任务在 send_task 阶段通常已同步完成，直接取结果。"""
        return await self.receive_result(task_id)

    async def close(self) -> None:
        for session in self._sessions.values():
            with contextlib.suppress(Exception):
                await session.__aexit__(None, None, None)
        self._sessions.clear()
