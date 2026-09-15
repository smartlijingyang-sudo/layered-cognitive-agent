"""phase.delegate.await — block until all children return.

Per ADR-0228 §D5: blocks until kernel signals all children returned.
Emits tuple of ``DelegationReceipt``. Idempotent (C9): re-feeding the
same receipts yields the same output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.delegation import DelegationReceipt
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _coerce_receipts(value: object) -> tuple[DelegationReceipt, ...]:
    """Accept either a tuple of receipts or a single receipt; normalize."""
    if value is None:
        return ()
    if isinstance(value, DelegationReceipt):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        coerced: list[DelegationReceipt] = []
        for item in value:
            if not isinstance(item, DelegationReceipt):
                raise TypeError(
                    f"delegate.await: expected DelegationReceipt, got {type(item).__name__}"
                )
            coerced.append(item)
        return tuple(coerced)
    raise TypeError(
        f"delegate.await: expected tuple[DelegationReceipt, ...], got {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class DelegateAwaitExecutor:
    """delegate.await: pass-through typed receipts collected by the kernel.

    Pure mapping from the kernel-fed ``delegation_receipt`` port to the
    same-named output. No state, no clock, no I/O — C4 / C8 / C9 hold by
    construction.
    """

    semantic_name: str = "delegate.await"
    region: str = "region:delegate"
    declared_inputs: tuple[PortName, ...] = ("delegation_request", "delegation_receipt")
    declared_outputs: tuple[PortName, ...] = ("delegation_receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context  # unused: pure pass-through of typed input ports
        receipts = _coerce_receipts(input.port_values.get("delegation_receipt"))
        return NodeOutput(port_values={"delegation_receipt": receipts})


@plugin(
    id="lca.nodes.delegate.await",
    Config=None,
    provides=("region:delegate::delegate.await",),
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
                "phase_delegate_await.checked",
                "phase_delegate_await.served",
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
    """Composite-key registration: ``{region}::{semantic_name}``."""
    del config
    executor = DelegateAwaitExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DelegateAwaitExecutor", "setup"]
