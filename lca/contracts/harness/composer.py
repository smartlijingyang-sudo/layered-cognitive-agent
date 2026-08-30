"""Composer contracts and complete graph containers.

ADR-0071 separates plan-bound composition by cognitive concept cluster.  A
cluster composer owns only its local contribution, while plan binding owns the
single transition from those contributions to a complete, runnable Agent
object graph.  Keeping those two shapes distinct prevents an incomplete graph
from being mistaken for a ready-to-run Agent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from lca.contracts.atoms.enums import ActionScope

_STANDARD_PHASE_CAPABILITY_FIELDS = ("brain", "body", "memory", "perceive_hub")


if TYPE_CHECKING:
    # Protocols are type-only here so importing ``lca.contracts.harness`` does
    # not create a contracts import cycle.
    from cordis import Context

    from lca.contracts.protocols import (
        AgentTransport,
        AgentUnit,
        Body,
        Brain,
        DecisionGate,
        HookRegistry,
        LLMAdapter,
        MemorySystem,
        ObservabilityBackend,
        PerceiveHub,
        SharedMemoryStore,
        StateStore,
        TeamStage,
        TeamStrategy,
    )
    from lca.contracts.protocols.spec import AgentSpec, TeamSpec


# ── Composition requests and graph containers ─────────────────────────


@dataclass(frozen=True, slots=True)
class AgentCompositionRequest:
    """The complete plan-derived input for one AgentGraph contribution.

    Every cluster composer consumes this immutable request.  Locating it in the
    contracts seam prevents the plan binder from depending on a plugin helper
    merely to describe the value it sends through the composer protocol.
    """

    spec: AgentSpec
    action_scope: ActionScope = ActionScope.SOLO
    team_channel: AgentTransport | None = None
    decision_gate: DecisionGate | None = None
    shared_store: SharedMemoryStore | None = None
    allowed_actions: frozenset[str] = frozenset()
    forbidden_actions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AgentGraph:
    """A complete, immutable object graph for one runnable Agent.

    This is intentionally a total value. It is created only after all declared
    cluster contributions are merged and checked; consumers may rely on every
    runtime dependency being present without re-checking fields. The five
    standard phase capabilities derive from these complete graph fields, so
    contributors only supply genuinely custom phase capabilities.
    """

    brain: Brain
    body: Body
    memory: MemorySystem
    state_store: StateStore
    perceive_hub: PerceiveHub
    hooks: HookRegistry
    observability: ObservabilityBackend
    llm: LLMAdapter
    phase_capabilities: Mapping[str, object] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze custom capabilities and derive standard ones from graph facts."""

        phase_capabilities = dict(self.phase_capabilities)
        redeclared = [
            capability
            for capability in _STANDARD_PHASE_CAPABILITY_FIELDS
            if capability in phase_capabilities
        ]
        if redeclared:
            raise ValueError(
                "AgentGraph phase_capabilities must not redeclare complete graph fields: "
                + ", ".join(redeclared)
            )
        phase_capabilities.update(
            {
                capability: getattr(self, capability)
                for capability in _STANDARD_PHASE_CAPABILITY_FIELDS
            }
        )
        object.__setattr__(
            self,
            "phase_capabilities",
            MappingProxyType(phase_capabilities),
        )


