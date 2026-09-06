"""SkillCatalogSensor — emit installed skills as a manifest item (PR14).

Reads the operational-skill store (``SkillPackageStore.list_installed``)
and projects the index into a list of dicts suitable for the manifest.
An empty store is a no-op (no item emitted).

When a Session is bound, also emits ``skill.catalog.published.v1`` when the
installed index digest changes (meta-event taxonomy skill domain).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from lca.contracts.harness.memory.skill import SkillCatalogEntry
from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.memory.operational_skills import SkillPackageStore


def _catalog_digest(entries: tuple[SkillCatalogEntry, ...]) -> str:
    encoded = json.dumps([asdict(entry) for entry in entries], ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SkillCatalogSensor(Sensor):
    """Snapshot the installed skill list into a ``skill_catalog`` item."""

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store
        self._last_digest: str = ""

    async def read(self, state: AgentState) -> list[ContextItem]:
        del state
        installed = self._store.list_installed()
        if not installed:
            return []
        entries = tuple(
            SkillCatalogEntry(
                skill_id=index.skill_id,
                name=index.name,
                description=index.summary or "",
                version=index.version,
                content_hash=getattr(index, "content_hash", "") or "",
                resources=tuple(getattr(index, "resource_paths", ()) or ()),
            )
            for index in installed
        )
        digest = _catalog_digest(entries)
        if digest != self._last_digest:
            from lca.infrastructure.observability.meta_event_emit import emit_skill_catalog_published

            emit_skill_catalog_published(entries=entries, digest=digest, source="perceive")
            self._last_digest = digest
        payload = [
            {
                "skill_id": entry.skill_id,
                "name": entry.name,
                "summary": entry.description,
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
