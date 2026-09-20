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
from lca.contracts.models.cognition.boundary import ProceduralMemoryCandidate
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


def _extract_procedural_candidate(
    state: object, observation: object
) -> ProceduralMemoryCandidate | None:
    """Universal cognitive meta-feature extraction for procedural memory candidates.

    ADR-0244: Identifies candidates based PURELY on structural execution indicators:
    - Multi-step tool execution sequence (>= 2 successful tool hops)
    - Production of concrete deliverables (files/artifacts)
    NEVER inspects specific skill names or regex patterns.
    """
    if observation is None or not getattr(observation, "success", False):
        return None

    # Meta-feature 1: Check for tool sequence or multi-step history in state
    turns = getattr(state, "turns", ()) or ()
    tool_sequence: list[str] = []
    for t in turns:
        dec = getattr(t, "decision", None)
        for tc in getattr(dec, "tool_calls", ()) or ():
            tname = getattr(tc, "tool_name", "")
            if tname:
                tool_sequence.append(str(tname))
        action_name = getattr(dec, "action_name", "") or getattr(dec, "tool_name", "")
        if action_name and action_name not in ("respond", "think", "wait"):
            tool_sequence.append(str(action_name))

    obs_extra = getattr(observation, "extra", {}) or {}
    files = obs_extra.get("generated_files") or ()

    # Trigger condition: multi-step tool sequence (>=2) or deliverable files produced
    if len(tool_sequence) >= 2 or len(files) > 0:
        candidate_id = new_id("cand_proc")
        return ProceduralMemoryCandidate(
            candidate_id=candidate_id,
            workflow_summary=f"Automated workflow with {len(tool_sequence)} steps and {len(files)} outputs",
            tool_sequence=tuple(tool_sequence),
            evidence_count=len(tool_sequence) + len(files),
            confidence=0.9,
            suggested_title=f"Procedural SOP ({len(tool_sequence)} actions)",
        )
    return None


@dataclass(frozen=True, slots=True)
class ReflectScoreExecutor:
    """Primitive: invoke the selected reflection seam, emit ``reflection``."""

    semantic_name: str = "phase.reflect.score"
    region: str = "reflect"
    declared_inputs: tuple[PortName, ...] = (
        "observation",
        "state",
        "cognitive_reflection_pipeline",
    )
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        observation = _normalize_observation(input.port_values.get("observation"))
        brain = getattr(runtime, "brain", None)
        if brain is None and hasattr(runtime, "get"):
            brain = runtime.get("brain")
        pipeline = input.port_values.get("cognitive_reflection_pipeline")
        state = input.port_values.get("state")
        if state is None and hasattr(runtime, "get"):
            state = runtime.get("agent_state")
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
            payload = await brain.reflect(state, observation)
        elif pipeline is not None and observation is not None:
            # Backward-compat: profiles that expose the reflection pipeline
            # capability but not a brain (lab / fixture paths). Without a
            # brain, there is no profile-selected critic to pass — preserve
            # the original short-circuit rather than silently injecting one.
            payload = await pipeline.reflect(
                state=state,
                observation=observation,
                critic=None,
            )

        # ADR-0244: Universal procedural memory candidate extraction
        candidate = _extract_procedural_candidate(state, observation)
        if candidate is not None:
            if payload is None:
                from lca.contracts.atoms.enums.enums import ReflectionVerdict
                from lca.contracts.models.core.execution.decision import Reflection

                payload = Reflection(
                    reflection_id=new_id("refl"),
                    verdict=ReflectionVerdict.ON_TRACK,
                    extra={"procedural_candidate": candidate},
                )
            elif hasattr(payload, "extra") and isinstance(payload.extra, dict):
                payload.extra["procedural_candidate"] = candidate

        # ADR-0246: semantic memory extraction moved to the
        # ``phase.reflect.memory.extract`` node (LLM distillation), so this
        # node no longer hardcodes intent keyword markers.

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
    ctx.provide("reflect::phase.reflect.score", ReflectScoreExecutor())


__all__ = ["ReflectScoreExecutor", "setup"]
