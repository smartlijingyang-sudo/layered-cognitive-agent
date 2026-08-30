"""SkillCatalogSensor — emit installed skills as a manifest item (PR14).

Reads the operational-skill store (``SkillPackageStore.list_installed``)
and projects the index into a list of dicts suitable for the manifest.
An empty store is a no-op (no item emitted).
"""

from __future__ import annotations

from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.memory.operational_skills import SkillPackageStore


class SkillCatalogSensor(Sensor):
    """Snapshot the installed skill list into a ``skill_catalog`` item."""

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store

    async def read(self, state: AgentState) -> list[ContextItem]:
        del state
        entries = self._store.list_installed()
        if not entries:
            return []
        payload = [
            {
                "skill_id": entry.skill_id,
                "name": entry.name,
                "summary": entry.summary,
                "source_url": entry.source_url,
                "version": entry.version,
            }
            for entry in entries
        ]
        return [
            ContextItem(
                kind="skill_catalog",
                payload=payload,
                provenance="skill_catalog_sensor",
            )
        ]


def build_skill_catalog_sensor(store: SkillPackageStore) -> Sensor:
    """Named factory: ``sensor.skill-catalog`` (PR14)."""
    return SkillCatalogSensor(store)
