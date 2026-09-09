"""act.shape — Decision → Intent (act-phase entry worker).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActShape(Worker)``。
模块级 ``register_worker`` 是 runtime 派发面的兜底
（``agent_lab.runtime.invoke.lookup_worker`` 直接查 ``_WORKERS``），
它与 cordis 启动路径殊途同源:同一个 ``_ActShape`` 类既被 cordis
启动注入,也通过模块 import 副作用注册到 ``lca.plugins.lab.internal.worker``。
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
    id="lab.act.shape",
    provides=["lab.act.shape.out:intent"],
    requires=["decision"],
    layer="L4",
    effects="none",
    description="act.shape — Decision → Intent for Body.act().",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.shape.out:intent",)),
        observability=EvidenceContract(
            descriptors=("lab.act.shape.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("decision",),
        emits=("lab.act.shape.out:intent",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.shape", _ActShape)
    register_worker("lab.act.shape", _ActShape)


class _ActShape(Worker):
    factory = "lab.act.shape"

    def execute(self, node, inputs, seams=None):
        out_port = node.config.get("to", "intent")
        decision_a = inputs.get(node.config.get("from", "decision"))
        raw = (
            decision_a.content
            if decision_a is not None and isinstance(decision_a.content, dict)
            else {}
        )
        return {
            out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content=dict(raw),
                schema_ref="tool.intent.v1",
            )
        }


# 模块级 fallback —— `python -m agent_lab.run` 进程外入口走
# ``load_all()`` 手动 import 而非 cordis 启动,这里保证 Worker
# 在没有走 cordis 的情况下也能被 ``lookup_worker`` 查到。
register_worker("act.shape", _ActShape)
register_worker("lab.act.shape", _ActShape)