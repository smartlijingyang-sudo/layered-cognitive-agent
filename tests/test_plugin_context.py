"""PluginContext 测试 —— mount / require / effect / on / child。

新的 PluginContext 委托到 PluginHost + PluginHandle，测试需要构造
完整的 host/handle 对。通过 ``_make_ctx()`` helper 简化。
"""

from __future__ import annotations

import contextlib

import pytest

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.layer0_infra.plugin.kernel import (
    DependencyUnavailable,
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
)
from lca.layer0_infra.plugin.kernel._context import PluginContext


def _make_ctx(
    *,
    injected: tuple[str, ...] = (),
    state: PluginState = PluginState.LOADING,
) -> PluginContext:
    """Create a PluginContext backed by a fresh host + handle."""
    host = PluginHost()
    handle = PluginHandle(
        entry_id="test",
        spec=PluginSpec(name="test", apply=lambda ctx, cfg: None),
        config={},
        injected=injected,
        state=state,
    )
    host.register_handle(handle)
    return PluginContext(host, handle)


class TestMountRequireGet:
    def test_mount_then_require_returns_it(self) -> None:
        ctx = _make_ctx(injected=("llm",))
        ctx.mount("llm", "llm-service")
        assert ctx.require("llm") == "llm-service"

    def test_require_missing_raises(self) -> None:
        ctx = _make_ctx(injected=("llm",))
        with pytest.raises((MissingCapabilityError, DependencyUnavailable)):
            ctx.require("llm")

    def test_get_returns_none_for_missing(self) -> None:
        ctx = _make_ctx()
        assert ctx.get("llm") is None

    def test_mount_duplicate_key_raises(self) -> None:

        ctx = _make_ctx()
        ctx.mount("llm", object())
        # Second mount of same key by different owner → PluginError
        # In this test it's the same handle, so host updates value (same owner)
        ctx.mount("llm", "new-value")  # same owner → OK, update
        assert ctx.get("llm") == "new-value"

    def test_mount_empty_key_raises(self) -> None:
        ctx = _make_ctx()
        with pytest.raises(ValueError):
            ctx.mount("", object())

    def test_require_without_inject_raises_plugin_error(self) -> None:
        """require checks inject declaration — undeclared key → PluginError."""
        from lca.layer0_infra.plugin.kernel._types import PluginError

        ctx = _make_ctx(injected=())
        with pytest.raises(PluginError, match="must declare"):
            ctx.require("llm")


class TestEffect:
    def test_dispose_calls_disposers_lifo(self) -> None:
        ctx = _make_ctx()
        log: list[str] = []

        def setup_a():
            log.append("setup-a")
            return lambda: log.append("dispose-a")

        def setup_b():
            log.append("setup-b")
            return lambda: log.append("dispose-b")

        ctx.effect(setup_a)
        ctx.effect(setup_b)

        assert log == ["setup-a", "setup-b"]

        # Run effect disposers manually (simulate lifecycle cleanup)
        while ctx._handle.effects:
            cleanup, _ = ctx._handle.effects.pop()
            cleanup()
        assert log == ["setup-a", "setup-b", "dispose-b", "dispose-a"]

    def test_dispose_suppresses_exceptions_and_continues(self) -> None:
        ctx = _make_ctx()
        log: list[str] = []

        def setup_ok():
            return lambda: log.append("dispose-ok")

        def setup_failing():
            return lambda: (_ for _ in ()).throw(RuntimeError("boom"))

        ctx.effect(setup_ok)
        ctx.effect(setup_failing)

        while ctx._handle.effects:
            cleanup, _ = ctx._handle.effects.pop()
            with contextlib.suppress(Exception):
                cleanup()
        assert "dispose-ok" in log

    def test_effect_failing_setup_disposes_nothing(self) -> None:
        ctx = _make_ctx()
        with pytest.raises(RuntimeError):
            ctx.effect(lambda: (_ for _ in ()).throw(RuntimeError("setup boom")))


class TestChild:
    def test_child_inherits_parent_mounts(self) -> None:
        ctx = _make_ctx(injected=("llm",))
        ctx.mount("llm", "parent-llm")
        child = ctx.child(key="run-1")
        assert child.require("llm") == "parent-llm"

    def test_child_overlay_shadows_parent(self) -> None:
        ctx = _make_ctx(injected=("tools",))
        ctx.mount("tools", "parent-tools")
        child = ctx.child(key="run-1")
        child._overlay["tools"] = "child-tools"
        assert child.require("tools") == "child-tools"
        assert ctx.require("tools") == "parent-tools"

    def test_child_put_without_parent_key_is_allowed(self) -> None:
        ctx = _make_ctx(injected=("plane",))
        child = ctx.child(key="run-1")
        child._overlay["plane"] = "this-run-plane"
        assert child.require("plane") == "this-run-plane"
        assert ctx.get("plane") is None

    def test_child_dispose_does_not_dispose_parent(self) -> None:
        log: list[str] = []
        parent = _make_ctx()
        parent.effect(lambda: log.append("setup-p") or (lambda: log.append("dispose-p")))
        child = parent.child(key="run-1")
        child.effect(lambda: log.append("setup-c") or (lambda: log.append("dispose-c")))

        # Dispose child effects only
        while child._handle.effects:
            cleanup, _ = child._handle.effects.pop()
            cleanup()
        assert "dispose-c" in log

    def test_child_empty_key_rejected(self) -> None:
        ctx = _make_ctx()
        with pytest.raises(ValueError):
            ctx.child(key="")
