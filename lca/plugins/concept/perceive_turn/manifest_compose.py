"""phase.concept.perceive_turn.perceive_manifest_compose — typed manifest.

``concept.perceive.turn`` 内嵌节点 4:typed ``tuple[ContextItem, ...]``
+ ``AgentState`` → ``ContextManifest`` typed boundary(ADR-0220 §4.2)。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.perceive.perception import (
    ContextItem,
    ContextManifest,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveManifestComposeExecutor:
    """``concept.perceive.turn`` 节点 4:context_items + state → ContextManifest。"""

    semantic_name: str = "perceive.manifest.compose"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("context_items", "state")
    declared_outputs: tuple[PortName, ...] = ("manifest",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """perceive.manifest.compose 入口。

        inputs 端口(yaml):context_items (tuple[ContextItem, ...]), state (AgentState)
        outputs 端口(yaml):manifest (ContextManifest)
        """
        del context
        items = input.port_values.get("context_items") or ()
        state = input.port_values.get("state")
        if not isinstance(items, tuple):
            raise TypeError(
                "perceive.manifest.compose: 'context_items' port must be a "
                f"tuple, got {type(items).__name__}"
            )
        for item in items:
            if not isinstance(item, ContextItem):
                raise TypeError(
                    "perceive.manifest.compose: context_items entries must be "
                    f"ContextItem instances, got {type(item).__name__}"
                )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "perceive.manifest.compose: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )

        manifest = ContextManifest(
            items=items,
            digest=f"manifest:{new_id('manifest')}",
            schema_version="1.0",
        )
        return NodeOutput(port_values={"manifest": manifest})


@plugin(
    id="phase.concept.perceive_turn.perceive_manifest_compose",
    Config=None,
    provides=("concept::perceive.manifest.compose",),
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
                "phase_concept_perceive_turn_perceive_manifest_compose.checked",
                "phase_concept_perceive_turn_perceive_manifest_compose.served",
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
    executor = PerceiveManifestComposeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PerceiveManifestComposeExecutor", "setup"]
