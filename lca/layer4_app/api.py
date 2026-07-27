"""L4 极简开发者 API —— 三行创建 Agent，五行组建团队。

支持通过注册表名字字符串或自定义协议实例来选择组件实现，
无需修改框架源码即可替换任何可插拔组件。
"""

from __future__ import annotations

import lca.layer4_app.defaults  # noqa: F401 — 触发默认注册
from lca.contracts.protocols import (
    BrainStrategy,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    ToolProtocol,
)
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer0_infra.registry import get_global_registry
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.supervisor import Supervisor
from lca.layer3_agent.team_orchestrator import TeamOrchestrator


class Agent:
    """
    三行上手的开发者入口：内部完成 L0-L3 全部对象的 DI 组装。

    用法：
        agent = Agent(role="研究员", goal="产出分析报告", backstory="十年经验", tools=[...], llm=llm)
        result = await agent.run("分析新能源电池行业趋势")

    可插拔参数（接受注册表名字字符串或满足协议的自定义实例）：
        memory          — 默认 "simple"
        observability   — 默认 "console"
        state_store     — 默认 "memory"
        brain_strategy  — 默认 "default"（ModularBrain + MAP 五模块）
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[ToolProtocol],
        llm: LLMAdapter,
        max_steps: int = 10,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain_strategy: str | BrainStrategy = "default",
    ):
        reg = get_global_registry()
        strategy_reg = get_global_strategy_registry()

        permission_manifest = ToolPermissionManifest(
            allowed_tools=[t.name for t in tools]
        )
        role_profile = RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        obs = self._resolve(reg, "observability", observability)
        mem = self._resolve(reg, "memory", memory)
        ss = self._resolve(reg, "state_store", state_store)

        # 解析 BrainStrategy：字符串走 StrategyRegistry，实例直接使用
        if isinstance(brain_strategy, str):
            brain_factory = strategy_reg.resolve(brain_strategy)
            if brain_factory is None:
                raise ValueError(
                    f"Unknown brain_strategy: {brain_strategy!r}. "
                    f"Available: {strategy_reg.list_strategies()}"
                )
            tools_desc = ", ".join(t.name for t in tools) or "(无可用工具)"
            brain = brain_factory(llm, role_profile, tools_desc)
        else:
            brain = brain_strategy

        from lca.layer4_app.defaults import _build_hooks, build_body, build_runtime

        body = build_body(tools, obs)
        hooks = _build_hooks(obs)
        event_bus = self._resolve(reg, "event_bus", "simple")

        runtime = build_runtime(brain, body, mem, hooks, event_bus, ss)
        self._base_agent = BaseAgent(runtime, role_profile, max_steps=max_steps)

    @staticmethod
    def _resolve(reg, category: str, value):
        if isinstance(value, str):
            impl = reg.resolve(category, value)
            if impl is None:
                raise ValueError(
                    f"Unknown {category}: {value!r}. Available: {reg.list(category)}"
                )
            return impl()
        return value

    async def run(self, task: str) -> Result:
        return await self._base_agent.execute(task)

    def _as_supervisor(self) -> Supervisor:
        rp = self._base_agent.role_profile
        ms = self._base_agent.max_steps
        return Supervisor(self._base_agent.runtime, rp, max_steps=max(ms, 20))


class MultiAgentTeam:
    """
    五行组建团队。

    用法：
        team = MultiAgentTeam(
            members=[researcher, writer, critic],
            process="hierarchical",
            supervisor=supervisor_agent,
        )
        result = await team.run("产出行业研究报告")
    """

    def __init__(
        self,
        members: list[Agent],
        process: str = "hierarchical",
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
    ):
        config = TeamConfig(
            process=process,  # type: ignore[arg-type]
            max_rounds=max_rounds,
        )
        base_members = [m._base_agent for m in members]
        base_supervisor = supervisor._as_supervisor() if supervisor else None
        self._orchestrator = TeamOrchestrator(base_members, config, base_supervisor)

    async def run(self, objective: str) -> Result:
        return await self._orchestrator.run(objective)
