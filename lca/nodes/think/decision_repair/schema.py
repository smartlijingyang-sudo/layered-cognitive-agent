"""Pure tool-call JSON-schema validation for think decision repair."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Routing reasons emitted by this node. Kept as module constants so
# the bundle predicate and the unit tests can refer to them without


def _tool_name_known(name: str, *, registry: Any | None) -> bool:
    """Empty / whitespace-only name is always rejected.

    Unknown-to-registry names reject when a registry is provided;
    without a registry we cannot tell and let the call through (the
    body layer's ``tool_wire_gate`` remains the safety net for wire-
    level rejection). This honors ADR-0047's split: schema repair
    lives here, wire-block lives in the body.
    """
    if not name or not name.strip():
        return False
    if registry is None:
        return True
    return registry.get(name) is not None


def _lookup_schema(name: str, *, registry: Any | None) -> Mapping[str, Any] | None:
    """Return the JSON Schema for ``name`` from the registered Tool, or ``None``.

    The Tool protocol exposes ``parameters`` as a ``ClassVar[dict]``
    (OpenAI function-calling style). Returning ``None`` signals "no
    schema declared" — the caller then passes the call through
    unchanged (cannot validate what isn't declared).
    """
    if registry is None:
        return None
    tool = registry.get(name)
    if tool is None:
        return None
    params = getattr(tool, "parameters", None)
    if not isinstance(params, Mapping):
        return None
    return params


def _matches_schema(args: Mapping[str, Any], schema: Mapping[str, Any]) -> bool:
    """Lightweight OpenAI-style JSON Schema check.

    Covers the subset the think layer needs to flag a malformed
    arguments dict: top-level ``type``, ``required`` keys, and
    per-property ``type`` against the actual value. Deeper features
    (``oneOf`` / ``$ref`` / ``pattern`` / numeric ranges) are out of
    scope — the body layer's full SchemaValidator is the deep check;
    the think layer only needs to catch "obviously wrong" payloads
    before re-routing. A ``True`` here means the args look right; a
    ``False`` triggers the repair path.
    """
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(args, Mapping):
        return False
    if expected_type == "array" and not isinstance(args, list):
        return False

    if expected_type == "object":
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for req in required:
            if not isinstance(req, str):
                continue
            if req not in args:
                return False
        for key, value in args.items():
            prop_schema = properties.get(key)
            if prop_schema is None:
                # Unknown property; reject to flag drift between the
                # model-visible schema and the model output. ADR-0047
                # treats drift as a wire-block signal.
                return False
            if not _value_matches_schema(value, prop_schema):
                return False

    elif expected_type == "array":
        items_schema = schema.get("items")
        if isinstance(items_schema, Mapping):
            for item in args:  # type: ignore[union-attr]
                if not _value_matches_schema(item, items_schema):
                    return False

    return True


def _value_matches_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    """Match a single value against an OpenAI-style JSON Schema fragment.

    Only the structural type tags the think layer needs to flag a
    malformed payload. ``None``-typed fields and ``enum`` are
    honored so a typo on a known enum value does not silently pass.
    """
    expected = schema.get("type")
    enum = schema.get("enum")
    if enum is not None and value not in enum:
        return False
    if expected is None:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        # ``bool`` is a subclass of ``int`` in Python; reject bools
        # explicitly so a model that returns ``True`` for an integer
        # field does not pass the gate.
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True
