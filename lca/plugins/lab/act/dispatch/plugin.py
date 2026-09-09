"""act.dispatch — Intent verdict → route port (body | denied | none).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActDispatch(Worker)``。
verdict 维度: ``allow`` → to_body;``deny`` → to_denied;其它 → to_none。
"""

from __future__ import annotations

from pydantic import BaseModel

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
    id="lab.act.dispatch",
    provides=[
        "lab.act.dispatch.out:to_body",
        "lab.act.dispatch.out:to_denied",
        "lab.act.dispatch.out:to_none",
    ],
    requires=["lab.act.authorize.out:authorized"],
    layer="L4",
    effects="none",
    description="act.dispatch — route Intent by verdict (body | denied | none).",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(
            grants=(
                "lab.act.dispatch.out:to_body",
                "lab.act.dispatch.out:to_denied",
                "lab.act.dispatch.out:to_none",
            )
        ),
        observability=EvidenceContract(
            descriptors=("lab.act.dispatch.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.authorize.out:authorized",),
        emits=(
            "lab.act.dispatch.out:to_body",
            "lab.act.dispatch.out:to_denied",
            "lab.act.dispatch.out:to_none",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.dispatch", _ActDispatch)
    register_worker("lab.act.dispatch", _ActDispatch)


class _ActDispatch(Worker):
    factory = "lab.act.dispatch"

    def execute(self, node, inputs, seams=None):
        src = node.config.get("from", "authorized")
        intent = inputs.get(src)
        if intent is None:
            return {}
        content = getattr(intent, "content", None)
        verdict = content.get("verdict") if isinstance(content, dict) else None
        if verdict == "allow":
            port = "to_body"
        elif verdict == "deny":
            port = "to_denied"
        else:
            port = "to_none"
        return {port: intent}


register_worker("act.dispatch", _ActDispatch)
register_worker("lab.act.dispatch", _ActDispatch)