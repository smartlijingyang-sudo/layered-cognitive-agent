"""assistant.tools plugin —— ADR-0187 §3 D12 的工具工厂。

把 ``create_assistant`` / ``create_assistant_skill`` 注册进 ``tools`` seam。
fork_for_run 会把工厂 bind 进本 profile 的每个 run；web-standard 不装
本插件，工具自然缺省。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_FRONTEND_BRIDGE,
    ASSISTANT_SKILL_OVERLAY,
)
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
from lca.infrastructure.tools.assistant.create_skill_tool import (
    assistant_create_skill_tool_from_run,
)
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool


@plugin(
    id="lca.plugins.assistant.tools",
    requires=(
        ASSISTANT_CATALOG.key,
        ASSISTANT_FRONTEND_BRIDGE.key,
        ASSISTANT_SKILL_OVERLAY.key,
        "tools",
    ),
    implements=[Tool],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.TOOLS,),
    description=(
        "注册 create_assistant / create_assistant_skill 工具工厂（ADR-0187 §3 D12）："
        "对话创建助理及其 Home 内 skill；后者仅在 run 绑定 assistant_id 时出现。"
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
        reads=(
            ASSISTANT_CATALOG.key,
            ASSISTANT_FRONTEND_BRIDGE.key,
            ASSISTANT_SKILL_OVERLAY.key,
            "tools",
        ),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """注册 ``assistant`` 工具工厂；工厂闭包持有 boot 期注入的 catalog/bridge/overlay。"""
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    bridge = ctx.require(ASSISTANT_FRONTEND_BRIDGE.key)
    overlay = ctx.require(ASSISTANT_SKILL_OVERLAY.key)

    def _assistant_tools_factory(run: object | None = None) -> list[Any] | None:
        tools: list[Any] = [AssistantCreateTool(catalog=catalog, bridge=bridge)]
        create_skill = assistant_create_skill_tool_from_run(run, overlay=overlay)
        if create_skill is not None:
            tools.append(create_skill)
        return tools

    ctx.require("tools").register_factory("assistant", _assistant_tools_factory)


__all__ = ["setup"]
