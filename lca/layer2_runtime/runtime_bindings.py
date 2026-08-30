"""声明式 Turn 的已验证运行绑定。

组合根在这里选择并封装每个可替换依赖；运行入口只负责创建或恢复状态，再把
状态交给这份不可变绑定创建的 driver。这样一份 ``CompiledRunPlan`` 所需的
解释、效果、Reducer、Journal 与终态依赖拥有单一的可导航事实源。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols.artifact_closure import ArtifactClosure
from lca.contracts.protocols.cognition import Brain, PerceiveHub
from lca.contracts.protocols.declarative_execution import PhaseCapabilityReader
from lca.contracts.protocols.declarative_phase_graph import PhaseExecutor
from lca.contracts.protocols.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.effect_handler import EffectHandlerRegistry
from lca.contracts.protocols.embodiment import Body
from lca.contracts.protocols.idempotency import IdempotencyStore
from lca.contracts.protocols.infra import StateStore
from lca.contracts.protocols.memory import MemorySystem
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.contracts.protocols.reducer import Reducer
from lca.contracts.protocols.resume_input import ResumeInputAdapter
from lca.contracts.protocols.runtime_composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime_lifecycle import RuntimeLifecyclePublisher
from lca.harness.declarative import MappingRestrictedScope
from lca.harness.declarative.phase_observation import PhaseObserver
from lca.harness.plan import compiled_run_plan_ref
from lca.layer2_runtime.runtime_event_publisher import NullRuntimeLifecyclePublisher

if TYPE_CHECKING:
    from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver


@dataclass(frozen=True, slots=True)
class RuntimePhaseCapabilities(PhaseCapabilityReader):
    """Frozen, composition-provided capability view for phase executors.

    The runtime does not enumerate standard phase dependencies.  Instead, each
    cognitive cluster contributes the capabilities required while closing
    ``AgentGraph``; custom executors can consume additional declared keys.
    """

    values: Mapping[str, object]

    def __post_init__(self) -> None:
        """Snapshot the contribution map before phase interpretation begins."""

        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def get(self, name: str) -> object | None:
        """Return a named capability from the graph's explicit contribution map."""

        return self.values.get(name)

    def require(self, name: str) -> object:
        """Return a declared capability or fail at the restricted seam."""

        value = self.get(name)
        if value is None:
            raise KeyError(f"phase capability is not declared: {name}")
        return value

    @property
    def brain(self) -> Brain:
        """Expose the composed Brain through the legacy runtime facade."""

        return cast("Brain", self.require("brain"))

    @property
    def body(self) -> Body:
        """Expose the capability required by the existing body effect protocol."""

        return cast("Body", self.require("body"))

    @property
    def memory(self) -> MemorySystem:
        """Expose the capability required by the existing memory effect protocol."""

        return cast("MemorySystem", self.require("memory"))

    @property
    def perceive_hub(self) -> PerceiveHub:
        """Expose the composed perception hub through the legacy runtime facade."""

        return cast("PerceiveHub", self.require("perceive_hub"))


