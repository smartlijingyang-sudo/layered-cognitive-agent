"""Operational skill store / importer factory."""

from __future__ import annotations

from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.infrastructure.skills.bundled.bundled import ensure_bundled_skills
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.http.importer import HttpSkillImporter
from lca.infrastructure.skills.settings.settings import get_skill_settings


def resolve_skill_store() -> DiskSkillPackageStore:
    """Pure construction: return the disk skill store without writing anything.

    RA-058: a function named "resolve" must never write to production.
    Bundled-skill materialization is an explicit boot step — see
    ``materialize_bundled_skills`` (called once by the skills provider,
    whose filesystem effect is declared on the plugin).
    """
    return DiskSkillPackageStore(get_skill_settings())


def materialize_bundled_skills(
    store: DiskSkillPackageStore | None = None,
) -> tuple[str, ...]:
    """Explicit boot step: install first-party bundled skills into ``store``.

    Returns the skill_ids that were (re)written; ``ensure_bundled_skills``
    is idempotent. The only production caller is ``lca-skills-provider``
    setup — every other call site uses the pure ``resolve_skill_store()``,
    so a mis-call can no longer silently rewrite the production
    ``~/.lca/skills`` (71515dace).
    """
    resolved = store if store is not None else resolve_skill_store()
    return ensure_bundled_skills(resolved)


def resolve_skill_importer(store: SkillPackageInstaller | None = None) -> HttpSkillImporter:
    """Return the default HTTP importer bound to the supplied installer seam."""
    resolved_store = store if store is not None else resolve_skill_store()
    return HttpSkillImporter(store=resolved_store)
