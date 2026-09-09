"""act.receipt_none — Intent (verdict=skip|no_effect) → synthetic skip Receipt.

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActReceiptNone(Worker)``。
在 ``act.dispatch.to_none`` 端口上兜底,生成 status=no_effect 的 receipt
让 act.observe 仍能形成 Observation 闭环。
"""

from __future__ import annotations

from pydantic import BaseModel

from agent_lab.primitives.artifact import Artifact, ArtifactKind

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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.lab.internal.worker import Worker, register_worker


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lab.act.receipt_none",
    provides=["lab.act.receipt_none.out:receipt"],
    requires=["lab.act.dispatch.out:to_none"],
    layer="L4",
    effects="none",
    description="act.receipt_none — synthetic skip Receipt (verdict=skip path).",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.receipt_none.out:receipt",)),
        observability=EvidenceContract(
            descriptors=("lab.act.receipt_none.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.dispatch.out:to_none",),
        emits=("lab.act.receipt_none.out:receipt",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.receipt_none", _ActReceiptNone)
    register_worker("lab.act.receipt_none", _ActReceiptNone)


class _ActReceiptNone(Worker):
    factory = "lab.act.receipt_none"

    def execute(self, node, inputs, seams=None):
        del seams
        c = getattr(inputs.get("authorized"), "content", {}) or {}
        if not isinstance(c, dict):
            c = {}
        return {
            "receipt": Artifact(
                kind=ArtifactKind.RECEIPT,
                content={
                    "status": "no_effect",
                    "tool": c.get("tool"),
                    "decision_id": c.get("decision_id", ""),
                    "action_type": str(c.get("action_type") or ""),
                    "response_text": c.get("response_text"),
                    "reason": c.get("reason"),
                },
                schema_ref="tool.receipt.v1",
            )
        }


register_worker("act.receipt_none", _ActReceiptNone)
register_worker("lab.act.receipt_none", _ActReceiptNone)