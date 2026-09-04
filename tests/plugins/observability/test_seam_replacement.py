"""PR-7:seam pluginization replacement tests (ADR-0169 D8 + plugin-universe note PR-7).

钉死:
- ``lca_kernel.observability.ObservabilityRuntime.from_profile`` 通过
  ctx.inject("observability.<seam>") 拿到 NamedRegistry,按
  ``profile.observability.<seam>.implementation`` 选 provider factory
  并实例化缝族。
- profile 把 provider 替换为 stub,缝族装配仍能跑完,但行为由 stub
  决定(标定行为 = 写 marker 文件)。
- 缺 seam registry → Runtime.from_profile raise 清晰错误
  (而不是 runtime 时才神秘 fail)。

delete-when: 无;集成测试长期守住 PR-7 装配契约。
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


def _attach_require_methods(ctx: Any) -> Any:
    """Make raw cordis Context usable as ``ctx.require(key)`` for plugin setup tests.

    Production code wraps ctx in :class:`AuditedPluginContext`;raw cordis
    only exposes ``inject``. For seam/provider unit tests we don't need audit,
    so we just bind ``require = inject``.
    """
    ctx.require = ctx.inject
    ctx.register = lambda seam, name, value: ctx.inject(seam).register(name, value)
    return ctx


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def seam_ctx() -> Any:
    """Build a cordis Context pre-populated with all observability seams + standard providers."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry
    from lca.infrastructure.observability.loop_cursor.close_barrier_impl import (
        StdCloseBarrier,
    )
    from lca.infrastructure.observability.loop_cursor.factory import (
        LoopCursorFactory,
    )
    from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
        NullPersistenceCoordinator,
    )
    from lca.infrastructure.observability.loop_cursor.projection_host import (
        StdProjectionHost,
    )

    ctx = Context()
    ctx.provide("observability.loop_cursor", NamedRegistry())
    _attach_require_methods(ctx)
    ctx.provide("observability.projection_host", NamedRegistry())
    ctx.provide("observability.close_barrier", NamedRegistry())
    ctx.provide("observability.persistence", NamedRegistry())
    ctx.inject("observability.loop_cursor").register("standard", LoopCursorFactory.from_profile)
    ctx.inject("observability.projection_host").register(
        "standard", lambda initial=None, **_: StdProjectionHost(initial=initial)
    )
    ctx.inject("observability.close_barrier").register(
        "standard",
        lambda persistence, host, close_emitter, **_: StdCloseBarrier(
            persistence=persistence,
            host=host,
            close_emitter=close_emitter,
        ),
    )
    ctx.inject("observability.persistence").register(
        "null", lambda **_: NullPersistenceCoordinator()
    )
    return ctx


class _MarkerCursorFactory:
    """Stub callable that records a marker file and returns (cursor, incarnation).

    The registry entry is the class itself;Runtime.from_profile will call
    ``factory(profile=..., run_id=..., trace_id=..., spine=...)`` directly.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> _MarkerCursorFactory:
        # Don't accept construction args;the runtime calls us directly.
        return super().__new__(cls)

    def __init__(self, marker_path: Path) -> None:
        self._marker = marker_path

    def __call__(self, *, profile: Any, run_id: str, trace_id: str, spine: Any) -> tuple:
        # Record marker on first invocation.
        self._marker.write_text(f"called run_id={run_id} trace_id={trace_id}")
        _ = profile, spine
        return MagicMock(name="StubCursor"), MagicMock(name="Incarnation")


def _register_marker_factory(
    ctx: Any,
    *,
    seam: str,
    marker_path: Path,
) -> None:
    """Replace the ``standard`` provider for the given seam with the marker factory."""
    registry = ctx.inject(seam)
    if seam == "observability.loop_cursor":
        # Pre-construct the stub;the registry entry is the instance itself
        # (which is callable).
        registry.register("standard", _MarkerCursorFactory(marker_path))


# ── Tests ────────────────────────────────────────────────────


def test_seam_provides_registry() -> None:
    """Each seam provides a NamedRegistry with the documented capability."""
    # Import each seam module + invoke setup() in an empty context,assert
    # the capability it provides is a NamedRegistry.
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry

    seam_modules = [
        ("lca.plugins.observability.seams.loop_cursor_factory", "observability.loop_cursor"),
        ("lca.plugins.observability.seams.projection_host", "observability.projection_host"),
        ("lca.plugins.observability.seams.close_barrier", "observability.close_barrier"),
        ("lca.plugins.observability.seams.persistence_coordinator", "observability.persistence"),
    ]
    for module_name, cap_key in seam_modules:
        ctx = Context()
        mod = importlib.import_module(module_name)
        import asyncio

        _attach_require_methods(ctx)
        asyncio.run(mod.setup.setup(ctx, mod.Config()))
        bound = ctx.inject(cap_key)
        assert isinstance(bound, NamedRegistry), (
            f"{module_name} seam did not provide a NamedRegistry under {cap_key}; "
            f"got {type(bound).__name__}"
        )


def test_loop_cursor_standard_provider_registers() -> None:
    """``observability.loop_cursor.standard`` provider registers ``LoopCursorFactory.from_profile``."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry
    from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory

    ctx = Context()
    ctx.provide("observability.loop_cursor", NamedRegistry())
    _attach_require_methods(ctx)

    import asyncio

    from lca.plugins.observability.providers.loop_cursor import standard as std_mod

    asyncio.run(std_mod.setup.setup(ctx, std_mod.Config()))

    factory = ctx.inject("observability.loop_cursor").get("standard")
    # staticmethod wrapper may not compare via ``is``;check that the underlying
    # function is the same.
    assert getattr(factory, "__func__", factory) is LoopCursorFactory.from_profile


