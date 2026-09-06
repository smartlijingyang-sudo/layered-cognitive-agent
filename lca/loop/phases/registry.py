"""PhaseExecutor registration read model (ADR-0194 §2.1, P4-L03).

Loop mechanism exposes semantic phase order and executor capability key shape.
Plugin implementations remain under ``lca.plugins`` until P4 plugin vertical cuts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lca.contracts.protocols.declarative.declarative_1.declarative_common import SemanticPhase
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import PhaseExecutor

SEMANTIC_PHASE_ORDER: tuple[SemanticPhase, ...] = (
    SemanticPhase.PERCEIVE,
    SemanticPhase.THINK,
    SemanticPhase.ACT,
    SemanticPhase.REFLECT,
    SemanticPhase.REMEMBER,
    SemanticPhase.STOP,
)

PHASE_EXECUTOR_CAPABILITY_PREFIX = "phase."


def semantic_phases() -> tuple[SemanticPhase, ...]:
    """Return the closed six-phase iteration order."""

    return SEMANTIC_PHASE_ORDER


def phase_executor_capability_key(*, semantic_phase: SemanticPhase, variant: str) -> str:
    """Build the canonical executor capability key for one semantic phase variant."""

    normalized = variant.strip()
    if not normalized:
        raise ValueError("phase executor variant must be non-empty")
    return f"{PHASE_EXECUTOR_CAPABILITY_PREFIX}{semantic_phase.value}.{normalized}"


def is_semantic_phase_closed_set(phases: Sequence[SemanticPhase]) -> bool:
    """True when ``phases`` contains exactly the ADR-0075 closed set."""

    return set(phases) == set(SEMANTIC_PHASE_ORDER)


class PhaseExecutorRegistry:
    """Read-only view over resolved phase executor bindings."""

    __slots__ = ("_executors",)

    def __init__(self, executors: Mapping[str, PhaseExecutor]) -> None:
        self._executors = dict(executors)

    def get(self, capability_key: str) -> PhaseExecutor | None:
        return self._executors.get(capability_key)

    def keys(self) -> frozenset[str]:
        return frozenset(self._executors)

    def for_semantic_phase(
        self,
        semantic_phase: SemanticPhase,
    ) -> tuple[tuple[str, PhaseExecutor], ...]:
        prefix = f"{PHASE_EXECUTOR_CAPABILITY_PREFIX}{semantic_phase.value}."
        return tuple(
            sorted(
                (key, executor)
                for key, executor in self._executors.items()
                if key.startswith(prefix)
            )
        )


__all__ = [
    "PHASE_EXECUTOR_CAPABILITY_PREFIX",
    "SEMANTIC_PHASE_ORDER",
    "PhaseExecutorRegistry",
    "is_semantic_phase_closed_set",
    "phase_executor_capability_key",
    "semantic_phases",
]
