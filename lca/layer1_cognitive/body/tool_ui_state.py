"""Tool UI state — Strategy Registry for journal ``plugin_state``.

SSOT, not dual-track guessing:
- ``arguments_preview`` / ``result_preview`` are *lossy* journal strings
- ``ToolStarted.plugin_state`` / ``ToolInvoked.plugin_state`` are *full*
  structured UI state (dict fields are not truncated by AttributePolicy)
- SafeExecutor produces both at the body boundary; projectors *prefer*
  plugin_state and only fall back to previews for legacy events.

Builder implementations live in ``tool_ui_builders`` (separated to stay
under the per-file effective-line limit).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.layer1_cognitive.body.tool_ui_builders import (
    _invoked_activate_skill,
    _invoked_default,
    _invoked_from_payload_state,
    _started_activate_skill,
    _started_default,
    _started_execute_code,
    _started_run_command,
    _started_web_search,
)

# ── Types ───────────────────────────────────────────────────

StartedBuilder = Callable[[dict[str, Any]], dict[str, Any]]
"""args → initial plugin_state for ToolStarted (code/command visible immediately)."""

InvokedBuilder = Callable[[dict[str, Any], dict[str, Any], bool, str], dict[str, Any]]
"""(args, payload, ok, error) → plugin_state for ToolInvoked."""

# Preview budget: stay under AttributePolicy generic 2k with valid JSON always.
_ARGS_PREVIEW_BUDGET = 1_800
_STRING_FIELD_BUDGET = 240

# Wire-relevant keys overlaid from plugin_state onto truncated args for SSE.
_WIRE_OVERLAY_KEYS = (
    "code",
    "command",
    "language",
    "description",
    "skill_id",
    "query",
    "path",
    "content",
    "directoryPath",
    "directory_path",
    "timeout",
    "timeout_s",
    "background",
)

# Noise keys from preview-only bookkeeping that must not leak into wire args.
_WIRE_NOISE_KEYS = (
    "code_truncated",
    "command_truncated",
    "code_chars",
    "command_chars",
    "args_preview_truncated",
    "success",
    "executionEnv",
    "hasResources",
    "source",
    "title",
    "description",
    "resources",
    "content",
    "stdout",
    "stderr",
    "output",
    "exitCode",
    "error",
    "errorDetail",
)

_STARTED_BUILDERS: dict[str, StartedBuilder] = {
    "execute_code": _started_execute_code,
    "run_command": _started_run_command,
    "sandbox_execute": _started_execute_code,
    "activate_skill": _started_activate_skill,
    "web_search": _started_web_search,
}

_INVOKED_BUILDERS: dict[str, InvokedBuilder] = {
    "activate_skill": _invoked_activate_skill,
    "execute_code": _invoked_from_payload_state,
    "run_command": _invoked_from_payload_state,
    "sandbox_execute": _invoked_from_payload_state,
    "list_files": _invoked_from_payload_state,
    "read_file": _invoked_from_payload_state,
    "write_file": _invoked_from_payload_state,
    "edit_file": _invoked_from_payload_state,
    "search_files": _invoked_from_payload_state,
    "move_files": _invoked_from_payload_state,
    "grep_content": _invoked_from_payload_state,
    "glob_files": _invoked_from_payload_state,
    "get_command_output": _invoked_from_payload_state,
    "kill_command": _invoked_from_payload_state,
    "export_file": _invoked_from_payload_state,
    "web_search": _invoked_from_payload_state,
    "run_skill_script": _invoked_from_payload_state,
}


# ── Public API ──────────────────────────────────────────────


def register_started_builder(tool_name: str, builder: StartedBuilder) -> None:
    _STARTED_BUILDERS[tool_name] = builder


def register_invoked_builder(tool_name: str, builder: InvokedBuilder) -> None:
    _INVOKED_BUILDERS[tool_name] = builder


def build_started_plugin_state(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Full initial UI state for ToolStarted (code/command not truncated)."""
    return _STARTED_BUILDERS.get(tool_name, _started_default)(args)


