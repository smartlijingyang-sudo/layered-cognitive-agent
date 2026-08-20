"""CLI debug command Protocol（ADR-0063 PR-9）。

``lca-ops debug <name>`` 的子命令由插件注册；新增子命令 = 一个插件，不改 cli.py。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CliDebugCommand(Protocol):
    """``lca-ops debug <name>`` 的子命令 handler。"""

    @property
    def name(self) -> str:
        """子命令名（如 'trace' / 'run' / 'scope'）。"""

    @property
    def description(self) -> str:
        """子命令一行说明。"""

    def run(self, **kwargs: Any) -> int:
        """执行子命令；返回退出码（0 成功）。"""