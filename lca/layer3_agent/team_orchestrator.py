"""TeamOrchestrator —— 管理团队的组织形态与通信信道。"""

from __future__ import annotations

from lca.contracts.protocols import (
    AgentTransport,
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    TeamRuntime,
    ToolRegistry,
)
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.shared_memory.shared_memory_tool import SharedMemoryTool
from lca.layer3_agent.supervisor import Supervisor


class TeamOrchestrator(TeamRuntime):
    """
    支持多种组织形态（hierarchical / sequential / parallel / graph / debate），
    通过 OrchestrationStrategyRegistry 解析策略，不再 if/elif 硬编码。

    共享记忆注入双路径（ADR-0016）：
    1. Runtime.configure(shared_memory=...) —— MemorySystem 层级共享（CoALA）
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
    ):
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
            supervisor=supervisor,
            transport=transport,
            roster_desc=roster_desc,
            team_id=self.team_id,
            shared_memory=self._shared_store,
        )

    def _inject_shared_memory(self) -> None:
        """将共享记忆 store + SharedMemoryTool 分发给每个成员。"""
        if self._shared_store is None:
            return
        for member in self.members:
            member.runtime.configure(shared_memory=self._shared_store)
            self._register_shared_memory_tool(member)

    def _register_shared_memory_tool(self, member: BaseAgent) -> None:
        """若成员 Body 暴露 tool_registry，注册绑定同一 store 的 SharedMemoryTool。"""
        body = getattr(member.runtime, "body", None)
        if body is None:
            return
        registry: ToolRegistry | None = getattr(body, "tool_registry", None)
        if registry is None:
            return
        tool = SharedMemoryTool(self._shared_store, team_id=self.team_id)  # type: ignore[arg-type]
        registry.register(tool)

    async def run(self, objective: str) -> Result:
        """按 TeamConfig.process 类型选择组织形态执行：dispatch 语义由 strategy 承担。"""
        return await self._strategy.run(self._context, objective)
