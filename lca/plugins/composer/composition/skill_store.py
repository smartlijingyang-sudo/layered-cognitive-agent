"""Resolve the active skill-store provider for composition concerns."""

from __future__ import annotations

from typing import Any

from lca.infrastructure.observability.facade.run.ambit import current_assistant_id
from lca.infrastructure.skills.assistant.resolver import resolve_skill_store


def active_skill_store(scope: object) -> Any:
    """Return the active store behind the declared ``skills`` capability.

    When the current run binds an ``assistant_id`` and ``assistant.skill_overlay``
    is available, merge that Home's ``skills/`` tree with the global store so
    prompt discovery and ``activate_skill`` see assistant-owned skills first.
    """
    return resolve_skill_store(scope, current_assistant_id())


__all__ = ["active_skill_store"]
