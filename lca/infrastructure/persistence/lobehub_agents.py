"""Read LobeHub ``agents`` rows for the ``agt_* ↔ asst_*`` mapping.

The mapping truth for a LobeHub agent row is
``agents.agency_config->>'lcaAssistantId'`` (ADR-0187 §3 D7; written by
``assistant.webserver_bridge``). The LCA ownership store keeps a user-scoped
copy for onboarding/REST flows, but run-created assistants exist only in this
table. Run binding consults this helper as a fail-soft fallback so
``lca-ops runs create --agent <agt_*>`` can bind to run-created assistants.
"""

from __future__ import annotations

from lca.infrastructure.persistence.postgres import (
    lobehub_database_url,
    postgres_connection,
)


def agent_assistant_id_from_lobehub(agent_id: str) -> str | None:
    """Return the ``asst_*`` id bound to a LobeHub ``agt_*`` row, or ``None``.

    Fail-soft: returns ``None`` when ``agent_id`` is empty, no Postgres URL is
    configured, the ``agents`` table is unreachable, or the row / mapping is
    absent. Never raises into the run-creation path.
    """
    if not agent_id:
        return None
    url = lobehub_database_url()
    if not url:
        return None
    try:
        with postgres_connection(url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT agency_config->>'lcaAssistantId' AS assistant_id "
                "FROM agents WHERE id = %s AND agency_config ? 'lcaAssistantId'",
                (agent_id,),
            )
            row = cur.fetchone()
    except Exception:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


__all__ = ("agent_assistant_id_from_lobehub",)
