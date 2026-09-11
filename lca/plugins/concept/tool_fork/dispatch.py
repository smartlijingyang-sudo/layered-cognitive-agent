"""phase.concept.tool.fork.dispatch — typed concept.tool.fork boundary.

concept.tool.fork 图唯一节点 plugin:把 ``BindingsView`` typed boundary
转成 ``ForkedTools`` typed boundary(ADR-0220 §4.1 + §7.3)。

实现策略:typed dispatch 调 ``ToolsService.fork_for_run``(typed signature
cc55b547 已落),不调 primitive 节点(避免在 P2 阶段引入 graph-of-graph
调度复杂度,留待 P3+ 真实跨图时收敛)。typed boundary 不变 — 同一份
``ForkedTools`` 输出可以被 primitive 和 concept 两个图各自生产,边界
contract 一致。

ADR-0220 P7: ``bindings`` 端口缺省时,从
``lca.infrastructure.runtime_plane.capability_bindings.current_bindings_view()``
读 typed boundary。这条 fallback 路径替代了 history 上 ``reasoner.py``
的反射读 ``AgentState`` 私有 seam-ref 字段(ADR §2.2 表同一根因
收敛点);若 fallback 也未绑定 → fail loud,要求 runtime 在每 turn
显式 set ``BindingsViewBuilder``,禁止悄悄构造空 BindingsView。
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


def _bindings_from_runtime_plane() -> BindingsView | None:
    """Pull the typed ``BindingsView`` from the runtime plane seam.

    ADR-0220 §7.3: replaces the legacy ``reasoner.py:300-305`` reflection
    reads on ``AgentState._xxx_ref`` private attrs. Returns ``None``
    when the runtime entry point did not bind a
    ``BindingsViewBuilder`` for the current turn — the caller
    (this node) treats that as a hard fail.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        current_bindings_view,
    )

    return current_bindings_view()


@dataclass(frozen=True, slots=True)
class ToolForkDispatchExecutor:
    """concept.tool.fork 节点:typed BindingsView → ForkedTools."""

    semantic_name: str = "tool.fork.dispatch"
    region: str = "concept"
    # ADR-0219 §5.5: typed port contract declared on the plugin.
    declared_inputs: tuple[PortName, ...] = ("bindings",)
    declared_outputs: tuple[PortName, ...] = ("forked_tools",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """tool.fork.dispatch 入口。

        inputs 端口(yaml):bindings (BindingsView)
        outputs 端口(yaml):forked_tools (ForkedTools)

        ADR-0220 P7 fallback 路径:端口未传 → 读
        ``RuntimePlane.current_bindings()`` typed seam,不再反射 state。
        两路都空 → fail loud,要求运行时显式 set
        ``BindingsViewBuilder``。
        """
        bindings = input.port_values.get("bindings")
        if bindings is None:
            bindings = _bindings_from_runtime_plane()
        if not isinstance(bindings, BindingsView):
            raise TypeError(
                "tool.fork.dispatch: 'bindings' port must be a BindingsView "
                f"instance, got {type(bindings).__name__}"
            )

        tools_service = getattr(context.runtime, "tools", None)
        if tools_service is None:
            raise RuntimeError("tool.fork.dispatch: 'tools' capability missing from runtime scope")

        forked = tools_service.fork_for_run(bindings)
        forked_tools = ForkedTools(
            items=tuple(forked.list_tools()),
            binding_keys=_FORKED_BINDING_KEYS,
        )
        return NodeOutput(port_values={"forked_tools": forked_tools})


@plugin(
    id="phase.concept.tool.fork.dispatch",
    Config=None,
    provides=("concept::tool.fork.dispatch",),
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
                "phase_concept_tool_fork_dispatch.checked",
                "phase_concept_tool_fork_dispatch.served",
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
    executor = ToolForkDispatchExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ToolForkDispatchExecutor", "setup"]
