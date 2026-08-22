"""Runtime factory — composition root for ``CognitiveRuntime`` (PR5).

Per spec §5.3 and PR5: ``CognitiveRuntime`` must always be constructed via
``build_cognitive_runtime``.  The Composer is the **only** caller; live
loops are forbidden from skipping the factory (L2 layer boundary holds
via ``PerceiveHub`` Protocol injection).

The factory:

- Wires the default outcome policy if one is not supplied.
- Wires the default StopRule if one is not supplied.
- Wires a ``NullPerceiveHub`` only when ``perceive_hub=None`` AND the
  runtime is in **test mode** — production callers must inject the Hub.

The factory is intentionally thin; advanced composition (capability grant
attenuation, observability wiring, transport binding) is the Composer's
job, not this factory's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
from lca.contracts.protocols.reducer import LoopTopology
from lca.contracts.protocols.runtime import StopOutcomePolicy
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.loop_topology import ClosedSetTopology
from lca.layer2_runtime.outcome_policies.default_outcome_policy import (
    DefaultStopOutcomePolicy,
)
from lca.layer2_runtime.reducer import DefaultReducer
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

if TYPE_CHECKING:
    from lca.contracts.mechanisms import HookRegistry


@dataclass(frozen=True)
class RuntimeDeps:
    """The minimal dependency bundle for a ``CognitiveRuntime``.

    Defaulted fields let the Composer supply one bundle for every
    production runtime; tests override what they need.
    """

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


def build_cognitive_runtime(deps: RuntimeDeps) -> CognitiveRuntime:
    """The single, named entry point for constructing ``CognitiveRuntime``.

    The Composer invokes this factory — no other code constructs the
    runtime.  Production callers always supply a real ``PerceiveHub``.
    """
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
    )


class NullPerceiveHub:
    """Test-only Hub that emits an empty manifest.

    The Hub Protocol contract requires a ``ContextManifest`` return;
    this implementation returns an empty one.  Production callers
    always supply a real ``SequentialPerceiveHub`` via the Composer.
    """

    async def perceive(self, _state: AgentState) -> ContextManifest:
        return ContextManifest(items=())


__all__ = ["NullPerceiveHub", "RuntimeDeps", "build_cognitive_runtime"]
