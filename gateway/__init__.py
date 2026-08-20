"""观测 SSE 网关（组合根外薄层，非 lca 包成员）。"""

# Lazy re-exports: importing ``gateway`` does NOT eagerly construct the
# Starlette app or boot the plugin tree. Tests, lca-ops, and the plugin
# loader can all touch ``gateway.runs.loop_drivers`` without dragging in
# the full HTTP app.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.app import app, create_app, get_registry

__all__ = ["app", "create_app", "get_registry"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from gateway import app as _app

        return getattr(_app, name)
    raise AttributeError(name)
