"""phase.think.context.compact — typed-boundary node for context compaction.

PR-3.8.2: lifts the off-graph context-compaction step into a typed
node that lives between ``think.budget.check`` and
``think.history.assemble`` in the think waterfall. Reads ``writer``
(``RunSessionWriterProtocol`` presence check) and ``state``
(``AgentState.budget`` for the ratio gate + ``retrieved_context`` for
the compaction payload) and emits a ``CompactReceipt`` plus a
``RoutingDecision`` typed port.

Threshold: when ``used_tokens / max_tokens >= 0.7`` a
``truncate_oldest`` strategy runs over the
``state.retrieved_context`` records, dropping the oldest by recency
until the payload fits a fraction of ``max_tokens``. Below the
threshold the node emits a ``noop`` receipt and forwards to
``think.history.assemble`` unchanged.

Failure semantics (per spec §2.2): if the compaction logic raises,
the node emits an empty ``CompactReceipt`` (never raises out of the
graph) and a ``RoutingDecision`` that re-routes to
``think.route.decide`` with ``next_hint="compact_skipped_error"`` so
Gate can fail-loud downstream — never silently drops an error.

ADR-0227 / ADR-0228: hand-written ``@plugin(...)`` carrier +
``declared_inputs`` / ``declared_outputs`` typed at compile time
(ADR-0219 §5.5). No per-node ``max_visits`` (ADR-0225).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import Budget
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

_COMPACTION_THRESHOLD_RATIO: float = 0.7
"""When ``used_tokens / max_tokens`` crosses this ratio, compaction runs."""

# Conservative target: leave the working payload at ~50% of max_tokens after
# compaction so the next turn has headroom before re-entering the node.
_TARGET_AFTER_RATIO: float = 0.5


@dataclass(frozen=True, slots=True)
class ThinkContextCompactExecutor:
    """think 节点: read ``writer`` + ``state`` -> emit ``CompactReceipt`` + ``RoutingDecision``."""

    semantic_name: str = "think.context.compact"
    region: str = "phase:think"
    # ``writer`` and ``state`` are kernel-injected runtime ports, not
    # produced by graph predecessors. They're read from ``context.runtime``
    # via ``_resolve_port``, mirroring the history.derive pattern.
    # Declared outputs only — the node has no typed-port inputs from the
    # port registry.
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("compact_receipt", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml): writer, state
        outputs 端口(yaml): compact_receipt, routing

        Reads ``state.budget`` and ``state.retrieved_context``. The
        ``writer`` port is required for typed-boundary presence but
        is not mutated (the writer keeps its own append surface per
        ADR-0226). Threshold-based gate: ratio >= 0.7 runs a
        ``truncate_oldest`` strategy over the retrieved context;
        ratio < 0.7 emits a ``noop`` receipt.

        On any exception the node emits an empty ``CompactReceipt``
        and re-routes to ``think.route.decide`` with
        ``next_hint="compact_skipped_error"``. The graph never sees
        a raised exception out of this node.
        """
        writer = _resolve_port("writer", input=input, context=context)
        state = _resolve_port("state", input=input, context=context)

        if writer is None:
            # Missing writer: typed-boundary contract fails loud — an
            # empty NodeOutput is the documented escape hatch for
            # missing required inputs (mirrors budget_check's pattern
            # of "missing state -> fail loud"). Returning empty keeps
            # the rest of the graph from receiving a typed port value
            # that isn't backed by a real input.
            return NodeOutput(port_values={})

        budget = _extract_budget(state)
        context_payload = _extract_context_payload(state)

        try:
            bytes_before = _payload_byte_size(context_payload)
            if _should_compact(budget):
                receipt, routing = self._apply_compaction(
                    context_payload=context_payload,
                    bytes_before=bytes_before,
                    budget=budget,
                )
            else:
                receipt = CompactReceipt.noop(bytes_seen=bytes_before)
                routing = _route_noop()
        except Exception:
            # bytes_before may not have been computed; fall back to 0
            # so the receipt keeps its typed shape even when the
            # payload projection itself blew up.
            receipt = CompactReceipt.skipped(bytes_seen=0)
            routing = _route_skipped_error()
        return NodeOutput(
            port_values={
                "compact_receipt": receipt,
                "routing": routing,
            }
        )

    def _apply_compaction(
        self,
        *,
        context_payload: tuple[Any, ...],
        bytes_before: int,
        budget: Budget,
    ) -> tuple[CompactReceipt, RoutingDecision]:
        """Run the ``truncate_oldest`` strategy over the retrieved context.

        Returns the typed receipt and a routing decision that advances to
        ``think.history.assemble``. Selection keeps the tail of the
        payload (most recent records) until the projected bytes fit
        ``_TARGET_AFTER_RATIO * max_tokens``; ``bytes_before <=
        bytes_after`` is impossible by construction because we only
        truncate down.
        """
        target_bytes = int(_TARGET_AFTER_RATIO * (budget.max_tokens or 0))
        kept = _truncate_oldest_to_byte_budget(
            context_payload,
            target_bytes=target_bytes,
        )
        bytes_after = _payload_byte_size(kept)
        # ``truncate_oldest`` is the only strategy wired in this PR;
        # ``summarize`` / ``spill`` remain documented future seams
        # (borrowed-nodes spec §2.2 acceptance tests only exercise
        # the noop + applied paths).
        receipt = CompactReceipt.applied(
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            strategy="truncate_oldest",
        )
        return receipt, _route_done()