@dataclass(frozen=True, slots=True)
class DeclarativeRuntimeBindings:
    """解释一个声明式 Turn 的完整且已经选择好的依赖闭包。

    该 module 的 interface 有意只暴露一个主要操作 ``new_driver``。它隐藏
    driver 创建、Journal 的逐 Turn 生命周期，以及这些依赖在 fresh/resume
    两种路径中的重复装配；所有字段仍是组合根可审计的显式事实。
    """

    plan: CompiledRunPlan | None
    phase_executors: Mapping[str, PhaseExecutor]
    capabilities: RuntimePhaseCapabilities
    reducer: Reducer
    hooks: HookRegistry
    effect_handler_registry: EffectHandlerRegistry
    delta_handler_registry: DeltaHandlerRegistry
    artifact_closure: ArtifactClosure
    idempotency_store: IdempotencyStore
    resume_input_adapter: ResumeInputAdapter
    state_store: StateStore
    effect_gateway_factory: EffectGatewayFactory
    delta_reducer_factory: DeltaReducerFactory
    journal_factory: RuntimeJournalFactory
    interpreter_factory: DeclarativeInterpreterFactory
    checkpoint_state_resolver_factory: CheckpointStateResolverFactory
    result_finalizer_factory: ResultFinalizerFactory
    phase_observer: PhaseObserver
    lifecycle_publisher: RuntimeLifecyclePublisher = field(
        default_factory=NullRuntimeLifecyclePublisher
    )

    @classmethod
    def assemble(
        cls,
        *,
        plan: CompiledRunPlan | None,
        phase_executors: Mapping[str, PhaseExecutor],
        capabilities: RuntimePhaseCapabilities,
        reducer: Reducer,
        hooks: HookRegistry,
        effect_handler_registry: EffectHandlerRegistry,
        delta_handler_registry: DeltaHandlerRegistry,
        artifact_closure: ArtifactClosure,
        idempotency_store: IdempotencyStore,
        resume_input_adapter: ResumeInputAdapter,
        state_store: StateStore,
        effect_gateway_factory: EffectGatewayFactory,
        delta_reducer_factory: DeltaReducerFactory,
        journal_factory: RuntimeJournalFactory,
        interpreter_factory: DeclarativeInterpreterFactory,
        checkpoint_state_resolver_factory: CheckpointStateResolverFactory,
        result_finalizer_factory: ResultFinalizerFactory,
        phase_observer: PhaseObserver,
        lifecycle_publisher: RuntimeLifecyclePublisher | None = None,
    ) -> DeclarativeRuntimeBindings:
        """冻结阶段 executor 映射，防止运行开始后出现环境式重新绑定。"""

        return cls(
            plan=plan,
            phase_executors=MappingProxyType(dict(phase_executors)),
            capabilities=capabilities,
            reducer=reducer,
            hooks=hooks,
            effect_handler_registry=effect_handler_registry,
            delta_handler_registry=delta_handler_registry,
            artifact_closure=artifact_closure,
            idempotency_store=idempotency_store,
            resume_input_adapter=resume_input_adapter,
            state_store=state_store,
            effect_gateway_factory=effect_gateway_factory,
            delta_reducer_factory=delta_reducer_factory,
            journal_factory=journal_factory,
            interpreter_factory=interpreter_factory,
            checkpoint_state_resolver_factory=checkpoint_state_resolver_factory,
            result_finalizer_factory=result_finalizer_factory,
            phase_observer=phase_observer,
            lifecycle_publisher=lifecycle_publisher or NullRuntimeLifecyclePublisher(),
        )

    def plan_ref(self) -> str:
        """Return the stable identity of the selected executable plan."""
        return compiled_run_plan_ref(self.require_executable_plan())

    def require_executable_plan(self) -> CompiledRunPlan:
        """Return the selected plan only when its phase executor seam is complete."""
        if self.plan is None or not self.phase_executors:
            raise ValueError(
                "DeclarativeRuntimeBindings requires a compiled_plan and phase_executors."
            )
        required = {binding.executor_capability for binding in self.plan.phase_bindings}
        missing = sorted(required.difference(self.phase_executors))
        if missing:
            raise ValueError(
                "DeclarativeRuntimeBindings is missing phase executors: " + ", ".join(missing)
            )
        return self.plan

    def new_checkpoint_state_resolver(self) -> CheckpointStateResolver:
        """Create the profile-selected recovery seam from the frozen binding closure."""
        return self.checkpoint_state_resolver_factory.create(state_store=self.state_store)

    def new_result_finalizer(self) -> ResultFinalizer:
        """Create the profile-selected terminal seam from the frozen binding closure."""
        return self.result_finalizer_factory.create(
            reducer=self.reducer,
            hooks=self.hooks,
            artifact_closure=self.artifact_closure,
            state_store=self.state_store,
        )

    def phase_scope(self) -> MappingRestrictedScope:
        """Expose only the frozen phase executor scope to the interpreter."""
        return MappingRestrictedScope(self.phase_executors)

    # Construct the profile-selected interpreter from this verified closure.
    def new_interpreter(self, *, journal: RuntimeJournal) -> DeclarativeInterpreter:
        interpreter = self.interpreter_factory.create(
            journal=journal,
            effect_gateway=self.new_effect_gateway(),
            reducer=self.new_delta_reducer(),
            phase_observer=self.phase_observer,
            lifecycle_publisher=self.lifecycle_publisher,
        )
        if not isinstance(interpreter, DeclarativeInterpreter):
            raise TypeError(
                "declarative_interpreter_factory.create must return DeclarativeInterpreter, "
                f"got {type(interpreter).__name__}"
            )
        return interpreter

    def new_effect_gateway(self):
        """Create the profile-selected effect seam from the frozen binding closure."""
        return self.effect_gateway_factory.create(
            capabilities=self.capabilities,
            effect_handler_registry=self.effect_handler_registry,
            idempotency_store=self.idempotency_store,
        )

    def new_delta_reducer(self):
        """Create the profile-selected delta seam from the frozen binding closure."""
        return self.delta_reducer_factory.create(
            reducer=self.reducer,
            delta_handler_registry=self.delta_handler_registry,
        )

    def new_driver(self) -> DeclarativeRuntimeDriver:
        """为一次 fresh 或 resume Turn 创建隔离的声明式 driver。"""

        from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver

        return DeclarativeRuntimeDriver(self, journal=self.journal_factory.create())

    def new_state(
        self,
        *,
        trace_id: str,
        task: str,
        budget: Budget,
        agent_role: str,
        from_role: str,
        team_awareness: TeamAwareness | None,
    ) -> AgentState:
        """Create the complete fresh-run state from the declared runtime inputs.

        Keeping this constructor typed makes the runtime's only fresh-state
        transition auditable: callers cannot pass arbitrary state fields or
        bypass the explicit trace, task, budget, and team-context contract.
        """

        return AgentState(
            trace_id=trace_id,
            task=task,
            budget=budget,
            agent_role=agent_role,
            from_role=from_role,
            team_awareness=team_awareness,
        )


__all__ = ["DeclarativeRuntimeBindings", "RuntimePhaseCapabilities"]
