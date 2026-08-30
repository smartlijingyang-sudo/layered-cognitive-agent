"""Operational skill store / importer factory."""

from __future__ import annotations

from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.infrastructure.skills.bundled import ensure_bundled_skills
from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
from lca.infrastructure.skills.http_importer import HttpSkillImporter
from lca.infrastructure.skills.settings import get_skill_settings


def resolve_skill_store() -> DiskSkillPackageStore:
    """Return the disk skill store after materializing first-party bundled skills."""
    store = DiskSkillPackageStore(get_skill_settings())
    ensure_bundled_skills(store)
    return store


def resolve_skill_importer(store: SkillPackageInstaller | None = None) -> HttpSkillImporter:
    """Return the default HTTP importer bound to the supplied installer seam."""
    resolved_store = store if store is not None else resolve_skill_store()
    return HttpSkillImporter(store=resolved_store)
