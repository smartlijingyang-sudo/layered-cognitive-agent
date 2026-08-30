"""Shared assembly invariants for open cognitive primitive groups.

A cognitive group owns two distinct facts: its ordered contribution catalog and
its single profile-selected assembly strategy.  Keeping these mechanics here
ensures Perceive and Gate services enforce identical collision and selection
rules without coupling their domain-specific protocols or construction inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from lca.contracts.mechanisms.capability import MissingCapabilityError

TContribution = TypeVar("TContribution")
TAssembler = TypeVar("TAssembler")


@dataclass(frozen=True, slots=True)
class OrderedContribution(Generic[TContribution]):
    """One immutable contribution registered by id and deterministic order."""

    id: str
    order: int
    value: TContribution


class OrderedContributionCatalog(Generic[TContribution]):
    """Fail-closed catalog for one cognitive group's ordered contributions.

    A profile enables each contribution exactly once.  Reusing an id would make
    activation order decide which implementation survives, so it is rejected
    rather than silently replacing the existing contribution.
    """

    def __init__(self, *, group: str, contribution_kind: str) -> None:
        self._group = group
        self._contribution_kind = contribution_kind
        self._entries: dict[str, OrderedContribution[TContribution]] = {}

    def register(self, *, id: str, order: int, value: TContribution) -> None:
        if id in self._entries:
            raise ValueError(
                f"{self._group} group already has {self._contribution_kind} contribution {id!r}"
            )
        self._entries[id] = OrderedContribution(id=id, order=order, value=value)

    def ordered(self) -> tuple[OrderedContribution[TContribution], ...]:
        """Return the immutable contribution view in deterministic order."""

        return tuple(sorted(self._entries.values(), key=lambda entry: (entry.order, entry.id)))


@dataclass(frozen=True, slots=True)
class AssemblyStrategy(Generic[TAssembler]):
    """The sole assembly strategy selected for one group scope."""

    id: str
    assembler: TAssembler


class SingleAssemblyStrategy(Generic[TAssembler]):
    """Own one replaceable, profile-selected assembly strategy per group.

    Re-registering the same identity supports configuration reconciliation.  A
    different identity is an ambiguous profile and fails while the group is
    still being assembled, before any runtime object is constructed.
    """

    def __init__(self, *, group: str, role: str) -> None:
        self._group = group
        self._role = role
        self._selection: AssemblyStrategy[TAssembler] | None = None

    @property
    def id(self) -> str | None:
        """Return the selected strategy identity for diagnostics."""

        return None if self._selection is None else self._selection.id

    def select(self, assembler: TAssembler, *, id: str) -> None:
        current = self._selection
        if current is not None and current.id != id:
            raise ValueError(
                f"{self._group} group already has {self._role} {current.id!r}; "
                f"cannot also register {id!r}"
            )
        self._selection = AssemblyStrategy(id=id, assembler=assembler)

    def require(self, *, message: str) -> TAssembler:
        """Return the selected strategy or fail closed for an incomplete profile."""

        if self._selection is None:
            raise MissingCapabilityError(message)
        return self._selection.assembler


__all__ = [
    "AssemblyStrategy",
    "OrderedContribution",
    "OrderedContributionCatalog",
    "SingleAssemblyStrategy",
]
