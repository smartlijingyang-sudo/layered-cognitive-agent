"""Postgres-backed tool message pluginState writer (LobeHub ``message_plugins``)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from lca.contracts.observability.tool_message_plugin_state import ToolMessagePluginStateStore
from lca.infrastructure.persistence.postgres import database_url_from_env, postgres_connection

_MERGE_STATE_SQL = """
UPDATE message_plugins
SET state = COALESCE(state, '{}'::jsonb) || %s::jsonb
WHERE tool_call_id = %s
"""


class NoopToolMessagePluginStateStore(ToolMessagePluginStateStore):
    """No-op writer for dev/test when LobeHub Postgres is unavailable."""

    async def write(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        state: dict[str, Any],
    ) -> None:
        del run_id, tool_call_id, state


class PostgresToolMessagePluginStateStore(ToolMessagePluginStateStore):
    """Merge projected tool state into ``message_plugins.state`` before ``tool_end``."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or database_url_from_env()

    @staticmethod
    def _merge_hil_run_id(run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        merged = dict(state)
        lca_raw = merged.get("lca")
        lca = dict(lca_raw) if isinstance(lca_raw, dict) else {}
        lca.setdefault("run_id", run_id)
        merged["lca"] = lca
        return merged

    def _write_sync(self, *, tool_call_id: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state)
        with postgres_connection(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_MERGE_STATE_SQL, (payload, tool_call_id))
            conn.commit()

    async def write(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        state: dict[str, Any],
    ) -> None:
        merged = self._merge_hil_run_id(run_id, state)
        await asyncio.to_thread(
            self._write_sync,
            tool_call_id=tool_call_id,
            state=merged,
        )


def resolve_tool_message_plugin_state_store() -> ToolMessagePluginStateStore:
    """Pick Postgres writer when ``DATABASE_URL`` is configured, else noop."""
    from lca.infrastructure.persistence.postgres import postgres_available

    if postgres_available():
        return PostgresToolMessagePluginStateStore()
    return NoopToolMessagePluginStateStore()


__all__ = (
    "NoopToolMessagePluginStateStore",
    "PostgresToolMessagePluginStateStore",
    "resolve_tool_message_plugin_state_store",
)