@dataclass(frozen=True, slots=True)
class AgentGraphContribution:
    """The local part of an AgentGraph owned by one cluster composer.

    ``None`` means that this composer does not own the field. This is the only
    graph shape allowed to be partial, making partiality explicit at the
    composition seam instead of hiding it behind an invalid ``AgentGraph``.
    ``phase_capabilities`` is reserved for custom capabilities: standard
    capabilities derive from the corresponding complete graph fields.
    """

    brain: Brain | None = None
    body: Body | None = None
    memory: MemorySystem | None = None
    state_store: StateStore | None = None
    perceive_hub: PerceiveHub | None = None
    hooks: HookRegistry | None = None
    observability: ObservabilityBackend | None = None
    llm: LLMAdapter | None = None
    phase_capabilities: Mapping[str, object] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze local phase capability contributions before graph merging."""

        object.__setattr__(
            self,
            "phase_capabilities",
            MappingProxyType(dict(self.phase_capabilities)),
        )


@dataclass(frozen=True, slots=True)
class TeamGraph:
    """A complete object graph for one Team collaboration cluster."""

    members: tuple[AgentUnit, ...]
    strategy: TeamStrategy
    stage: TeamStage
    transport: AgentTransport | None
    observability: ObservabilityBackend
    lead: AgentUnit | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Module-level accessors (ADR-0015) ──────────────────────────────────


def agent_graph_has_brain(graph: AgentGraph) -> bool:
    """A complete AgentGraph always contains its Brain dependency."""

    return graph.brain is not None


def agent_graph_has_body(graph: AgentGraph) -> bool:
    """A complete AgentGraph always contains its Body dependency."""

    return graph.body is not None


def team_graph_member_count(graph: TeamGraph) -> int:
    """Return the number of TeamGraph members."""

    return len(graph.members)


# ── Composer Protocols ───────────────────────────────────────────────


@runtime_checkable
class AgentGraphComposer(Protocol):
    """Compose one local contribution for exactly one cognitive cluster.

    Brain, Body, and Perceive composition have deliberately narrow interfaces:
    they may contribute their own fields but cannot claim to return a complete
    Agent graph or compose a Team.
    """

    key: ClassVar[str]

    def compose_agent(
        self, request: AgentCompositionRequest, scope: Context
    ) -> AgentGraphContribution:
        """Construct the contribution owned by this composer."""
        ...


@runtime_checkable
class TeamGraphComposer(Protocol):
    """Compose one complete TeamGraph for the collaboration cluster."""

    key: ClassVar[str]

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        """Construct a complete TeamGraph for one TeamSpec."""
        ...


# ── Module-level helpers (ADR-0015) ──────────────────────────────────


def merge_agent_graphs(*contributions: AgentGraphContribution) -> AgentGraph:
    """Close disjoint cluster contributions into one complete AgentGraph.

    Every runtime field has exactly one cluster owner.  Rejecting a second
    non-null contribution makes a profile conflict visible at the composition
    seam instead of letting capability ordering silently choose an
    implementation.  The function then applies the closure check once, at
    the real seam between composition and execution.  A partial graph
    therefore cannot reach any caller that accepts an ``AgentGraph``.
    """

    if not contributions:
        raise ValueError("merge_agent_graphs requires at least one contribution")

    fields = (
        "brain",
        "body",
        "memory",
        "state_store",
        "perceive_hub",
        "hooks",
        "observability",
        "llm",
    )
    values: dict[str, Any] = dict.fromkeys(fields)
    owners: dict[str, str] = {}
    phase_capabilities: dict[str, object] = {}
    phase_capability_owners: dict[str, str] = {}
    metadata: dict[str, Any] = {}
    for index, contribution in enumerate(contributions, start=1):
        contributor = str(contribution.metadata.get("composer", f"contribution[{index}]"))
        for field_name in fields:
            value = getattr(contribution, field_name)
            if value is None:
                continue
            if field_name in owners:
                raise ValueError(
                    "AgentGraph contribution conflict for "
                    f"{field_name!r}: {owners[field_name]!r} and {contributor!r} both provide it"
                )
            values[field_name] = value
            owners[field_name] = contributor
        redeclared = [
            capability
            for capability in _STANDARD_PHASE_CAPABILITY_FIELDS
            if capability in contribution.phase_capabilities
        ]
        if redeclared:
            raise ValueError(
                "AgentGraph contribution must provide standard phase capabilities "
                "through complete graph fields, not phase_capabilities: " + ", ".join(redeclared)
            )
        for capability, value in contribution.phase_capabilities.items():
            if value is None:
                raise ValueError(
                    "AgentGraph phase capability must not be None: "
                    f"{capability!r} from {contributor!r}"
                )
            if capability in phase_capability_owners:
                raise ValueError(
                    "AgentGraph phase capability conflict for "
                    f"{capability!r}: {phase_capability_owners[capability]!r} and "
                    f"{contributor!r} both provide it"
                )
            phase_capabilities[capability] = value
            phase_capability_owners[capability] = contributor
        metadata.update(contribution.metadata)

    missing = tuple(field_name for field_name in fields if values[field_name] is None)
    if missing:
        raise ValueError(
            "AgentGraph is incomplete after merging contributions: " + ", ".join(missing)
        )
    return AgentGraph(
        phase_capabilities=phase_capabilities,
        metadata=metadata,
        **values,
    )


__all__ = [
    "AgentCompositionRequest",
    "AgentGraph",
    "AgentGraphComposer",
    "AgentGraphContribution",
    "TeamGraph",
    "TeamGraphComposer",
    "agent_graph_has_body",
    "agent_graph_has_brain",
    "merge_agent_graphs",
    "team_graph_member_count",
]
