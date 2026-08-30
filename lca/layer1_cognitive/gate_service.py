from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.cognition import DecisionGateAssembler
from lca.layer1_cognitive.group_assembly import (
    AssemblyStrategy,
    OrderedContributionCatalog,
    SingleAssemblyStrategy,
)


@dataclass(frozen=True, slots=True)
class GateEntry:
    id: str
    slot: str
    order: int
    factory: Callable[[], DecisionGate] | type[DecisionGate]


GateAssemblerEntry: TypeAlias = AssemblyStrategy[DecisionGateAssembler]


class GateService:
    """Live Decision-group registry with plugin-selected Gate composition.

    Gate plugins own membership, slots, and ordering. A single assembler
    contribution owns the strategy used to form an executable DecisionGate.
    The shared group-assembly primitives keep strategy selection and identity
    collision handling consistent with the Perceive group.
    """

    key = "gates"

    def __init__(self) -> None:
        self._gates = OrderedContributionCatalog[GateEntry](group="gate", contribution_kind="gate")
        self._assembly = SingleAssemblyStrategy[DecisionGateAssembler](
            group="gate", role="assembler"
        )

    def add(
        self,
        factory: Callable[[], DecisionGate] | type[DecisionGate],
        *,
        id: str,
        slot: str = "loop",
        order: int = 0,
    ) -> None:
        """Register one profile-selected Gate contribution.

        Duplicate identities are configuration conflicts, not replacement
        directives: failing here prevents load order from choosing policy.
        """

        entry = GateEntry(id=id, slot=slot, order=order, factory=factory)
        self._gates.register(id=id, order=order, value=entry)

    def set_assembler(self, assembler: DecisionGateAssembler, *, id: str) -> None:
        """Select the only Gate-assembly strategy for this group scope."""

        if not isinstance(assembler, DecisionGateAssembler):
            raise TypeError(
                "gate assembler must implement DecisionGateAssembler, "
                f"got {type(assembler).__name__}"
            )
        self._assembly.select(assembler, id=id)

    @property
    def assembler_id(self) -> str | None:
        """Return the profile-selected Gate strategy id for diagnostics."""

        return self._assembly.id

    def create(self, gate_id: str) -> DecisionGate:
        for entry in self._gates.ordered():
            if entry.id == gate_id:
                return _instantiate(entry.value.factory)
        raise KeyError(gate_id)

    def assemble(self, slot: str = "loop") -> DecisionGate:
        """Compose one slot through the Profile's registered Gate strategy."""

        gates = tuple(
            _instantiate(entry.value.factory)
            for entry in self._gates.ordered()
            if entry.value.slot == slot
        )
        assembler = self._assembly.require(
            message="gate group has no assembler; enable one profile contribution"
        )
        return assembler.assemble(gates=gates)


def _instantiate(factory: Callable[[], DecisionGate] | type[DecisionGate]) -> DecisionGate:
    result = factory() if callable(factory) else factory
    if not isinstance(result, DecisionGate):
        raise TypeError(f"gate factory produced {type(result).__name__}, expected DecisionGate")
    return result


__all__ = ["GateAssemblerEntry", "GateEntry", "GateService"]
