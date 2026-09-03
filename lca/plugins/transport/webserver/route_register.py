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
        missing = tuple(key for key in spec.requires if not _require_present(ctx, key))
        if missing:
            raise RuntimeError(
                f"{plugin_id}: missing required capability {missing!r} for {spec.path}"
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
    """Materialise a Starlette ``Route`` from a :class:`RouteSpec`.

    Handlers are bracketed with ``transport.route.enter`` /
    ``transport.route.exit`` (ADR-0165.1). Emit helpers no-op when the
    EventSpine is not activated, so partial profiles stay quiet.
    """
    from starlette.routing import Route

    return Route(
        spec.path,
        _instrument_route_handler(spec.handler, path=spec.path),
        methods=list(spec.methods),
    )


def _bind_run_from_request(request: Any) -> str | None:
    """If the route carries ``run_id``, bind SpineContext before emitting."""
    params = getattr(request, "path_params", None) or {}
    run_id = params.get("run_id")
    if not run_id:
        return None
    from lca.infrastructure.observability.spine.context import SpineContext

    SpineContext.set_run(str(run_id))
    return str(run_id)


_carrier_seq = 0


def _next_carrier_seq() -> int:
    """Return the next monotonic carrier sequence number (ADR-0166 S4).

    Process-local, decoupled from run-local ``EventRecord.sequence``.
    Transport EP 携带 ``carrier_seq`` 让 reader 区分两条 timeline。
    """
    global _carrier_seq
    _carrier_seq += 1
    return _carrier_seq


def _instrument_route_handler(handler: Any, *, path: str) -> Any:
    """Wrap an HTTP handler with transport.route enter/exit spine events."""
    import asyncio
    import functools
    import inspect

    from lca.plugins.events.publishers.spine_reflector_transport import (
        emit_transport_route_enter,
        emit_transport_route_exit,
    )

    if inspect.iscoroutinefunction(handler):

        @functools.wraps(handler)
        async def _async_wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            method = str(getattr(request, "method", "") or "")
            run_id = _bind_run_from_request(request)
            seq = _next_carrier_seq()
            emit_transport_route_enter(
                path=path,
                method=method,
                run_id=run_id,
                carrier_seq=seq,
            )
            try:
                result = await handler(request, *args, **kwargs)
            except BaseException:
                emit_transport_route_exit(
                    path=path,
                    method=method,
                    outcome="failure",
                    run_id=run_id,
                    carrier_seq=seq,
                )
                raise
            emit_transport_route_exit(
                path=path,
                method=method,
                outcome="success",
                run_id=run_id,
                carrier_seq=seq,
            )
            return result

        return _async_wrapper

    @functools.wraps(handler)
    def _sync_wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
        method = str(getattr(request, "method", "") or "")
        run_id = _bind_run_from_request(request)
        seq = _next_carrier_seq()
        emit_transport_route_enter(
            path=path,
            method=method,
            run_id=run_id,
            carrier_seq=seq,
        )
        try:
            result = handler(request, *args, **kwargs)
        except BaseException:
            emit_transport_route_exit(
                path=path,
                method=method,
                outcome="failure",
                run_id=run_id,
                carrier_seq=seq,
            )
            raise
        if asyncio.iscoroutine(result):

            async def _await_result() -> Any:
                try:
                    value = await result
                except BaseException:
                    emit_transport_route_exit(
                        path=path,
                        method=method,
                        outcome="failure",
                        run_id=run_id,
                        carrier_seq=seq,
                    )
                    raise
                emit_transport_route_exit(
                    path=path,
                    method=method,
                    outcome="success",
                    run_id=run_id,
                    carrier_seq=seq,
                )
                return value

            return _await_result()
        emit_transport_route_exit(
            path=path,
            method=method,
            outcome="success",
            run_id=run_id,
            carrier_seq=seq,
        )
        return result

    return _sync_wrapper
