"""Gate group service — decision gates add themselves; assemble() builds the chain."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lca.contracts.protocols import DecisionGate
from lca.layer1_cognitive.brain.decision_gates.chained import ChainedDecisionGate


@dataclass(frozen=True, slots=True)
class GateEntry:
    id: str
    slot: str
    order: int
    factory: Callable[[], DecisionGate] | type[DecisionGate]


class GateService:
    """Live registry of DecisionGate contributions (ADR-0056)."""

    key = "gates"

    def __init__(self) -> None:
        self._entries: dict[str, GateEntry] = {}

    def add(
        self,
        factory: Callable[[], DecisionGate] | type[DecisionGate],
        *,
        id: str,
        slot: str = "loop",
        order: int = 0,
    ) -> None:
        self._entries[id] = GateEntry(id=id, slot=slot, order=order, factory=factory)

    def create(self, gate_id: str) -> DecisionGate:
        entry = self._entries[gate_id]
        return _instantiate(entry.factory)

    def assemble(self, slot: str = "loop") -> DecisionGate:
        chosen = [entry for entry in self._entries.values() if entry.slot == slot]
        chosen.sort(key=lambda entry: (entry.order, entry.id))
        gates = tuple(_instantiate(entry.factory) for entry in chosen)
        return ChainedDecisionGate(*gates)


def _instantiate(factory: Callable[[], DecisionGate] | type[DecisionGate]) -> DecisionGate:
    result = factory() if callable(factory) else factory
    if not isinstance(result, DecisionGate):
        raise TypeError(f"gate factory produced {type(result).__name__}, expected DecisionGate")
    return result
