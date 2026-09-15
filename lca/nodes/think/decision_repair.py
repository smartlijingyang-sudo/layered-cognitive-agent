"""phase.think.decision.repair — typed-boundary node for decision repair.

PR-3.8.3: typed-boundary node that sits between
``think.decision.parse`` and ``think.gate`` in the think waterfall.
Handles three malformed-Decision cases the upstream parser cannot
itself fix:

1. Empty ``tool_name`` or tool name unknown to the registered
   ``ToolRegistry`` — emits
   ``RoutingDecision(next_node="think.route.decide",
   reason="decision_rejected_schema")`` and forwards the original
   ``Decision`` (no mutation; C13 typed-boundary discipline).
2. ``tool_calls[*].arguments`` fails JSON Schema validation against
   the tool's ``parameters`` schema. The node attempts one
   deterministic repair — close braces + strip trailing comma — over
   the raw preview carried on ``Decision.extra[TOOL_WIRE_RAW_PREVIEW]``
   (per ADR-0047 wire-block structure). If the repaired payload
   parses and validates, the node emits the repaired ``Decision`` +
   ``RoutingDecision(next_node="think.gate",
   reason="decision_repaired")``. If repair fails, the node emits
   the original ``Decision`` +
   ``RoutingDecision(next_node="think.route.decide",
   reason="decision_rejected_truncated")`` so the downstream route
   picks up a full re-reason rather than a silently truncated call.
3. Otherwise, pass-through with
   ``RoutingDecision(next_node="think.gate",
   reason="decision_ok")``.

Failure semantics (spec §2.3): never silently pass a malformed
``Decision`` to ``think.gate``. Either repair it deterministically
or re-route to ``think.route.decide`` so Gate can fail-loud
downstream. The node never raises out of the graph — every error
path produces a typed empty / re-route ``NodeOutput``.

Idempotency: same ``decision`` ⇒ same ``(decision, routing)``. The
repair rules are deterministic (no random retry, no hidden
counter), and the node holds no instance state.

ADR-0227 / ADR-0228: hand-written ``@plugin(...)`` carrier +
``declared_inputs`` / ``declared_outputs`` typed at compile time
(ADR-0219 §5.5). No per-node ``max_visits`` (ADR-0225).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.atoms.semantic.keys import TOOL_WIRE_RAW_PREVIEW
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# Runtime key the typed-boundary convention uses to expose the
# forked-per-run ``ToolRegistry``. Kept as a single SSOT constant so
# the test fixtures and any future wiring land on the same string.
_RUNTIME_TOOLS_KEY: str = "tools"

# Routing reasons emitted by this node. Kept as module constants so
# the bundle predicate and the unit tests can refer to them without
# duplicating string literals.
_REASON_OK: str = "decision_ok"
_REASON_REPAIRED: str = "decision_repaired"
_REASON_REJECTED_SCHEMA: str = "decision_rejected_schema"
_REASON_REJECTED_TRUNCATED: str = "decision_rejected_truncated"

# Outcome sentinels for the per-call validation loop. Strings rather
# than an enum so the function stays allocation-free at runtime; the
# caller branches on identity (these are module-level singletons).
_OK: str = "ok"
_REPAIR_SUCCEEDED: str = "repair_succeeded"
_REPAIR_REJECTED: str = "repair_rejected"
_SCHEMA_REJECTED: str = "schema_rejected"


@dataclass(frozen=True, slots=True)
class ThinkDecisionRepairExecutor:
    """think 节点: validate / repair ``Decision.tool_calls[*].arguments`` -> forward or re-route."""

    semantic_name: str = "think.decision.repair"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("decision", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml): decision
        outputs 端口(yaml): decision, routing

        Reads the ``decision`` port and the optional ``tools`` runtime
        registry (``context.runtime["tools"]``, a ``ToolRegistry`` per
        ADR-0047). Emits the original or repaired ``Decision`` plus a
        ``RoutingDecision`` whose ``next_node`` steers the waterfall
        toward ``think.gate`` (ok / repaired) or
        ``think.route.decide`` (rejected).

        Empty ``decision`` (None or no tool_calls) yields an empty
        ``NodeOutput`` so the bundle edge decides routing — typical
        wiring: ``when: eq port.decision value: None`` re-routes to
        ``think.route.decide`` for a full re-reason.
        """
        decision = input.port_values.get("decision")
        if not _has_tool_calls(decision):
            return NodeOutput(port_values={})

        registry = _resolve_registry(context.runtime)
        # Past this point the executor body operates on ``decision`` /
        # ``registry`` only; ``context`` is held only so we can read
        # the runtime tools map.

        outcome, repaired_calls = _validate_or_repair_calls(
            decision.tool_calls,
            raw_preview=_raw_preview_from_decision(decision),
            registry=registry,
        )

        if outcome == _SCHEMA_REJECTED:
            return NodeOutput(
                port_values={
                    "decision": decision,
                    "routing": _route_rejected_schema(),
                }
            )

        if outcome == _REPAIR_REJECTED:
            return NodeOutput(
                port_values={
                    "decision": decision,
                    "routing": _route_rejected_truncated(),
                }
            )

        if outcome == _REPAIR_SUCCEEDED:
            repaired_decision = _with_tool_calls(decision, repaired_calls)
            return NodeOutput(
                port_values={
                    "decision": repaired_decision,
                    "routing": _route_repaired(),
                }
            )

        return NodeOutput(
            port_values={
                "decision": decision,
                "routing": _route_ok(),
            }
        )


