"""Tool state builders — Strategy Registry for converting tool results to plugin_state.

Each tool type has a builder that transforms Observation → plugin_state.
The registry maps tool_name → builder function.

Design: Strategy + Registry pattern.
Adding a new tool = adding one builder function + registering it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from lca.contracts.models.observability.journal import ToolInvoked

_log = logging.getLogger(__name__)

# Type alias for builder functions
ToolStateBuilder = Callable[[dict[str, Any], dict[str, Any], bool, str], dict[str, Any]]
"""(arguments, payload, ok, error) → plugin_state"""


# ── Builder functions ───────────────────────────────────────


def build_sandbox_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Build plugin_state for sandbox tools (execute_code, run_command)."""
    state: dict[str, Any] = {
        "success": ok,
        "executionEnv": "sandbox",
    }

    # Extract code/output fields
    for key in (
        "code",
        "output",
        "stderr",
        "stdout",
        "exitCode",
        "exit_code",
        "command",
        "language",
    ):
        if key in payload:
            state[key] = payload[key]

    if error:
        state["error"] = error
        state["errorDetail"] = error

    return state


def build_skill_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Build plugin_state for activate_skill — includes full SKILL.md content."""
    state: dict[str, Any] = {
        "success": ok,
        "hasResources": True,
    }

    skill_id = payload.get("skill_id") or args.get("skill_id", "")
    text = payload.get("text", "")

    if skill_id:
        state["id"] = skill_id
        state["name"] = skill_id

    # Extract title from first heading
    if isinstance(text, str):
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                state["title"] = stripped[2:].strip()
                break

    # Full content for UI rendering
    if isinstance(text, str) and text:
        state["content"] = text

    # Extract resource list
    if "可用资源:" in text:
        # Parse resource list from header
        for line in text.split("\n"):
            if "可用资源:" in line:
                resources = line.split("可用资源:")[-1].strip()
                state["resources"] = resources
                break

    if error:
        state["error"] = error

    return state


def build_file_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Build plugin_state for file tools (write_file, read_file)."""
    state: dict[str, Any] = {"success": ok}

    for key in ("path", "url", "size", "sizeBytes", "size_bytes", "mime_type", "mimeType"):
        if key in payload:
            state[key] = payload[key]

    if error:
        state["error"] = error

    return state


def build_web_search_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Build plugin_state for web_search."""
    state: dict[str, Any] = {"success": ok}

    if "query" in args:
        state["query"] = args["query"]
    if "results" in payload:
        state["results"] = payload["results"]

    if error:
        state["errorDetail"] = error

    return state


def build_default_state(
    args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Default fallback builder — passes through payload fields."""
    state: dict[str, Any] = {"success": ok}

    # Copy relevant payload fields
    for key in ("output", "result", "data", "text", "content"):
        if key in payload:
            state[key] = payload[key]

    if error:
        state["error"] = error

    return state


# ── Registry ────────────────────────────────────────────────


_TOOL_STATE_BUILDERS: dict[str, ToolStateBuilder] = {
    # Sandbox tools
    "execute_code": build_sandbox_state,
    "run_command": build_sandbox_state,
    "sandbox_execute": build_sandbox_state,
    # Skill tools
    "activate_skill": build_skill_state,
    # File tools
    "write_file": build_file_state,
    "read_file": build_file_state,
    "list_files": build_file_state,
    # Search tools
    "web_search": build_web_search_state,
}


def get_tool_state_builder(tool_name: str) -> ToolStateBuilder:
    """Get the state builder for a tool. Returns default if not registered."""
    return _TOOL_STATE_BUILDERS.get(tool_name, build_default_state)


def register_tool_state_builder(tool_name: str, builder: ToolStateBuilder) -> None:
    """Register a custom state builder for a tool."""
    _TOOL_STATE_BUILDERS[tool_name] = builder


def build_tool_plugin_state(
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
    ok: bool,
    error: str,
) -> dict[str, Any]:
    """Build plugin_state for a tool invocation using the registry."""
    builder = get_tool_state_builder(tool_name)
    return builder(args, payload, ok, error)


def build_state_from_invoked(event: ToolInvoked) -> dict[str, Any]:
    """Build plugin_state from a ToolInvoked journal event."""
    args = _safe_parse_json(event.arguments_preview)
    payload = _safe_parse_json(event.result_preview)

    # If event has plugin_state, use it directly
    if event.plugin_state:
        state = dict(event.plugin_state)
        state["success"] = event.ok
        if event.error:
            state["error"] = event.error
        return state

    # Otherwise, build from payload using registry
    return build_tool_plugin_state(event.tool_name, args, payload, event.ok, event.error or "")


def _safe_parse_json(text: str) -> dict[str, Any]:
    """Parse JSON safely, returning empty dict on failure."""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
