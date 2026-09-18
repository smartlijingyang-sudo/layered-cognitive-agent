"""Resolve the active skill store for a run/assistant scope (ADR-0242 D4).

Single source of the "global vs assistant-merged" decision so prompt
discovery (``<available_skills>``), skill tools (``activate_skill``) and run
assembly read the SAME store.  Before this helper existed, discovery already
used the merged view while the skill tools were still bound to the global
store — the "有发现、无加载" gap (ADR-0242 §1.1).
"""

from __future__ import annotations

from typing import Any, cast

from lca.contracts.mechanisms.capability.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore


def resolve_skill_store(scope: object, assistant_id: str) -> Any:
    """Return the global ``skills`` store or an assistant-merged view.

    The global store is returned when ``assistant_id`` is empty or the
    ``assistant.skill_overlay`` capability is absent, so the legacy
    (non-assistant / web-standard) path keeps its exact pre-ADR-0242
    behavior.  With both present, the merged view makes Home skills visible
    to every skill consumer of the run.
    """
    store = provider_current(require_capability(scope, "skills"))
    if store is None:
        raise MissingCapabilityError("skills")
    assistant_id = (assistant_id or "").strip()
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
        global_store=cast("Any", store),
        overlay=cast("AssistantSkillOverlay", overlay),
        assistant_id=assistant_id,
    )


__all__ = ["resolve_skill_store"]
