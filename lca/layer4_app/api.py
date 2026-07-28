"""L4 极简开发者 API —— 三行创建 Agent，五行组建团队。

支持通过注册表名字字符串或自定义协议实例来选择组件实现，
无需修改框架源码即可替换任何可插拔组件。
"""

from __future__ import annotations

from typing import TypeVar, cast

import lca.layer4_app.defaults  # noqa: F401 — 触发默认注册
from lca.contracts.protocols import (
    BrainStrategy,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamRuntime,
    Tool,
)
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer0_infra.registry import ComponentRegistry, get_global_registry
from lca.layer1_cognitive.body.action_handlers import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.supervisor import Supervisor
from lca.layer3_agent.team_orchestrator import TeamOrchestrator

T = TypeVar("T")


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
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = 10,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain_strategy: str | BrainStrategy = "default",
    ):
        reg = get_global_registry()

        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        obs = self._resolve(reg, "observability", observability)
        mem = self._resolve(reg, "memory", memory)
        ss = self._resolve(reg, "state_store", state_store)

        # 构建 ActionRegistry —— Body 和 DecisionParser 共享同一实例，
        # 保证"执行器支持什么"与"解析器校验什么"永远一致
        tool_reg = SimpleToolRegistry()
        for t in tools:
            tool_reg.register(t)
        safe_exec = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=[t.name for t in tools]), obs
        )
        from lca.layer4_app.defaults import build_default_transport_registry

        transport_reg = build_default_transport_registry()
        action_registry = build_default_action_registry(tool_reg, safe_exec, transport_reg)

        # 解析 BrainStrategy：字符串走 StrategyRegistry（验证存在性），实例直接使用
        brain: BrainStrategy
        if isinstance(brain_strategy, str):
            from lca.layer2_runtime.strategy_registry import get_global_strategy_registry

            strategy_reg = get_global_strategy_registry()
            if strategy_reg.resolve(brain_strategy) is None:
                raise ValueError(
                    f"Unknown brain_strategy: {brain_strategy!r}. Available: {strategy_reg.list()}"
                )
            tools_desc = ", ".join(t.name for t in tools) or "(无可用工具)"
            from lca.layer4_app.defaults import _build_brain

            brain = _build_brain(llm, role_profile, tools_desc, action_registry=action_registry)
        else:
            brain = brain_strategy

        from lca.layer4_app.defaults import _build_hooks, build_body, build_runtime

        body = build_body(tools, obs, action_registry=action_registry)
        hooks = _build_hooks(obs)
        event_bus: EventBus = self._resolve(reg, "event_bus", "simple")

        runtime = build_runtime(brain, body, mem, hooks, event_bus, ss)
        self._base_agent = BaseAgent(runtime, role_profile, max_steps=max_steps)

    @staticmethod
    def _resolve(reg: ComponentRegistry, category: str, value: str | T) -> T:
        if isinstance(value, str):
            impl = reg.resolve(category, value)
            if impl is None:
                raise ValueError(f"Unknown {category}: {value!r}. Available: {reg.list(category)}")
            return cast("T", impl())
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
        from lca.layer4_app.defaults import build_team_transport

        transport, roster_desc = build_team_transport(base_members)
        self._orchestrator: TeamRuntime = TeamOrchestrator(
            base_members,
            config,
            base_supervisor,
            transport=transport,
            roster_desc=roster_desc,
        )

    async def run(self, objective: str) -> Result:
        return await self._orchestrator.run(objective)
