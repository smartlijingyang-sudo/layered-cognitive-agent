"""Session runtime plugin —— 提供 ``session.store`` capability（PR-3c 骨架）。

装配 DSH 风格 in-memory Session runtime：:class:`SessionStore` 持有活
Session 索引，:class:`lca.plugins.session.runtime.session.Session` 承担
append-only 日志真值 + observer contained fire + reentry 拒绝 + 增量
header fold。

本骨架不动：

- 落盘由 SessionObserver（``JsonlSessionPersistence`` /
  ``PersistenceObserver``）挂接，本 plugin 不拥有写盘；
- 16 个 publisher plugin 与 EventSpine（ADR-0183 总线，本 plugin 不发事件）。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.session.runtime.store import SessionStore

__all__ = ["Config", "setup"]


class Config(BaseModel):
    """Session runtime 无配置项；拒绝未知键防声明漂移。"""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.runtime",
    provides=["session.store"],
    requires=[],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Session runtime：提供 session.store（in-memory SessionStore）。"
        "DSH 风格 Session 实体：append-only 日志真值 + observer contained fire + "
        "reentry 拒绝 + 增量 request_header fold。不接落盘链，不发事件。"
    ),
    test_suite="tests/plugins/session/test_runtime.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Session runtime boot：provide 一个全新 SessionStore（每次 profile 启动一个）。

    外部后果：``session.store`` 由 RunSessionBuilder 按 run_id 消费；
    缺席时 publishers 降级 EventBus。
    """
    del config
    ctx.provide("session.store", SessionStore())
