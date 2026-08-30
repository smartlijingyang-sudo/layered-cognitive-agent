"""Perceive, memory, state, and stop-cluster assembly helpers."""

from __future__ import annotations

from typing import cast

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.protocols import (
    MemorySystem,
    PerceiveHub,
    SharedMemoryStore,
    StateStore,
    StopPolicy,
)
from lca.contracts.protocols.spec import STATE_STORE_CHOICE_PROFILE_DEFAULT
from lca.infrastructure.capability.memory import MemoryService
from lca.infrastructure.capability.state_store import StateStoreService
from lca.infrastructure.observability.adapters import TelemetryMemoryAdapter
from lca.plugins.composer.internal.skill_store import active_skill_store


def resolve_memory(
    choice: str | MemorySystem,
    shared_store: SharedMemoryStore | None,
    memory_service: MemoryService,
) -> MemorySystem:
    """Resolve memory ownership, then apply the standard telemetry decorator."""

    if shared_store is not None:
        memory: MemorySystem = memory_service.create(shared_store=shared_store)
    elif not isinstance(choice, str):
        memory = choice
    elif choice in memory_service.providers.names():
        memory = memory_service.providers.get(choice)()
    else:
        raise MissingCapabilityError("memory")
    return TelemetryMemoryAdapter(memory)


def resolve_state_store(choice: str | StateStore, service: StateStoreService) -> StateStore:
    """Resolve the declared state-store choice through its capability service."""

    if not isinstance(choice, str):
        return choice
    if choice == STATE_STORE_CHOICE_PROFILE_DEFAULT:
        return service.create()
    if choice in service.providers.names():
        return service.providers.get(choice)()
    raise MissingCapabilityError("state_store")


def build_perceive_hub(
    memory: MemorySystem,
    *,
    store: object,
    scope: object,
    action_scope: ActionScope,
) -> PerceiveHub:
    """Assemble the active Perceive contributions for one Agent graph.

    The Perceive service owns contribution order and no-op behavior.  This
    composition helper supplies only the explicit run-local dependencies that
    its assembly interface requires.
    """

    service = require_capability(scope, "perceive")
    team = action_scope in {ActionScope.LEAD, ActionScope.MEMBER}
    members = service.members(team=team)
    skill_store = (
        active_skill_store(scope)
        if any(getattr(item, "needs", None) == "skills" for item in members)
        else None
    )
    return cast(
        "PerceiveHub", service.assemble(memory, store=store, skill_store=skill_store, team=team)
    )


def resolve_stop_policy(*, scope: object) -> StopPolicy:
    """Resolve the State-cluster policy consumed only by the fixed stop phase."""

    return cast("StopPolicy", require_capability(scope, "stop_policy"))


__all__ = [
    "build_perceive_hub",
    "resolve_memory",
    "resolve_state_store",
    "resolve_stop_policy",
]
