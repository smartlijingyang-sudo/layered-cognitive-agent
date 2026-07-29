"""A2ATransport —— Google A2A 协议传输实现。

通过 HTTP 调用远程 A2A Agent 端点，实现跨框架 Agent 互操作。
依赖 httpx（已加入项目依赖）。

A2A 协议核心流程：
1. 解析 AgentCard 获取端点 URL
2. send_task: POST 到 /tasks/send 创建异步任务
3. poll_status: GET /tasks/{task_id} 查询状态
4. receive_result: 从任务结果中提取 Observation
"""

from __future__ import annotations

from typing import Any

import httpx

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.protocols import AgentTransport


class A2ATransport(AgentTransport):
    """Google A2A 协议传输实现。

    通过 HTTP 与远程 A2A Agent 通信。AgentCard 可以是：
    - 字符串：直接作为 endpoint URL
    - 包含 url/endpoint 属性的对象：提取 URL
    """

    protocol_name: str = "a2a"

    def __init__(
        self,
        timeout_s: float = 30.0,
        default_endpoint: str | None = None,
    ) -> None:
        self._timeout = timeout_s
        self._default_endpoint = default_endpoint
        self._task_endpoints: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _resolve_endpoint(self, agent_card: Any) -> str:
        if isinstance(agent_card, str):
            return agent_card
        if hasattr(agent_card, "url"):
            return str(agent_card.url)
        if hasattr(agent_card, "endpoint"):
            return str(agent_card.endpoint)
        if self._default_endpoint:
            return self._default_endpoint
        raise ValueError(f"无法从 AgentCard 解析 A2A 端点 URL: {agent_card!r}")

    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str:
        endpoint = self._resolve_endpoint(agent_card)
        task_id = new_id("a2a_task")
        self._task_endpoints[task_id] = endpoint

        client = await self._get_client()
        payload: dict[str, Any] = {
            "task_id": task_id,
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": subtask}],
            },
        }
        if context_refs:
            parts = payload["message"]["parts"]
            parts.extend({"kind": "reference", "ref": ref} for ref in context_refs)

        try:
            response = await client.post(f"{endpoint}/tasks/send", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self._task_endpoints[task_id] = f"error:{exc}"

        return task_id

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        """HTTP 轮询等待任务完成。"""
        import asyncio

        poll_interval = 0.1
        elapsed = 0.0
        while True:
            status = await self.poll_status(task_id)
            if status != "working":
                return await self.receive_result(task_id)
            if timeout_s is not None and elapsed >= timeout_s:
                raise TimeoutError(f"a2a wait_result 超时: {task_id}")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    async def poll_status(self, task_id: str) -> str:
        endpoint_info = self._task_endpoints.get(task_id, "")
        if endpoint_info.startswith("error:"):
            return "failed"

        client = await self._get_client()
        try:
            response = await client.get(f"{endpoint_info}/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status", {}).get("state", "working")
            return str(status)
        except httpx.HTTPError:
            return "working"

    async def receive_result(self, task_id: str) -> Observation:
        endpoint_info = self._task_endpoints.get(task_id, "")
        if endpoint_info.startswith("error:"):
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=endpoint_info[6:],
            )

        client = await self._get_client()
        try:
            response = await client.get(f"{endpoint_info}/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()

            status = data.get("status", {})
            if status.get("state") != "completed":
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"Task not completed: state={status.get('state')}",
                )

            artifacts = data.get("artifacts", [])
            output_parts: list[str] = []
            for artifact in artifacts:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        output_parts.append(part.get("text", ""))

            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload="\n".join(output_parts) if output_parts else None,
                extra={"a2a_task_id": task_id, "raw_response": data},
            )
        except httpx.HTTPError as exc:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"A2A receive_result failed: {exc}",
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
