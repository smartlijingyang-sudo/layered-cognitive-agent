"""Contracts for discoverable, auditable operational skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SkillCatalogEntry:
    """Model-safe metadata for one discoverable skill, without its body."""

    skill_id: str
    name: str
    description: str
    version: str
    content_hash: str
    resources: tuple[str, ...] = ()
    when_to_use: str = ""
    trust: str = "local"
    model_invocable: bool = True
    user_invocable: bool = True


@dataclass(frozen=True)
class SkillCatalogSnapshot:
    entries: tuple[SkillCatalogEntry, ...]
    digest: str


@dataclass(frozen=True)
class LoadedSkill:
    entry: SkillCatalogEntry
    content: str


class SkillProvider(Protocol):
    """One named source of skill metadata and full skill content."""

    name: str

    async def snapshot_for(self, session_id: str) -> SkillCatalogSnapshot: ...

    async def load(self, name: str, session_id: str) -> LoadedSkill: ...


class SkillEventSink(Protocol):
    """Minimal SessionStore surface used by the skills service."""

    async def append(self, event_data: Any, *, actor: str | None = None, **kwargs: Any) -> Any: ...
