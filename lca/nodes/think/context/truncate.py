"""``think.context.truncate`` graph node (PR-B single-responsibility split).

Single responsibility: take a typed ``context_payload`` + a typed
:class:`Budget` and emit a :class:`CompactReceipt` describing the
``truncate_oldest`` strategy applied.

This is one of two nodes that replace the prior
``think.context.compact``: the gate decision lives in
``think.budget.gate``; this node owns only the strategy. No routing
output, no state writes, no journal access — typed ports in, typed
``CompactReceipt`` out.

Failure semantics: if the truncation raises, the node emits a
``CompactReceipt.skipped`` so the typed-boundary contract is preserved
downstream (an empty receipt keeps ``CompactReceipt`` consumers from
seeing ``None``).

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# Soft compaction threshold: only truncate once the working context has
# grown past this fraction of the token budget. Below it the node emits a
# ``noop`` receipt (the prior single ``context.compact`` gated the same way;
# PR-B keeps that behaviour here rather than truncating every turn). The
# hard "budget exceeded → terminate" check is the separate
# ``think.budget.gate`` node.
_COMPACTION_THRESHOLD_RATIO: float = 0.7
# Conservative target: leave the working payload at ~50% of max_tokens after
# compaction so the next turn has headroom before re-entering the node.
_TARGET_AFTER_RATIO: float = 0.5


@dataclass(frozen=True, slots=True)
class ThinkContextTruncateExecutor:
    """think.context.truncate 节点: typed ``(budget, context_payload)`` → ``CompactReceipt``."""

    semantic_name: str = "think.context.truncate"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("budget", "context_payload")
    declared_outputs: tuple[PortName, ...] = ("compact_receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Apply ``truncate_oldest`` (past the soft gate) and emit the receipt.

        The upstream ``think.budget.gate`` owns the hard termination
        check; this node owns the soft compaction decision + strategy.
        Below ``_COMPACTION_THRESHOLD_RATIO`` the working context is left
        untouched (``noop`` receipt); at/above it the oldest payload is
        truncated toward ``_TARGET_AFTER_RATIO``. On any exception the
        node emits a ``skipped`` receipt — never raises out of the graph.

        ``budget`` / ``context_payload`` come from typed ports when the
        orchestrator projects them, otherwise via the whitelisted
        ``state`` runtime carrier (``state.budget`` /
        ``state.retrieved_context``), mirroring the prior single node.
        """
        budget = _resolve_budget(input=input, context=context)
        payload = _resolve_context_payload(input=input, context=context)
        try:
            if not _should_compact(budget):
                receipt = CompactReceipt.noop(bytes_seen=_payload_byte_size(payload))
            else:
                receipt = self._apply_truncate(payload=payload, budget=budget)
        except Exception:
            receipt = CompactReceipt.skipped(bytes_seen=0)
        return NodeOutput(port_values={"compact_receipt": receipt})

    def _apply_truncate(
        self,
        *,
        payload: tuple[Any, ...],
        budget: Budget,
    ) -> CompactReceipt:
        bytes_before = _payload_byte_size(payload)
        target_bytes = int(_TARGET_AFTER_RATIO * (budget.max_tokens or 0))
        kept = _truncate_oldest_to_byte_budget(payload, target_bytes=target_bytes)
        bytes_after = _payload_byte_size(kept)
        if kept == payload:
            return CompactReceipt.noop(bytes_seen=bytes_before)
        return CompactReceipt.applied(
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            strategy="truncate_oldest",
        )


def _resolve_budget(*, input: NodeInput, context: NodeContext) -> Budget:
    """Pull the typed ``Budget`` value from the port registry.

    Falls back to ``context.runtime.state.budget`` when the orchestrator
    has not projected ``state.budget`` upstream — the AST guard allows
    this because the outermost runtime access is ``state`` (a whitelisted
    runtime carrier), not ``budget`` itself.
    """
    value = input.port_values.get("budget")
    if isinstance(value, Budget):
        return value
    runtime = getattr(context, "runtime", None)
    if runtime is not None:
        state = getattr(runtime, "state", None)
        if state is not None:
            candidate = getattr(state, "budget", None)
            if isinstance(candidate, Budget):
                return candidate
    raise TypeError(
        "think.context.truncate expects a typed Budget port value (or "
        "context.runtime.state.budget fallback); got "
        f"{type(value).__name__ if value is not None else 'None'}"
    )


def _resolve_context_payload(*, input: NodeInput, context: NodeContext) -> tuple[Any, ...]:
    """Return the typed ``context_payload`` as a tuple.

    Falls back to ``context.runtime.state.retrieved_context`` when no
    projector has supplied the port — the whitelisted ``state`` carrier is
    the same source the prior single ``context.compact`` node read, so the
    split stays behavior-preserving. Missing on both ⇒ empty payload.
    """
    value = input.port_values.get("context_payload")
    if value is None:
        runtime = getattr(context, "runtime", None)
        state = getattr(runtime, "state", None) if runtime is not None else None
        value = getattr(state, "retrieved_context", None)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _should_compact(budget: Budget) -> bool:
    """Soft compaction gate: ``used_tokens`` past ``_COMPACTION_THRESHOLD_RATIO``.

    ``max_tokens`` unset / non-positive ⇒ no compaction (a step-bounded run
    keeps a ``noop`` receipt so downstream stays deterministic).
    """
    if budget.max_tokens is None or budget.max_tokens <= 0:
        return False
    return budget.used_tokens >= _COMPACTION_THRESHOLD_RATIO * budget.max_tokens


def _payload_byte_size(payload: tuple[Any, ...]) -> int:
    """Byte size of the payload as projected to the LLM wire.

    Each element is rendered with :func:`repr` and the lengths are
    summed. Precise token accounting lives elsewhere — this is the
    deterministic, dependency-free estimate the node uses to decide
    when the target byte budget has been met.
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
    invoking compaction (the upstream ``think.budget.gate`` enforces
    that the run continues only when the budget has remaining room).
    """
    if not payload:
        return payload
    if target_bytes <= 0:
        return ()
    kept: list[Any] = []
    running = 0
    for item in reversed(payload):
        size = len(repr(item))
        if running + size > target_bytes and kept:
            break
        kept.append(item)
        running += size
    kept.reverse()
    return tuple(kept)


@plugin(
    id="phase.think.context.truncate",
    Config=None,
    provides=("think::think.context.truncate",),
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
                "phase_think_context_truncate.checked",
                "phase_think_context_truncate.served",
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
    executor = ThinkContextTruncateExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkContextTruncateExecutor", "setup"]
