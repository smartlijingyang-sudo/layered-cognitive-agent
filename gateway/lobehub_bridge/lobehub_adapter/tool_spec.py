"""Tool wire specification types, constants, and declarative builders.

Core abstractions for mapping LCA tool invocations to LobeHub's frontend protocol.
Also holds wire protocol constants (formerly protocol.py) and JSON helpers.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

# ═══════════════════════════════════════════════════════════
#  Wire protocol constants
# ═══════════════════════════════════════════════════════════

PLUGIN_SCHEMA_SEPARATOR: Final = "____"

# Plugin identifiers
LOBE_SKILLS_ID: Final = "lobe-skills"
LOBE_SKILL_STORE_ID: Final = "lobe-skill-store"
LOBE_LOCAL_SYSTEM_ID: Final = "lobe-local-system"
LOBE_WEB_BROWSING_ID: Final = "lobe-web-browsing"
LOBE_USER_INTERACTION_ID: Final = "lobe-user-interaction"
LOBE_CLOUD_SANDBOX_ID: Final = "lobe-cloud-sandbox"

# API method names — Skills
SKILLS_API_ACTIVATE: Final = "activateSkill"
SKILLS_API_EXEC: Final = "execScript"
SKILLS_API_READ_REF: Final = "readReference"

# API method names — Skill store
SKILL_STORE_API_SEARCH: Final = "searchSkill"
SKILL_STORE_API_IMPORT: Final = "importSkill"
SKILL_STORE_API_IMPORT_MARKET: Final = "importFromMarket"

# API method names — Web browsing
WEB_BROWSING_API_SEARCH: Final = "search"

# API method names — User interaction
USER_INTERACTION_API_ASK: Final = "askUserQuestion"

# API method names — Cloud sandbox (computer tools)
API_EXECUTE_CODE: Final = "executeCode"
API_RUN_COMMAND: Final = "runCommand"
API_LIST_FILES: Final = "listFiles"
API_READ_FILE: Final = "readFile"
API_WRITE_FILE: Final = "writeFile"
API_EDIT_FILE: Final = "editFile"
API_SEARCH_FILES: Final = "searchFiles"
API_MOVE_FILES: Final = "moveFiles"
API_GREP_CONTENT: Final = "grepContent"
API_GLOB_FILES: Final = "globFiles"
API_GET_COMMAND_OUTPUT: Final = "getCommandOutput"
API_KILL_COMMAND: Final = "killCommand"
API_EXPORT_FILE: Final = "exportFile"

# Limits
SKILL_CONTENT_MAX_LEN: Final = 32_000
TOOL_RESULT_PREVIEW_LIMIT: Final = 500

# ═══════════════════════════════════════════════════════════
#  JSON helpers
# ═══════════════════════════════════════════════════════════


def parse_args_json(raw: str) -> dict[str, Any]:
    """Parse a JSON arguments string; return ``{}`` on any failure."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_json_string(raw: str) -> str:
    """Ensure *raw* is valid JSON; wrap in ``{"preview": ...}`` if not."""
    text = (raw or "").strip()
    if not text:
        return "{}"
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"preview": text[:200]})


def first_str(args: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string value found under *keys*."""
    for key in keys:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def copy_fields(
    args: dict[str, Any],
    mapping: Sequence[tuple[str, str]] | dict[str, str],
) -> dict[str, Any]:
    """Generic field copy/rename. ``mapping`` is ``(source_key, dest_key)`` pairs."""
    items = mapping if isinstance(mapping, Sequence) else mapping.items()
    out: dict[str, Any] = {}
    for src, dst in items:
        val = args.get(src)
        if isinstance(val, str) and val.strip():
            out[dst] = val.strip()
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            out[dst] = val
    return out


# ═══════════════════════════════════════════════════════════
#  Strategy protocols
# ═══════════════════════════════════════════════════════════


class ArgsTransform(Protocol):
    """Strategy: adapt LCA tool arguments → LobeHub wire arguments."""

    def __call__(self, args: dict[str, Any]) -> dict[str, Any]: ...


class StateBuilder(Protocol):
    """Strategy: build LobeHub pluginState from LCA tool result."""

    def __call__(
        self, args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
    ) -> dict[str, Any]: ...


# ═══════════════════════════════════════════════════════════
#  ToolWireSpec
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ToolWireSpec:
    """Declarative mapping from an LCA tool to LobeHub's wire protocol."""

    lca_name: str
    identifier: str
    api_name: str
    transform_args: ArgsTransform
    build_state: StateBuilder

    @property
    def wire_name(self) -> str:
        return wire_tool_name(self.identifier, self.api_name)


def wire_tool_name(identifier: str, api_name: str) -> str:
    """Build the ``identifier____apiName`` wire format LobeHub expects."""
    return f"{identifier}{PLUGIN_SCHEMA_SEPARATOR}{api_name}"


def split_wire_name(wire_name: str) -> tuple[str, str]:
    """Split ``identifier____apiName`` back into LobeHub plugin coordinates."""
    if PLUGIN_SCHEMA_SEPARATOR in wire_name:
        identifier, api_name = wire_name.split(PLUGIN_SCHEMA_SEPARATOR, 1)
        return identifier, api_name
    return wire_name, ""


# ═══════════════════════════════════════════════════════════
#  FieldMapper: declarative arg transform builder
# ═══════════════════════════════════════════════════════════


class FieldMapper:
    """Declarative argument transform — maps fields by type."""

    def __init__(
        self,
        *,
        strings: Sequence[tuple[str, str]] = (),
        ints: Sequence[tuple[str, str]] = (),
        floats: Sequence[tuple[str, str]] = (),
        bools: Sequence[tuple[str, str]] = (),
        lists: Sequence[tuple[str, str]] = (),
    ) -> None:
        self._strings = list(strings)
        self._ints = list(ints)
        self._floats = list(floats)
        self._bools = list(bools)
        self._lists = list(lists)

    def __call__(self, args: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for src, dst in self._strings:
            val = args.get(src)
            if isinstance(val, str) and val.strip():
                out[dst] = val.strip()
        for src, dst in self._ints:
            val = args.get(src)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[dst] = int(val)
        for src, dst in self._floats:
            val = args.get(src)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[dst] = float(val)
        for src, dst in self._bools:
            val = args.get(src)
            if isinstance(val, bool):
                out[dst] = val
        for src, dst in self._lists:
            val = args.get(src)
            if isinstance(val, list):
                out[dst] = val
        return out


# ═══════════════════════════════════════════════════════════
#  Spec factory
# ═══════════════════════════════════════════════════════════


def merge_success_state(
    _args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
) -> dict[str, Any]:
    """Default state builder: shallow-copy payload + success + optional error."""
    state = dict(payload)
    state["success"] = ok
    if not ok and error:
        state["error"] = error
    return state


def _add_error(
    state: dict[str, Any], ok: bool, error: str, *, key: str = "error"
) -> dict[str, Any]:
    if not ok and error:
        state[key] = error
    return state


def make_spec(
    lca_name: str,
    identifier: str,
    api_name: str,
    transform_args: ArgsTransform,
    build_state: StateBuilder | None = None,
) -> ToolWireSpec:
    """Create a ToolWireSpec with a default state builder if none provided."""
    return ToolWireSpec(
        lca_name=lca_name,
        identifier=identifier,
        api_name=api_name,
        transform_args=transform_args,
        build_state=build_state or merge_success_state,
    )
