"""phase.primitive.capability.fork.dispatch — typed capability fork dispatch.

primitive.capability.fork 图唯一节点 plugin:把 ``BindingsView`` typed
转发给 ``ToolsService.fork_for_run``,出 ``ForkedTools`` typed boundary
(ADR-0220 §4.1)。

``requires=("tools",)`` 通过 Cordis 校验,运行时从
``context.runtime.tools`` 拿 ``ToolsService`` 实例(cordis scope 动态解析)。
反射归零:不读 ``AgentState._xxx_ref``,只走 typed ``BindingsView``。
"""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.models.cognition.boundary import (
    BindingsView,
    ForkedTools,
)
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

# binding_keys typed frozenset mirrors BindingsView fields (ADR-0220 §4.1).
_FORKED_BINDING_KEYS: frozenset[str] = frozenset(
    {
        "file_store",
        "bindings",
        "sandbox",
        "search",
        "skill_store",
        "machine_resolver",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityForkDispatchExecutor:
    """primitive.capability.fork 节点:typed BindingsView → ForkedTools."""

    semantic_name: str = "capability.fork.dispatch"
    region: str = "primitive"
    # ADR-0219 §5.5: typed port contract declared on the plugin.
    declared_inputs: tuple[PortName, ...] = ("bindings",)
    declared_outputs: tuple[PortName, ...] = ("forked_tools",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """capability.fork.dispatch 入口。

        inputs 端口(yaml):bindings (BindingsView)
        outputs 端口(yaml):forked_tools (ForkedTools)
        """
        bindings = input.port_values.get("bindings")
        if not isinstance(bindings, BindingsView):
            raise TypeError(
                "capability.fork.dispatch: 'bindings' port must be a BindingsView "
                f"instance, got {type(bindings).__name__}"
            )

        tools_service = getattr(context.runtime, "tools", None)
        if tools_service is None:
            raise RuntimeError(
                "capability.fork.dispatch: 'tools' capability missing from runtime scope"
            )

        forked = tools_service.fork_for_run(bindings)
        forked_tools = ForkedTools(
            items=tuple(forked.list_tools()),
            binding_keys=_FORKED_BINDING_KEYS,
        )
        return NodeOutput(port_values={"forked_tools": forked_tools})


@plugin(
    id="phase.primitive.capability.fork.dispatch",
    Config=None,
    provides=("primitive::capability.fork.dispatch",),
    requires=("tools",),
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
                "phase_primitive_capability_fork_dispatch.checked",
                "phase_primitive_capability_fork_dispatch.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "tools"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = CapabilityForkDispatchExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["CapabilityForkDispatchExecutor", "setup"]
