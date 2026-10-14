"""Single seam for the ``agt_* -> asst_*`` assistant-binding question (RA-141).

Three answerers used to exist (the ownership store's sqlite/postgres
implementations plus the LobeHub fallback), with the precedence living only
in a code comment hand-chained inside
``command_endpoints.decode_create_run``. This module owns the precedence so
new callers stop re-implementing the chain and the order is unit-testable
without an HTTP endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.ownership import AssistantOwnership

__all__ = ("resolve_assistant_binding",)


def resolve_assistant_binding(
    agent_id: str,
    ownership: AssistantOwnership | None,
    *,
    lobehub_fallback: Callable[[str], str | None] | None = None,
) -> str | None:
    """Resolve a LobeHub ``agt_*`` agent id to its ``asst_*`` assistant id.

    Precedence (single source of truth for "agt_* -> asst_*"):

    1. the ownership store — ``ownership.assistant_id_for_agent(agent_id)``,
       the user-scoped copy the ownership domain maintains;
    2. the LobeHub ``agents`` row fallback —
       ``agents.agency_config->>'lcaAssistantId'`` (ADR-0187 §3 D7, written
       by ``assistant.webserver_bridge``). Run-created assistants exist
       only in this table; the ownership store has no row for them.

    Fail-soft: a miss on both sources returns ``None`` (no DB / no mapping
    ⇒ unbound, I-A1). Never raises into the run-creation path.

    ``lobehub_fallback`` is the injected LobeHub reader. Callers on the
    transport layer pass their own lazy proxy (RA-135: importing this
    module must never require ``lobehub_agents`` to be importable). When
    ``None``, the real
    :func:`lca.infrastructure.persistence.lobehub_agents.agent_assistant_id_from_lobehub`
    is imported lazily inside this call, so an import-time failure of that
    module degrades to ``None`` instead of breaking the caller.
    """
    if ownership is not None:
        bound = ownership.assistant_id_for_agent(agent_id)
        if bound:
            return bound
    fallback = lobehub_fallback
    if fallback is None:
        try:
            from lca.infrastructure.persistence.lobehub_agents import (
                agent_assistant_id_from_lobehub as fallback,
            )
        except Exception:
            return None
    try:
        return fallback(agent_id)
    except Exception:
        return None
