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
from lca.nodes.think.context.budgeting import (
    TARGET_AFTER_RATIO,
    payload_byte_size,
    resolve_budget,
    resolve_context_payload,
    should_compact,
    truncate_oldest_to_byte_budget,
)


@dataclass(frozen=True, slots=True)
class ThinkContextTruncateExecutor:
    """think.context.truncate 节点: typed ``(budget, context_payload)`` → ``CompactReceipt``."""

    semantic_name: str = "think.context.truncate"
    region: str = "think"
    # Runtime-carrier read; matches the convention used by the rest of
    # the think subgraph (see ``think.budget.gate`` and ``think.decision.
    # repair``). The plan validator does not model runtime carriers as
    # port producers, so a typed ``state`` input would fail to lift.
    declared_inputs: tuple = ()
    declared_outputs: tuple[PortName, ...] = (PortName("compact_receipt"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Apply ``truncate_oldest`` (past the soft gate) and emit the receipt.

        The upstream ``think.budget.gate`` owns the hard termination
        check; this node owns the soft compaction decision + strategy.
        Below ``COMPACTION_THRESHOLD_RATIO`` the working context is left
        untouched (``noop`` receipt); at/above it the oldest payload is
        truncated toward ``TARGET_AFTER_RATIO``. On any exception the
        node emits a ``skipped`` receipt — never raises out of the graph.

        ``budget`` / ``context_payload`` come from typed ports when the
        orchestrator projects them, otherwise via the whitelisted
        ``state`` runtime carrier (``state.budget`` /
        ``state.retrieved_context``), mirroring the prior single node.
        """
        budget = resolve_budget(context=context)
        payload = resolve_context_payload(context=context)
        try:
            if not should_compact(budget):
                receipt = CompactReceipt.noop(bytes_seen=payload_byte_size(payload))
            else:
                receipt = self._apply_truncate(payload=payload, budget=budget)
        except Exception:
            receipt = CompactReceipt.skipped(bytes_seen=0)
        return NodeOutput(port_values={PortName("compact_receipt"): receipt})

    def _apply_truncate(
        self,
        *,
        payload: tuple[Any, ...],
        budget: Budget,
    ) -> CompactReceipt:
        bytes_before = payload_byte_size(payload)
        target_bytes = int(TARGET_AFTER_RATIO * (budget.max_tokens or 0))
        kept = truncate_oldest_to_byte_budget(payload, target_bytes=target_bytes)
        bytes_after = payload_byte_size(kept)
        if kept == payload:
            return CompactReceipt.noop(bytes_seen=bytes_before)
        return CompactReceipt.applied(
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            strategy="truncate_oldest",
        )


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
