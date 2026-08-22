"""Runtime factory used by plan-bound Agent assembly.

The factory stays intentionally thin: it closes an already-composed graph into
a ``CognitiveRuntime`` without leaking runtime construction into TeamComposer
or the HTTP carrier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    Body,
    Brain,
    MemorySystem,
    PerceiveHub,
    Reducer,
    StateStore,
    StopRule,
)
from lca.contracts.protocols.control_plan import ControlPlan
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.contracts.protocols.reducer import LoopTopology
from lca.contracts.protocols.runtime import StopOutcomePolicy
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.loop_topology import ClosedSetTopology
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.reducer import DefaultReducer
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

if TYPE_CHECKING:
    from lca.contracts.mechanisms import HookRegistry


@dataclass(frozen=True)
class RuntimeDeps:
    """The minimal dependency bundle for a ``CognitiveRuntime``."""

    brain: Brain
    body: Body
    memory: MemorySystem
    hooks: HookRegistry
    state_store: StateStore
    perceive_hub: PerceiveHub
    stop_rule: StopRule = field(default=None)  # type: ignore[assignment]
    outcome_policy: StopOutcomePolicy = field(default_factory=DefaultStopOutcomePolicy)
    reducer: Reducer = field(default_factory=DefaultReducer)
    topology: LoopTopology = field(default_factory=ClosedSetTopology)
    control_plan: ControlPlan | None = None
    compiled_plan: CompiledRunPlan | None = None
    phase_executors: Mapping[str, Any] = field(default_factory=dict)


def build_cognitive_runtime(deps: RuntimeDeps) -> CognitiveRuntime:
    """Construct a runtime from one fully composed dependency bundle."""

    stop_rule = deps.stop_rule or DefaultStopRule(deps.outcome_policy)
    return CognitiveRuntime(
        brain=deps.brain,
        body=deps.body,
        memory=deps.memory,
        hooks=deps.hooks,
        state_store=deps.state_store,
        stop_rule=stop_rule,
        perceive_hub=deps.perceive_hub,
        reducer=deps.reducer,
        topology=deps.topology,
        control_plan=deps.control_plan,
        compiled_plan=deps.compiled_plan,
        phase_executors=deps.phase_executors,
    )


class NullPerceiveHub:
    """Test-only hub that emits an empty context manifest."""

    async def perceive(self, _state: AgentState) -> ContextManifest:
        return ContextManifest(items=())


__all__ = ["NullPerceiveHub", "RuntimeDeps", "build_cognitive_runtime"]
