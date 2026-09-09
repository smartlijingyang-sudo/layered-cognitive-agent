"""act.observe — Receipt | EXCEPTION → Observation (single exit from act phase).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActObserve(Worker)``。
EXCEPTION 形态: 从 ``receipt`` 或 ``exception`` 端口还原成
Observation 载荷;无 receipt 时退化为空 dict。
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
    id="lab.act.observe",
    provides=["lab.act.observe.out:observation"],
    requires=["lab.act.execute.out:receipt"],
    layer="L4",
    effects="none",
    description=(
        "act.observe — Receipt or EXCEPTION → Observation; "
        "single exit from the act phase."
    ),
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.observe.out:observation",)),
        observability=EvidenceContract(
            descriptors=("lab.act.observe.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.execute.out:receipt",),
        emits=("lab.act.observe.out:observation",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.observe", _ActObserve)
    register_worker("lab.act.observe", _ActObserve)


class _ActObserve(Worker):
    factory = "lab.act.observe"

    def execute(self, node, inputs, seams=None):
        out_port = node.config.get("to", "observation")
        receipt = inputs.get(node.config.get("from", "receipt"))
        exception = inputs.get("exception")
        if receipt is not None and getattr(receipt, "kind", None) == ArtifactKind.EXCEPTION:
            content = getattr(receipt, "content", {}) or {}
            content = (
                content.get("original", content)
                if isinstance(content, dict)
                else {"raw": content}
            )
        elif exception is not None and getattr(exception, "kind", None) == ArtifactKind.EXCEPTION:
            content = getattr(exception, "content", {}) or {}
            content = (
                content.get("original", content)
                if isinstance(content, dict)
                else {"raw": content}
            )
        elif receipt is None:
            content = {}
        else:
            content = getattr(receipt, "content", {}) or {}
            if not isinstance(content, dict):
                content = {"raw": content}
        return {
            out_port: Artifact(
                kind=ArtifactKind.MANIFEST,
                content=content,
                schema_ref="observation.v1",
            )
        }


register_worker("act.observe", _ActObserve)
register_worker("lab.act.observe", _ActObserve)