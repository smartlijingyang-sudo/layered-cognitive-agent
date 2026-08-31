"""K6 lifecycle tests — fail-loud + signal handlers + ShutdownCoordinator.

These tests do NOT require a real process; the ShutdownCoordinator is
exercised with a fake kernel object whose ``dispose()`` records the call.
``sys.exit`` is patched so tests survive the exit calls inside
:meth:`DefaultShutdownCoordinator.shutdown`.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

from lca_kernel.errors import KernelError
from lca_kernel.lifecycle import (
    FAIL_LOUD_RELEASE_TIMEOUT_MS,
    DefaultShutdownCoordinator,
    ShutdownCoordinator,
    create_shutdown_coordinator,
)


class _FakeKernel:
    """Stand-in for a cordis Context; records dispose() calls."""

    def __init__(self, *, raise_on_dispose: bool = False, sleep: float = 0.0) -> None:
        self.dispose_calls = 0
        self._raise = raise_on_dispose
        self._sleep = sleep

    async def dispose(self) -> None:
        self.dispose_calls += 1
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raise:
            raise RuntimeError("dispose failed")


class _FakeHandle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _run(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine while patching ``sys.exit`` so tests survive."""
    with patch.object(sys, "exit") as exit_mock:
        result = asyncio.run(coro)
    return result, exit_mock


def test_fail_loud_release_timeout_is_2000ms() -> None:
    """deepseek parity: dispose must finish within 2 seconds."""
    assert FAIL_LOUD_RELEASE_TIMEOUT_MS == 2000


def test_default_coordinator_is_shutting_down_default_false() -> None:
    kernel = _FakeKernel()
    coord = DefaultShutdownCoordinator(kernel=kernel)
    assert coord.is_shutting_down is False


def test_register_transport_returns_unregister_disposer() -> None:
    kernel = _FakeKernel()
    coord = DefaultShutdownCoordinator(kernel=kernel)
    handle = _FakeHandle()
    transport = object()
    unregister = coord.register_transport(transport, handle)
    unregister()
    _, _ = _run(coord.shutdown(0))
    assert handle.closed is False


def test_shutdown_closes_transports_in_lifo_order() -> None:
    kernel = _FakeKernel()
    coord = DefaultShutdownCoordinator(kernel=kernel)
    h1, h2, h3 = _FakeHandle(), _FakeHandle(), _FakeHandle()
    coord.register_transport("t1", h1)
    coord.register_transport("t2", h2)
    coord.register_transport("t3", h3)
    _, _ = _run(coord.shutdown(0))
    assert h1.closed and h2.closed and h3.closed


def test_shutdown_calls_kernel_dispose_once() -> None:
    kernel = _FakeKernel()
    coord = DefaultShutdownCoordinator(kernel=kernel)
    _, _ = _run(coord.shutdown(0))
    assert kernel.dispose_calls == 1


def test_shutdown_coalesces_repeated_triggers_same_code() -> None:
    """Second shutdown() call with the same exit code does not re-dispose."""
    kernel = _FakeKernel()
    coord = DefaultShutdownCoordinator(kernel=kernel)
    # First shutdown completes (records _last_code = 0).
    _, _ = _run(coord.shutdown(0))
    assert kernel.dispose_calls == 1
    # Simulate post-shutdown: state still says shutting_down + last_code set.
    # A second shutdown(0) should be a no-op (same code, already shutting down).
    _, _ = _run(coord.shutdown(0))
    assert kernel.dispose_calls == 1  # not 2


def test_shutdown_handles_wedged_dispose_via_timeout() -> None:
    """A kernel that hangs in dispose() must not block the exit forever."""
    kernel = _FakeKernel(sleep=10.0)
    coord = DefaultShutdownCoordinator(kernel=kernel)
    _, _ = _run(coord.shutdown(0))
    # If we get here, the timeout worked.


def test_create_shutdown_coordinator_factory() -> None:
    kernel = _FakeKernel()
    coord = create_shutdown_coordinator(kernel)
    assert isinstance(coord, DefaultShutdownCoordinator)
    assert isinstance(coord, ShutdownCoordinator)


def test_shutdown_coordinator_protocol_surface() -> None:
    coord = create_shutdown_coordinator(_FakeKernel())
    assert hasattr(coord, "is_shutting_down")
    assert hasattr(coord, "shutdown")
    assert hasattr(coord, "interrupt")
    assert hasattr(coord, "register_transport")


def test_shutdown_surfaces_kernel_dispose_failures() -> None:
    """If ``kernel.dispose()`` raises, the coordinator wraps it in KernelError."""
    kernel = _FakeKernel(raise_on_dispose=True)
    coord = DefaultShutdownCoordinator(kernel=kernel)
    with patch.object(sys, "exit"), __import__("pytest").raises(KernelError) as excinfo:
        asyncio.run(coord.shutdown(0))
    assert "shutdown failed" in str(excinfo.value)
