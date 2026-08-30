"""Run-scoped activated operational skills (for run_skill_script)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.protocols.memory.operational_skills import SkillNotFoundError

# Re-export for backward compatibility
__all__ = [
    "ActivatedSkill",
    "activated_skills_scope",
    "get_activated_skills",
    "get_newly_activated",
    "register_activated",
    "resolve_skill_for_exec",
]

_activated_skills: ContextVar[tuple[ActivatedSkill, ...]] = ContextVar(
    "lca_activated_skills",
    default=(),
)


def get_activated_skills() -> tuple[ActivatedSkill, ...]:
    return _activated_skills.get()


def register_activated(skill_id: str, name: str) -> None:
    current = _activated_skills.get()
    entry = ActivatedSkill(skill_id=skill_id, name=name)
    filtered = tuple(item for item in current if item.skill_id != skill_id)
    _activated_skills.set((*filtered, entry))


def get_newly_activated(
    known: Sequence[ActivatedSkill],
) -> list[ActivatedSkill]:
    """Return skills in contextvar that are not yet in *known* (by skill_id)."""
    known_ids = {s.skill_id for s in known}
    return [s for s in _activated_skills.get() if s.skill_id not in known_ids]


def resolve_skill_for_exec(skill_id: str | None) -> ActivatedSkill:
    activated = get_activated_skills()
    if skill_id:
        sid = skill_id.strip()
        for item in reversed(activated):
            if item.skill_id == sid or item.name == sid:
                return item
        raise SkillNotFoundError(f"未激活 skill: {skill_id!r}；请先 activate_skill")
    if not activated:
        raise SkillNotFoundError("无已激活 skill；请先 activate_skill")
    return activated[-1]


@contextmanager
def activated_skills_scope(items: Sequence[ActivatedSkill]) -> Iterator[tuple[ActivatedSkill, ...]]:
    cleaned = tuple(items)
    token: Token[tuple[ActivatedSkill, ...]] = _activated_skills.set(cleaned)
    try:
        yield cleaned
    finally:
        _activated_skills.reset(token)
