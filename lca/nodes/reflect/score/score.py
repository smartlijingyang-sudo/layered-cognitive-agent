"""phase.reflect.score — primitive node: invoke brain / reflection pipeline.

ADR-0221: reads the typed ``observation`` port from upstream perceive and
emits a typed ``reflection`` payload. Prefers the
``cognitive_reflection_pipeline`` capability (LCA-default seam), falls back
to ``brain.reflect`` when no pipeline is wired.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType, ContentType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.protocols.think.cognition import Brain
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _normalize_observation(value: object) -> object:
    """Convert an ``EffectReceipt`` to an ``Observation`` at the reflect boundary.

    ADR-0220 separates the act-world receipt from the reflect-world
    observation. Downstream reflection primitives (critic, memory) expect
    ``Observation.success``; the receipt exposes ``outcome`` instead.
    """
    if isinstance(value, EffectReceipt):
        return Observation(
            observation_id=new_id("obs"),
            success=value.outcome is EffectOutcome.SUCCEEDED,
            payload=None,
            content_type=ContentType.TEXT,
            error=value.error_code,
            extra={
                "effect_receipt_invocation_id": value.invocation_id,
                "effect_receipt_provider": value.provider,
                "effect_receipt_error_code": value.error_code,
                "effect_receipt_retryable": value.retryable,
            },
        )
    return value


@dataclass(frozen=True, slots=True)
class ReflectScoreExecutor:
    """Primitive: invoke the selected reflection seam, emit ``reflection``."""

    semantic_name: str = "phase.reflect.score"
    region: str = "reflect"
    declared_inputs: tuple[PortName, ...] = ("observation",)
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        observation = _normalize_observation(input.port_values.get("observation"))
        brain = runtime.get("brain")
        pipeline = runtime.get("cognitive_reflection_pipeline")
        payload: object | None = None
        # Prefer ``brain.reflect`` when the profile wired one: ``ModularBrain``
        # owns the canonical critic → pipeline wiring, so this path reaches
        # ``SimpleCritic.critique`` and emits a non-empty
        # ``critic.eval.{start,end}.state_id``. The previous branch routed
        # directly to ``pipeline.reflect(critic=None)`` and short-circuited
        # to ``ReflectionVerdict.ON_TRACK, lesson=None`` — the outer loop
        # never learned a tool had succeeded, so the agent re-issued the
        # same tool call every step (run-time loop until budget exhaustion).
        if isinstance(brain, Brain) and observation is not None:
            payload = await brain.reflect(runtime.get("agent_state"), observation)
        elif pipeline is not None and observation is not None:
            # Backward-compat: profiles that expose the reflection pipeline
            # capability but not a brain (lab / fixture paths). Without a
            # brain, there is no profile-selected critic to pass — preserve
            # the original short-circuit rather than silently injecting one.
            payload = await pipeline.reflect(
                state=runtime.get("agent_state"),
                observation=observation,
                critic=None,
            )
        return NodeOutput(
            port_values={
                "reflection": payload,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            },
        )


@plugin(
    id="phase.reflect.score",
    provides=("reflect::phase.reflect.score",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_phase_subgraph_parity.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_reflect_score.checked", "phase_reflect_score.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("phase:reflect::phase.reflect.score", ReflectScoreExecutor())


__all__ = ["ReflectScoreExecutor", "setup"]
