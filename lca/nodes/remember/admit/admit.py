"""phase.remember.admit — primitive: memory admission gate and authority verification.

ADR-0244: Filters meaningless noise and hallucinated assumptions using the
User > Tool > Model authority hierarchy. Only admitted memory items (verified
facts or validated procedural SOP candidates) pass through to phase.remember.write.
Pure text or zero-candidate reflections are filtered with zero cost (admitted=False).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class RememberAdmitExecutor:
    """Primitive: verify authority and admit memory candidates; emit admitted flag."""

    semantic_name: str = "phase.remember.admit"
    region: str = "remember"
    declared_inputs: tuple[PortName, ...] = (
        "decision",
        "observation",
        "reflection",
    )
    declared_outputs: tuple[PortName, ...] = (
        "decision",
        "observation",
        "reflection",
        "admitted",
        "candidate",
        "routing",
    )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        decision = input.port_values.get("decision")
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")

        # Fast-Path: missing reflection or explicit fast_path flag
        if reflection is None:
            return self._emit_rejection(decision, observation, reflection)

        extra: dict[str, Any] = getattr(reflection, "extra", {}) or {}
        if extra.get("fast_path") is True:
            return self._emit_rejection(decision, observation, reflection)

        # Extract candidates
        procedural_candidate = extra.get("procedural_candidate")
        semantic_candidates = self._semantic_candidates(extra)

        if procedural_candidate is None and not semantic_candidates:
            return self._emit_rejection(decision, observation, reflection)

        # Authority Check (ADR-0244 §3.3: User > Tool > Model)
        # Procedural candidates require successful tool chain execution
        if procedural_candidate is not None:
            obs_success = getattr(observation, "success", True)
            if not obs_success:
                # Failed execution must not be admitted as a viable SOP
                return self._emit_rejection(decision, observation, reflection)
            return self._emit_admission(
                decision, observation, reflection, candidate=procedural_candidate
            )

        # Semantic candidates: reject ungrounded model conjectures, keep the rest.
        admitted = [cand for cand in semantic_candidates if self._is_admissible(cand)]
        if not admitted:
            return self._emit_rejection(decision, observation, reflection)
        return self._emit_admission(decision, observation, reflection, candidate=admitted)

    @staticmethod
    def _semantic_candidates(extra: dict[str, Any]) -> list[dict[str, Any]]:
        """读取 ADR-0246 结构化候选列表；兼容旧的单候选 ``memory_candidate``。"""
        candidates = extra.get("memory_candidates")
        if isinstance(candidates, list):
            return [c for c in candidates if isinstance(c, dict)]
        single = extra.get("memory_candidate")
        if isinstance(single, dict):
            return [single]
        return []

    @staticmethod
    def _is_admissible(candidate: dict[str, Any]) -> bool:
        """权威度过滤：低置信度的模型推断不落盘（User > Tool > Model）。"""
        source = str(candidate.get("source") or "model")
        try:
            confidence = float(candidate.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return not (source == "model" and confidence < 0.8)

    def _emit_admission(
        self,
        decision: object,
        observation: object,
        reflection: object,
        candidate: object,
    ) -> NodeOutput:
        return NodeOutput(
            port_values={
                "decision": decision,
                "observation": observation,
                "reflection": reflection,
                "admitted": True,
                "candidate": candidate,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            }
        )

    def _emit_rejection(
        self,
        decision: object,
        observation: object,
        reflection: object,
    ) -> NodeOutput:
        return NodeOutput(
            port_values={
                "decision": decision,
                "observation": observation,
                "reflection": reflection,
                "admitted": False,
                "candidate": None,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            }
        )


@plugin(
    id="phase.remember.admit",
    provides=("remember::phase.remember.admit",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/integration/test_memory_and_procedural_distillation.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_remember_admit.checked",
                "phase_remember_admit.served",
            )
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
    ctx.provide("remember::phase.remember.admit", RememberAdmitExecutor())


__all__ = ["RememberAdmitExecutor", "setup"]
