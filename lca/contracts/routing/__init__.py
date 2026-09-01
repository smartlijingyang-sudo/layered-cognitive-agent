"""Webserver routing contracts — declared data, not commands.

DR-0163 决策 3 / 优雅落点:路由挂载是声明式数据 + 一次 registration traversal,
不是 ``for route in ROUTES: if route.path == "/journal/live": ...``。

`RouteSpec` 是路由的合约:声明 path / handler / methods / capability 依赖。
`requires` 缺失 → 注册阶段抛错；`optional` 缺失 → 该 spec 跳过,handler
根本不会出现在路由表上(Starlette default 404,nothing 503)。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = ["RouteSpec"]


@dataclass(frozen=True)
class RouteSpec:
    """A single HTTP route declaration with capability gating.

    Attributes:
        path: Starlette route path, e.g. ``"/runs/{run_id}/live"``.
        handler: ASGI-callable (sync or async function taking ``Request``).
        methods: HTTP methods, e.g. ``("GET", "OPTIONS")``.
        requires: Capability keys that MUST be present on the boot ``ctx`` for
            this spec to be registered. Any one missing → registration raises.
        optional: Capability keys whose absence causes the spec to be skipped
            (no disposal needed). Resource is not mounted; requests to
            ``path`` get Starlette's default 404.
    """

    path: str
    handler: Callable[..., Any]
    methods: tuple[str, ...]
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()

    def declares(self, cap: str) -> bool:
        """True when this spec declares ``cap`` as required or optional."""
        return cap in self.requires or cap in self.optional
