"""act.receipt_denied — Intent (verdict=deny) → synthetic deny Receipt.

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActReceiptDenied(Worker)``。
在 ``act.dispatch.to_denied`` 端口上兜底,生成 status=denied 的 receipt
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
    id="lab.act.receipt_denied",
    provides=["lab.act.receipt_denied.out:receipt"],
    requires=["lab.act.dispatch.out:to_denied"],
    layer="L4",
    effects="none",
    description="act.receipt_denied — synthetic deny Receipt (verdict=deny path).",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_AUTHORIZE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.receipt_denied.out:receipt",)),
        observability=EvidenceContract(
            descriptors=("lab.act.receipt_denied.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.dispatch.out:to_denied",),
        emits=("lab.act.receipt_denied.out:receipt",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.receipt_denied", _ActReceiptDenied)
    register_worker("lab.act.receipt_denied", _ActReceiptDenied)


class _ActReceiptDenied(Worker):
    factory = "lab.act.receipt_denied"

    def execute(self, node, inputs, seams=None):
        del seams
        c = getattr(inputs.get("authorized"), "content", {}) or {}
        if not isinstance(c, dict):
            c = {}
        return {
            "receipt": Artifact(
                kind=ArtifactKind.RECEIPT,
                content={
                    "status": "denied",
                    "tool": c.get("tool"),
                    "decision_id": c.get("decision_id", ""),
                    "action_type": str(c.get("action_type") or ""),
                    "error": "grant denied",
                },
                schema_ref="tool.receipt.v1",
            )
        }


register_worker("act.receipt_denied", _ActReceiptDenied)
register_worker("lab.act.receipt_denied", _ActReceiptDenied)