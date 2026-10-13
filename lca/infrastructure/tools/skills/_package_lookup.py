"""Shared skill-package lookup for skill lifecycle tools.

``activate`` / ``deactivate`` / ``retire`` resolve a user-supplied skill
reference the same way: exact skill id first, then a case-insensitive name
fallback for input tolerance. One canonical implementation instead of
three copies.
"""

from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)


def resolve_package(store: SkillPackageStore, raw: str) -> SkillPackage | None:
    """Resolve a skill package by id, falling back to case-insensitive name."""
    try:
        return store.get(raw)
    except SkillNotFoundError:
        # INTENTIONAL: 精确 ID 未命中 → 落到 case-insensitive 名字 fallback;
        # 这是用户输入容错的预期路径,不是错误。
        pass
    raw_lower = raw.lower()
    for entry in store.list_installed():
        if entry.name.lower() == raw_lower:
            return store.get(entry.skill_id)
    return None