def _route_done() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.history.assemble",
        next_hint="compact_done",
    )


def _route_noop() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.history.assemble",
        next_hint="compact_noop",
    )


def _route_skipped_error() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.route.decide",
        next_hint="compact_skipped_error",
    )


def _should_compact(budget: Budget) -> bool:
    """Threshold gate: ``used / max`` >= 0.7 and ``max_tokens`` is set.

    ``max_tokens is None`` means the budget isn't tokenized (e.g. a
    step-bounded run); treat as "no compaction needed" and emit a
    noop receipt so downstream code stays deterministic.
    """
    if budget.max_tokens is None or budget.max_tokens <= 0:
        return False
    return budget.used_tokens >= _COMPACTION_THRESHOLD_RATIO * budget.max_tokens


def _extract_budget(state: object) -> Budget:
    """Pull the ``Budget`` instance off the ``state`` port value.

    Mirrors the typed-mock acceptance pattern used by
    ``budget_check``'s ``_extract_budget``: any object with a typed
    ``budget`` attribute is acceptable, so test stubs do not need to
    carry the full ``AgentState``.
    """
    budget_obj = getattr(state, "budget", None)
    if not isinstance(budget_obj, Budget):
        raise TypeError(
            "think.context.compact expects a state-like object with a "
            f"Budget attribute on .budget; got {type(budget_obj).__name__}"
        )
    return budget_obj


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``.

    Mirrors the history.derive convention: runtime is a namespace object;
    resolve by attribute first, then mapping-style .get. This allows
    kernel-injected ports (state, writer) to bypass the port registry
    while keeping the typed-port contract at the node layer.
    """
    value = input.port_values.get(name)
    if value is None and hasattr(context, "runtime") and context.runtime is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    return value


def _extract_context_payload(state: object) -> tuple[Any, ...]:
    """Return ``state.retrieved_context`` as an immutable tuple.

    ``AgentState.retrieved_context`` is typed ``list[Any]``; the
    node treats it as an opaque payload so it stays agnostic of the
    concrete record type (``MemoryRecord`` / message / dict).
    """
    payload = getattr(state, "retrieved_context", None)
    if payload is None:
        return ()
    if isinstance(payload, tuple):
        return payload
    return tuple(payload)


def _payload_byte_size(payload: tuple[Any, ...]) -> int:
    """Byte size of the retrieved context as projected to the LLM wire.

    Each element is rendered with :func:`repr` and the lengths are
    summed. This is a stable, deterministic estimate of how many
    bytes the payload contributes to the model-visible request;
    precise token accounting lives in
    ``lca.contracts.observability.cost.token_meter`` and is out of
    scope for this node (C6 minimal: keep the threshold gate here,
    leave exact accounting to the cost seam).
    """
    return sum(len(repr(item)) for item in payload)


def _truncate_oldest_to_byte_budget(
    payload: tuple[Any, ...],
    *,
    target_bytes: int,
) -> tuple[Any, ...]:
    """Keep the tail (most recent) of ``payload`` until it fits ``target_bytes``.

    Empty payload is a no-op. ``target_bytes <= 0`` collapses to the
    empty tuple — the caller must ensure ``max_tokens > 0`` before
    invoking compaction (guaranteed by :func:`_should_compact`).
    """
    if not payload:
        return payload
    if target_bytes <= 0:
        return ()
    kept: list[Any] = []
    running = 0
    # Walk tail-first so the most recent records survive.
    for item in reversed(payload):
        size = len(repr(item))
        if running + size > target_bytes and kept:
            break
        kept.append(item)
        running += size
    kept.reverse()
    return tuple(kept)


@plugin(
    id="phase.think.context.compact",
    Config=None,
    provides=("phase:think::think.context.compact",),
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
                "phase_think_context_compact.checked",
                "phase_think_context_compact.served",
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
    executor = ThinkContextCompactExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkContextCompactExecutor", "setup"]
