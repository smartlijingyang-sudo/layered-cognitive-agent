from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeAlias

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.protocols import MemorySystem, PerceiveHub, Sensor
from lca.contracts.protocols.think.cognition import PerceiveHubAssembler
from lca.cognition.group_assembly import (
    AssemblyStrategy,
    OrderedContributionCatalog,
    SingleAssemblyStrategy,
)

Needs = Literal["none", "store", "skills"]


@dataclass(frozen=True, slots=True)
class SensorEntry:
    id: str
    order: int
    factory: Callable[..., Sensor]
    team_only: bool = False
    needs: Needs = "none"


PerceiveAssemblerEntry: TypeAlias = AssemblyStrategy[PerceiveHubAssembler]


class PerceiveService:
    """Live Perceive-group registry with plugin-selected Hub assembly.

    Sensor plugins contribute ordered facts here. A separate, single
    PerceiveHubAssembler contribution selects how those facts become a Hub.
    The shared group-assembly primitives own collision detection and strategy
    selection, while this service retains Perceive-specific filtering and
    dependency-aware Sensor construction.
    """

    key = "perceive"

    def __init__(self) -> None:
        self._sensors = OrderedContributionCatalog[SensorEntry](
            group="perceive", contribution_kind="sensor"
        )
        self._assembly = SingleAssemblyStrategy[PerceiveHubAssembler](
            group="perceive", role="assembler"
        )

    def add(
        self,
        factory: Callable[..., Sensor],
        *,
        id: str,
        order: int,
        team_only: bool = False,
        needs: Needs = "none",
    ) -> None:
        """Register one profile-selected Sensor contribution.

        Contribution identities are fail-closed: two plugins cannot silently
        overwrite one another just because profile loading order changed.
        """

        entry = SensorEntry(
            id=id,
            order=order,
            factory=factory,
            team_only=team_only,
            needs=needs,
        )
        self._sensors.register(id=id, order=order, value=entry)

    def set_assembler(self, assembler: PerceiveHubAssembler, *, id: str) -> None:
        """Select the only Hub-assembly strategy for this group scope."""

        if not isinstance(assembler, PerceiveHubAssembler):
            raise TypeError(
                "perceive assembler must implement PerceiveHubAssembler, "
                f"got {type(assembler).__name__}"
            )
        self._assembly.select(assembler, id=id)

    @property
    def assembler_id(self) -> str | None:
        """Return the profile-selected Hub strategy id for diagnostics."""

        return self._assembly.id

    def members(self, *, team: bool = False) -> tuple[SensorEntry, ...]:
        return tuple(
            entry.value for entry in self._sensors.ordered() if not entry.value.team_only or team
        )

    def assemble(
        self,
        memory: MemorySystem,
        *,
        store: object | None = None,
        skill_store: object | None = None,
        team: bool = False,
    ) -> PerceiveHub:
        """Build the Hub through the Profile's registered assembly strategy."""

        sensors: list[Sensor] = []
        for entry in self.members(team=team):
            try:
                if entry.needs == "store":
                    sensors.append(entry.factory(store))
                elif entry.needs == "skills":
                    sensors.append(entry.factory(skill_store))
                else:
                    sensors.append(entry.factory())
            except MissingCapabilityError:
                raise
            except Exception:  # noqa: S112 — broken factory must not abort Hub
                continue

        assembler = self._assembly.require(
            message="perceive group has no Hub assembler; enable one profile contribution"
        )
        return assembler.assemble(sensors=tuple(sensors), memory=memory)


__all__ = ["Needs", "PerceiveAssemblerEntry", "PerceiveService", "SensorEntry"]
