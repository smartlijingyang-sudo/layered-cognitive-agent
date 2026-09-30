"""Deterministic tool-call argument repair for think decision repair."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lca.contracts.atoms.semantic.keys import TOOL_WIRE_RAW_PREVIEW
from lca.contracts.models.core.execution.decision import Decision, ToolCall

# Routing reasons emitted by this node. Kept as module constants so
# the bundle predicate and the unit tests can refer to them without
from lca.nodes.think.decision_repair.constants import (
    _OK,
    _REPAIR_REJECTED,
    _REPAIR_SUCCEEDED,
    _SCHEMA_REJECTED,
)
from lca.nodes.think.decision_repair.schema import (
    _lookup_schema,
    _matches_schema,
    _tool_name_known,
)


def _resolve_registry(tools_obj: Any | None) -> Any | None:
    """Return the ``ToolRegistry`` from the ``tools`` typed port, or ``None``.

    Typed-boundary convention (PR-3.7.c): registries travel via the
    typed ``tools`` port so the node stays free of import-time
    coupling to the act layer. Returns ``None`` when no registry is
    available so the schema-validation path can short-circuit
    gracefully — empty / unknown tool names still reject per the
    spec, but a missing registry only weakens the unknown-name check.
    """
    if tools_obj is None:
        return None
    return tools_obj


def _validate_or_repair_calls(
    tool_calls: list[ToolCall],
    *,
    raw_preview: str | None,
    registry: Any | None,
) -> tuple[str, list[ToolCall]]:
    """Walk ``tool_calls`` and return ``(outcome, repaired_calls)``.

    Outcomes:

    - ``_OK`` — every call's ``tool_name`` is known and its
      ``arguments`` match the tool's JSON schema unchanged.
      ``repaired_calls`` equals ``tool_calls`` by content.
    - ``_REPAIR_SUCCEEDED`` — at least one call's ``arguments``
      failed the schema check and the deterministic repair produced
      a schema-valid payload. ``repaired_calls`` is a fresh list
      with the repaired calls spliced in (calls that did not need
      repair are returned unchanged).
    - ``_REPAIR_REJECTED`` — at least one call's ``arguments``
      failed the schema check and the repair could not produce a
      schema-valid payload. ``repaired_calls`` equals ``tool_calls``
      so the executor can simply forward the original.
    - ``_SCHEMA_REJECTED`` — at least one ``tool_name`` is empty or
      unknown to the registry. ``repaired_calls`` equals
      ``tool_calls`` for the same reason as ``_REPAIR_REJECTED``.
    """
    repaired: list[ToolCall] = []
    saw_repair = False
    for call in tool_calls:
        if not _tool_name_known(call.tool_name, registry=registry):
            return _SCHEMA_REJECTED, list(tool_calls)

        schema = _lookup_schema(call.tool_name, registry=registry)
        wire_bad = (call.wire_status or "ok") in {"incomplete", "invalid"}
        if schema is None and not wire_bad:
            # No schema available — pass the call through unchanged.
            repaired.append(call)
            continue

        if not wire_bad and schema is not None and _matches_schema(call.arguments, schema):
            repaired.append(call)
            continue

        if schema is None:
            # Incomplete wire and no schema to repair against — Body
            # keeps the ADR-0047 execute block so the model sees the
            # Observation instead of a silent re-route.
            repaired.append(call)
            continue

        # Schema mismatch or incomplete wire → one deterministic repair
        # over the raw preview (Decision.extra or ToolCall.wire_raw_preview).
        repaired_args = _attempt_repair(call, schema=schema, raw_preview=raw_preview)
        if repaired_args is None:
            if wire_bad:
                # Keep the incomplete call so Body can emit the ADR-0047
                # Observation; re-routing here would skip the error the
                # model needs in order to stop repeating the same payload.
                repaired.append(call)
                continue
            return _REPAIR_REJECTED, list(tool_calls)

        repaired.append(_with_arguments(call, repaired_args))
        saw_repair = True

    if saw_repair:
        return _REPAIR_SUCCEEDED, repaired
    return _OK, repaired


def _attempt_repair(
    call: ToolCall,
    *,
    schema: Mapping[str, Any],
    raw_preview: str | None,
) -> Mapping[str, Any] | None:
    """Try one deterministic repair of the tool call's arguments.

    Strategy (per spec §2.3 / brief):

    1. Locate the raw arguments string — ``raw_preview`` if the
       upstream parser attached one to ``Decision.extra``
       (ADR-0047 wire-block artifact); otherwise fall back to a
       JSON dump of ``call.arguments`` (which is already valid JSON,
       so the repair is a no-op and the schema check decides).
    2. Strip a single trailing comma, then close any unbalanced
       braces / brackets so the truncated JSON becomes parseable.
    3. Re-parse; if it parses and matches ``schema``, return the
       repaired dict. Otherwise return ``None`` so the caller emits
       ``decision_rejected_truncated``.

    Deterministic by construction: same raw string + same schema ⇒
    same result; no hidden counter, no random retry.
    """
    raw = _raw_arguments(call, raw_preview=raw_preview)
    repaired_raw = _balance_braces(raw)
    if repaired_raw is None:
        return None
    try:
        parsed = json.loads(repaired_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    if not _matches_schema(parsed, schema):
        return None
    return parsed


def _raw_arguments(call: ToolCall, *, raw_preview: str | None) -> str:
    """Prefer the ADR-0047 raw preview; fall back to the parsed dump.

    The wire-block layer (``tool_wire_gate.py``) preserves the raw
    arguments string in ``Decision.extra[TOOL_WIRE_RAW_PREVIEW]``
    when the parser had to widen the raw payload. The think-level
    repair node reads the same key from the parent Decision (see
    ``_raw_preview_from_decision``); when the preview is missing
    the repair falls back to the already-parsed arguments, in
    which case the brace-balance step is a no-op and the schema
    check decides.
    """
    if isinstance(raw_preview, str) and raw_preview:
        return raw_preview
    try:
        return json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _raw_preview_from_decision(decision: Decision) -> str | None:
    """Return ``Decision.extra[TOOL_WIRE_RAW_PREVIEW]`` if present.

    Decision-level because ``ToolCall`` does not currently expose a
    per-call raw preview — the wire-block layer attaches the
    truncated raw arguments string to the parent Decision so the
    repair node has a single SSOT to read from.
    """
    raw = decision.extra.get(TOOL_WIRE_RAW_PREVIEW)
    if isinstance(raw, str) and raw:
        return raw
    for call in decision.tool_calls:
        preview = call.wire_raw_preview
        if isinstance(preview, str) and preview:
            return preview
    return None


def _balance_braces(raw: str) -> str | None:
    """Close any unbalanced ``{`` / ``[`` and strip one trailing comma.

    The repair is intentionally minimal — a single-pass brace /
    bracket counter with a one-comma strip. Anything more elaborate
    would need a real partial-JSON parser and would be the wrong
    layer per ADR-0047's wire-block-vs-schema-repair split. Returns
    ``None`` if the input has no parseable JSON object/array root.
    """
    stripped = raw.rstrip()
    if stripped.endswith(","):
        stripped = stripped[:-1].rstrip()

    opens = stripped.count("{") - stripped.count("}")
    closes = stripped.count("[") - stripped.count("]")

    if opens == 0 and closes == 0:
        return stripped

    # Only close when there is a real opener. If the input has
    # unbalanced closers the JSON was already malformed in a way
    # brace-balancing cannot fix.
    if opens < 0 or closes < 0:
        return None

    repaired = stripped + ("}" * opens) + ("]" * closes)
    return repaired


def _with_arguments(call: ToolCall, args: Mapping[str, Any]) -> ToolCall:
    """Return a new ``ToolCall`` with the parsed ``args`` attached.

    ``ToolCall`` is a dataclass (mutable); ``replace`` produces a
    fresh instance so the original stays intact for diagnostics.
    """
    return replace(call, arguments=dict(args))


def _with_tool_calls(decision: Decision, calls: list[ToolCall]) -> Decision:
    """Return a new ``Decision`` with the repaired tool-call list.

    Decision is ``frozen=True`` so ``dataclasses.replace`` is the
    only sanctioned mutation path. The original ``Decision`` is
    forwarded unchanged when the repair fails — repair success is
    the only branch that returns a fresh instance here.
    """
    return replace(decision, tool_calls=list(calls))
