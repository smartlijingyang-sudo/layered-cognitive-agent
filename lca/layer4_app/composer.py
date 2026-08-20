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
from typing import TYPE_CHECKING, Any, TypeVar

# Capabilities come from the booted cordis.Context. Per-compose llm/tools
# tables are local so overlapping compose cannot clobber the parent.

if TYPE_CHECKING:
    from cordis import Context

from lca.contracts.atoms.enums import (
    ActionScope,
    ComponentKind,
    DecisionGateName,
    HookEvent,
    MemoryLayer,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol, consume
from lca.contracts.mechanisms.capability import (
    CapabilityKey,
    MissingCapabilityError,
    provider_current,
    require_capability,
)
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
    LLMAdapter,
    MemorySystem,
    ObservabilityBackend,
    PerceiveHub,
    Sensor,
    SharedMemoryStore,
    StateStore,
    TeamAssembly,
    TeamStage,
    TeamUnit,
)
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
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer0_infra.capability.memory import MemoryService
from lca.layer0_infra.capability.state_store import StateStoreService
from lca.layer0_infra.capability.tools import ToolsService
from lca.layer0_infra.capability.transport import TransportService
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    create_observability,
    team_id_for,
)
from lca.layer0_infra.observability import record as _journal_record
from lca.layer0_infra.observability.adapters import TelemetryLLMAdapter, TelemetryMemoryAdapter
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
from lca.layer1_cognitive.sensors import (
    build_clock_sensor,
    build_workspace_artifacts_sensor,
)
from lca.layer1_cognitive.sensors.journal_backed import (
    build_inbox_facts_sensor,
    build_team_inbox_sensor,
)
from lca.layer1_cognitive.sensors.skill_catalog import build_skill_catalog_sensor
from lca.layer1_cognitive.sensors.workspace_instructions import (
    build_workspace_instructions_sensor,
)
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import make_journal_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer3_agent.orchestration_registry import OrchestrationFactory
from lca.layer3_agent.team_handle import TeamHandle
from lca.layer4_app.defaults import build_default_registries
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY
from lca.layer4_app.runtime_factory import RuntimeDeps, build_cognitive_runtime
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

__all__ = [
    "AgentComposer",
    "TeamComposer",
    "build_default_transport_registry",
    "build_team_transport",
]

T = TypeVar("T")


