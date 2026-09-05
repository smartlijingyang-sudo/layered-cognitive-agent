"""Resolve the active skill-store provider for composition concerns."""

from __future__ import annotations

from typing import Any

from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.infrastructure.observability.facade.run_ambit import current_assistant_id
from lca.infrastructure.skills.assistant_merged_store import AssistantMergedSkillStore


def active_skill_store(scope: object) -> Any:
    """Return the active store behind the declared ``skills`` capability.

    When the current run binds an ``assistant_id`` and ``assistant.skill_overlay``
    is available, merge that Home's ``skills/`` tree with the global store so
    prompt discovery and ``activate_skill`` see assistant-owned skills first.
    """
    store = provider_current(require_capability(scope, "skills"))
    if store is None:
        raise MissingCapabilityError("skills")
    assistant_id = current_assistant_id().strip()
    if not assistant_id:
        return store
    try:
        overlay_svc = require_capability(scope, "assistant.skill_overlay")
    except MissingCapabilityError:
        return store
    overlay = provider_current(overlay_svc)
    if overlay is None:
        return store
    return AssistantMergedSkillStore(
        global_store=store,
        overlay=overlay,
        assistant_id=assistant_id,
    )


__all__ = ["active_skill_store"]