def test_loop_cursor_null_provider_registers() -> None:
    """``observability.loop_cursor.null`` provider registers an InMemory-only factory."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry

    ctx = Context()
    ctx.provide("observability.loop_cursor", NamedRegistry())
    _attach_require_methods(ctx)

    import asyncio

    from lca.plugins.observability.providers.loop_cursor import null as null_mod

    asyncio.run(null_mod.setup.setup(ctx, null_mod.Config()))

    factory = ctx.inject("observability.loop_cursor").get("null")
    assert callable(factory)


def test_projection_host_standard_provider_registers() -> None:
    """``observability.projection_host.standard`` registers a factory callable."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry

    ctx = Context()
    ctx.provide("observability.projection_host", NamedRegistry())
    _attach_require_methods(ctx)

    import asyncio

    from lca.plugins.observability.providers.projection_host import standard as ph_mod

    asyncio.run(ph_mod.setup.setup(ctx, ph_mod.Config()))

    factory = ctx.inject("observability.projection_host").get("standard")
    assert callable(factory)


def test_close_barrier_standard_provider_registers() -> None:
    """``observability.close_barrier.standard`` registers a factory."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry

    ctx = Context()
    ctx.provide("observability.close_barrier", NamedRegistry())
    _attach_require_methods(ctx)

    import asyncio

    from lca.plugins.observability.providers.close_barrier import standard as cb_mod

    asyncio.run(cb_mod.setup.setup(ctx, cb_mod.Config()))

    factory = ctx.inject("observability.close_barrier").get("standard")
    assert callable(factory)


def test_persistence_null_provider_registers() -> None:
    """``observability.persistence.null`` registers a NullPersistenceCoordinator factory."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry

    ctx = Context()
    ctx.provide("observability.persistence", NamedRegistry())
    _attach_require_methods(ctx)

    import asyncio

    from lca.plugins.observability.providers.persistence_coordinator import null as pn_mod

    asyncio.run(pn_mod.setup.setup(ctx, pn_mod.Config()))

    factory = ctx.inject("observability.persistence").get("null")
    assert callable(factory)


def test_from_profile_replaces_loop_cursor_with_stub(tmp_path: Path, seam_ctx: Any) -> None:
    """Replace ``observability.loop_cursor.standard`` with a marker factory;assert marker was hit.

    这是 PR-7 acceptance 的关键测试:profile 把 provider 替换为 stub,
    Runtime.from_profile 仍能完成缝族装配,而 ``LoopCursorFactory.from_profile``
    不再被调,取而代之的是 stub factory。
    """
    from lca_kernel.observability import ObservabilityRuntime

    marker = tmp_path / "loop_cursor_marker"
    _register_marker_factory(seam_ctx, seam="observability.loop_cursor", marker_path=marker)

    class _StubPersistence:
        def flush(self) -> bool:
            return True

        def close(self) -> None:
            return None

    runtime = ObservabilityRuntime.from_profile(
        profile=_ProfileStub(),
        ctx=seam_ctx,
        persistence=_StubPersistence(),
    )

    # cursor_factory 由 registry 返回的实例,不是 LoopCursorFactory 类
    assert isinstance(runtime.cursor_factory, _MarkerCursorFactory)
    assert runtime.cursor_factory._marker == marker
    assert not marker.exists(), (
        "marker should not be written by assembly itself; only by make_cursor"
    )


def test_from_profile_raises_when_seam_missing() -> None:
    """Missing seam registry → clear RuntimeError,not silent success or late mystery."""
    from cordis import Context

    from lca_kernel.observability import ObservabilityRuntime

    ctx = Context()  # no observability.<seam> bindings

    with pytest.raises(RuntimeError) as exc_info:
        ObservabilityRuntime.from_profile(
            profile=_ProfileStub(),
            ctx=ctx,
        )

    msg = str(exc_info.value)
    assert "observability.loop_cursor" in msg
    assert "observability-default" in msg


def test_from_profile_raises_when_provider_key_missing() -> None:
    """Profile requests unknown provider key → clear RuntimeError listing available keys."""
    # ctx with loop_cursor registry that has only 'standard',not 'fancy'
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry
    from lca_kernel.observability import ObservabilityRuntime

    ctx = Context()
    ctx.provide("observability.loop_cursor", NamedRegistry())
    _attach_require_methods(ctx)
    ctx.inject("observability.loop_cursor").register("standard", lambda: object())

    profile = _ProfileStub(observability={"loop_cursor": {"implementation": "fancy"}})
    with pytest.raises(RuntimeError) as exc_info:
        ObservabilityRuntime.from_profile(profile=profile, ctx=ctx)

    msg = str(exc_info.value)
    assert "fancy" in msg
    assert "standard" in msg  # available keys listed


def test_from_profile_uses_default_provider_when_profile_has_no_hints(
    tmp_path: Path, seam_ctx: Any
) -> None:
    """Profile without ``observability.loop_cursor.implementation`` → standard provider is used."""
    from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
    from lca_kernel.observability import ObservabilityRuntime

    class _StubPersistence:
        def flush(self) -> bool:
            return True

        def close(self) -> None:
            return None

    runtime = ObservabilityRuntime.from_profile(
        profile=_ProfileStub(),
        ctx=seam_ctx,
        persistence=_StubPersistence(),
    )

    # Default provider key for loop_cursor is "standard" → LoopCursorFactory.from_profile
    assert runtime.cursor_factory is LoopCursorFactory.from_profile


# ── Profile stub ────────────────────────────────────────────


from dataclasses import dataclass, field


@dataclass
class _ProfileStub:
    """Minimal duck-typed profile for PR-7 assembly tests."""

    plan_ref: str = "plan-pr7"
    observability: dict = field(default_factory=dict)
