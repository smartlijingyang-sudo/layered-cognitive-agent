"""L4 极简开发者 API —— 三行创建 Agent，五行组建团队。"""

from __future__ import annotations

from typing import Any, Optional

from contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from contracts.result import Result
from layer0_infra.observability.console_observability import ConsoleObservability
from layer1_cognitive.brain.modular_brain import ModularBrain
from layer1_cognitive.brain.reasoner import SimpleReasoner, DEFAULT_REACT_TEMPLATE
from layer1_cognitive.brain.critic import SimpleCritic
from layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from layer1_cognitive.brain.map_modules import (
    SimpleTaskDecomposer, SimpleStatePredictor, SimpleStateEvaluator,
    SimpleConflictMonitor, SimpleTaskCoordinator,
)
from layer1_cognitive.body.tool_registry import SimpleToolRegistry
from layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from layer1_cognitive.body.simple_body import SimpleBody
from layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from layer1_cognitive.event_bus import SimpleEventBus
from layer1_cognitive.prompt_manager import SimplePromptManager
from layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from layer2_runtime.runtime_loop import CognitiveRuntime
from layer2_runtime.hooks import HOOK_NAMES
from layer0_infra.state_mgmt.in_memory_store import InMemoryStateStore
from layer3_agent.base_agent import BaseAgent
from layer3_agent.supervisor import Supervisor
from layer3_agent.team_orchestrator import TeamOrchestrator


class Agent:
    """
    三行上手的开发者入口：内部完成 L0-L3 全部对象的 DI 组装。

    用法：
        agent = Agent(role="研究员", goal="产出分析报告", backstory="十年经验", tools=[...], llm=llm)
        result = await agent.run("分析新能源电池行业趋势")
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Any],
        llm: Any,
        max_steps: int = 10,
    ):
        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(
            role=role, goal=goal, backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        observability = ConsoleObservability()
        prompt_manager = SimplePromptManager()
        prompt_manager.register_template("react_prompt", DEFAULT_REACT_TEMPLATE)

        tool_registry = SimpleToolRegistry()
        for t in tools:
            tool_registry.register(t)
        tools_desc = ", ".join(f"{t.name}" for t in tools) or "(无可用工具)"

        safe_executor = SimpleSafeExecutor(permission_manifest, observability)
        body = SimpleBody(tool_registry, safe_executor)

        reasoner = SimpleReasoner(llm, prompt_manager, role_profile, tools_desc)
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            task_decomposer=SimpleTaskDecomposer(),
            state_predictor=SimpleStatePredictor(),
            state_evaluator=SimpleStateEvaluator(),
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
        )

        memory = SimpleMemorySystem()
        hooks = SimpleHookRegistry(observability)
        for event_name in HOOK_NAMES:
            hooks.register(event_name, default_logging_hook)

        event_bus = SimpleEventBus()
        state_store = InMemoryStateStore()

        runtime = CognitiveRuntime(brain, body, memory, hooks, event_bus, state_store)
        self._base_agent = BaseAgent(runtime, role_profile, max_steps=max_steps)

    async def run(self, task: str) -> Result:
        return await self._base_agent.execute(task)


class MultiAgentTeam:
    """
    五行组建团队。

    用法：
        team = MultiAgentTeam(
            members=[researcher, writer, critic],
            process="hierarchical",
            supervisor=Supervisor(role="项目负责人"),
        )
        result = await team.run("产出行业研究报告")
    """

    def __init__(
        self,
        members: list[Agent],
        process: str = "hierarchical",
        supervisor: Optional[Agent] = None,
        max_rounds: Optional[int] = None,
    ):
        config = TeamConfig(
            process=process,  # type: ignore[arg-type]
            max_rounds=max_rounds,
        )
        base_members = [m._base_agent for m in members]
        base_supervisor = supervisor._base_agent if supervisor else None
        if base_supervisor:
            base_supervisor.__class__ = Supervisor
        self._orchestrator = TeamOrchestrator(base_members, config, base_supervisor)

    async def run(self, objective: str) -> Result:
        return await self._orchestrator.run(objective)
