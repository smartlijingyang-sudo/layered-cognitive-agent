"""assistant.tools plugin —— ADR-0187 §3 D12 的工具工厂。

把 ``create_assistant`` / ``create_assistant_skill`` 注册进 ``tools`` seam。
fork_for_run 会把工厂 bind 进本 profile 的每个 run；web-standard 不装
本插件，工具自然缺省。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_FRONTEND_BRIDGE,
    ASSISTANT_PROFILE_BACKFILL,
    ASSISTANT_SKILL_OVERLAY,
    ASSISTANT_TOOL_OVERLAY,
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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.tools.assistant import FileRoleCardResolver, build_assistant_tools


def _default_tool_names_provider(
    tools_service: Any, bindings: object
) -> Callable[[], tuple[str, ...]]:
    """返回创建时写入新 Home tools.yaml 的默认工具名提供者。

    用当前 run 的 BindingsView 物化平台默认工具集（与 tools_from_scope 同源），
    使新助理的 tools.yaml 显式记录其默认工具。物化失败返回空元组，保持
    模板 ``allow: []`` 行为（fail-soft）。
    """

    def _names() -> tuple[str, ...]:
        try:
            from lca.contracts.models.cognition.boundary import BindingsView

            b = bindings if isinstance(bindings, BindingsView) else BindingsView()
            return tuple(sorted({t.name for t in tools_service.materialize(b)}))
        except Exception:
            return ()

    return _names


@plugin(
    id="lca.plugins.assistant.tools.tools",
    requires=(
        ASSISTANT_CATALOG.key,
        ASSISTANT_FRONTEND_BRIDGE.key,
        ASSISTANT_PROFILE_BACKFILL.key,
        ASSISTANT_SKILL_OVERLAY.key,
        ASSISTANT_TOOL_OVERLAY.key,
        "tools",
    ),
    implements=[Tool],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.TOOLS,),
    description=(
        "注册 create_assistant / create_assistant_skill / 自定义工具管理工具（ADR-0187 §3 D12 + "
        "ADR-0243 D6）：对话创建助理及其 Home 内 skill/tool；后者仅在 run 绑定 assistant_id 时出现。"
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
            ASSISTANT_PROFILE_BACKFILL.key,
            ASSISTANT_SKILL_OVERLAY.key,
            ASSISTANT_TOOL_OVERLAY.key,
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
    tool_overlay = ctx.require(ASSISTANT_TOOL_OVERLAY.key)
    profile_backfill_svc = ctx.require(ASSISTANT_PROFILE_BACKFILL.key)
    tools_service = ctx.require("tools")

    async def _profile_backfill(assistant_id: str, records: object) -> None:
        backfill = getattr(profile_backfill_svc, "backfill_from_records", None)
        if callable(backfill):
            backfill(assistant_id, records)

    try:
        role_resolver: FileRoleCardResolver | None = FileRoleCardResolver()
    except Exception:
        role_resolver = None

    def _catalog_names() -> list[str]:
        return tools_service.names()

    def _assistant_tools_factory(bindings: object) -> list[Any] | None:
        return build_assistant_tools(
            bindings,
            catalog=catalog,
            bridge=bridge,
            overlay=overlay,
            tool_overlay=tool_overlay,
            role_resolver=role_resolver,
            default_tool_names=_default_tool_names_provider(tools_service, bindings),
            catalog_names=_catalog_names,
            profile_backfill=_profile_backfill,
        )

    ctx.require("tools").register_factory("assistant", _assistant_tools_factory)


__all__ = ["setup"]
