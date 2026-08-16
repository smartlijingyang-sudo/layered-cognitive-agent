"""Service base class — constructor-shape plugin pattern.

Subclass ``Service`` to create class-based plugins that auto-register
on construction. Mirrors Cordis ``Service`` abstract class.

Usage:
    class MyService(Service):
        name = "my-service"
        inject = ("llm", "tools")

        def __init__(self, ctx, config):
            super().__init__(ctx, config)

        async def init(self):
            yield lambda: cleanup()  # optional async init hook
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any, ClassVar

from lca.layer0_infra.plugin.kernel._context import PluginContext


class Service:
    """Service base class. Auto-registers on construction."""

    name: ClassVar[str] = ""
    inject: ClassVar[tuple[str, ...]] = ()

    def __init__(self, ctx: PluginContext, config: Any = None) -> None:
        self.ctx = ctx
        check_fn = getattr(type(self), "check", None)
        if callable(check_fn) and check_fn is not Service.check:
            ctx.mount(self.name, self, check=check_fn)
        else:
            ctx.mount(self.name, self)

    @classmethod
    def check(cls) -> bool:
        """Availability predicate. False → consumers stay PENDING."""
        return True

    async def init(self) -> Generator[Callable[[], None], None, None] | None:
        """Optional async init hook. Yield disposers."""
        return None

    def resolve_config(self, base: Any = None, head: Any = None) -> Any:
        """Merge intercept config from ctx chain (shallow merge)."""
        configs: list[dict] = []
        if base:
            configs.append(base if isinstance(base, dict) else {"value": base})
        ctx: PluginContext | None = self.ctx
        while ctx is not None:
            intercept = ctx.get_intercept(self.name)
            if intercept:
                configs.append(intercept if isinstance(intercept, dict) else {"value": intercept})
            ctx = ctx.parent
        if head:
            configs.append(head if isinstance(head, dict) else {"value": head})
        result: dict = {}
        for c in configs:
            result.update(c)
        return result
