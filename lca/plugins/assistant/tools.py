"""assistant.tools plugin —— ADR-0187 §3 D12 的工具工厂。

把 ``create_assistant`` 工具注册进 ``tools`` seam（``register_factory``）。
fork_for_run 会把工厂 bind 进本 profile 的每个 run；web-standard 不装
本插件（I-A1/I-A10），工具自然缺省。

依赖注入：``assistant.catalog``（require，创建真值入口）+
``assistant.frontend_bridge``（require 保证 boot 序；运行期工具对
bridge=None 仍容错，仅无前端注册）。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_FRONTEND_BRIDGE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import Tool
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool


@plugin(
    id="lca.plugins.assistant.tools",
    requires=(ASSISTANT_CATALOG.key, ASSISTANT_FRONTEND_BRIDGE.key, "tools"),
    implements=[Tool],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.TOOLS,),
    description=(
        "注册 create_assistant 工具工厂（ADR-0187 §3 D12）：对话创建助理的"
        "执行面；工具经 catalog 写 Home、经 frontend_bridge 投影前端入口。"
    ),
    test_suite="tests/plugins/assistant/test_tools_plugin.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.tools.checked",
                "lca.plugins.assistant.tools.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, ASSISTANT_FRONTEND_BRIDGE.key, "tools"),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """注册 ``assistant`` 工具工厂；工厂闭包持有 boot 期注入的 catalog/bridge。

    ``assistant.frontend_bridge`` 列为硬依赖以保证 boot 序（webserver_bridge
    先于本插件），同属 assistant-runtime bundle；运行期工具仍对 bridge=None
    容错（fail-soft）。
    """
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    bridge = ctx.require(ASSISTANT_FRONTEND_BRIDGE.key)

    def _assistant_tools_factory(run: object | None = None) -> list[Any] | None:
        del run  # create_assistant 不依赖 run bindings（catalog/bridge boot 期注入）
        return [AssistantCreateTool(catalog=catalog, bridge=bridge)]

    ctx.require("tools").register_factory("assistant", _assistant_tools_factory)


__all__ = ["setup"]
