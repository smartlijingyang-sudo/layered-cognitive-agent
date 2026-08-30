"""Skill orchestration over a provider, with Session facts as the audit trail."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.events import (
    ContextInjected,
    SkillCatalogPublished,
    SkillLoaded,
    SkillUserInvoked,
)
from lca.contracts.harness.skill import (
    LoadedSkill,
    SkillCatalogEntry,
    SkillCatalogSnapshot,
    SkillEventSink,
    SkillProvider,
)
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)


class DiskSkillProvider(SkillProvider):
    """Expose an existing installed skill store through the harness provider SPI."""

    name = "filesystem"

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store

    async def snapshot_for(self, session_id: str) -> SkillCatalogSnapshot:
        del session_id
        entries = tuple(
            self._entry(self._store.get(index.skill_id)) for index in self._store.list_installed()
        )
        digest = _catalog_digest(entries)
        return SkillCatalogSnapshot(entries=entries, digest=digest)

    async def load(self, name: str, session_id: str) -> LoadedSkill:
        del session_id
        package = self._resolve(name)
        return LoadedSkill(entry=self._entry(package), content=package.content)

    def _resolve(self, name: str) -> SkillPackage:
        try:
            return self._store.get(name)
        except SkillNotFoundError:
            normalized = name.casefold().strip()
            for index in self._store.list_installed():
                if index.name.casefold() == normalized:
                    return self._store.get(index.skill_id)
        raise SkillNotFoundError(f"unknown skill: {name!r}")

    @staticmethod
    def _entry(package: SkillPackage) -> SkillCatalogEntry:
        return SkillCatalogEntry(
            skill_id=package.skill_id,
            name=package.name,
            description=package.summary,
            when_to_use=package.summary,
            version=package.version,
            content_hash=package.content_hash,
            resources=package.resource_paths,
        )


class SkillCatalogService:
    """Publishes changed catalogs and loads skills through one provider path."""

    def __init__(self, provider: SkillProvider) -> None:
        self._provider = provider
        self._published_digests: dict[str, str] = {}

    async def snapshot_for(self, session_id: str) -> SkillCatalogSnapshot:
        return await self._provider.snapshot_for(session_id)

    async def resolve(self, name: str, session_id: str) -> LoadedSkill:
        """Resolve a visible skill without activating or recording it."""
        return await self._provider.load(name, session_id)

    async def publish_catalog(
        self, session_id: str, events: SkillEventSink
    ) -> SkillCatalogSnapshot:
        snapshot = await self.snapshot_for(session_id)
        if self._published_digests.get(session_id) != snapshot.digest:
            await events.append(
                SkillCatalogPublished(entries=snapshot.entries, digest=snapshot.digest),
                actor="system",
            )
            self._published_digests[session_id] = snapshot.digest
        return snapshot

    async def load_for_model(
        self, name: str, session_id: str, events: SkillEventSink
    ) -> LoadedSkill:
        return await self._load(name, session_id, events, invocation="model")

    async def load_for_user(
        self, name: str, session_id: str, events: SkillEventSink
    ) -> LoadedSkill:
        return await self._load(name, session_id, events, invocation="user")

    async def activate_for_user(
        self, name: str, session_id: str, raw_text: str, events: SkillEventSink
    ) -> LoadedSkill:
        """Resolve, audit, and load a user activation through one provider seam."""
        loaded = await self._provider.load(name, session_id)
        await events.append(
            SkillUserInvoked(skill_id=loaded.entry.skill_id, raw_text=raw_text), actor="user"
        )
        await self._record_loaded(loaded, events, invocation="user")
        return loaded

    async def _load(
        self, name: str, session_id: str, events: SkillEventSink, *, invocation: str
    ) -> LoadedSkill:
        loaded = await self._provider.load(name, session_id)
        await self._record_loaded(loaded, events, invocation=invocation)
        return loaded

    async def _record_loaded(
        self, loaded: LoadedSkill, events: SkillEventSink, *, invocation: str
    ) -> None:
        await events.append(
            SkillLoaded(
                skill_id=loaded.entry.skill_id,
                content_hash=loaded.entry.content_hash,
                invocation=invocation,
            ),
            actor="agent" if invocation == "model" else "user",
        )


class SkillLoadTool(Tool):
    """The model-facing ``skill(name)`` tool, backed by SkillCatalogService."""

    name = "skill"
    description = "Load the full instructions for a skill listed in the skill catalog."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill id or name"}},
        "required": ["name"],
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self, catalog: SkillCatalogService, *, session_id: str, events: SkillEventSink
    ) -> None:
        self._catalog = catalog
        self._session_id = session_id
        self._events = events

    async def execute(self, args: dict[str, Any]) -> Observation:
        name = str(args.get("name") or "").strip()
        try:
            loaded = await self._catalog.load_for_model(name, self._session_id, self._events)
        except SkillNotFoundError as exc:
            return Observation(
                observation_id=new_id("obs"), success=False, payload=None, error=str(exc)
            )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "skill_id": loaded.entry.skill_id,
                "name": loaded.entry.name,
                "content": loaded.content,
                "resources": list(loaded.entry.resources),
            },
            content_type=ContentType.TEXT,
        )


@dataclass(frozen=True)
class SkillSlashInvocation:
    skill: LoadedSkill
    remaining_text: str


class SkillSlashActivationPolicy:
    """Server-side, deterministic handling for a user ``/skill`` gesture."""

    def __init__(self, catalog: SkillCatalogService) -> None:
        self._catalog = catalog

    async def pre_step(
        self, session_id: str, raw_text: str, events: SkillEventSink
    ) -> SkillSlashInvocation | None:
        parsed = _parse_slash(raw_text)
        if parsed is None:
            return None
        name, remaining_text = parsed
        try:
            loaded = await self._catalog.activate_for_user(name, session_id, raw_text, events)
        except SkillNotFoundError:
            return None
        await events.append(
            ContextInjected(
                source=f"skill:{loaded.entry.skill_id}",
                content_ref=f"skill:{loaded.entry.skill_id}@{loaded.entry.content_hash}",
            ),
            actor="system",
        )
        return SkillSlashInvocation(skill=loaded, remaining_text=remaining_text)


def _catalog_digest(entries: tuple[SkillCatalogEntry, ...]) -> str:
    encoded = json.dumps([asdict(entry) for entry in entries], ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_slash(raw_text: str) -> tuple[str, str] | None:
    text = raw_text.strip()
    if not text.startswith("/") or text.startswith("//"):
        return None
    command, _, remaining = text[1:].partition(" ")
    if not command:
        return None
    return command, remaining.strip()
