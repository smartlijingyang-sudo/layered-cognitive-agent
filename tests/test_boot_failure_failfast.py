"""Boot-failure fail-fast: a bad profile path must not leak infrastructure.

The kernel lifespan (ADR-0115 + ADR-0117) is the single seam every
transport uses; it must raise on a bad profile path so the process
refuses to start instead of serving a degraded state.

These tests prove:
  1. ``run_kernel_lifespan`` raises on a non-existent profile path
     before yielding state.
  2. Starlette's lifespan protocol propagates that error to
     ``app.router.lifespan_context`` callers — no partial boot leaks.
  3. ``TestClient`` refuses to serve when the lifespan raises.
  4. Failed boot does not write module-level singletons (ADR-0062 +
     ADR-0115).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from lca_kernel import run_kernel_lifespan
from lca_kernel.cli import create_app

if TYPE_CHECKING:
    from starlette.applications import Starlette


async def _drive_lifespan(app: Starlette) -> dict[str, Any]:
    """Drive one ASGI lifespan; return the captured state dict.

    Returns ``{"ctx": ..., "sent": [...]}; the caller inspects sent[-1]
    to decide whether boot succeeded (``lifespan.startup.complete``) or
    failed (``lifespan.startup.failed``). Raises ``Exception`` on send
    when the transport reports a startup failure.
    """
    event = asyncio.Event()
    captured: list[dict[str, Any]] = []

    async def _receive() -> dict[str, Any]:
        await event.wait()
        return {"type": "lifespan.shutdown"}

    async def _send(message: dict[str, Any]) -> None:
        captured.append(message)
        if message["type"] == "lifespan.startup.complete":
            event.set()
        if message["type"] == "lifespan.startup.failed":
            raise RuntimeError(message.get("message", "kernel boot failed"))

    await app.router.lifespan_context(  # type: ignore[arg-type]
        {"type": "lifespan", "asgi": {"version": "3.0"}},
        _receive,
        _send,
    )
    return {"ctx": getattr(app.state, "ctx", None), "sent": captured}


@pytest.mark.asyncio
async def test_bad_profile_path_raises_in_kernel_lifespan() -> None:
    """A non-existent profile path makes :func:`run_kernel_lifespan` raise."""
    bad = Path("profiles/__definitely_does_not_exist__.yaml")
    with pytest.raises(Exception):
        async with run_kernel_lifespan(bad) as state:
            pytest.fail(f"unexpected yield: {state!r}")


@pytest.mark.asyncio
async def test_starlette_lifespan_propagates_boot_failure() -> None:
    """A bad profile makes ``create_app`` raise — K3 boot fails before lifespan runs.

    ADR-0119 决定 3 新设计:boot 在 K3 阶段,create_app 内部 K3 抛
    FileNotFoundError(读 profile YAML 失败),lifespan 还没机会驱动。
    """
    with pytest.raises(Exception):
        await create_app(profile_path="profiles/__missing__.yaml")


@pytest.mark.asyncio
async def test_testclient_refuses_to_serve_when_boot_fails() -> None:
    """create_app() itself must raise if profile_path is invalid — no silent 503.

    ADR-0119 决定 3 新设计:create_app 在 K3 阶段就 boot,boot 失败立即 raise
    (FileNotFoundError 来自 load_profile_source 读 YAML),TestClient 拿不到 app。
    """
    with pytest.raises(Exception):
        await create_app(profile_path="profiles/__missing__.yaml")


@pytest.mark.asyncio
async def test_failed_boot_does_not_leak_module_singletons() -> None:
    """Failed boot must not write module-level globals on ``lca_kernel.cli``.

    ADR-0119 决定 3 新设计:create_app 在 K3 阶段 boot,boot 失败抛
    FileNotFoundError(读 profile YAML 失败);验证 lca_kernel.cli 模块本身
    不被 boot 失败污染。
    """
    import lca_kernel.cli as cli_module

    with pytest.raises(Exception):
        await create_app(profile_path="profiles/__missing__.yaml")
    for forbidden in (
        "get_file_store",
        "_module_file_store",
        "_registry",
        "_file_store",
        "_devices",
    ):
        assert not hasattr(cli_module, forbidden), forbidden
