"""Declarative route registration helper for transport plugins.

ADR-0163 决策 3 / 5 实现。

Capability contract has two surfaces:

- ``spec.requires`` —— 受 audited ``ctx.require`` 治理;plugin 必须在
  ``@plugin(requires=...)`` 声明同名 cap。声明里没出现的 cap 调用
  ``require`` → ``UndeclaredInteractionError``。
- ``spec.optional`` —— 用 ``ctx.inject(key, default=None)`` 探测;不会
  触发 audited 校验,因此 plugin 不必为 optional 扩展其声明。

优雅点:4 个 routes plugin 共享这一个函数 → 命令式 ``for route in
ROUTES: if path == "/x"`` 路径-字符串判断全部消失。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.routing import RouteSpec

__all__ = ["register_routes"]


def _require_present(ctx: Any, key: str) -> bool:
    """Audited ``ctx.require`` probe. Throws ``MissingCapabilityError`` if absent.

    Caller MUST declare ``key`` in the ``@plugin(requires=...)`` tuple.
    """
    if ctx is None:
        return False
    require = getattr(ctx, "require", None)
    if not callable(require):
        return False
    try:
        return require(key) is not None
    except (MissingCapabilityError, KeyError):
        return False


def _inject_probe(ctx: Any, key: str) -> bool:
    """Best-effort probe via ``ctx.inject(key, default=None)``.

    Optional routes must not contend with the audited plugin manifest. By
    going through ``inject`` (not ``require``) we stay honest: optional
    means "if you happen to have it, mount it".
    """
    if ctx is None:
        return False
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        return False
    try:
        return inject(key, default=None) is not None
    except (MissingCapabilityError, KeyError):
        return False


def register_routes(
    registry: Any,
    ctx: Any,
    specs: tuple[RouteSpec, ...],
    *,
    plugin_id: str,
) -> tuple[str, ...]:
    """Register every spec that satisfies its capability contract.

    - ``spec.requires`` key missing on ``ctx`` → raise ``RuntimeError``.
    - ``spec.optional`` key missing on ``ctx`` → spec silently skipped.
    - All keyed capabilities are present → spec materialised and registered.

    The kernel boot unit catches the raise and surfaces a structured
    ``PluginSetupError`` upstream; tests can assert boot failure shape.

    Args:
        registry: A :class:`lca.plugins.transport.webserver.router.RouteRegistry`.
        ctx: Booted plugin context; may be None only for compatibility shims.
        specs: Declarative route specifications in registration order.
        plugin_id: Used in disposal labels and error messages so an operator
            can locate the offending plugin when boot fails.
    """
    registered: list[str] = []
    for spec in specs:
        missing = tuple(
            key for key in spec.requires if not _require_present(ctx, key)
        )
        if missing:
            raise RuntimeError(
                f"{plugin_id}: missing required capability {missing!r} "
                f"for {spec.path}"
            )
        if any(key for key in spec.optional if not _inject_probe(ctx, key)):
            # Optional capability absent;the route simply is not registered.
            # Requests for this path receive Starlette's default 404.
            continue
        dispose = registry.register_http(_starlette_route(spec))
        inner: Any = ctx._runtime()  # type: ignore[attr-defined]
        inner.effect(dispose, label=f"route:{spec.path}")
        registered.append(spec.path)
    return tuple(registered)


def _starlette_route(spec: RouteSpec) -> Any:
    """Materialise a Starlette ``Route`` from a :class:`RouteSpec`."""
    from starlette.routing import Route

    return Route(spec.path, spec.handler, methods=list(spec.methods))
