"""act.body — act-phase Body composition worker (PR-D final cleanup carrier).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActBody(Worker)``。
Body 装配委托给 ``lca.plugins.lab.act.body_provider.get_body()``;
错误折叠进 receipt content（status=error）。
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
    id="lab.act.body",
    provides=["lab.act.body.out:receipt"],
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
    description="act.body — Body composition worker for the act phase.",
    kind=PluginKind.COMPOSITE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_EXECUTE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.body.out:receipt",)),
        observability=EvidenceContract(
            descriptors=("lab.act.body.completed", "lab.act.body.failed"),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.authorize.out:authorized",),
        emits=("lab.act.body.out:receipt",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.body", _ActBody)
    register_worker("lab.act.body", _ActBody)


class _ActBody(Worker):
    factory = "lab.act.body"

    def execute(self, node, inputs, seams=None):
        if seams is None:
            raise RuntimeError(
                "lab.act.body requires a typed Seams handle from the runner"
            )
        intent_a = inputs.get("authorized")
        content = (
            intent_a.content
            if intent_a is not None and isinstance(intent_a.content, dict)
            else {}
        )
        tool_name = content.get("tool")
        try:
            result = seams.body.act(intent=content, plan_ref=seams.plan_ref)
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


register_worker("act.body", _ActBody)
register_worker("lab.act.body", _ActBody)