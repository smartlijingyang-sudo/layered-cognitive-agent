"""TeamOrchestrator —— 管理团队的组织形态与通信信道。

L3 层职责：
    作为团队级组合根，TeamOrchestrator 负责：
    1. 通过 OrchestrationStrategyRegistry 解析编排策略（注册表模式，无 if/elif）
    2. 注入共享记忆（SharedStoreBindable 单路径，ADR-0016）
    3. 绑定 Supervisor 的全部能力（transport / roster / hooks / guard）
       —— supervisor 是组合期角色，不是独立类型
    所有策略分发委托给 OrchestrationStrategy 实现，L3 不含业务逻辑。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.enums import CompletionPolicyName
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import (
    AgentTransport,
    OrchestrationContext,
    OrchestrationStrategy,
    SharedMemoryStore,
    TeamEntrypoint,
)
from lca.contracts.protocols.capabilities import (
    ExposesComponents,
    SharedStoreBindable,
)
from lca.contracts.protocols.cognition import CompletionPolicy
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.layer0_infra.component_registry import get_global_registry
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.simple_agent import SimpleAgent
from lca.layer3_agent.supervisor_role import SupervisionCapabilities, apply_supervision


class TeamOrchestrator(TeamEntrypoint):
    """
    支持多种组织形态（hierarchical / sequential / parallel / graph / debate），
    通过 OrchestrationStrategyRegistry 解析策略，不再 if/elif 硬编码。

    共享记忆通过 SharedStoreBindable 单路径注入（ADR-0016）：
    MemorySystem 层级共享，Agent 通过 perceive/update/query 统一访问。
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
            self._inject_shared_store()

        # ── 组合期：创建 ledger + 绑定 supervisor 全部能力 ──
        team_progress: DelegationLedgerProtocol | None = None
        if supervisor is not None:
            team_progress = self._create_ledger(members)
            policy = self._resolve_completion_policy(config)
            caps = SupervisionCapabilities(
                transport=transport,
                roster_desc=roster_desc,
                ledger=team_progress,
                completion_policy=policy,
            )
            apply_supervision(supervisor, caps)

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
        mandatory_roles = frozenset(m.role_profile.role for m in members)
        reg = get_global_registry()
        ledger_cls = reg.require("delegation_ledger", "default")
        return cast("DelegationLedgerProtocol", ledger_cls(mandatory_roles=mandatory_roles))

    @staticmethod
    def _resolve_completion_policy(config: TeamConfig) -> CompletionPolicy | None:
        """从全局注册表解析 completion policy 工厂并实例化。"""
        policy_name = config.completion_policy if config else CompletionPolicyName.ROSTER_COVERAGE
        if policy_name == CompletionPolicyName.NONE:
            return None
        reg = get_global_registry()
        policy_factory = reg.require("completion_policy", policy_name)
        return cast("CompletionPolicy", policy_factory())

    # ── 共享记忆 ────────────────────────────────────────────

    def _inject_shared_store(self) -> None:
        """将共享 store 通过 SharedStoreBindable 协议分发给每个成员。"""
        if self._shared_store is None:
            return
        for member in self.members:
            if isinstance(member.runtime, ExposesComponents):
                memory = member.runtime.memory
                if isinstance(memory, SharedStoreBindable):
                    memory.bind_shared_store(self._shared_store)

    # ── 执行入口 ────────────────────────────────────────────

    async def run(
        self,
        objective: str | object,
        ctx: object | None = None,
    ) -> Result:
        """按 TeamConfig.process 类型选择组织形态执行：dispatch 语义由 strategy 承担。"""
        del ctx  # InvocationContext 预留
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
