"""Composition root — wires all layers into working object graphs.

``AgentComposer`` / ``TeamComposer`` 从声明式 ``AgentSpec`` / ``TeamSpec``
组装封闭的 Agent / Team 对象图：spec 是唯一声明式输入，composer 是唯一
组装点，构造后无 bind/install（ADR-0005 / ADR-0029 / ADR-0030 / ADR-0033）。
团队侧按本质模型组装（ADR-0034）：TeamSpec 是团队形态的唯一事实来源，
composer 把它编译成封闭 TeamStrategy，运行期句柄不编排。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TypeVar

from lca.contracts.atoms.enums import (
    ActionScope,
    ComponentKind,
    DecisionGateName,
    HookEvent,
    MemoryLayer,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.mechanisms.registries import Registries
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_coordination import (
    Coordination,
    LeadMandate,
    gate_name_for_mandate,
)
from lca.contracts.protocols import (
    AgentUnit,
    Brain,
    BrainFactory,
    BudgetPolicy,
    DecisionGate,
    EventBus,
    LLMAdapter,
    MemorySystem,
    ObservabilityBackend,
    SharedMemoryStore,
    StateStore,
    TeamAssembly,
    TeamStage,
    TeamUnit,
)
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.contracts.protocols.infra import AgentTransport, Tool
from lca.contracts.protocols.spec import (
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    OBSERVABILITY_CHOICE_CONSOLE,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
    strategy_key_for_governance,
)
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    create_observability,
    team_id_for,
)
from lca.layer0_infra.observability.adapters import TelemetryLLMAdapter, TelemetryMemoryAdapter
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer3_agent.orchestration_registry import OrchestrationFactory
from lca.layer3_agent.team_handle import TeamHandle
from lca.layer4_app.defaults import EVENT_BUS_SIMPLE, build_default_registries
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)
from lca.layer4_app.telemetry_bridge import install_telemetry_bridge, make_bus_drain_hook

__all__ = [
    "AgentComposer",
    "TeamComposer",
    "build_default_transport_registry",
    "build_team_transport",
]

T = TypeVar("T")


def _resolve_component(
    reg: ComponentRegistryProtocol,
    category: str,
    value: object,
    expected_type: type[T],
) -> T:
    result = reg.require(category, value)() if isinstance(value, str) else value
    if not isinstance(result, expected_type):
        raise TypeError(
            f"{category} expected {expected_type.__name__}, got {type(result).__name__}"
        )
    return result


def _unwrap_llm(llm: LLMAdapter) -> LLMAdapter:
    if isinstance(llm, TelemetryLLMAdapter):
        return llm._inner
    return llm


def _format_tools_xml(tools: Sequence[Tool]) -> str:
    """Render tools as LobeHub-style XML block with name + description."""
    if not tools:
        return "（无可用工具）"
    lines = []
    for t in tools:
        desc = t.description or t.name
        lines.append(f'<tool name="{t.name}">{desc}</tool>')
    return "\n".join(lines)


def _promote_lead(lead: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    limits = policy.resolve(lead)
    return CognitiveAgent(
        lead.runtime,
        lead.role_profile,
        lead.observability,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


class AgentComposer:
    """Compose a single closed CognitiveAgent from a declarative AgentSpec."""

    def __init__(self, registries: Registries | None = None) -> None:
        self._registries = registries if registries is not None else build_default_registries()

    @property
    def registries(self) -> Registries:
        return self._registries

    def register_component(self, category: str, name: str, impl: object) -> None:
        self._registries.components.register(category, name, impl)

    def register_brain_factory(self, name: str, factory: BrainFactory) -> None:
        self._registries.brain_factories.register(name, factory)

    def register_orchestration_strategy(self, key: str, factory: OrchestrationFactory) -> None:
        self._registries.orchestration.register(key, factory)

    def compose(
        self,
        spec: AgentSpec,
        *,
        action_scope: ActionScope = ActionScope.SOLO,
        team_channel: AgentTransport | None = None,
        decision_gate: DecisionGate | None = None,
        shared_store: SharedMemoryStore | None = None,
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent from *spec* (closed graph)."""
        profile = spec.profile
        hub = create_observability(spec.observability)
        mem = self._resolve_memory(spec.memory, shared_store)
        state_store = _resolve_component(
            self._registries.components,
            ComponentKind.STATE_STORE,
            spec.state_store,
            StateStore,  # type: ignore[type-abstract]
        )

        tool_registry = SimpleToolRegistry()
        for tool in spec.tools:
            tool_registry.register(tool)
        safe_executor = SimpleSafeExecutor(profile.tool_permission_manifest)
        transport_registry = build_default_transport_registry()
        if team_channel is not None:
            transport_registry.register(team_channel)
        action_registry = build_default_action_registry(
            tool_registry,
            safe_executor,
            transport_registry,
            scope=action_scope,
        )

        brain = self._resolve_brain(spec, profile, action_registry)
        if decision_gate is not None:
            brain = self._apply_lead_brain(brain, decision_gate=decision_gate)

        body = SimpleBody(
            tool_registry=tool_registry,
            safe_executor=safe_executor,
            transport_registry=transport_registry,
            action_registry=action_registry,
        )
        event_bus = _resolve_component(
            self._registries.components,
            ComponentKind.EVENT_BUS,
            EVENT_BUS_SIMPLE,
            EventBus,  # type: ignore[type-abstract]
        )
        runtime = CognitiveRuntime(
            brain,
            body,
            mem,
            self._build_hooks(event_bus),
            state_store,
            stop_rule=DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        return CognitiveAgent(
            runtime,
            profile,
            hub,
            max_steps=spec.max_steps,
            max_wall_clock_seconds=spec.max_wall_clock_seconds,
        )

    def compose_as_lead(
        self,
        spec: AgentSpec,
        *,
        transport: AgentTransport,
        mandate: LeadMandate,
        observability: ObservabilityHub | None = None,
    ) -> CognitiveAgent:
        """Build a closed lead agent from *spec* (awareness-aware reasoner + gate)."""
        lead_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        gate = self._resolve_decision_gate(gate_name_for_mandate(mandate))
        composed = self.compose(
            lead_spec,
            action_scope=ActionScope.LEAD,
            team_channel=transport,
            decision_gate=gate,
        )
        policy = _resolve_component(
            self._registries.components,
            ComponentKind.BUDGET_POLICY,
            LEAD_BUDGET_POLICY_KEY,
            BudgetPolicy,  # type: ignore[type-abstract]
        )
        return _promote_lead(composed, policy)

    def compose_member(
        self,
        spec: AgentSpec,
        *,
        shared_store: SharedMemoryStore | None = None,
        observability: ObservabilityHub | None = None,
    ) -> CognitiveAgent:
        """Build a team member from *spec* (shared memory / shared observability)."""
        member_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        return self.compose(member_spec, action_scope=ActionScope.MEMBER, shared_store=shared_store)

    def _resolve_memory(
        self,
        choice: str | MemorySystem,
        shared_store: SharedMemoryStore | None,
    ) -> MemorySystem:
        if shared_store is not None:
            mem: MemorySystem = SimpleMemorySystem(shared_store=shared_store)
        else:
            mem = _resolve_component(
                self._registries.components,
                ComponentKind.MEMORY,
                choice,
                MemorySystem,  # type: ignore[type-abstract]
            )
        return TelemetryMemoryAdapter(mem)

    def _resolve_brain(
        self,
        spec: AgentSpec,
        profile: RoleProfile,
        action_registry: ActionRegistryProtocol,
    ) -> Brain:
        if not isinstance(spec.brain, str):
            return spec.brain
        factory_reg = self._registries.brain_factories
        if spec.brain not in factory_reg:
            raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {factory_reg.list()}")
        tools_desc = _format_tools_xml(spec.tools)
        available_skills = self._render_available_skills()
        factory = factory_reg.resolve(spec.brain)
        instrumented_llm: LLMAdapter = TelemetryLLMAdapter(_unwrap_llm(spec.llm))
        resolved: Brain = factory(
            instrumented_llm,
            profile,
            tools_desc,
            action_registry=action_registry,
            tools=list(spec.tools),
            available_skills=available_skills,
        )
        return resolved

    @staticmethod
    def _render_available_skills() -> str:
        """Render installed skill catalog for prompt injection."""
        from lca.layer0_infra.skills.factory import resolve_skill_store

        try:
            store = resolve_skill_store()
            installed = store.list_installed()
        except Exception:
            return "（技能库不可用）"
        if not installed:
            return "（本地无已安装 skill，用 search_skill 从 Market 搜索）"
        return "\n".join(f"- {e.skill_id}: {e.name}" for e in installed)

    @staticmethod
    def _build_hooks(event_bus: EventBus) -> SimpleHookRegistry:
        hooks = SimpleHookRegistry()
        install_telemetry_bridge(event_bus)
        event_hook = make_event_emitting_hook(event_bus)
        for event_name in HookEvent:
            hooks.register(event_name, default_logging_hook)
            hooks.register(event_name, event_hook)
        # run 收尾前排空总线：异步桥接事件（step.completed 等）先于容器关闭落 journal
        hooks.register(HookEvent.ON_COMPLETE, make_bus_drain_hook(event_bus))
        return hooks

    @staticmethod
    def _apply_lead_brain(brain: Brain, *, decision_gate: DecisionGate) -> Brain:
        """Return a new ModularBrain carrying the lead decision gate.

        ADR-0035：Reasoner 不再按 mandate 升级——唯一的 PromptReasoner
        通过 ``AgentState.team_awareness`` 统一覆盖 solo / member / lead。
        """
        if not isinstance(brain, ModularBrain):
            raise TypeError(f"lead composition requires ModularBrain (got {type(brain).__name__})")

        return ModularBrain(
            reasoner=brain.reasoner,
            critic=brain.critic,
            skill_router=brain.skill_router,
            decision_gate=decision_gate,
            agent_gates=brain.agent_gates,
        )

    def _resolve_decision_gate(self, name: DecisionGateName) -> DecisionGate | None:
        if name == DecisionGateName.NONE:
            return None
        factory = self._registries.components.require(ComponentKind.DECISION_GATE, name)
        result = factory()
        if not isinstance(result, DecisionGate):
            raise TypeError(
                f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
            )
        return result


class TeamComposer(AgentComposer):
    """Compose a closed team from a declarative TeamSpec (ADR-0034).

    管线五步，每步一个命名职责：共享观测 → 共享记忆 → 封闭成员 →
    舞台（角色校验 + transport + 调用通道）→ 装配视图（含 lead 时闭合 lead）
    → 注册表解析封闭策略 → 运行句柄。团队形态只从 TeamSpec.governance
    单向派生，composer 不做运行期决策。
    """

    def compose_team(
        self,
        *,
        members: Sequence[AgentSpec],
        lead: LeadSpec | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: Sequence[MemoryLayer] | None = None,
        delegate_max_attempts: int | None = None,
        observability: str | ObservabilityHub | None = None,
    ) -> TeamUnit:
        """Assemble a closed team from kwargs; folds governance at the boundary."""
        governance = _governance_from(lead, coordination)
        spec = TeamSpec(
            members=tuple(members),
            governance=governance,
            shared_memory_layers=tuple(shared_memory_layers or ()),
            delegate_max_attempts=(
                delegate_max_attempts
                if delegate_max_attempts is not None
                else DEFAULT_DELEGATE_MAX_ATTEMPTS
            ),
            observability=observability,
        )
        return self.compose_team_spec(spec)

    def compose_team_spec(self, spec: TeamSpec) -> TeamUnit:
        """Assemble the closed team object graph from *spec* (sole composition path)."""
        shared_obs = self._resolve_team_observability(spec)
        shared_store: SharedMemoryStore | None = (
            TeamSharedMemoryStore(list(spec.shared_memory_layers))
            if spec.shared_memory_layers
            else None
        )
        closed_members = tuple(
            self.compose_member(member_spec, shared_store=shared_store, observability=shared_obs)
            for member_spec in spec.members
        )
        stage, transport = self._build_stage(closed_members)
        assembly = self._assemble(spec, stage, transport, shared_obs)
        strategy_key = strategy_key_for_governance(spec.governance)
        strategy = self._registries.orchestration.resolve(strategy_key, assembly)
        profile = self._trace_profile(strategy_key, spec.governance, closed_members, assembly.lead)
        return TeamHandle(strategy, profile, shared_obs, closed_members, assembly.lead)

    def _build_stage(self, members: tuple[CognitiveAgent, ...]) -> tuple[TeamStage, AgentTransport]:
        """Validate roles (fail-fast) and close the member invocation channel."""
        roles = [member.role_profile.role for member in members]
        if any(not role for role in roles):
            raise ValueError("member role_profile.role is required for transport invoke")
        if len(set(roles)) != len(roles):
            raise ValueError(f"duplicate member roles in team: {sorted(roles)}")
        transport = build_team_transport(list(members))
        return TeamStage(members=members, invoker=TransportMemberInvoker(transport)), transport

    def _assemble(
        self,
        spec: TeamSpec,
        stage: TeamStage,
        transport: AgentTransport,
        shared_obs: ObservabilityHub,
    ) -> TeamAssembly:
        """Close the lead agent when governance is a LeadSpec; build the factory view."""
        governance = spec.governance
        closed_lead: CognitiveAgent | None = None
        if isinstance(governance, LeadSpec):
            closed_lead = self.compose_as_lead(
                governance.agent,
                transport=transport,
                mandate=governance.mandate,
                observability=shared_obs,
            )
        return TeamAssembly(
            governance=governance,
            stage=stage,
            lead=closed_lead,
            delegate_max_attempts=spec.delegate_max_attempts,
        )

    @staticmethod
    def _trace_profile(
        strategy_key: str,
        governance: Governance,
        members: tuple[CognitiveAgent, ...],
        lead: AgentUnit | None,
    ) -> TeamTraceProfile:
        """Static span profile — all data known at composition time (no reflection)."""
        mandate = governance.mandate.value if isinstance(governance, LeadSpec) else None
        return TeamTraceProfile(
            team_id=team_id_for(strategy_key),
            strategy_key=strategy_key,
            mandate=mandate,
            lead_role=lead.role_profile.role if lead is not None else "",
            member_roles=tuple(member.role_profile.role for member in members),
        )

    def _resolve_team_observability(self, spec: TeamSpec) -> ObservabilityHub:
        """Single shared hub for the whole team (span tree continuity).

        Priority: explicit TeamSpec arg > member specs in order > lead spec > console default.
        First hub instance wins as-is; first choice string is resolved once and shared.
        """
        candidates: list[str | ObservabilityBackend] = []
        if spec.observability is not None:
            candidates.append(spec.observability)
        candidates.extend(member.observability for member in spec.members)
        governance = spec.governance
        if isinstance(governance, LeadSpec):
            candidates.append(governance.agent.observability)
        for choice in candidates:
            if isinstance(choice, ObservabilityHub):
                return choice
            if isinstance(choice, str):
                return create_observability(choice)
        return create_observability(OBSERVABILITY_CHOICE_CONSOLE)


def _governance_from(lead: LeadSpec | None, coordination: Coordination | None) -> Governance:
    """Fold the public XOR knobs into the single governance slot."""
    if lead is not None:
        if coordination is not None:
            raise ValueError("Team requires exactly one of lead= or coordination=")
        return lead
    if coordination is not None:
        return coordination
    raise ValueError("Team requires exactly one of lead= or coordination=")
