"""phase.delegate.fold — aggregate receipts into a typed folded result.

Per ADR-0228 §Decision 5: the third and terminal node of the
``delegate`` subgraph. Reads the tuple of ``DelegationReceipt`` produced
by ``delegate.await`` and emits a typed ``FoldedDelegationResult`` plus
an updated ``Decision`` that the outer ``think`` phase consumes.

C13 boundary contract: every port crossing is typed
(``DelegationReceipt`` → ``FoldedDelegationResult`` + ``Decision``); no
``dict[str, Any]`` smuggling across the seam.

C4 / C5 invariants: this node never writes state and never carries
capability grants of its own; the kernel boundary is the parent grant
that authorised ``delegate.compose`` (see ADR-0228 §Decision 5
"capability monotonicity").

This is a hand-written ``@plugin(...)`` carrier (ADR-0228 §Decision 2
canonical shape); no decorator shortcut.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.delegation import (
    DelegationReceipt,
    FoldedDelegationResult,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _as_receipt(receipt: object) -> DelegationReceipt:
    """Coerce arbitrary upstream payload into a typed ``DelegationReceipt``."""
    if isinstance(receipt, DelegationReceipt):
        return receipt
    raise TypeError(
        "delegate.fold: 'delegation_receipt' port entry must be a "
        f"DelegationReceipt, got {type(receipt).__name__}"
    )


@dataclass(frozen=True, slots=True)
class DelegateFoldExecutor:
    """``delegate.fold`` node: receipts → folded result + updated decision.

    Composite key: ``delegate::delegate.fold``.
    Inputs: ``delegation_receipt`` (tuple of ``DelegationReceipt``).
    Outputs: ``decision`` (re-derived ``Decision`` for downstream think
    phase), ``folded_result`` (typed ``FoldedDelegationResult``).

    When every receipt is ``status="ok"`` the synthesised decision's
    ``action_type`` is ``respond`` (the children have already done the
    work; the body just needs to surface the answer). When any receipt
    is non-ok (error / timeout / cancelled) the body still has work to
    do, so ``action_type`` becomes ``use_tool`` to push the failure
    back into the act subgraph (e.g. for retry / escalation).
    """

    semantic_name: str = "delegate.fold"
    region: str = "delegate"
    declared_inputs: tuple[PortName, ...] = ("delegation_receipt",)
    declared_outputs: tuple[PortName, ...] = ("decision", "folded_result")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """delegate.fold 入口。

        inputs 端口(yaml): delegation_receipt (tuple[DelegationReceipt])
        outputs 端口(yaml): decision (Decision), folded_result
            (FoldedDelegationResult)
        """
        del context  # unused: pure function of input ports

        raw = input.port_values.get("delegation_receipt")
        if raw is None:
            receipts: tuple[DelegationReceipt, ...] = ()
        elif isinstance(raw, tuple):
            receipts = tuple(_as_receipt(r) for r in raw)
        else:
            raise TypeError(
                "delegate.fold: 'delegation_receipt' port must be a tuple "
                f"of DelegationReceipt, got {type(raw).__name__}"
            )

        ok_count = sum(1 for r in receipts if r.status == "ok")
        error_count = len(receipts) - ok_count

        # ADR-0228 §Decision 5: action_type is "respond" only when every
        # child returned ok; any non-ok receipt pushes the body back into
        # the act subgraph for retry / escalation.
        action_type = ActionType.RESPOND.value if error_count == 0 else ActionType.USE_TOOL.value

        # folded_payload keys are delegate_from so the body can route per
        # child; values carry either the child payload (status="ok") or
        # an ``{"error": ...}`` diagnostic bag.
        folded_payload: dict[str, Any] = {
            r.delegate_from: r.payload if r.payload is not None else {"error": r.error}
            for r in receipts
        }

        folded = FoldedDelegationResult(
            receipt_count=len(receipts),
            ok_count=ok_count,
            error_count=error_count,
            folded_payload=folded_payload,
        )

        decision = Decision(
            decision_id=(f"folded-{receipts[0].delegate_from}" if receipts else "folded-none"),
            action_type=action_type,
            rationale=(
                f"delegate.fold: aggregated {len(receipts)} receipt(s); "
                f"ok={ok_count} error={error_count}"
            ),
            confidence=1.0 if error_count == 0 else 0.0,
            extra={"folded_receipt_count": len(receipts)},
        )

        return NodeOutput(
            port_values={
                "decision": decision,
                "folded_result": folded,
            }
        )


@plugin(
    id="phase.delegate.fold",
    Config=None,
    provides=("delegate::delegate.fold",),
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
                "phase_delegate_fold.checked",
                "phase_delegate_fold.served",
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
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = DelegateFoldExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DelegateFoldExecutor", "setup"]
