"""cron tools plugin —— ADR-0268 §4 的 ``cron`` 工具工厂。

工厂从 run bindings 的 ``home_path``（assistant home）构造
``CronService(CronStore(Path(home_path)))``，返回 cron.add/view/list/
update/remove 五个工具。``assistant_id`` 缺省取 bindings 或 ambient
``current_assistant_id()``，作为任务 owner。run 未绑定 home_path 时
工厂返回 None，工具自然缺省。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from lca.contracts.protocols import Tool
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _cron_tools_factory(bindings: object) -> list[Any] | None:
    """把 run bindings 物化为 cron 工具集；未绑定 assistant home 时返回 None。"""
    from lca.contracts.models.cognition.boundary import BindingsView
    from lca.infrastructure.observability.facade.run.ambit import current_assistant_id
    from lca.infrastructure.tools.cron import build_cron_tools

    b = bindings if isinstance(bindings, BindingsView) else BindingsView()
    home_path = b.home_path
    if not home_path:
        return None
    assistant_id = b.assistant_id or current_assistant_id().strip()
    if not assistant_id:
        return None
    service = CronService(CronStore(Path(home_path)))
    return build_cron_tools(service=service, owner=assistant_id)


@plugin(
    id="lca.plugins.domain.tools.cron",
    requires=("tools",),
    implements=[Tool],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="tools",
    description=(
        "注册 cron 工具工厂（ADR-0268 §4）：cron.add / cron.view / cron.list / "
        "cron.update / cron.remove，DEFERRED 经 tool_search 加载。"
    ),
    test_suite="tests/plugins/domain/tools/cron/test_cron_tools.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.domain.tools.cron.checked",
                "lca.plugins.domain.tools.cron.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("tools",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """注册 ``cron`` 工具工厂到 ToolsService 的 ``tools`` seam。"""
    del config
    ctx.require("tools").register_factory("cron", _cron_tools_factory)


__all__ = ["setup"]
