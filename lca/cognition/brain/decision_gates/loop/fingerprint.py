"""Shared fingerprint helpers for loop detection gates (ADR-0191 R7)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256

from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.session.context.turn_control_reader import ControlTurnView

_DIRECTORY_ARG_KEYS = ("directoryPath", "directory", "path", "dir")
_INSPECT_TOOLS = frozenset({"listFiles", "list_files", "readFile", "read_file"})
_RUN_COMMAND_TOOLS = frozenset({"runCommand", "local_runCommand", "run_command"})
_WORKSPACE_ROOT_ALIASES = frozenset({".", "./", "", "/mnt/data", "/mnt/data/"})


def _normalize_directory_path(path: str) -> str:
    stripped = path.strip()
    if stripped.rstrip("/") in _WORKSPACE_ROOT_ALIASES or stripped == "/mnt/data":
        return "."
    return stripped


def _normalize_shell_command(command: str) -> str:
    """Collapse cwd wrappers and path variants for intent-level loop detection."""
    text = command.strip()
    while True:
        match = re.match(r"cd\s+[^\s&]+\s*&&\s*(.+)", text, re.DOTALL | re.IGNORECASE)
        if match is None:
            break
        text = match.group(1).strip()
    officecli = re.match(
        r'officecli\s+(\S+)\s+(?:["\'])([^"\']+)(?:["\'])',
        text,
        re.IGNORECASE,
    )
    if officecli is not None:
        subcommand = officecli.group(1).lower()
        path = os.path.basename(officecli.group(2).strip())
        return f"officecli {subcommand} {path}"
    return text


def _normalize_tool_arguments(
    tool_name: str,
    arguments: Mapping[str, object] | None,
) -> dict[str, object]:
    if arguments is None:
        return {}
    normalized = dict(arguments)
    if tool_name in _RUN_COMMAND_TOOLS:
        command = normalized.get("command")
        if isinstance(command, str):
            normalized["command"] = _normalize_shell_command(command)
    if tool_name not in _INSPECT_TOOLS:
        return normalized
    for key in _DIRECTORY_ARG_KEYS:
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = _normalize_directory_path(value)
    return normalized


def fingerprint_payload(payload: object) -> str:
    """Return a deterministic SHA-256 digest for one normalized JSON payload."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def normalize_for_fingerprint(value: object) -> object | None:
    """Return a conservative JSON-safe canonical value or ``None`` when unknown."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        normalized_mapping: dict[str, object] = {}
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str):
                return None
            normalized_value = normalize_for_fingerprint(value[key])
            if normalized_value is None and value[key] is not None:
                return None
            normalized_mapping[key] = normalized_value
        return normalized_mapping
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        normalized_sequence: list[object] = []
        for item in value:
            normalized_value = normalize_for_fingerprint(item)
            if normalized_value is None and item is not None:
                return None
            normalized_sequence.append(normalized_value)
        return normalized_sequence
    if isinstance(value, (set, frozenset)):
        normalized_set: list[object] = []
        for item in value:
            normalized_value = normalize_for_fingerprint(item)
            if normalized_value is None and item is not None:
                return None
            normalized_set.append(normalized_value)
        return sorted(
            normalized_set,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    return None


def tool_call_fingerprint(tool_call: ToolCall) -> str | None:
    payload = normalize_for_fingerprint(
        {
            "tool_name": tool_call.tool_name,
            "arguments": _normalize_tool_arguments(
                tool_call.tool_name,
                tool_call.arguments,
            ),
        }
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


def view_tool_fingerprint(turn: ControlTurnView) -> str | None:
    if turn.tool_name is None:
        return None
    payload = normalize_for_fingerprint(
        {
            "tool_name": turn.tool_name,
            "arguments": _normalize_tool_arguments(
                turn.tool_name,
                turn.tool_arguments,
            ),
        }
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


def view_observation_fingerprint(turn: ControlTurnView) -> str | None:
    payload = normalize_for_fingerprint(
        {
            "success": turn.observation_success,
            "payload": turn.observation_payload,
            "error": turn.observation_error,
        }
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


__all__ = [
    "fingerprint_payload",
    "normalize_for_fingerprint",
    "tool_call_fingerprint",
    "view_observation_fingerprint",
    "view_tool_fingerprint",
]
