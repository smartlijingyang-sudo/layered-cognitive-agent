"""act.authorize — Intent → stamped Intent (allow|deny|skip).

Cordis 终态: 唯一真源是 ``@plugin`` 装饰器 + ``class _ActAuthorize(Worker)``。
verdict 维度: use_tool/call_tool 看 ``allow`` 白名单;no_effect 走 skip;
respond/stop/ask_human/delegate/handoff 走 allow;其它走 skip。
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
    id="lab.act.authorize",
    provides=["lab.act.authorize.out:authorized"],
    requires=["lab.act.shape.out:intent"],
    layer="L4",
    effects="none",
    description="act.authorize — Intent → stamped Intent with grant verdict.",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_AUTHORIZE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.authorize.out:authorized",)),
        observability=EvidenceContract(
            descriptors=("lab.act.authorize.completed",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.act.shape.out:intent",),
        emits=("lab.act.authorize.out:authorized",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the Worker on the cordis context as the canonical carrier."""
    register_worker("act.authorize", _ActAuthorize)
    register_worker("lab.act.authorize", _ActAuthorize)


class _ActAuthorize(Worker):
    factory = "lab.act.authorize"

    def execute(self, node, inputs, seams=None):
        out_port = node.config.get("to", "authorized")
        intent_a = inputs.get(node.config.get("from", "intent"))
        content = (
            intent_a.content
            if intent_a is not None and isinstance(intent_a.content, dict)
            else {}
        )
        allow = set(node.config.get("allow", []) or [])
        effect_kind = str(content.get("effect_kind") or "")
        tool = content.get("tool")
        if effect_kind == "no_effect":
            verdict = "skip"
        elif effect_kind in ("respond", "stop", "ask_human", "delegate", "handoff"):
            verdict = "allow"
        elif effect_kind in ("use_tool", "call_tool"):
            verdict = "allow" if tool in allow else "deny"
        else:
            verdict = "skip"
        stamped = {**content, "verdict": verdict, "tool": tool}
        return {
            out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content=stamped,
                schema_ref="tool.intent.v1",
            )
        }


register_worker("act.authorize", _ActAuthorize)
register_worker("lab.act.authorize", _ActAuthorize)