"""act.execute — authorized Intent → EffectReceipt via SimpleBody.act (C10 narrow gate).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActExecute(Worker)``。
Body 装配委托给 ``lca.plugins.lab.act.body_provider.get_body()``
（已迁到 ``lca/plugins/lab/act/body_provider/plugin.py``,与 LCA
``lca.plugins.composer.act.body_provider`` 平行）。
错误折叠进 receipt content（status=error）,不在 runner 层 try/catch。
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
    id="lab.act.execute",
    provides=["lab.act.execute.out:receipt"],
    requires=[
        "lab.act.authorize.out:authorized",
        "lab.body",
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ],
    layer="L4",
    effects="world",
    description=(
        "act.execute — authorized Intent → EffectReceipt via SimpleBody.act; "
        "the C10 narrow gate between cognition and the world."
    ),
    kind=PluginKind.COMPOSITE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_EXECUTE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.execute.out:receipt",)),
        observability=EvidenceContract(
            descriptors=("lab.act.execute.completed", "lab.act.execute.failed"),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.authorize.out:authorized",),
        emits=("lab.act.execute.out:receipt",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.execute", _ActExecute)
    register_worker("lab.act.execute", _ActExecute)


class _ActExecute(Worker):
    factory = "lab.act.execute"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.act.body_provider import get_body

        intent_a = inputs.get("authorized")
        content = (
            intent_a.content
            if intent_a is not None and isinstance(intent_a.content, dict)
            else {}
        )
        tool_name = content.get("tool")
        try:
            body = get_body()
            result = body.act(intent=content, plan_ref="lab-act")
            return {
                "receipt": Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "ok",
                        "tool": tool_name,
                        "decision_id": content.get("decision_id", ""),
                        "result": result,
                    },
                    schema_ref="tool.receipt.v1",
                )
            }
        except Exception as exc:
            return {
                "receipt": Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={
                        "status": "error",
                        "tool": tool_name,
                        "error": str(exc),
                    },
                    schema_ref="tool.receipt.v1",
                )
            }


register_worker("act.execute", _ActExecute)
register_worker("lab.act.execute", _ActExecute)