"""Shared fingerprint helpers for loop detection gates (ADR-0191 R7)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256

from lca.contracts.models.core.decision import ToolCall
from lca.infrastructure.session.turn_control_reader import ControlTurnView


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
        {"tool_name": tool_call.tool_name, "arguments": tool_call.arguments}
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


def view_tool_fingerprint(turn: ControlTurnView) -> str | None:
    if turn.tool_name is None:
        return None
    payload = normalize_for_fingerprint(
        {"tool_name": turn.tool_name, "arguments": turn.tool_arguments or {}}
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
