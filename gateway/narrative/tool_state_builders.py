"""Tool state builders — thin gateway facade over layer1 tool_ui_state.

SSOT for UI state production is ``lca.layer1_cognitive.body.tool_ui_state``.
This module remains for:
- TurnBuilder snapshot assembly from journal events
- Backward-compatible imports from ``gateway.narrative``

When ``ToolInvoked.plugin_state`` is present, it is used as-is (journal SSOT).
Otherwise we rebuild from previews via the same registry (legacy events).
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.observability.journal import ToolInvoked
from lca.layer1_cognitive.body.tool_ui_state import (
    build_invoked_plugin_state,
    build_started_plugin_state,
)


def build_tool_plugin_state(
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
    ok: bool,
    error: str,
) -> dict[str, Any]:
    """Rebuild plugin_state from args+payload (legacy / missing journal state)."""
    obs = Observation(
        observation_id="rebuild",
        success=ok,
        payload=payload,
        error=error,
    )
    return build_invoked_plugin_state(tool_name, args, obs)


def build_state_from_invoked(event: ToolInvoked) -> dict[str, Any]:
    """Build plugin_state from a ToolInvoked journal event.

    Prefer journal ``plugin_state`` (complete UI truth). Fall back to rebuilding
    from truncated previews only for legacy events.
    """
    if event.plugin_state:
        state = dict(event.plugin_state)
        state["success"] = event.ok
        if event.error and not event.ok:
            state.setdefault("error", event.error)
            state.setdefault("errorDetail", event.error)
        return state

    args = _safe_parse_json(event.arguments_preview)
    payload = _safe_parse_json(event.result_preview)
    return build_tool_plugin_state(event.tool_name, args, payload, event.ok, event.error or "")


def build_state_from_started(
    tool_name: str,
    arguments_preview: str,
    plugin_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initial card state for ToolStarted."""
    if plugin_state:
        return dict(plugin_state)
    args = _safe_parse_json(arguments_preview)
    return build_started_plugin_state(tool_name, args)


def _safe_parse_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
