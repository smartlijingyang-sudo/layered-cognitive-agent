"""SupervisorBinder — composition-time hierarchical supervisor assembly (ADR-0026).

Single entry for wiring channel + decision gate + supervisor cognition.
Failures are explicit (no silent skip). Cognition promotion is injectable
so custom reasoners are not forced through ``isinstance(SimpleReasoner)``.
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import AgentTransport, Reasoner
from lca.contracts.protocols.capabilities import (
    HasBrainBodyMemory,
    HasChannel,
    HasReplaceableReasoner,
)
from lca.contracts.protocols.cognition import DecisionGate, SupportsDecisionGate
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner, SupervisorReasoner
from lca.layer3_agent.simple_agent import CognitiveAgent

SupervisorCognitionFactory = Callable[[Reasoner], Reasoner]


class SupervisorBindError(TypeError):
    """Hierarchical supervisor composition failed; fix assembly, do not ignore."""


def default_supervisor_cognition_factory(reasoner: Reasoner) -> Reasoner:
    """Default: identity if already supervisor; promote SimpleReasoner; else error."""
    if isinstance(reasoner, SupervisorReasoner):
        return reasoner
    if isinstance(reasoner, SimpleReasoner):
        return SupervisorReasoner.from_simple(reasoner)
    raise SupervisorBindError(
        f"cannot install supervisor cognition for reasoner type "
        f"{type(reasoner).__name__}: expected SimpleReasoner or SupervisorReasoner, "
        f"or pass SupervisorBinder(cognition_factory=...) that understands this type"
    )


class SupervisorBinder:
    """Assemble hierarchical supervisor capabilities at composition time.

    Parameters
    ----------
    cognition_factory:
        Maps the brain's current reasoner to supervisor cognition.
        Default promotes ``SimpleReasoner`` → ``SupervisorReasoner``.
        Inject a custom factory for specialized supervisor brains.
    """

    def __init__(
        self,
        *,
        cognition_factory: SupervisorCognitionFactory | None = None,
    ) -> None:
        self._cognition_factory: SupervisorCognitionFactory = (
            cognition_factory or default_supervisor_cognition_factory
        )

    def bind(
        self,
        supervisor: CognitiveAgent,
        *,
        transport: AgentTransport | None = None,
        policy: DecisionGate | None = None,
    ) -> None:
        """Wire channel, decision gate, and supervisor reasoner. Always explicit."""
        rt = supervisor.runtime
        if not isinstance(rt, HasBrainBodyMemory):
            raise SupervisorBindError(
                "supervisor.runtime must expose body/brain/memory "
                f"(HasBrainBodyMemory); got {type(rt).__name__}"
            )

        if transport is not None:
            if not isinstance(rt.body, HasChannel):
                raise SupervisorBindError(
                    "transport provided but supervisor body does not support "
                    f"HasChannel.bind_channel; body={type(rt.body).__name__}"
                )
            rt.body.bind_channel(transport)

        if policy is not None:
            if not isinstance(rt.brain, SupportsDecisionGate):
                raise SupervisorBindError(
                    "decision gate provided but supervisor brain does not support "
                    f"SupportsDecisionGate; brain={type(rt.brain).__name__}"
                )
            rt.brain.install_decision_gate(policy)

        self._install_cognition(rt.brain)

    def _install_cognition(self, brain: object) -> None:
        if not isinstance(brain, HasReplaceableReasoner):
            raise SupervisorBindError(
                "supervisor brain must expose a replaceable ``reasoner`` attribute "
                f"(HasReplaceableReasoner); brain={type(brain).__name__}. "
                "Install SupervisorReasoner on the brain before TeamOrchestrator, "
                "or use a ModularBrain-compatible brain."
            )
        current = brain.reasoner
        promoted = self._cognition_factory(current)
        if not isinstance(promoted, Reasoner):
            raise SupervisorBindError(
                f"cognition_factory must return a Reasoner; got {type(promoted).__name__}"
            )
        brain.reasoner = promoted
