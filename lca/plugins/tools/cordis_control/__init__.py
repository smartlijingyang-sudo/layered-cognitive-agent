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
