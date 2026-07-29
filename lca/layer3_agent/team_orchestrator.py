"""TeamOrchestrator —— 管理团队的组织形态与通信信道。

L3 层职责：
    作为团队级组合根，TeamOrchestrator 负责：
    1. 通过 OrchestrationStrategyRegistry 解析编排策略（注册表模式，无 if/elif）
    2. 注入共享记忆双路径（SharedStoreBindable + SharedMemoryTool）
    3. 绑定 Supervisor 的全部能力（transport / roster / hooks / guard）
       —— supervisor 是组合期角色，不是独立类型
    所有策略分发委托给 OrchestrationStrategy 实现，L3 不含业务逻辑。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.enums import CompletionPolicyName, HookEvent
from lca.contracts.protocols import (
    AgentTransport,
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    TeamEntrypoint,
    ToolRegistry,
)
from lca.contracts.protocols.capabilities import (
    ExposesComponents,
    HookRegistryHolder,
    RosterAware,
    SharedStoreBindable,
    TransportBindable,
)
from lca.contracts.protocols.cognition import SupportsCompletionGuard
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.layer1_cognitive.memory.shared_memory_tool import SharedMemoryTool
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer1_cognitive.team_progress.progress_hooks import (
    ledger_tracking_hook,
    progress_injection_hook,
)
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.simple_agent import SimpleAgent


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
        members: list[SimpleAgent],
        config: TeamConfig,
        supervisor: SimpleAgent | None = None,
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

        # ── 组合期：创建 ledger + 绑定 supervisor 全部能力 ──
        team_progress: DelegationLedgerProtocol | None = None
        if supervisor is not None:
            team_progress = self._create_ledger(members)
            self._bind_supervisor(supervisor, transport, roster_desc, team_progress, config)

        self._context = OrchestrationContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            roster_desc=roster_desc,
            team_progress=team_progress,
            team_id=self.team_id,
            shared_memory=self._shared_store,
        )

    # ── 组合期绑定 ──────────────────────────────────────────

    @staticmethod
    def _create_ledger(members: list[SimpleAgent]) -> DelegationLedgerProtocol:
        """从全局注册表解析 DelegationLedger 并实例化。"""
        from lca.layer0_infra.component_registry import get_global_registry

        mandatory_roles = frozenset(m.role_profile.role for m in members)
        reg = get_global_registry()
        ledger_cls = reg.require("delegation_ledger", "default")
        return cast("DelegationLedgerProtocol", ledger_cls(mandatory_roles=mandatory_roles))

    @staticmethod
    def _bind_supervisor(
        supervisor: SimpleAgent,
        transport: AgentTransport | None,
        roster_desc: str,
        ledger: DelegationLedgerProtocol,
        config: TeamConfig,
    ) -> None:
        """在组合根完成 Supervisor 的全部能力绑定。

        supervisor 是角色而非类型 —— 同一个 SimpleAgent 被放入
        context.supervisor 即承担 supervisor 职责，此处一次性绑定：
        1. transport / roster（让 supervisor 感知团队拓扑）
        2. ledger tracking hook（POST_ACT 记账）
        3. progress injection hook（PRE_THINK 注入进度）
        4. completion guard（roster_coverage 确定性收尾）
        """
        rt = supervisor.runtime
        if not isinstance(rt, ExposesComponents):
            return

        # 1. transport + roster
        if transport is not None:
            body = rt.body
            if isinstance(body, TransportBindable):
                body.bind_transport(transport)
            brain = rt.brain
            if isinstance(brain, RosterAware):
                brain.set_team_roster(roster_desc)

        # 2-3. hooks
        policy_name = config.completion_policy if config else CompletionPolicyName.ROSTER_COVERAGE
        if policy_name != CompletionPolicyName.NONE and isinstance(rt, HookRegistryHolder):
            rt.hooks.register(HookEvent.POST_ACT, ledger_tracking_hook)
            rt.hooks.register(HookEvent.PRE_THINK, progress_injection_hook)

        # 4. completion guard
        if policy_name != CompletionPolicyName.NONE:
            from lca.layer0_infra.component_registry import get_global_registry

            reg = get_global_registry()
            policy_factory = reg.require("completion_policy", policy_name)
            policy = policy_factory()
            if isinstance(rt, SupportsCompletionGuard):
                rt.install_completion_guard(policy)

    # ── 共享记忆 ────────────────────────────────────────────

    def _inject_shared_memory(self) -> None:
        """将共享记忆 store + SharedMemoryTool 分发给每个成员。"""
        if self._shared_store is None:
            return
        for member in self.members:
            if isinstance(member.runtime, ExposesComponents):
                memory = member.runtime.memory
                if isinstance(memory, SharedStoreBindable):
                    memory.bind_shared_store(self._shared_store)
            self._register_shared_memory_tool(member)

    def _register_shared_memory_tool(self, member: SimpleAgent) -> None:
        """若成员 Body 暴露 tool_registry，注册绑定同一 store 的 SharedMemoryTool。"""
        store = self._shared_store
        if store is None:
            return
        if not isinstance(member.runtime, ExposesComponents):
            return
        body = member.runtime.body
        registry: ToolRegistry | None = getattr(body, "tool_registry", None)
        if registry is None:
            return
        tool = SharedMemoryTool(store, team_id=self.team_id)
        registry.register(tool)

    # ── 执行入口 ────────────────────────────────────────────

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
