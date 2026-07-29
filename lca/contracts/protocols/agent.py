"""L3 Agent 级入口协议。
agent.py 的极简是刻意的克制——L3 门面协议不应该关心"怎么想"，只关心"怎么进/怎么出"
命名注记（ADR-0017）：本文件两个协议曾用名 AgentEntrypoint / TeamEntrypoint，
与 L2 的 Runtime（认知循环协议）容易混淆——三者语义不同：
  - Runtime      : "每一步怎么循环"（L2, runtime.py）
  - AgentEntrypoint / TeamEntrypoint : "整体入口长什么样"（L3, 本文件）
新代码请使用 AgentEntrypoint / TeamEntrypoint；旧名保留一个发布周期的 alias。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.invocation import InvocationContext
from lca.contracts.message import AgentMessage
from lca.contracts.result import Result
from lca.contracts.state import StateSnapshot


@runtime_checkable
class AgentEntrypoint(Protocol):
    async def execute(
        self, task: str | AgentMessage, ctx: InvocationContext | None = None
    ) -> Result: ...
    async def resume(
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result: ...
    async def cancel(self) -> None: ...


@runtime_checkable
class TeamEntrypoint(Protocol):
    """团队级入口契约：接收 objective，跑完编排后返回 Result。

    区别于 AgentEntrypoint.execute：语义单位是"团队"而非单个 Agent，
    不携带 max_steps（预算下沉到各 BaseAgent 自身）。
    """

    async def run(
        self, objective: str | AgentMessage, ctx: InvocationContext | None = None
    ) -> Result: ...