class _ScopeAsCapabilityContext:
    """Adapter: makes ``cordis.Context`` usable where ``CapabilityHub`` is expected.

    The CapabilityHub interface is: ``mount(key, service)``, ``require(key)``,
    ``get(key)``, ``keys()``. This adapter delegates to a cordis Context.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def require(self, key: str) -> Any:
        result = self._ctx.inject(key)
        if result is None:
            from lca.contracts.mechanisms.capability import MissingCapabilityError

            raise MissingCapabilityError(key)
        return result

    def get(self, key: str) -> Any | None:
        return self._ctx.inject(key)

    def mount(self, key: str, service: Any) -> None:
        # cordis supports provide(); composer hands off to Context
        self._ctx.provide(key, service)

    def keys(self) -> list[str]:
        return [k for k in dir(self._ctx) if not k.startswith("_")]


def _scope_is_team(scope: object | None) -> bool:
    """Heuristic: detect LEAD/MEMBER scope (ActionScope or cordis ctx).

    Used by ``_build_perceive_hub`` to decide whether to wire
    ``TeamInboxSensor`` (only for team runs).
    """
    if scope is None:
        return False
    # ActionScope is an Enum whose values include SOLO, MEMBER, LEAD.
    value = getattr(scope, "value", None)
    if value is not None:
        return str(value).lower() in {"member", "lead", "team"}
    marker = getattr(scope, "team_scope", None) or getattr(scope, "_team_scope", None)
    if marker is None:
        return False
    return str(marker).lower() in {"lead", "member", "team"}


def _run_store_from_scope(scope: object | None) -> Any | None:
    """Best-effort: pull a RunStore out of a cordis scope, or return None."""
    if scope is None:
        return None
    return getattr(scope, "run_store", None) or getattr(scope, "_run_store", None)


def _is_plugin_tree(scope: object | None) -> bool:
    """True when *scope* is a cordis Context (has ``inject``), not ActionScope."""
    return callable(getattr(scope, "inject", None))


def _ctx_factory(scope: object | None, key: str) -> Any | None:
    """Resolve a named factory from the plugin tree. Missing key → None."""
    inject = getattr(scope, "inject", None)
    if not callable(inject):
        return None
    try:
        return inject(key)
    except Exception:
        return None


def _resolve_named_factory(scope: object | None, key: str, standard: Any | None) -> Any | None:
    """Plugin tree wins; unit tests without a booted tree use *standard*.

    When the plugin tree is active a missing key means the plugin was
    disabled — do NOT fall back to Standard (disable would become a no-op).
    """
    if _is_plugin_tree(scope):
        return _ctx_factory(scope, key)
    return standard


def _skill_store_from_scope(scope: object | None) -> Any:
    """Installed-skill store: plugin-tree skills seam, nowhere else.

    A booted context with an empty provider table is a miss, not a cue
    to call ``resolve_skill_store()``.
    """
    if _is_plugin_tree(scope):
        store = provider_current(require_capability(scope, "skills"))
        if store is None:
            raise MissingCapabilityError("skills")
        return store
    from lca.layer0_infra.skills.factory import resolve_skill_store

    return resolve_skill_store()


# Spec §5.5 — fixed PerceiveHub composition order. Plugins provide named
# factories; the Composer is the only assembler.
_SENSOR_ORDER: tuple[str, ...] = (
    "sensor.clock",
    "sensor.workspace-artifacts",
    "sensor.inbox-facts",
    "sensor.team-inbox",
    "sensor.workspace-instructions",
    "sensor.skill-catalog",
)
_TEAM_ONLY_SENSORS: frozenset[str] = frozenset({"sensor.team-inbox"})
_STORE_SENSORS: frozenset[str] = frozenset({"sensor.inbox-facts", "sensor.team-inbox"})


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
        scope: Context | None = None,
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent from *spec* (closed graph).

        Capabilities are resolved from the cordis plugin tree (profile-driven).
        Full rewrite in Chunk 5 — uses cordis.Context.scope() for per-agent
        isolation.
        """
        if scope is None:
            from lca.layer4_app.api import get_or_create_default_ctx

            scope = get_or_create_default_ctx()
        profile = spec.profile
        ctx = self._resolve_capability_context(scope)
        if _is_plugin_tree(scope) and isinstance(spec.observability, str):
            hub = require_capability(scope, "observability").create()
        else:
            hub = create_observability(spec.observability)
        mem = self._resolve_memory(
            spec.memory, shared_store, ctx.require(CapabilityKey.MEMORY.value)
        )
        state_store = self._resolve_state_store(
            spec.state_store, ctx.require(CapabilityKey.STATE_STORE.value)
        )

        ctx.require(CapabilityKey.LLM.value)
        spec_llm = self._instrument_llm(spec.llm)

        ctx.require(CapabilityKey.TOOLS.value)
        tools_factory = _resolve_named_factory(
            scope, "tools.compose_service", None
        )
        if tools_factory is None:
            # Back-compat fallback for unit tests without a booted plugin tree.
            tools_factory = ToolsService
        tool_registry = tools_factory()
        for tool in spec.tools:
            tool_registry.register(tool)
        safe_executor_cls = _resolve_named_factory(
            scope, "safe_executor.simple", SimpleSafeExecutor
        )
        if safe_executor_cls is None:
            raise MissingCapabilityError("safe_executor.simple")
        safe_executor = safe_executor_cls(profile.tool_permission_manifest)
        transport_registry = _fork_transport(
            ctx.require(CapabilityKey.TRANSPORT.value), team_channel
        )
        action_registry = build_default_action_registry(
            tool_registry,
            safe_executor,
            transport_registry,
            scope=action_scope,
        )

        brain = self._resolve_brain(spec, profile, spec_llm, scope=scope)
        if decision_gate is not None:
            brain = self._apply_lead_brain(brain, decision_gate=decision_gate)

        body_cls = _resolve_named_factory(scope, "body.simple", SimpleBody)
        if body_cls is None:
            raise MissingCapabilityError("body.simple")
        body = body_cls(
            tool_registry=tool_registry,
            safe_executor=safe_executor,
            transport_registry=transport_registry,
            action_registry=action_registry,
        )
        hooks = self._build_hooks(scope)
        perceive_hub = self._build_perceive_hub(
            mem, hub=hub, scope=scope, action_scope=action_scope
        )
        stop_factory = _resolve_named_factory(
            scope,
            "stop_rule.default",
            lambda: DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        if stop_factory is None:
            raise MissingCapabilityError("stop_rule.default")
        runtime = build_cognitive_runtime(
            RuntimeDeps(
                brain=brain,
                body=body,
                memory=consume("memory", mem, CognitiveRuntime),
                hooks=hooks,
                state_store=consume("state_store", state_store, CognitiveRuntime),
                perceive_hub=perceive_hub,
                stop_rule=stop_factory(),
                middleware_registry=self._build_middleware_registry(hooks, scope),
            )
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
        scope: Context | None = None,
    ) -> CognitiveAgent:
        """Build a closed lead agent from *spec* (awareness-aware reasoner + gate)."""
        lead_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        gate = self._resolve_decision_gate(gate_name_for_mandate(mandate), scope=scope)
        composed = self.compose(
            lead_spec,
            action_scope=ActionScope.LEAD,
            team_channel=transport,
            decision_gate=gate,
            scope=scope,
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
        scope: Context | None = None,
    ) -> CognitiveAgent:
        """Build a team member from *spec* (shared memory / shared observability)."""
        member_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        return self.compose(
            member_spec,
            action_scope=ActionScope.MEMBER,
            shared_store=shared_store,
            scope=scope,
        )

    def _resolve_memory(
        self,
        choice: str | MemorySystem,
        shared_store: SharedMemoryStore | None,
        memory_service: MemoryService,
    ) -> MemorySystem:
        if shared_store is not None:
            mem: MemorySystem = memory_service.create(shared_store=shared_store)
        elif not isinstance(choice, str):
            mem = choice
        elif choice in memory_service.providers.names():
            mem = memory_service.providers.get(choice)()
        else:
            raise MissingCapabilityError("memory")
        return TelemetryMemoryAdapter(mem)

    def _resolve_state_store(
        self, choice: str | StateStore, service: StateStoreService
    ) -> StateStore:
        if not isinstance(choice, str):
            return choice
        if choice in service.providers.names():
            return service.providers.get(choice)()
        raise MissingCapabilityError("state_store")

    def _resolve_brain(
        self,
        spec: AgentSpec,
        profile: RoleProfile,
        llm: LLMAdapter,
        *,
        scope: Context | None = None,
    ) -> Brain:
        if not isinstance(spec.brain, str):
            return spec.brain
        # When a plugin tree is active the spec.brain key maps to a
        # named factory ``brain_factory.<key>``; the bare ``brain_factory``
        # key is the canonical default. Unknown keys raise ValueError so
        # callers don't silently fall through to a wrong factory.
        if _is_plugin_tree(scope):
            brain_key = spec.brain
            factory = _resolve_named_factory(scope, f"brain_factory.{brain_key}", None)
            if factory is None:
                # Fall back to the default brain_factory — but only if the
                # spec.brain matches the conventional default name.
                factory = _resolve_named_factory(scope, "brain_factory", None)
                if factory is None or brain_key != "default":
                    raise ValueError(
                        f"Unknown brain: {spec.brain!r}. Available: "
                        "brain_factory.default, brain_factory.modular"
                    )
        else:
            factory_reg = self._registries.brain_factories
            if spec.brain not in factory_reg:
                raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {factory_reg.list()}")
            factory = factory_reg.resolve(spec.brain)
        resolved: Brain = factory(
            consume("llm", llm, PromptReasoner),
            profile,
            _format_tools_xml(spec.tools),
            tools=list(spec.tools),
            available_skills=self._render_available_skills(scope),
        )
        return resolved

    @staticmethod
    def _instrument_llm(llm: LLMAdapter) -> LLMAdapter:
        """Wrap raw LLM adapter with telemetry instrumentation."""
        return TelemetryLLMAdapter(_unwrap_llm(llm))

    @staticmethod
    def _render_available_skills(scope: object | None = None) -> str:
        """Render installed skill catalog from the skills seam."""
        if not _is_plugin_tree(scope):
            return "（技能库不可用）"
        store = _skill_store_from_scope(scope)
        try:
            installed = store.list_installed()
        except Exception:
            return "（技能库不可用）"
        if not installed:
            return "（本地无已安装 skill，用 search_skill 从 Market 搜索）"
        return "\n".join(f"- {e.skill_id}: {e.name}" for e in installed)

    @staticmethod
    def _standard_hooks() -> SimpleHookRegistry:
        hooks = SimpleHookRegistry()
        journal_hook = make_journal_emitting_hook(_journal_record)
        for event_name in HookEvent:
            hooks.register(event_name, default_logging_hook)
            hooks.register(event_name, journal_hook)
        return hooks

    @staticmethod
    def _build_hooks(scope: object | None = None) -> SimpleHookRegistry:
        factory = _resolve_named_factory(scope, "hook_registry.simple", None)
        if factory is not None:
            hooks = factory()
            if isinstance(hooks, SimpleHookRegistry):
                return hooks
        return AgentComposer._standard_hooks()

    @staticmethod
    def _build_perceive_hub(
        memory: MemorySystem,
        *,
        hub: object | None = None,
        scope: object | None = None,
        action_scope: ActionScope | None = None,
    ) -> PerceiveHub:
        """Build the ``SequentialPerceiveHub`` with the v3 named factories.

        Spec §5.5: composition order is fixed (clock → workspace-artifacts →
        inbox-facts → team-inbox → workspace-instructions → skill-catalog).
        Missing factories are skipped; the Hub is robust to partial plugin
        trees.

        This is the only place the Hub is composed.  Plugins provide
        named factories (via ``ctx.provide``); the Composer is the
        single assembler.  Unit tests that call this without a booted
        plugin tree receive the Standard layer1 factories.
        """
        from lca.layer0_infra.observability import RunStore

        store_cls = _resolve_named_factory(scope, "journal_store", RunStore)
        store = (
            getattr(hub, "_run_store", None)
            or _run_store_from_scope(scope)
            or (store_cls() if store_cls is not None else RunStore())
        )

        standard: dict[str, Any] = {
            "sensor.clock": build_clock_sensor,
            "sensor.workspace-artifacts": build_workspace_artifacts_sensor,
            "sensor.inbox-facts": build_inbox_facts_sensor,
            "sensor.team-inbox": build_team_inbox_sensor,
            "sensor.workspace-instructions": build_workspace_instructions_sensor,
            "sensor.skill-catalog": build_skill_catalog_sensor,
        }

        sensors: list[Sensor] = []
        team_mode = _scope_is_team(action_scope) or _scope_is_team(scope)
        for key in _SENSOR_ORDER:
            if key in _TEAM_ONLY_SENSORS and not team_mode:
                continue
            factory = _resolve_named_factory(scope, key, standard.get(key))
            if factory is None:
                continue
            try:
                if key in _STORE_SENSORS:
                    sensors.append(factory(store))
                elif key == "sensor.skill-catalog":
                    sensors.append(factory(_skill_store_from_scope(scope)))
                else:
                    sensors.append(factory())
            except MissingCapabilityError:
                raise
            except Exception:  # noqa: S112 — broken factory must not abort Hub
                continue

        return SequentialPerceiveHub(sensors=sensors, memory=memory)

    @staticmethod
    def _build_middleware_registry(
        hooks: SimpleHookRegistry,
        scope: object | None = None,
    ) -> InMemoryMiddlewareRegistry:
        from lca.layer2_runtime.hook_middleware import install_hook_bridge

        factory = _resolve_named_factory(scope, "middleware_registry.memory", None)
        if factory is not None:
            registry = factory(hooks)
            if isinstance(registry, InMemoryMiddlewareRegistry):
                return registry
        registry = InMemoryMiddlewareRegistry()
        install_hook_bridge(registry, hooks)
        return registry

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

    def _resolve_decision_gate(
        self, name: DecisionGateName, *, scope: object | None = None
    ) -> DecisionGate | None:
        if name == DecisionGateName.NONE:
            return None
        if name == DecisionGateName.MUST_CONSULT_ALL:
            factory = _resolve_named_factory(scope, "gate.must-consult-all", MustConsultAllMembers)
            if factory is None:
                raise MissingCapabilityError("gate.must-consult-all")
            result = factory() if callable(factory) else factory
        else:
            factory = self._registries.components.require(ComponentKind.DECISION_GATE, name)
            result = factory()
        if not isinstance(result, DecisionGate):
            raise TypeError(
                f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
            )
        return result

    @staticmethod
    def _resolve_capability_context(ctx: Context) -> Any:
        """Resolve the capability context — cordis.Context IS the context."""
        return _ScopeAsCapabilityContext(ctx)


def _fork_transport(parent: TransportService, extra: AgentTransport | None) -> TransportService:
    """Per-compose transport table: copy parent protocols, don't mutate them.

    The fresh child ``TransportService`` is built through the
    ``transport.compose_service`` named factory when a plugin tree is
    available, so the composition root never instantiates a concrete
    capability service inline.
    """
    factory = _resolve_named_factory(None, "transport.compose_service", None)
    if factory is None:
        # No plugin tree: synthesize a child TransportService directly.
        # The composition root has no thread-local scope — the only
        # fallback is the canonical class.
        factory = TransportService
    child = factory()
    for protocol in parent.list_protocols():
        child.register(parent.resolve(protocol))
    if extra is not None:
        child.register(extra)
    return child


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

    def compose_team_spec(
        self,
        spec: TeamSpec,
        *,
        scope: Context | None = None,
    ) -> TeamUnit:
        """Assemble the closed team object graph from *spec* (sole composition path)."""
        shared_obs = self._resolve_team_observability(spec)
        shared_store: SharedMemoryStore | None = (
            TeamSharedMemoryStore(list(spec.shared_memory_layers))
            if spec.shared_memory_layers
            else None
        )
        closed_members = tuple(
            self.compose_member(
                member_spec,
                shared_store=shared_store,
                observability=shared_obs,
                scope=scope,
            )
            for member_spec in spec.members
        )
        stage, transport = self._build_stage(closed_members)
        assembly = self._assemble(spec, stage, transport, shared_obs, scope=scope)
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
        *,
        scope: Context | None = None,
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
                scope=scope,
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
