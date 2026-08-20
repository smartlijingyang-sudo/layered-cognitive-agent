"""Perceive group service — sensors add themselves; assemble() builds the Hub."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.protocols import MemorySystem, PerceiveHub, Sensor
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub

Needs = Literal["none", "store", "skills"]


@dataclass(frozen=True, slots=True)
class SensorEntry:
    id: str
    order: int
    factory: Callable[..., Sensor]
    team_only: bool = False
    needs: Needs = "none"


class PerceiveService:
    """Live registry of Sensor contributions (ADR-0056)."""

    key = "perceive"

    def __init__(self) -> None:
        self._entries: dict[str, SensorEntry] = {}

    def add(
        self,
        factory: Callable[..., Sensor],
        *,
        id: str,
        order: int,
        team_only: bool = False,
        needs: Needs = "none",
    ) -> None:
        self._entries[id] = SensorEntry(
            id=id,
            order=order,
            factory=factory,
            team_only=team_only,
            needs=needs,
        )

    def members(self, *, team: bool = False) -> tuple[SensorEntry, ...]:
        items = [entry for entry in self._entries.values() if not entry.team_only or team]
        return tuple(sorted(items, key=lambda entry: (entry.order, entry.id)))

    def assemble(
        self,
        memory: MemorySystem,
        *,
        store: object | None = None,
        skill_store: object | None = None,
        team: bool = False,
    ) -> PerceiveHub:
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
        return SequentialPerceiveHub(sensors=sensors, memory=memory)


def register_builtin_sensors(service: PerceiveService) -> None:
    """Standard sensors for callers that have no booted plugin tree."""
    from lca.layer1_cognitive.sensors.clock import build_clock_sensor
    from lca.layer1_cognitive.sensors.journal_backed import (
        build_inbox_facts_sensor,
        build_team_inbox_sensor,
    )
    from lca.layer1_cognitive.sensors.skill_catalog import build_skill_catalog_sensor
    from lca.layer1_cognitive.sensors.workspace_artifacts import (
        build_workspace_artifacts_sensor,
    )
    from lca.layer1_cognitive.sensors.workspace_instructions import (
        build_workspace_instructions_sensor,
    )

    service.add(build_clock_sensor, id="clock", order=10)
    service.add(build_workspace_artifacts_sensor, id="workspace-artifacts", order=20)
    service.add(build_inbox_facts_sensor, id="inbox-facts", order=30, needs="store")
    service.add(
        build_team_inbox_sensor,
        id="team-inbox",
        order=40,
        team_only=True,
        needs="store",
    )
    service.add(build_workspace_instructions_sensor, id="workspace-instructions", order=50)
    service.add(build_skill_catalog_sensor, id="skill-catalog", order=60, needs="skills")
