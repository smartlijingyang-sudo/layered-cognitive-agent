"""TeamOrchestrator —— 管理团队的组织形态与通信信道。

L3 层职责：
    作为团队级组合根，TeamOrchestrator 负责：
    1. 通过 OrchestrationStrategyRegistry 解析编排策略（注册表模式，无 if/elif）
    2. 注入共享记忆双路径（SharedStoreBindable + SharedMemoryTool）
    3. 绑定 Supervisor 的 transport / roster 能力
    所有策略分发委托给 OrchestrationStrategy 实现，L3 不含业务逻辑。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.protocols import (
    AgentTransport,
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    SupervisorProtocol,
    TeamEntrypoint,
    ToolRegistry,
)
from lca.contracts.protocols.capabilities import RosterAware, SharedStoreBindable, TransportBindable
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer1_cognitive.memory.shared_memory_tool import SharedMemoryTool
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.supervisor import Supervisor


class TeamOrchestrator(TeamEntrypoint):
    """
    支持多种组织形态（hierarchical / sequential / parallel / graph / debate），
    通过 OrchestrationStrategyRegistry 解析策略，不再 if/elif 硬编码。

    共享记忆注入双路径（ADR-0016）：
    1. SharedStoreBindable 协议绑定 —— MemorySystem 层级共享（CoALA）
    2. SharedMemoryTool 注入成员 ToolRegistry —— 单体循环内经 use_tool 访问
    """

    def __init__(
        self,
        members: list[BaseAgent],
        config: TeamConfig,
        supervisor: Supervisor | None = None,
        transport: AgentTransport | None = None,
        roster_desc: str = "",
        strategy: OrchestrationStrategy | None = None,
        team_id: str = "",
    ) -> None:
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.roster_desc = roster_desc
        self.team_id = team_id or f"team-{config.process}"

        if strategy is not None:
            self._strategy = strategy
        else:
            registry = get_global_orchestration_registry()
            self._strategy = registry.resolve(config.process)

        self._shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            self._shared_store = TeamSharedMemoryStore(config.shared_memory_layers)
            self._inject_shared_memory()

        self._context = OrchestrationContext(
            members=members,
            config=config,
            supervisor=cast("SupervisorProtocol | None", supervisor),
            transport=transport,
            roster_desc=roster_desc,
            team_id=self.team_id,
            shared_memory=self._shared_store,
        )

        if supervisor is not None and transport is not None:
            self._bind_supervisor_capabilities(supervisor, transport, roster_desc)

    def _inject_shared_memory(self) -> None:
        """将共享记忆 store + SharedMemoryTool 分发给每个成员。"""
        if self._shared_store is None:
            return
        for member in self.members:
            memory = getattr(member.runtime, "memory", None)
            if memory is not None and isinstance(memory, SharedStoreBindable):
                memory.bind_shared_store(self._shared_store)
            self._register_shared_memory_tool(member)

    @staticmethod
    def _bind_supervisor_capabilities(
        supervisor: Supervisor, transport: AgentTransport, roster_desc: str
    ) -> None:
        """在组合根完成 Supervisor 的 transport / roster 绑定，避免 L3 越层访问。"""
        body = getattr(supervisor.runtime, "body", None)
        if body is not None and isinstance(body, TransportBindable):
            body.bind_transport(transport)
        brain = getattr(supervisor.runtime, "brain", None)
        if brain is not None and isinstance(brain, RosterAware):
            brain.set_team_roster(roster_desc)

    def _register_shared_memory_tool(self, member: BaseAgent) -> None:
        """若成员 Body 暴露 tool_registry，注册绑定同一 store 的 SharedMemoryTool。"""
        store = self._shared_store
        if store is None:
            return
        body = getattr(member.runtime, "body", None)
        if body is None:
            return
        registry: ToolRegistry | None = getattr(body, "tool_registry", None)
        if registry is None:
            return
        tool = SharedMemoryTool(store, team_id=self.team_id)
        registry.register(tool)

    async def run(
        self,
        objective: str | object,
        ctx: object | None = None,
    ) -> Result:
        """按 TeamConfig.process 类型选择组织形态执行：dispatch 语义由 strategy 承担。"""
        del ctx  # InvocationContext 预留
        from lca.contracts.message import AgentMessage, agent_message_as_text

        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
