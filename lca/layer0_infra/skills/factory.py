"""Operational skill store / importer factory."""

from __future__ import annotations

from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore
from lca.layer0_infra.skills.http_importer import HttpSkillImporter
from lca.layer0_infra.skills.settings import get_skill_settings


def resolve_skill_store() -> DiskSkillPackageStore:
    return DiskSkillPackageStore(get_skill_settings())


def resolve_skill_importer() -> HttpSkillImporter:
    store = resolve_skill_store()
    return HttpSkillImporter(store=store)
