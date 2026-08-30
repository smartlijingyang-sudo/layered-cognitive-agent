"""Project (args + Observation) → wire-shaped LobeHub state.

Reads the Tool's RenderContract and produces a dict shaped exactly as the
LobeHub renderer expects to read from pluginState + args.

This is the SINGLE source of truth for what crosses the SSE wire as
``projected_state``.  It replaces the brittle argv-style key lifting in
``gateway/runs/journal_lifting.py`` (which will be deleted in Task 7).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.layer0_infra.tools.contract.render import FieldSpec, get_contract

__all__ = [
    "project_args",
    "project_content",
    "project_full",
    "project_tool_state",
]


def project_tool_state(
    tool_name: str,
    args: dict[str, Any],
    observation: Observation,
) -> dict[str, Any]:
    """Map args + observation → wire-shaped state dict via the RenderContract.

    Result keys are ``wire_key`` (LobeHub-facing names).  Sources:

    - ``argument``   → read from *args*
    - ``observation`` → read from ``observation.payload``
    - ``evidence_ref`` / ``constant`` → skipped

    Required-but-missing fields are **omitted** (no partial state for
    required fields).  Optional-but-missing fields emit ``None`` so the
    frontend knows the slot exists.
    """
    contract = get_contract(tool_name)
    if contract is None:
        return {}

    obs_payload: dict[str, Any] = (
        observation.payload if isinstance(observation.payload, dict) else {}
    )
    result: dict[str, Any] = {}
    for field in contract.state:
        value = _read_field(field, args, obs_payload)
        if value is _MISSING:
            if field.required:
                continue  # required + missing → omit
            result[field.wire_key] = None
        else:
            result[field.wire_key] = value
    return result


def project_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Map python_key args → wire_key args via the RenderContract.

    Both required and optional missing fields are omitted — LobeHub
    expects required argv to be present; absent optional fields are
    simply not sent.
    """
    contract = get_contract(tool_name)
    if contract is None:
        return {}

    result: dict[str, Any] = {}
    for field in contract.args:
        if field.python_key in args:
            result[field.wire_key] = args[field.python_key]
    return result


def project_content(tool_name: str, observation: Observation) -> str | None:
    """Extract the primary content string from the observation, if declared.

    Returns ``observation.payload[content_field]`` when the contract
    declares one; otherwise ``None``.
    """
    contract = get_contract(tool_name)
    if contract is None or contract.content_field is None:
        return None
    obs_payload: dict[str, Any] = (
        observation.payload if isinstance(observation.payload, dict) else {}
    )
    value = obs_payload.get(contract.content_field)
    return value if isinstance(value, str) else None


def project_full(
    tool_name: str,
    args: dict[str, Any],
    observation: Observation,
) -> dict[str, Any]:
    """Convenience wrapper returning args + state + content projection."""
    return {
        "args": project_args(tool_name, args),
        "state": project_tool_state(tool_name, args, observation),
        "content": project_content(tool_name, observation),
    }


# ── internals ──────────────────────────────────────────────────────

_MISSING: object = object()
"""Sentinel distinguishing 'key not present' from an explicit ``None``."""


def _read_field(
    field: FieldSpec,
    args: dict[str, Any],
    obs_payload: dict[str, Any],
) -> Any:
    """Read a single field's value from the appropriate source.

    Returns ``_MISSING`` when the key is absent from the source dict.
    """
    if field.source == "evidence_ref" or field.source == "constant":
        return _MISSING
    if field.source == "argument":
        if field.python_key not in args:
            return _MISSING
        return args[field.python_key]
    if field.source == "observation":
        if field.python_key not in obs_payload:
            return _MISSING
        return obs_payload[field.python_key]
    return _MISSING