def build_invoked_plugin_state(
    tool_name: str,
    args: dict[str, Any],
    obs: Observation,
) -> dict[str, Any]:
    """Full final UI state for ToolInvoked.

    Prefer ``payload.state`` (computer/search already LobeHub-shaped), then
    tool-specific builders (skills), then defaults.
    """
    payload = obs.payload if isinstance(obs.payload, dict) else {}
    ok = bool(obs.success)
    error = "" if ok else (obs.error or "")

    nested = payload.get("state") if isinstance(payload, dict) else None
    if isinstance(nested, dict) and nested:
        state = dict(nested)
        state["success"] = ok
        if error and not ok:
            state.setdefault("error", error)
            state.setdefault("errorDetail", error)
        if tool_name == "activate_skill" and "content" not in state:
            skill_state = _invoked_activate_skill(args, payload, ok, error)
            for key in ("content", "title", "description", "resources", "id", "name", "skill_id"):
                if key in skill_state and key not in state:
                    state[key] = skill_state[key]
        return state

    return _INVOKED_BUILDERS.get(tool_name, _invoked_default)(args, payload, ok, error)


def compact_args_preview(args: dict[str, Any]) -> str:
    """Valid JSON under budget for ``arguments_preview`` (never mid-string cut)."""
    compact: dict[str, Any] = {}
    for key, value in args.items():
        if key == "code" and isinstance(value, str):
            compact["code_chars"] = len(value)
            if len(value) > _STRING_FIELD_BUDGET:
                compact["code"] = value[:_STRING_FIELD_BUDGET] + "…"
                compact["code_truncated"] = True
            else:
                compact["code"] = value
            continue
        if key == "command" and isinstance(value, str):
            compact["command_chars"] = len(value)
            if len(value) > 500:
                compact["command"] = value[:500] + "…"
                compact["command_truncated"] = True
            else:
                compact["command"] = value
            continue
        if isinstance(value, str) and len(value) > _STRING_FIELD_BUDGET:
            compact[key] = value[:_STRING_FIELD_BUDGET] + "…"
            continue
        compact[key] = value

    raw = json.dumps(compact, ensure_ascii=False, default=str)
    if len(raw) <= _ARGS_PREVIEW_BUDGET:
        return raw

    # Emergency shrink: keep identifiers + sizes only.
    emergency: dict[str, Any] = {}
    keep_keys = {
        "language",
        "description",
        "skill_id",
        "query",
        "path",
        "timeout",
        "timeout_s",
        "background",
    }
    for key, value in compact.items():
        if key.endswith("_chars") or key.endswith("_truncated") or key in keep_keys:
            emergency[key] = value
        elif isinstance(value, str):
            emergency[key] = value[:80] + ("…" if len(value) > 80 else "")
        elif isinstance(value, (int, float, bool)) or value is None:
            emergency[key] = value
    emergency["args_preview_truncated"] = True
    return json.dumps(emergency, ensure_ascii=False, default=str)[:_ARGS_PREVIEW_BUDGET]


def wire_arguments_json(
    *,
    arguments_preview: str,
    plugin_state: dict[str, Any] | None,
) -> str:
    """Merge truncated preview + full plugin_state into valid wire args JSON."""
    base: dict[str, Any] = {}
    if arguments_preview:
        try:
            parsed = json.loads(arguments_preview)
            if isinstance(parsed, dict):
                base = dict(parsed)
        except (json.JSONDecodeError, TypeError, ValueError):
            base = {}

    state = plugin_state or {}
    for key in _WIRE_OVERLAY_KEYS:
        value = state.get(key)
        if value is None or value == "":
            continue
        base[key] = value

    if "skill_id" not in base:
        skill_id = state.get("skill_id") or state.get("id")
        if isinstance(skill_id, str) and skill_id:
            base["skill_id"] = skill_id

    for noise in _WIRE_NOISE_KEYS:
        base.pop(noise, None)

    return json.dumps(base, ensure_ascii=False, default=str)