def _has_tool_calls(decision: object) -> bool:
    """``Decision`` is present and carries at least one ``ToolCall``.

    ``None`` and Decision with empty ``tool_calls`` both fall through
    to an empty ``NodeOutput`` so the bundle edge routes them. The
    rationale: upstream ``think.decision.parse`` emits an empty
    tool-call list when the LLM chose ``respond`` / ``ask_user``
    action types, and those should reach ``think.gate`` unchanged
    via the bundle predicate on the upstream parse → gate edge —
    not by a repair node returning them with a synthetic
    ``decision_ok`` routing.
    """
    if not isinstance(decision, Decision):
        return False
    return bool(decision.tool_calls)


def _resolve_registry(runtime: Mapping[str, Any] | None) -> Any | None:
    """Return the ``ToolRegistry`` exposed on the node runtime, or ``None``.

    Typed-boundary convention (PR-3.7.c): registries travel via
    ``context.runtime`` so the node stays free of import-time
    coupling to the act layer. Returns ``None`` when no registry is
    available so the schema-validation path can short-circuit
    gracefully — empty / unknown tool names still reject per the
    spec, but a missing registry only weakens the unknown-name check.
    """
    if runtime is None:
        return None
    tools_obj = runtime.get(_RUNTIME_TOOLS_KEY)
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
        if schema is None:
            # No schema available — pass the call through unchanged.
            repaired.append(call)
            continue

        if _matches_schema(call.arguments, schema):
            repaired.append(call)
            continue

        # Schema mismatch → attempt one deterministic repair over the
        # raw preview if present on the parent Decision; the raw
        # preview is the ADR-0047 wire-side artifact that records
        # the truncated arguments string.
        repaired_args = _attempt_repair(call, schema=schema, raw_preview=raw_preview)
        if repaired_args is None:
            return _REPAIR_REJECTED, list(tool_calls)

        repaired.append(_with_arguments(call, repaired_args))
        saw_repair = True

    if saw_repair:
        return _REPAIR_SUCCEEDED, repaired
    return _OK, repaired


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


def _route_ok() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.gate",
        next_hint=_REASON_OK,
    )


def _route_repaired() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.gate",
        next_hint=_REASON_REPAIRED,
    )


def _route_rejected_schema() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.route.decide",
        next_hint=_REASON_REJECTED_SCHEMA,
    )


def _route_rejected_truncated() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.route.decide",
        next_hint=_REASON_REJECTED_TRUNCATED,
    )


@plugin(
    id="phase.think.decision.repair",
    Config=None,
    provides=("phase:think::think.decision.repair",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_decision_repair.checked",
                "phase_think_decision_repair.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册: ``{region}::{semantic_name}``。"""
    del config
    executor = ThinkDecisionRepairExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkDecisionRepairExecutor", "setup"]
