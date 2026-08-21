"""cordis_control Tool 子包 —— Creator §13.3 的运行时 plugin 编排入口。

Public surface
--------------
- :func:`build_cordis_control_tool` — 装配期构造 Tool 实例。
- :data:`ALLOWED_ACTIONS` / :data:`IDENTIFIER` / :data:`MANIFEST` —— 词表常量。
- :class:`CordisControlTool` —— 实现类（多数调用方只跟 build 出来的 Protocol 打交道）。

实现分层
--------
- :mod:`tool` —— 4-action 分发 + 事件落盘。
- :mod:`loader` —— plugin 源加载 + 动态 import + plugin_meta 提取。
"""

from __future__ import annotations

from lca.plugins.tools.cordis_control.tool import (
    ALLOWED_ACTIONS,
    IDENTIFIER,
    MANIFEST,
    CordisControlTool,
    build_cordis_control_tool,
)

__all__ = [
    "ALLOWED_ACTIONS",
    "IDENTIFIER",
    "MANIFEST",
    "CordisControlTool",
    "build_cordis_control_tool",
]


# ── Plugin manifest setup ─────────────────────────────────────
# This sub-package is referenced as ``$module: lca.plugins.tools.cordis_control``
# by ``bundles/scenario-cordis-creator.yaml``；provide a no-op setup that
# registers the plugin metadata so the resolve path finds a callable.
# The actual Tool is built via :func:`build_cordis_control_tool` at Agent
# composition time (after the Composer is constructed).


from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")


@plugin(
    id="lca-tool-cordis-control",
    provides=["tools.cordis_control"],
    implements=["Tool"],
    layer="L1",
    effects="world",
    description="cordis_control Tool — Creator §13.3 control plane",
    test_suite="tests/test_cordis_creator_e2e.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """cordis_control Tool is consumed at Agent construction time; this
    setup is a no-op that only registers the plugin metadata."""
